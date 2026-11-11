"""Job handlers registered with the runner (imported once at startup)."""
import logging

from sqlalchemy.orm import Session

from app.agents.ba_agent import get_ba_agents
from app.agents.brd_generator import get_brd_generator
from app.models import Campaign, Project
from app.services import ba_rounds, brd_service, jobs, money_executor, paypal_io, strategist_service

log = logging.getLogger("briefpay.jobs")


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
    """Compute and store the forecast, deadline advice and nudge ranking (deterministic), then the wording: the model's, with every
    number checked against the facts, or the template wording if the model is unavailable (T-47)."""
    from app.agents.strategist import get_strategist
    from app.services import strategist_words
    c = db.get(Campaign, payload["campaign_id"])
    project = db.get(Project, c.project_id)
    log.info("[Strategist] Computing forecast & deadline advice for campaign #%s (project #%s)...", c.id, c.project_id)
    r = strategist_service.run_report(db, c)
    # Commit the forecast row so SQLite's write lock is released before add_narrative() logs AgentRun on a second session.
    db.commit()
    log.info("[Strategist] Drafting narrative & nudges for campaign #%s report #%s...", c.id, r.id)
    words = strategist_words.add_narrative(db, r, c, project, get_strategist(),
                                           {"forecast": r.forecast_json, "suggestions": r.suggestions_json})
    log.info("[Strategist] Report #%s ready (wording=%s, flags=%s, agent_run_id=%s).",
             r.id, words["source"], words["flags"], words["agent_run_id"])
    return {"report_id": r.id, "probability": r.forecast_json["probability"], "wording": words["source"], "flags": words["flags"]}


@jobs.register("AUTO_CHECKS")
def auto_checks(db: Session, payload: dict) -> dict:
    """Run the automatic checks for a submission and save them. Safe to retry."""
    from app.services import submission_service
    return submission_service.run_auto_checks(db, payload["submission_id"])


@jobs.register("VERIFY_QUESTIONS")
def verify_questions(db: Session, payload: dict) -> dict:
    """Write the evidence questions for a checked submission. Falls back to template questions if the AI is unavailable. Safe to retry."""
    from app.agents.verifier import get_verifier
    from app.services import verify_questions as vq
    return vq.generate(db, payload["submission_id"], get_verifier())


@jobs.register("VERIFY_JUDGE")
def verify_judge(db: Session, payload: dict) -> dict:
    """Judge a submission's evidence (one model call) and apply the fixed rules. Never decides on a model failure. Safe to retry."""
    from app.agents.verifier import get_verifier
    from app.services import submission_service, verify_judge as vj
    return vj.judge(db, payload["submission_id"], get_verifier(), submission_service.new_checker())


@jobs.register("POLL_STEPS")
def poll_steps(db: Session, payload: dict) -> dict:
    """Ask PayPal about steps still waiting for confirmation (the webhook fallback). Read-only; safe to repeat."""
    from app.services import poll
    return poll.poll(db, paypal_io.get_reader(), paypal_io.get_payout_reader(), project_id=payload.get("project_id"), force=bool(payload.get("force")))


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
