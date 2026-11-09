"""PayPal webhook receiver (SPEC 9.5). Verify with PayPal, store once, queue the work, answer fast.

  1. the signature is checked by PayPal itself; a failure is stored with verified = false and answered 400
  2. a repeated event id is a harmless 200 (PayPal retries; two deliveries can also race)
  3. the real work happens in a PROCESS_WEBHOOK job, so a slow handler never makes PayPal time out
  4. if PayPal cannot be asked, answer 503 and store nothing, so PayPal redelivers later
"""
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import WebhookEvent
from app.services import jobs, paypal_io
from app.services.guardian_rules import PayPalUnavailable

router = APIRouter()
MAX_BODY_BYTES = 256_000


def reply(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": {}}}, status_code=status)


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_db),
                         verifier: paypal_io.WebhookVerifier = Depends(paypal_io.get_verifier)) -> JSONResponse:
    raw_bytes = await request.body()
    if len(raw_bytes) > MAX_BODY_BYTES:
        return reply(413, "BODY_TOO_LARGE", "Webhook body is too large")
    raw = raw_bytes.decode("utf-8", errors="replace")
    try:
        event = json.loads(raw)
        event_id, event_type = event["id"], event["event_type"]
    except (ValueError, KeyError, TypeError):
        return reply(400, "BAD_EVENT", "Body must be a PayPal event with an id and an event_type")
    if not (isinstance(event_id, str) and 0 < len(event_id) <= 64 and isinstance(event_type, str) and 0 < len(event_type) <= 64):
        return reply(400, "BAD_EVENT", "Body must be a PayPal event with an id and an event_type")

    if db.scalars(select(WebhookEvent.id).where(WebhookEvent.paypal_event_id == event_id)).first() is not None:
        return JSONResponse({"status": "duplicate"})

    webhook_id = get_settings().paypal_webhook_id
    if not webhook_id:
        return reply(503, "WEBHOOK_NOT_CONFIGURED", "PAYPAL_WEBHOOK_ID is not set, so events cannot be verified")
    try:
        verified = verifier.verify_webhook_signature(dict(request.headers), raw, webhook_id)
    except PayPalUnavailable:
        return reply(503, "PAYPAL_UNAVAILABLE", "Could not verify the event right now; PayPal will redeliver it")

    resource = event.get("resource") if isinstance(event.get("resource"), dict) else {}
    row = WebhookEvent(paypal_event_id=event_id, event_type=event_type, resource_id=str(resource.get("id"))[:64] if resource.get("id") else None,
                       payload_json=event, verified=bool(verified))
    db.add(row)
    try:
        db.flush()
    except IntegrityError:  # two deliveries of the same event raced each other
        db.rollback()
        return JSONResponse({"status": "duplicate"})
    if not verified:
        db.commit()
        return reply(400, "INVALID_SIGNATURE", "The event signature could not be verified")
    jobs.enqueue(db, "PROCESS_WEBHOOK", {"webhook_event_id": row.id})
    db.commit()
    return JSONResponse({"status": "accepted"})
