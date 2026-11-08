"""Job handlers registered with the runner (imported once at startup)."""
from sqlalchemy.orm import Session

from app.agents.ba_agent import get_ba_agents
from app.agents.brd_generator import get_brd_generator
from app.models import Project
from app.services import ba_rounds, brd_service, jobs, money_executor, paypal_io


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
