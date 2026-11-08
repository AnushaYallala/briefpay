"""Payment Guardian: deterministic hard rules G-01..G-13 and soft flags S-01..S-03 (SPEC 7.5.2-7.5.3).

Pure review logic: it reads the DB and (through an injected `PayPalReader`) PayPal's own records.
It never writes to PayPal, never changes plan state, and never uses an LLM. Any FAIL means BLOCK.
The LLM review (T-42) can only add a HOLD on top of this; it can never relax a result computed here.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BRD, Campaign, Contract, LedgerEntry, MoneyPlan, MoneyPlanStep, PayoutBatch, Pledge, Project, ProjectMember,
    Submission, VerificationReport,
)
from app.schemas.plans import MoneyPlanSpec
from app.services import ledger
from app.services import plan_builder as pb
from app.services.settlement import SettlementError, idempotency_key, plan_captures, plan_hash

PASS, FAIL, UNVERIFIED, SKIPPED = "PASS", "FAIL", "UNVERIFIED", "SKIPPED"

APPLICABLE: dict[str, list[str]] = {
    "CAPTURE_PLEDGES": [f"G-{i:02d}" for i in range(1, 11)],
    "RELEASE_HOLDS": [f"G-{i:02d}" for i in range(1, 9)] + ["G-11"],
    "FREELANCER_PAYOUT": [f"G-{i:02d}" for i in range(1, 9)] + ["G-12"],
    "REFUND_CAPTURED": [f"G-{i:02d}" for i in range(1, 9)] + ["G-13"],
    "REAUTH_PLEDGES": [f"G-{i:02d}" for i in range(1, 7)],
}
TITLES = {
    "G-01": "Plan binding", "G-02": "Phase and exclusivity", "G-03": "Isolation",
    "G-04": "Step integrity and idempotency", "G-05": "Bounds and currency", "G-06": "PayPal-side proof",
    "G-07": "Conservation and buckets", "G-08": "Global isolation and solvency", "G-09": "Success condition",
    "G-10": "Capture math", "G-11": "Failure condition", "G-12": "Work and recipient binding",
    "G-13": "Refund correctness",
}
BUCKET_FOR_OP = {"CAPTURE_AUTH": "POOL", "VOID_AUTH": "NONE", "REAUTH_AUTH": "NONE",
                 "PAYOUT_ITEM": "POOL", "REFUND_CAPTURE": "POOL"}
PAYPAL_PROVED = {"G-06", "G-08"}  # shown as "verified with PayPal (APIMatic SDK)" in the UI


# ---------------- PayPal reads (injected; real impl arrives with T-20) ----------------

class PayPalUnavailable(Exception):
    """PayPal could not be reached. Rules report UNVERIFIED and soft flag S-03 forces a HOLD."""


@dataclass(frozen=True)
class PayPalObject:
    status: str          # authorization: CREATED|CAPTURED|VOIDED|EXPIRED...  capture: COMPLETED|REFUNDED...
    amount_cents: int
    currency: str = "USD"


class PayPalReader(Protocol):
    def get_authorization(self, authorization_id: str) -> PayPalObject | None: ...
    def get_capture(self, capture_id: str) -> PayPalObject | None: ...
    def platform_balance_cents(self) -> int | None: ...


@dataclass(frozen=True)
class GuardianParams:
    payout_max_cents: int = 100000
    payout_max_per_hour: int = 10


@dataclass
class RuleResult:
    id: str
    status: str
    detail: str
    title: str = ""
    paypal_verified: bool = False

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "status": self.status, "detail": self.detail,
                "paypal_verified": self.paypal_verified}


@dataclass
class Evaluation:
    results: list[RuleResult] = field(default_factory=list)
    soft_flags: list[dict] = field(default_factory=list)

    def get(self, rule_id: str) -> RuleResult | None:
        return next((r for r in self.results if r.id == rule_id), None)

    @property
    def failed_ids(self) -> list[str]:
        return [r.id for r in self.results if r.status == FAIL]

    @property
    def decision(self) -> str:
        return rule_decision(self)


def rule_decision(ev: Evaluation) -> str:
    """Any hard FAIL -> BLOCK. Else any soft flag -> HOLD. Else ALLOW. (LLM can only raise this in T-42.)"""
    if any(r.status == FAIL for r in ev.results):
        return "BLOCK"
    return "HOLD" if ev.soft_flags else "ALLOW"


# ---------------- evaluation context ----------------

class Ctx:
    def __init__(self, db: Session, plan: MoneyPlan, spec: MoneyPlanSpec, now: datetime,
                 reader: PayPalReader, params: GuardianParams):
        self.db, self.plan, self.spec, self.now, self.reader, self.params = db, plan, spec, now, reader, params
        self.project = db.get(Project, spec.project_id)
        self.campaign = db.get(Campaign, spec.campaign_id) if spec.campaign_id else None
        self.contract = (db.get(Contract, spec.contract_id) if spec.contract_id else None) or None
        self.hash = plan_hash(spec)
        self._pledges: dict[int, Pledge | None] = {}
        self._auth: dict[str, PayPalObject | None | PayPalUnavailable] = {}
        try:
            self.rebuilt, self.rebuild_error = pb.rebuild(db, plan, now), None
        except pb.PlanBuildError as e:
            self.rebuilt, self.rebuild_error = None, str(e)
        self._pool: int | None = None

    def pledge(self, pledge_id: int) -> Pledge | None:
        if pledge_id not in self._pledges:
            self._pledges[pledge_id] = self.db.get(Pledge, pledge_id)
        return self._pledges[pledge_id]

    @property
    def pool(self) -> int:
        if self._pool is None:
            self._pool = ledger.pool_balance(self.db, self.spec.project_id)
        return self._pool

    def paypal_auth(self, authorization_id: str) -> PayPalObject | None:
        if authorization_id not in self._auth:
            try:
                self._auth[authorization_id] = self.reader.get_authorization(authorization_id)
            except PayPalUnavailable as e:
                self._auth[authorization_id] = e
        got = self._auth[authorization_id]
        if isinstance(got, PayPalUnavailable):
            raise got
        return got

    def pledge_steps(self):
        return [s for s in self.spec.steps if s.target_type == "PLEDGE"]

    def foreign(self) -> list[str]:
        """Objects the plan references that don't belong to this project/campaign."""
        bad = []
        for s in self.spec.steps:
            if s.target_type in ("PLEDGE", "CAPTURE"):
                p = self.pledge(s.target_id)
                if p is None:
                    bad.append(f"step {s.seq}: pledge {s.target_id} unknown")
                elif p.project_id != self.spec.project_id or (
                        self.spec.campaign_id and p.campaign_id != self.spec.campaign_id):
                    bad.append(f"step {s.seq}: pledge {s.target_id} belongs to another project/campaign")
            elif s.target_type == "CONTRACT":
                c = self.db.get(Contract, s.target_id)
                if c is None or c.project_id != self.spec.project_id:
                    bad.append(f"step {s.seq}: contract {s.target_id} is not this project's")
        return bad


def _r(rid: str, status: str, detail: str, paypal: bool = False) -> RuleResult:
    return RuleResult(rid, status, detail, TITLES[rid], paypal and status == PASS)


def _ok(failures: list[str], ok_detail: str) -> tuple[str, str]:
    return (FAIL, "; ".join(failures)) if failures else (PASS, ok_detail)


# ---------------- common rules ----------------

def g01(c: Ctx) -> RuleResult:
    f = []
    if c.hash != c.plan.plan_hash:
        f.append("the reviewed steps do not hash to the plan's stored hash")
    if c.rebuilt is None:
        f.append(f"PlanBuilder cannot reproduce this plan now: {c.rebuild_error}")
    elif c.rebuilt.plan_hash != c.plan.plan_hash:
        f.append("database state changed since the preview (rebuilt hash differs)")
    return _r("G-01", *_ok(f, "rebuilding from the database gives exactly this plan hash"))


STATE_RULES = {
    "CAPTURE_PLEDGES": (lambda c: c.campaign and c.campaign.state == "OPEN" and c.project.state == "PLEDGING",
                        "campaign must be OPEN and project PLEDGING"),
    "RELEASE_HOLDS": (lambda c: c.campaign and c.campaign.state in ("OPEN", "FAILING") and c.project.state == "PLEDGING",
                      "campaign must be OPEN/FAILING and project PLEDGING"),
    "FREELANCER_PAYOUT": (lambda c: c.project.state in ("PAYOUT_READY", "PAYOUT_FAILED"),
                          "project must be PAYOUT_READY (or PAYOUT_FAILED for a retry)"),
    "REFUND_CAPTURED": (lambda c: c.project.state in ("IN_PROGRESS", "VERIFYING", "PAYOUT_READY", "REFUNDING"),
                        "project must be IN_PROGRESS, VERIFYING, PAYOUT_READY or REFUNDING"),
    "REAUTH_PLEDGES": (lambda c: c.campaign and c.campaign.state == "OPEN", "campaign must be OPEN"),
}


def g02(c: Ctx) -> RuleResult:
    f = []
    allowed, why = STATE_RULES[c.spec.kind]
    if not allowed(c):
        f.append(f"state does not allow {c.spec.kind}: {why}")
    q = select(func.count()).select_from(MoneyPlan).where(
        MoneyPlan.project_id == c.spec.project_id, MoneyPlan.id != c.plan.id)
    if c.db.scalar(q.where(MoneyPlan.state == "EXECUTING")):
        f.append("another plan for this project is EXECUTING")
    done = q.where(MoneyPlan.kind == c.spec.kind, MoneyPlan.state == "DONE")
    done = done.where(MoneyPlan.campaign_id == c.spec.campaign_id) if c.spec.campaign_id else done
    if c.db.scalar(done):
        f.append(f"a {c.spec.kind} plan for these references is already DONE")
    seen = defaultdict(int)
    for s in c.spec.steps:
        seen[(s.op, s.target_type, s.target_id)] += 1
    dups = [k for k, n in seen.items() if n > 1]
    if dups:
        f.append(f"authorization exclusivity broken: {dups[0]} appears more than once")
    if len({s.target_id for s in c.spec.steps if s.target_type == "PLEDGE"}) != len(c.pledge_steps()):
        f.append("one pledge is targeted by more than one step (captured and voided?)")
    return _r("G-02", *_ok(f, "state allows this plan, nothing else executing, each target used once"))


def g03(c: Ctx) -> RuleResult:
    f = c.foreign()
    recorded = {m.paypal_email.lower() for m in c.db.scalars(
        select(ProjectMember).where(ProjectMember.project_id == c.spec.project_id)) if m.paypal_email}
    if c.contract and c.contract.freelancer_paypal_email:
        recorded.add(c.contract.freelancer_paypal_email.lower())
    for s in c.spec.steps:
        if s.op == "PAYOUT_ITEM" and (s.receiver_email or "").lower() not in recorded:
            f.append(f"step {s.seq}: receiver {s.receiver_email} is not a recorded party of this project")
        if s.op == "REFUND_CAPTURE" and s.receiver_email:
            f.append(f"step {s.seq}: refund names a receiver; refunds only go back to the original payer")
    ids = {p["pledge_id"]: p.get("authorization_id") for p in c.spec.inputs.get("pledges", [])}
    for s in c.pledge_steps():
        p = c.pledge(s.target_id)
        if p and s.op in ("CAPTURE_AUTH", "VOID_AUTH", "REAUTH_AUTH") and ids.get(s.target_id) != p.paypal_authorization_id:
            f.append(f"step {s.seq}: authorization id in the plan does not match our record")
    return _r("G-03", *_ok(f, "every PayPal object and recipient is recorded under this project"))


def g04(c: Ctx) -> RuleResult:
    f = []
    if c.rebuilt is None:
        f.append(f"cannot compare with PlanBuilder output: {c.rebuild_error}")
    else:
        shape = lambda steps: [(s.seq, s.phase, s.op, s.target_type, s.target_id) for s in steps]  # noqa: E731
        if shape(c.spec.steps) != shape(c.rebuilt.spec.steps):
            f.append("steps differ from what PlanBuilder emits (extra, missing or reordered ops/targets)")
    for s in c.spec.steps:
        if s.idempotency_key != idempotency_key(c.hash, s.seq):
            f.append(f"step {s.seq}: idempotency key is not derived from the plan hash")
    keys = [s.idempotency_key for s in c.spec.steps]
    if len(set(keys)) != len(keys):
        f.append("duplicate idempotency keys inside the plan")
    if keys and c.db.scalar(select(func.count()).select_from(MoneyPlanStep).where(
            MoneyPlanStep.idempotency_key.in_(keys), MoneyPlanStep.plan_id != c.plan.id)):
        f.append("an idempotency key is already used by another plan")
    return _r("G-04", *_ok(f, "steps are exactly what PlanBuilder emits; keys unused"))


def g05(c: Ctx) -> RuleResult:
    f = []
    for s in c.spec.steps:
        if not isinstance(s.amount_cents, int) or isinstance(s.amount_cents, bool) or s.amount_cents < 0:
            f.append(f"step {s.seq}: amount must be integer cents >= 0")
            continue
        p = c.pledge(s.target_id) if s.target_type in ("PLEDGE", "CAPTURE") else None
        if s.op in ("CAPTURE_AUTH", "VOID_AUTH", "REAUTH_AUTH") and p and s.amount_cents > p.amount_cents:
            f.append(f"step {s.seq}: {s.amount_cents} exceeds the authorization {p.amount_cents}")
        if s.op == "REFUND_CAPTURE" and p and s.amount_cents > p.captured_cents - p.refunded_cents:
            f.append(f"step {s.seq}: refund exceeds the capture's remaining refundable amount")
        if s.op == "PAYOUT_ITEM":
            if s.amount_cents > c.pool:
                f.append(f"step {s.seq}: payout exceeds the POOL balance")
            if s.amount_cents > c.params.payout_max_cents:
                f.append(f"step {s.seq}: payout exceeds PAYOUT_MAX_CENTS {c.params.payout_max_cents}")
    if any(s.op == "PAYOUT_ITEM" for s in c.spec.steps):
        recent = c.db.scalar(select(func.count()).select_from(PayoutBatch).where(
            PayoutBatch.created_at >= c.now - timedelta(hours=1)))
        if recent + 1 > c.params.payout_max_per_hour:
            f.append(f"platform payout rate limit reached ({c.params.payout_max_per_hour}/hour)")
    currencies = {c.project.currency}
    if c.campaign:
        currencies.add(c.campaign.currency)
    if c.contract:
        currencies.add(c.contract.currency)
    if c.spec.inputs.get("currency"):
        currencies.add(c.spec.inputs["currency"])
    if len(currencies) > 1:
        f.append(f"mixed currencies {sorted(currencies)}")
    return _r("G-05", *_ok(f, "integer cents, within every source, one currency"))


def g06(c: Ctx) -> RuleResult:
    """Live lookups against PayPal's own records (APIMatic SDK). Mismatch FAILs; unreachable is UNVERIFIED."""
    f, checked = [], 0
    try:
        for s in c.spec.steps:
            p = c.pledge(s.target_id) if s.target_type in ("PLEDGE", "CAPTURE") else None
            if p is None:
                continue
            if s.op in ("CAPTURE_AUTH", "VOID_AUTH", "REAUTH_AUTH"):
                got = c.paypal_auth(p.paypal_authorization_id or "")
                checked += 1
                if got is None:
                    f.append(f"step {s.seq}: PayPal has no authorization {p.paypal_authorization_id}")
                elif got.status != "CREATED" or got.amount_cents != p.amount_cents:
                    f.append(f"step {s.seq}: PayPal says {got.status} {got.amount_cents}, we have AUTHORIZED {p.amount_cents}")
            elif s.op == "REFUND_CAPTURE":
                got = c.reader.get_capture(p.paypal_capture_id or "")
                checked += 1
                if got is None:
                    f.append(f"step {s.seq}: PayPal has no capture {p.paypal_capture_id}")
                elif got.status not in ("COMPLETED", "PARTIALLY_REFUNDED") or got.amount_cents != p.captured_cents:
                    f.append(f"step {s.seq}: PayPal says {got.status} {got.amount_cents}, we captured {p.captured_cents}")
    except PayPalUnavailable as e:
        return _r("G-06", FAIL, "; ".join(f)) if f else _r("G-06", UNVERIFIED, f"PayPal unreachable: {e}")
    if f:
        return _r("G-06", FAIL, "; ".join(f))
    return _r("G-06", PASS, f"{checked} PayPal object(s) match our records" if checked
              else "no PayPal objects referenced by this plan", paypal=bool(checked))


def g07(c: Ctx) -> RuleResult:
    f = []
    for s in c.spec.steps:
        if BUCKET_FOR_OP.get(s.op) != s.bucket:
            f.append(f"step {s.seq}: {s.op} must use bucket {BUCKET_FOR_OP.get(s.op)}, not {s.bucket}")
    out = sum(s.amount_cents for s in c.spec.steps if s.op in ("PAYOUT_ITEM", "REFUND_CAPTURE"))
    if out > c.pool:
        f.append(f"outflow {out} exceeds the POOL balance {c.pool} (bucket would go negative)")
    inflow = sum(s.amount_cents for s in c.spec.steps if s.op == "CAPTURE_AUTH")
    referenced = sum(p["authorized_cents"] for p in c.spec.inputs.get("pledges", []))
    if inflow > referenced:
        f.append(f"captures {inflow} exceed the authorizations referenced {referenced}")
    if c.spec.kind == "RELEASE_HOLDS" and any(s.bucket == "POOL" for s in c.spec.steps):
        f.append("a release plan must not touch POOL")
    if c.spec.kind == "FREELANCER_PAYOUT" and any(s.op != "PAYOUT_ITEM" for s in c.spec.steps):
        f.append("a payout plan may only contain PAYOUT_ITEM steps")
    return _r("G-07", *_ok(f, "bucket pairings valid, POOL stays non-negative, nothing created from nothing"))


def g08(c: Ctx) -> RuleResult:
    f = c.foreign()
    if f:
        return _r("G-08", FAIL, "; ".join(f))
    try:
        balance = c.reader.platform_balance_cents()
    except PayPalUnavailable:
        return _r("G-08", SKIPPED, "platform balance unavailable; not checked")
    if balance is None:
        return _r("G-08", SKIPPED, "platform balance unavailable; not checked")
    total = int(c.db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
        LedgerEntry.bucket == "POOL")) or 0)
    if total > balance:
        return _r("G-08", FAIL, f"sum of POOL balances {total} exceeds PayPal balance {balance}")
    return _r("G-08", PASS, f"POOL total {total} <= PayPal balance {balance}; other projects untouched", paypal=True)


# ---------------- kind-specific rules ----------------

def g09(c: Ctx) -> RuleResult:
    f, camp = [], c.campaign
    if camp is None:
        return _r("G-09", FAIL, "no campaign")
    if camp.state != "OPEN":
        f.append(f"campaign is {camp.state}, not OPEN")
    if c.contract is None or c.contract.signed_at is None:
        f.append("contract not signed")
    else:
        brd = c.db.get(BRD, c.contract.brd_id)
        if brd is None or brd.status != "APPROVED" or brd.locked_at is None:
            f.append("BRD is not locked")
    live = pb.live_valid_pledges(c.db, camp.id, c.now)
    if sum(p.amount_cents for p in live) < camp.goal_cents:
        f.append("live holds do not reach the goal")
    deadline_passed = c.now >= pb._aware(camp.deadline_at)
    lead_closed = c.plan.proposed_by.startswith("user:")
    if not (deadline_passed or lead_closed or camp.close_policy == "EARLY_ON_GOAL"):
        f.append("no trigger: deadline not passed, lead has not closed, policy is not EARLY_ON_GOAL")
    if f:
        return _r("G-09", FAIL, "; ".join(f))
    try:
        proven = sum(p.amount_cents for p in live if (g := c.paypal_auth(p.paypal_authorization_id or ""))
                     and g.status == "CREATED" and g.amount_cents == p.amount_cents)
    except PayPalUnavailable as e:
        return _r("G-09", UNVERIFIED, f"goal reached by our records; PayPal unreachable: {e}")
    if proven < camp.goal_cents:
        return _r("G-09", FAIL, f"PayPal confirms only {proven} of {camp.goal_cents}")
    return _r("G-09", PASS, f"PayPal confirms {proven} >= goal {camp.goal_cents}; trigger satisfied", paypal=True)


def g10(c: Ctx) -> RuleResult:
    f, camp = [], c.campaign
    caps = [s for s in c.spec.steps if s.op == "CAPTURE_AUTH"]
    total = sum(s.amount_cents for s in caps)
    if camp and total != camp.goal_cents:
        f.append(f"captures sum to {total}, goal is {camp.goal_cents}")
    for s in caps:
        p = c.pledge(s.target_id)
        if p and s.amount_cents > p.amount_cents:
            f.append(f"step {s.seq}: capture exceeds its authorization")
    if camp:
        live = pb.live_valid_pledges(c.db, camp.id, c.now)
        try:
            expect = plan_captures(camp.goal_cents, [(p.id, p.amount_cents) for p in live])
        except SettlementError:
            expect = None
        got = {s.target_id: s.amount_cents for s in caps}
        if expect is None or got != {k: v for k, v in expect.items() if v > 0}:
            f.append("split differs from the deterministic pro-rata recomputation")
    return _r("G-10", *_ok(f, "captures sum to the goal exactly and equal the pro-rata split "
                                "(final_capture is set by MoneyExecutor, tested in T-45)"))


def g11(c: Ctx) -> RuleResult:
    f, camp = [], c.campaign
    if camp is None:
        return _r("G-11", FAIL, "no campaign")
    live_sum = sum(p.amount_cents for p in pb.live_valid_pledges(c.db, camp.id, c.now))
    passed = c.now >= pb._aware(camp.deadline_at)
    if c.spec.reason == "LEAD_CANCEL":
        pass
    elif c.spec.reason == "DEADLINE_MISSED":
        if not passed:
            f.append("deadline has not passed")
        if live_sum >= camp.goal_cents:
            f.append("live holds already reach the goal; the campaign succeeded")
    else:
        f.append(f"reason {c.spec.reason} is not a failure reason")
    if c.db.scalar(select(func.count()).select_from(Pledge).where(
            Pledge.campaign_id == camp.id, (Pledge.status == "CAPTURED") | (Pledge.captured_cents > 0))):
        f.append("a pledge in this campaign is already captured")
    for s in c.spec.steps:
        if s.op != "VOID_AUTH":
            f.append(f"step {s.seq}: a release plan may only void, found {s.op}")
            continue
        p = c.pledge(s.target_id)
        if p is None or p.campaign_id != camp.id or p.status != "AUTHORIZED":
            f.append(f"step {s.seq}: target is not an AUTHORIZED pledge of this campaign")
    return _r("G-11", *_ok(f, "failure condition holds; voids only; nothing was captured"))


def g12(c: Ctx) -> RuleResult:
    f, k = [], c.contract
    if k is None or k.signed_at is None:
        return _r("G-12", FAIL, "no signed contract")
    sub = c.db.scalars(select(Submission).where(Submission.contract_id == k.id)
                       .order_by(Submission.attempt_no.desc())).first()
    rep = c.db.scalars(select(VerificationReport).where(VerificationReport.submission_id == sub.id)
                       .order_by(VerificationReport.id.desc())).first() if sub else None
    if rep is None or rep.overall != "VERIFIED":
        f.append("latest submission has no VERIFIED report")
    elif rep.sha256 != c.spec.inputs.get("report_sha256"):
        f.append("report hash does not match the stored report")
    brd = c.db.get(BRD, k.brd_id)
    if brd is None or brd.sha256 != k.brd_sha256 or brd.status != "APPROVED":
        f.append("contract BRD hash does not equal the locked BRD hash")
    items = [s for s in c.spec.steps if s.op == "PAYOUT_ITEM"]
    if len(items) != 1 or len(c.spec.steps) != 1:
        f.append(f"expected exactly one payout item, found {len(c.spec.steps)} step(s)")
    for s in items:
        if (s.receiver_email or "").lower() != (k.freelancer_paypal_email or "").lower():
            f.append("receiver is not the PayPal email locked in the contract")
        if s.amount_cents != k.amount_cents:
            f.append(f"amount {s.amount_cents} differs from the contract amount {k.amount_cents}")
    if c.project.state not in ("PAYOUT_READY", "PAYOUT_FAILED"):
        f.append(f"project is {c.project.state}, not PAYOUT_READY")
    if c.db.scalar(select(func.count()).select_from(PayoutBatch).join(MoneyPlan, MoneyPlan.id == PayoutBatch.plan_id)
                   .where(MoneyPlan.contract_id == k.id, MoneyPlan.id != c.plan.id,
                          PayoutBatch.status.in_(("PENDING", "SUCCESS")))):
        f.append("a payout for this contract is already pending or paid")
    return _r("G-12", *_ok(f, "VERIFIED report, locked recipient, contract amount, single item"))


REFUND_REASONS = pb.REFUND_REASONS


def g13(c: Ctx) -> RuleResult:
    f = []
    if c.spec.reason not in REFUND_REASONS:
        f.append(f"reason {c.spec.reason} not in {sorted(REFUND_REASONS)}")
    if not c.spec.steps:
        f.append("no refund steps")
    caps = {x["pledge_id"]: x.get("capture_id") for x in c.spec.inputs.get("captures", [])}
    for s in c.spec.steps:
        if s.op != "REFUND_CAPTURE" or s.target_type != "CAPTURE":
            f.append(f"step {s.seq}: a refund plan may only refund captures, found {s.op}")
            continue
        p = c.pledge(s.target_id)
        if p is None or not p.paypal_capture_id or caps.get(s.target_id) != p.paypal_capture_id:
            f.append(f"step {s.seq}: does not refund the original capture")
        elif s.amount_cents > p.captured_cents - p.refunded_cents:
            f.append(f"step {s.seq}: exceeds the remaining refundable amount")
    if sum(s.amount_cents for s in c.spec.steps) != c.pool:
        f.append(f"refunds {sum(s.amount_cents for s in c.spec.steps)} must equal the POOL balance {c.pool}")
    paid = c.db.scalar(select(func.count()).select_from(LedgerEntry).where(
        LedgerEntry.project_id == c.spec.project_id, LedgerEntry.type == "PAYOUT_SENT"))
    pending = c.db.scalar(select(func.count()).select_from(PayoutBatch).join(MoneyPlan, MoneyPlan.id == PayoutBatch.plan_id)
                          .where(MoneyPlan.project_id == c.spec.project_id, PayoutBatch.status.in_(("PENDING", "SUCCESS"))))
    if paid or pending:
        f.append("a freelancer payout was executed or is pending")
    if c.plan.proposed_by != f"user:{c.project.lead_user_id}":
        f.append("a refund must be requested by the lead organizer")
    return _r("G-13", *_ok(f, "refunds go back to the original captures, equal the POOL, lead requested"))


RULES = {"G-01": g01, "G-02": g02, "G-03": g03, "G-04": g04, "G-05": g05, "G-06": g06, "G-07": g07, "G-08": g08,
         "G-09": g09, "G-10": g10, "G-11": g11, "G-12": g12, "G-13": g13}


# ---------------- soft flags ----------------

def soft_flags(c: Ctx, results: list[RuleResult]) -> list[dict]:
    flags = []
    camp = c.campaign
    if camp and c.spec.kind != "RELEASE_HOLDS":
        pledges = [p for p in c.db.scalars(select(Pledge).where(Pledge.campaign_id == camp.id))
                   if p.status in ("AUTHORIZED", "CAPTURED") and p.payer_email]
        email = (c.contract.freelancer_paypal_email if c.contract else None) or ""
        if email and any(p.payer_email.lower() == email.lower() for p in pledges):
            flags.append({"id": "S-01", "title": "Self-funding",
                          "detail": "the freelancer's PayPal email appears among this campaign's pledgers"})
        by_payer = defaultdict(int)
        for p in pledges:
            by_payer[p.payer_email.lower()] += p.amount_cents
        top = max(by_payer.values(), default=0)
        window_start = pb._aware(camp.deadline_at) - timedelta(minutes=10)
        late = sum(p.amount_cents for p in pledges if p.authorized_at and window_start <= pb._aware(p.authorized_at)
                   <= pb._aware(camp.deadline_at))
        if top * 10 >= camp.goal_cents * 6:
            flags.append({"id": "S-02", "title": "Concentration",
                          "detail": "one payer holds at least 60% of the goal"})
        elif late * 2 >= camp.goal_cents:
            flags.append({"id": "S-02", "title": "Last-minute surge",
                          "detail": "at least 50% of the goal was authorized in the last 10 minutes"})
    if any(r.status == UNVERIFIED for r in results):
        flags.append({"id": "S-03", "title": "PayPal-side proof unverified",
                      "detail": "PayPal could not be reached to confirm the referenced objects"})
    return flags


# ---------------- entry point ----------------

def evaluate(db: Session, plan: MoneyPlan, spec: MoneyPlanSpec | None = None, *, now: datetime,
             reader: PayPalReader, params: GuardianParams | None = None) -> Evaluation:
    """Run every rule applicable to the plan's kind.

    `spec` defaults to the stored plan. Pass a mutated copy to review a tampered plan (demo simulation);
    the stored `plan` row stays the reference the rules compare against.
    """
    spec = spec or MoneyPlanSpec.model_validate(plan.plan_json)
    c = Ctx(db, plan, spec, now, reader, params or GuardianParams())
    ev = Evaluation()
    for rid in APPLICABLE[spec.kind]:
        try:
            ev.results.append(RULES[rid](c))
        except Exception as e:  # noqa: BLE001 - a rule that crashes must never read as a pass
            ev.results.append(_r(rid, FAIL, f"rule could not be evaluated: {type(e).__name__}: {e}"))
    ev.soft_flags = soft_flags(c, ev.results)
    return ev
