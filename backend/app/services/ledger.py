"""LedgerService: append-only, gapless seq per project, POOL bucket only (SPEC 6.2, 6.3, D-020)."""
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.models import LedgerEntry

POOL, NONE = "POOL", "NONE"

# type -> sign rule on amount_cents: 0 = memo row, +1 = into POOL, -1 = out of POOL
LEDGER_TYPES: dict[str, int] = {
    "PLEDGE_AUTHORIZED": 0,
    "PLEDGE_CAPTURED": +1,
    "PLEDGE_VOIDED": 0,
    "PLEDGE_EXPIRED": 0,
    "REFUND": -1,
    "PAYOUT_SENT": -1,
    "PAYOUT_RETURNED": +1,
    "STATE_CHANGE": 0,
    "BRD_LOCKED": 0,
    "CONTRACT_SIGNED": 0,
    "GUARDIAN_DECISION": 0,
    "APPROVAL": 0,
    "PLAN_EXECUTED": 0,
}


class LedgerError(Exception):
    pass


def _forbid(mapper, connection, target):  # noqa: ARG001
    raise LedgerError("ledger_entries is append-only: rows are never updated or deleted")


event.listen(LedgerEntry, "before_update", _forbid)
event.listen(LedgerEntry, "before_delete", _forbid)


def pool_balance(db: Session, project_id: int) -> int:
    """I-1: Sum of POOL rows. Holds are never money, so they never appear here (I-8)."""
    total = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
            LedgerEntry.project_id == project_id, LedgerEntry.bucket == POOL
        )
    )
    return int(total or 0)


def append(
    db: Session,
    project_id: int,
    type: str,
    amount_cents: int = 0,
    *,
    actor: str,
    ref_type: str | None = None,
    ref_id: str | int | None = None,
    meta: dict | None = None,
) -> LedgerEntry:
    """Add one row. Caller owns the transaction (commit/rollback)."""
    if type not in LEDGER_TYPES:
        raise LedgerError(f"unknown ledger type {type}")
    sign = LEDGER_TYPES[type]
    if sign == 0 and amount_cents != 0:
        raise LedgerError(f"{type} is a memo row and must have amount 0")
    if sign > 0 and amount_cents <= 0:
        raise LedgerError(f"{type} must be a positive amount into POOL")
    if sign < 0 and amount_cents >= 0:
        raise LedgerError(f"{type} must be a negative amount out of POOL")
    bucket = POOL if sign else NONE
    # I-1: the pool can never go negative, so pledgers/freelancer can't be paid from money that isn't there
    if sign < 0 and pool_balance(db, project_id) + amount_cents < 0:
        raise LedgerError("POOL balance would go negative")

    last = db.scalar(select(func.max(LedgerEntry.seq)).where(LedgerEntry.project_id == project_id))
    entry = LedgerEntry(
        project_id=project_id,
        seq=(last or 0) + 1,  # gapless (I-4); UNIQUE(project_id, seq) rejects a racing writer
        bucket=bucket,
        type=type,
        amount_cents=amount_cents,
        ref_type=ref_type,
        ref_id=None if ref_id is None else str(ref_id),
        actor=actor,
        meta_json=meta or {},
    )
    db.add(entry)
    db.flush()
    return entry
