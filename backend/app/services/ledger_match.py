"""Ledger vs PayPal (SPEC 9.7, 11.1 #12): for each ledger row that stands for a PayPal object, ask PayPal and compare. Read-only.

  MATCH         PayPal agrees: the object exists, is final, and the amount equals the ledger amount
  PENDING       PayPal knows it but it is not final yet
  MISMATCH      PayPal disagrees: another amount, or a failed / declined / cancelled object
  NOT_FOUND     the ledger says it happened, PayPal has no such object
  UNAVAILABLE   PayPal could not be asked right now (nothing is concluded)

Rows that stand for no PayPal object (state changes, approvals, holds, ...) are not part of the answer. The answer is computed
on request and never stored: the ledger is append-only and a read must not write. At most MAX_ROWS PayPal lookups are made per call.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LedgerEntry, PayoutBatch, PayoutItem
from app.services.guardian_rules import PayPalUnavailable

MAX_ROWS = 30
CAPTURE_DONE = ("COMPLETED", "REFUNDED", "PARTIALLY_REFUNDED")
CAPTURE_BAD = ("DECLINED", "FAILED", "DENIED")
REFUND_BAD = ("FAILED", "CANCELLED")
PAYOUT_OK = ("SUCCESS", "SUCCEEDED")
PAYOUT_WAITING = ("PENDING", "HELD", "ONHOLD", "UNCLAIMED")
RESULTS = ("MATCH", "PENDING", "MISMATCH", "NOT_FOUND", "UNAVAILABLE")


def _result(status: str, detail: str, **extra) -> dict:
    return {"status": status, "detail": detail, **extra}


def _capture(entry: LedgerEntry, reader) -> dict | None:
    cid = (entry.meta_json or {}).get("capture_id")
    if not cid:
        return None
    got = reader.get_capture(cid)
    if got is None:
        return _result("NOT_FOUND", "PayPal has no capture with this id", paypal_ref=cid)
    if got.status in CAPTURE_BAD:
        return _result("MISMATCH", f"PayPal says the capture is {got.status}", paypal_ref=cid, paypal_status=got.status)
    if got.status not in CAPTURE_DONE:
        return _result("PENDING", f"PayPal says the capture is {got.status}", paypal_ref=cid, paypal_status=got.status)
    if got.amount_cents != entry.amount_cents:
        return _result("MISMATCH", f"PayPal captured {got.amount_cents} cents, the ledger says {entry.amount_cents}", paypal_ref=cid,
                       paypal_status=got.status, paypal_cents=got.amount_cents)
    return _result("MATCH", "PayPal captured exactly this amount", paypal_ref=cid, paypal_status=got.status, paypal_cents=got.amount_cents)


def _refund(entry: LedgerEntry, reader) -> dict | None:
    rid = (entry.meta_json or {}).get("refund_id")
    if not rid:
        return None
    got = reader.get_refund(rid)
    if got is None:
        return _result("NOT_FOUND", "PayPal has no refund with this id", paypal_ref=rid)
    if got.status in REFUND_BAD:
        return _result("MISMATCH", f"PayPal says the refund is {got.status}", paypal_ref=rid, paypal_status=got.status)
    if got.status != "COMPLETED":
        return _result("PENDING", f"PayPal says the refund is {got.status}", paypal_ref=rid, paypal_status=got.status)
    if got.amount_cents != -entry.amount_cents:
        return _result("MISMATCH", f"PayPal refunded {got.amount_cents} cents, the ledger says {-entry.amount_cents}", paypal_ref=rid,
                       paypal_status=got.status, paypal_cents=got.amount_cents)
    return _result("MATCH", "PayPal refunded exactly this amount", paypal_ref=rid, paypal_status=got.status, paypal_cents=got.amount_cents)


def _payout(db: Session, entry: LedgerEntry, payout_reader, batches: dict) -> dict | None:
    meta = entry.meta_json or {}
    plan_id = meta.get("plan_id")
    if plan_id is None:
        return None
    batch = db.scalars(select(PayoutBatch).where(PayoutBatch.plan_id == plan_id)).first()
    item = db.scalars(select(PayoutItem).where(PayoutItem.batch_id == batch.id, PayoutItem.amount_cents == -entry.amount_cents)).first() if batch else None
    if batch is None or item is None or not batch.paypal_batch_id:
        return _result("NOT_FOUND", "no payout batch of ours is recorded for this row")
    if batch.paypal_batch_id not in batches:                    # one lookup per batch per call
        batches[batch.paypal_batch_id] = payout_reader.get_payout_batch(batch.paypal_batch_id)
    found = next((i for i in batches[batch.paypal_batch_id].get("items", []) if str(i.get("sender_item_id")) == item.sender_item_id), None)
    ref = batch.paypal_batch_id
    if found is None:
        return _result("NOT_FOUND", "PayPal's batch does not contain our payout item", paypal_ref=ref)
    status, cents = found.get("transaction_status"), found.get("amount_cents")
    if status in PAYOUT_OK:
        if cents != -entry.amount_cents:
            return _result("MISMATCH", f"PayPal paid {cents} cents, the ledger says {-entry.amount_cents}", paypal_ref=ref, paypal_status=status, paypal_cents=cents)
        return _result("MATCH", "PayPal paid exactly this amount", paypal_ref=ref, paypal_status=status, paypal_cents=cents)
    if status in PAYOUT_WAITING:
        return _result("PENDING", f"PayPal says the payout is {status}", paypal_ref=ref, paypal_status=status)
    return _result("MISMATCH", f"PayPal says the payout is {status}", paypal_ref=ref, paypal_status=status)


def match(db: Session, project_id: int, reader, payout_reader) -> dict:
    """{seq: result} for the project's PayPal-backed ledger rows (the newest MAX_ROWS), plus a count per result."""
    rows = list(db.scalars(select(LedgerEntry).where(LedgerEntry.project_id == project_id,
                                                     LedgerEntry.type.in_(("PLEDGE_CAPTURED", "REFUND", "PAYOUT_SENT"))).order_by(LedgerEntry.seq.desc())))
    checked, batches = {}, {}
    for e in rows[:MAX_ROWS]:
        try:
            if e.type == "PLEDGE_CAPTURED":
                r = _capture(e, reader)
            elif e.type == "REFUND":
                r = _refund(e, reader)
            else:
                r = _payout(db, e, payout_reader, batches)
        except PayPalUnavailable as ex:
            r = _result("UNAVAILABLE", f"PayPal could not be asked: {ex}")
        if r is not None:
            checked[e.seq] = r
    counts = {k: sum(1 for r in checked.values() if r["status"] == k) for k in RESULTS}
    return {"project_id": project_id, "results": {str(k): v for k, v in sorted(checked.items())}, "counts": counts,
            "limited": len(rows) > MAX_ROWS, "all_match": bool(checked) and counts["MATCH"] == len(checked)}
