from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import (
    BRD, Campaign, Contract, Pledge, Project, ProjectMember, Submission, User, VerificationReport,
)
from sqlalchemy.orm import sessionmaker

from app.agents.guardian_llm import GuardianLLM
from app.agents.llm_adapter import LLMAdapter, RawResult
from app.services import guardian_rules as g
from app.services import ledger
from app.services.paypal_io import PayPalWriteError

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
GOAL = 40000


class World:
    """One Velugu Cove project with a signed contract and an OPEN campaign."""

    def __init__(self, db, tag=""):
        self.db = db
        self.tag = tag
        lead = User(email=f"lakshmi{tag}@x.com", display_name="Lakshmi")
        db.add(lead)
        db.flush()
        self.project = Project(title="Velugu Cove", lead_user_id=lead.id, state="PLEDGING", currency="USD")
        db.add(self.project)
        db.flush()
        self.lead = ProjectMember(project_id=self.project.id, user_id=lead.id, role="LEAD")
        arjun = User(email=f"arjun{tag}@x.com", display_name="Arjun")
        db.add_all([self.lead, arjun])
        db.flush()
        fm = ProjectMember(project_id=self.project.id, user_id=arjun.id, role="FREELANCER", paypal_email=f"arjun{tag}@sandbox.com")
        db.add(fm)
        db.flush()
        brd = BRD(project_id=self.project.id, version=1, status="APPROVED", content_json={}, content_md="",
                  sha256="b" * 64, score_at_generation=93, locked_at=NOW)
        db.add(brd)
        db.flush()
        self.contract = Contract(project_id=self.project.id, brd_id=brd.id, brd_sha256=brd.sha256,
                                 freelancer_member_id=fm.id, freelancer_paypal_email=f"arjun{tag}@sandbox.com",
                                 amount_cents=GOAL, delivery_days=5, terms_md="t", sha256="c" * 64, signed_at=NOW)
        self.campaign = Campaign(project_id=self.project.id, number=1, proposer_member_id=self.lead.id, goal_cents=GOAL,
                                 deadline_at=NOW + timedelta(hours=40), state="OPEN", opens_at=NOW - timedelta(hours=8))
        db.add_all([self.contract, self.campaign])
        db.flush()
        self.n = 0

    def pledge(self, cents, status="AUTHORIZED", honor_hours=60, campaign=None, **kw) -> Pledge:
        self.n += 1
        c = campaign or self.campaign
        p = Pledge(campaign_id=c.id, project_id=self.project.id, display_name=f"P{self.n}", amount_cents=cents,
                   paypal_order_id=f"ORDER{self.tag}{self.n}", paypal_authorization_id=f"AUTH{self.tag}{self.n}", status=status,
                   authorized_at=NOW, honor_until=NOW + timedelta(hours=honor_hours), **kw)
        self.db.add(p)
        self.db.flush()
        return p

    def capture_all(self):
        """Pretend the capture plan ran: pledges CAPTURED, POOL funded, campaign CAPTURED."""
        for p in self.db.scalars(select(Pledge).where(Pledge.status == "AUTHORIZED")):
            p.status, p.captured_cents, p.paypal_capture_id = "CAPTURED", p.amount_cents, f"CAP{p.id}"
            ledger.append(self.db, self.project.id, "PLEDGE_CAPTURED", p.amount_cents, actor="paypal")
        self.campaign.state = "CAPTURED"
        self.db.flush()

    def verified_report(self, overall="VERIFIED", attempt=1):
        sub = Submission(contract_id=self.contract.id, attempt_no=attempt, repo_url="r", commit_sha="s", deployed_url="u")
        self.db.add(sub)
        self.db.flush()
        rep = VerificationReport(submission_id=sub.id, verdicts_json=[], overall=overall, must_pass_pct=100,
                                 should_pass_pct=100, summary="ok", sha256=("d" if overall == "VERIFIED" else "e") * 64)
        self.db.add(rep)
        self.db.flush()
        return rep




class FakeReader:
    """Stands in for PayPal's own records. Mirrors our DB unless told otherwise."""

    def __init__(self, db, balance=10**9, down=False, overrides=None):
        self.db, self.balance, self.down, self.overrides = db, balance, down, overrides or {}

    def _guard(self):
        if self.down:
            raise g.PayPalUnavailable("connection refused")

    def get_authorization(self, authorization_id):
        self._guard()
        if authorization_id in self.overrides:
            return self.overrides[authorization_id]
        p = self.db.scalars(select(Pledge).where(Pledge.paypal_authorization_id == authorization_id)).first()
        if p is None:
            return None
        return g.PayPalObject("CREATED" if p.status == "AUTHORIZED" else "CAPTURED", p.amount_cents)

    def get_capture(self, capture_id):
        self._guard()
        if capture_id in self.overrides:
            return self.overrides[capture_id]
        p = self.db.scalars(select(Pledge).where(Pledge.paypal_capture_id == capture_id)).first()
        return g.PayPalObject("COMPLETED", p.captured_cents) if p else None

    def platform_balance_cents(self):
        self._guard()
        return self.balance


class FakeWriter:
    """Records every PayPal write. `errors[op]` is a queue of exceptions to raise on successive calls."""

    def __init__(self):
        self.calls: list[dict] = []
        self.errors: dict[str, list[Exception]] = {}
        self.crash_on_call: int | None = None

    def _do(self, op, request_id, **kw):
        self.calls.append({"op": op, "request_id": request_id, **kw})
        if self.crash_on_call is not None and len(self.calls) == self.crash_on_call:
            raise RuntimeError("process died mid-run")
        queue = self.errors.get(op, [])
        if queue:
            raise queue.pop(0)
        return {"id": f"{op.upper()}-{request_id}", "status": "PENDING"}

    def capture_authorization(self, authorization_id, amount_cents, currency, final_capture, request_id):
        return self._do("capture", request_id, authorization_id=authorization_id, amount_cents=amount_cents,
                        currency=currency, final_capture=final_capture)

    def void_authorization(self, authorization_id, request_id):
        return self._do("void", request_id, authorization_id=authorization_id)

    def refund_capture(self, capture_id, amount_cents, currency, request_id):
        return self._do("refund", request_id, capture_id=capture_id, amount_cents=amount_cents)

    def create_payout_batch(self, sender_batch_id, items, currency, email_subject, request_id):
        return self._do("payout", request_id, sender_batch_id=sender_batch_id, items=items, currency=currency)

    def ops(self):
        return [c["op"] for c in self.calls]

    def keys(self):
        return [c["request_id"] for c in self.calls]


def transient(msg="timeout"):
    return PayPalWriteError(msg, transient=True)


def rejected(msg="INSTRUMENT_DECLINED"):
    return PayPalWriteError(msg, transient=False)



LOW = {"risk_level": "low", "findings": [], "explanation_for_sponsors": "Nothing unusual."}
HIGH = {"risk_level": "high", "explanation_for_sponsors": "Several pledges look coordinated.",
        "findings": [{"type": "SHILL_PLEDGING_SUSPECTED", "detail": "P1 and P2 landed together", "severity": "high"}]}


class ScriptedBackend:
    """A model backend that returns queued outputs (or raises queued exceptions) and records what it was asked."""

    provider, model = "scripted", "scripted-1"

    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    def generate(self, **kw):
        self.calls.append(kw)
        o = self.outputs.pop(0) if self.outputs else LOW
        if isinstance(o, Exception):
            raise o
        return RawResult(data=o, provider="scripted", model="scripted-1")


def scripted_llm(db, *outputs):
    backend = ScriptedBackend(*outputs)
    return GuardianLLM(LLMAdapter(backend, sessionmaker(bind=db.get_bind(), expire_on_commit=False))), backend
