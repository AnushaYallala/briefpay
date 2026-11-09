"""The money invariants I-1 ... I-8 (SPEC 6.3), checked from the database (and PayPal for I-7). Read-only.

Each check returns PASS, FAIL (with the offending rows) or NOT_CHECKED (with the reason). The report is "ok" only when
nothing FAILs; NOT_CHECKED is shown, never hidden.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, LedgerEntry, MoneyPlan, MoneyPlanStep, Pledge, Project
from app.services.guardian_rules import PayPalUnavailable
from app.services.ledger import LEDGER_TYPES, NONE, POOL

POOL_IN = ("PLEDGE_CAPTURED", "PAYOUT_RETURNED")
POOL_OUT = ("PAYOUT_SENT", "REFUND")
HOLD_TYPES = ("PLEDGE_AUTHORIZED", "PLEDGE_VOIDED", "PLEDGE_EXPIRED")
RELEASED = ("VOIDED", "EXPIRED")


def _check(cid: str, title: str, problems: list, not_checked: str | None = None) -> dict:
    if not_checked:
        return {"id": cid, "title": title, "status": "NOT_CHECKED", "reason": not_checked, "problems": []}
    return {"id": cid, "title": title, "status": "FAIL" if problems else "PASS", "problems": problems[:50],
            "problem_count": len(problems)}


def _entries(db: Session, project_ids: list[int]) -> dict[int, list[LedgerEntry]]:
    by_project: dict[int, list[LedgerEntry]] = defaultdict(list)
    for e in db.scalars(select(LedgerEntry).where(LedgerEntry.project_id.in_(project_ids)).order_by(LedgerEntry.project_id, LedgerEntry.seq)):
        by_project[e.project_id].append(e)
    return by_project


def _pledge_ref(e: LedgerEntry) -> int | None:
    return int(e.ref_id) if e.ref_type == "pledge" and (e.ref_id or "").isdigit() else None


def i1_pool_balance(db: Session, project_ids: list[int], entries: dict) -> dict:
    problems = []
    for pid in project_ids:
        balance = 0
        for e in entries.get(pid, []):
            if e.bucket == POOL:
                balance += e.amount_cents
                if balance < 0:
                    problems.append({"project_id": pid, "seq": e.seq, "why": f"POOL went negative ({balance})"})
        # cross-check the ledger against the objects it describes
        pledges = db.scalars(select(Pledge).where(Pledge.project_id == pid)).all()
        paid = sum(-e.amount_cents for e in entries.get(pid, []) if e.type == "PAYOUT_SENT")
        returned = sum(e.amount_cents for e in entries.get(pid, []) if e.type == "PAYOUT_RETURNED")
        expected = sum(p.captured_cents for p in pledges) - sum(p.refunded_cents for p in pledges) - paid + returned
        if balance != expected:
            problems.append({"project_id": pid, "why": f"POOL {balance} != captured - refunded - paid out ({expected})"})
    return _check("I-1", "POOL balance = captured - refunded - paid out, and never below 0", problems)


def i2_pool_uses(project_ids: list[int], entries: dict) -> dict:
    problems = []
    for pid in project_ids:
        for e in entries.get(pid, []):
            sign = LEDGER_TYPES.get(e.type)
            if sign is None:
                problems.append({"project_id": pid, "seq": e.seq, "why": f"unknown type {e.type}"})
            elif e.bucket == POOL and not ((e.type in POOL_IN and e.amount_cents > 0) or (e.type in POOL_OUT and e.amount_cents < 0)):
                problems.append({"project_id": pid, "seq": e.seq, "why": f"{e.type} {e.amount_cents} is not a legal POOL movement"})
            elif e.bucket != POOL and (sign != 0 or e.amount_cents != 0):
                problems.append({"project_id": pid, "seq": e.seq, "why": f"{e.type} moves money outside the POOL bucket"})
    return _check("I-2", "POOL money only funds the freelancer payout or refunds", problems)


def i3_captures(db: Session, project_ids: list[int]) -> dict:
    problems = []
    plans = db.scalars(select(MoneyPlan).where(MoneyPlan.project_id.in_(project_ids), MoneyPlan.kind == "CAPTURE_PLEDGES",
                                               MoneyPlan.state == "DONE")).all()
    for plan in plans:
        campaign = db.get(Campaign, plan.campaign_id)
        steps = db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id, MoneyPlanStep.op == "CAPTURE_AUTH")).all()
        for s in steps:
            pledge = db.get(Pledge, s.target_id)
            if pledge is None or s.amount_cents > pledge.amount_cents:
                problems.append({"plan_id": plan.id, "step_id": s.id, "why": "capture is larger than its authorization"})
        total = sum(s.amount_cents for s in steps)
        if campaign is not None and total != campaign.goal_cents:
            problems.append({"plan_id": plan.id, "why": f"captures total {total} != goal {campaign.goal_cents}"})
    return _check("I-3", "Each capture <= its hold, and captures add up to the goal exactly", problems)


def i4_gapless(project_ids: list[int], entries: dict) -> dict:
    problems = []
    for pid in project_ids:
        seqs = [e.seq for e in entries.get(pid, [])]
        if seqs != list(range(1, len(seqs) + 1)):
            problems.append({"project_id": pid, "why": "ledger seq has a gap or a duplicate", "seqs": seqs[:20]})
    return _check("I-4", "Ledger sequence numbers are gapless per project", problems)


def i5_exclusive(project_ids: list[int], entries: dict) -> dict:
    problems = []
    for pid in project_ids:
        captured, released = defaultdict(int), set()
        for e in entries.get(pid, []):
            ref = _pledge_ref(e)
            if ref is None:
                continue
            if e.type == "PLEDGE_CAPTURED":
                captured[ref] += 1
            elif e.type in ("PLEDGE_VOIDED", "PLEDGE_EXPIRED"):
                released.add(ref)
        for ref, n in captured.items():
            if n > 1:
                problems.append({"project_id": pid, "pledge_id": ref, "why": f"captured {n} times"})
            if ref in released:
                problems.append({"project_id": pid, "pledge_id": ref, "why": "both captured and released"})
    return _check("I-5", "Each hold ends exactly one way: captured, voided or expired", problems)


def i6_release(db: Session, project_ids: list[int], entries: dict) -> dict:
    problems = []
    plans = db.scalars(select(MoneyPlan).where(MoneyPlan.project_id.in_(project_ids), MoneyPlan.kind == "RELEASE_HOLDS",
                                               MoneyPlan.state == "DONE")).all()
    for plan in plans:
        captured = {_pledge_ref(e) for e in entries.get(plan.project_id, []) if e.type == "PLEDGE_CAPTURED"}
        for p in db.scalars(select(Pledge).where(Pledge.campaign_id == plan.campaign_id, Pledge.paypal_authorization_id.is_not(None))):
            if p.status not in RELEASED:
                problems.append({"plan_id": plan.id, "pledge_id": p.id, "why": f"pledge is {p.status} after the release"})
            if p.id in captured:
                problems.append({"plan_id": plan.id, "pledge_id": p.id, "why": "a released pledge was captured"})
    return _check("I-6", "After a release, every hold is voided or expired and nothing was captured", problems)


def i7_solvency(project_ids: list[int], entries: dict, reader) -> dict:
    title = "All POOL balances together <= the platform's PayPal balance"
    if reader is None:
        return _check("I-7", title, [], not_checked="no PayPal reader")
    try:
        available = reader.platform_balance_cents()
    except PayPalUnavailable as e:
        return _check("I-7", title, [], not_checked=f"PayPal balance unavailable: {e}")
    if available is None:
        return _check("I-7", title, [], not_checked="PayPal returned no balance")
    owed = sum(e.amount_cents for pid in project_ids for e in entries.get(pid, []) if e.bucket == POOL)
    return _check("I-7", title, [] if owed <= available else [{"why": f"POOL total {owed} > PayPal balance {available}"}])


def i8_holds_are_not_money(project_ids: list[int], entries: dict) -> dict:
    problems = [{"project_id": pid, "seq": e.seq, "why": f"{e.type} carries money ({e.bucket} {e.amount_cents})"}
                for pid in project_ids for e in entries.get(pid, [])
                if e.type in HOLD_TYPES and (e.bucket != NONE or e.amount_cents != 0)]
    return _check("I-8", "Holds are never money: hold rows are memos with amount 0", problems)


def report(db: Session, *, reader=None, project_id: int | None = None) -> dict:
    q = select(Project.id).order_by(Project.id)
    if project_id is not None:
        q = q.where(Project.id == project_id)
    project_ids = list(db.scalars(q))
    entries = _entries(db, project_ids)
    checks = [
        i1_pool_balance(db, project_ids, entries), i2_pool_uses(project_ids, entries), i3_captures(db, project_ids),
        i4_gapless(project_ids, entries), i5_exclusive(project_ids, entries), i6_release(db, project_ids, entries),
        # I-7 compares ALL pools with the platform balance; a single-project report cannot judge it
        i7_solvency(project_ids, entries, reader) if project_id is None
        else _check("I-7", "All POOL balances together <= the platform's PayPal balance", [], not_checked="only checked across all projects"),
        i8_holds_are_not_money(project_ids, entries),
    ]
    return {"ok": all(c["status"] != "FAIL" for c in checks), "projects": len(project_ids), "checks": checks}
