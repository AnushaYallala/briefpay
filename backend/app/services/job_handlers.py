"""Job handlers registered with the runner (imported once at startup)."""
from sqlalchemy.orm import Session

from app.agents.ba_agent import get_ba_agents
from app.agents.brd_generator import get_brd_generator
from app.models import Campaign, Project
from app.services import ba_rounds, brd_service, jobs, money_executor, paypal_io, strategist_service


@jobs.register("EXECUTE_PLAN")
def execute_plan(db: Session, payload: dict) -> dict:
    """Run an approved plan. Retries (same idempotency keys) are safe; a refusal fails the job visibly."""
    plan = money_executor.execute(db, payload["plan_id"], paypal_io.get_writer())
    return {"plan_id": plan.id, "state": plan.state}


@jobs.register("BA_RUN")
def ba_run(db: Session, payload: dict) -> dict:
    """Score the current BA round and, if the score is not ready, write the next questions. Safe to retry."""
    project = db.get(Project, payload["project_id"])
    agent, qagent = get_ba_agents()
    return ba_rounds.run_round(db, project, agent, qagent)


@jobs.register("BRD_GENERATE")
def brd_generate(db: Session, payload: dict) -> dict:
    """Draft, assemble, render and store the BRD. Safe to retry: a project that already has one pending reports it."""
    return brd_service.generate_once(db, db.get(Project, payload["project_id"]), get_brd_generator())


@jobs.register("STRATEGIST_RUN")
def strategist_run(db: Session, payload: dict) -> dict:
    """Compute and store the forecast, deadline advice and nudge ranking (deterministic; the optional LLM wording is T-47)."""
    r = strategist_service.run_report(db, db.get(Campaign, payload["campaign_id"]))
    return {"report_id": r.id, "probability": r.forecast_json["probability"]}


@jobs.register("AUTO_CHECKS")
def auto_checks(db: Session, payload: dict) -> dict:
    """Run the automatic checks for a submission and save them. Safe to retry."""
    from app.services import submission_service
    return submission_service.run_auto_checks(db, payload["submission_id"])


@jobs.register("PROCESS_WEBHOOK")
def process_webhook(db: Session, payload: dict) -> dict:
    """Apply a verified PayPal event. Safe to repeat; `NotReady` makes the runner retry with backoff."""
    from datetime import datetime, timezone

    from app.models import WebhookEvent
    from app.services import webhook_processing

    row = db.get(WebhookEvent, payload["webhook_event_id"])
    if row is None or not row.verified:
        return {"effect": "SKIPPED", "why": "unknown or unverified event"}
    if row.processed_at is not None:
        return {"effect": "ALREADY_PROCESSED"}
    result = webhook_processing.process(db, row.payload_json, payout_reader=paypal_io.get_payout_reader())
    row.processed_at, row.error = datetime.now(timezone.utc), None
    return result
