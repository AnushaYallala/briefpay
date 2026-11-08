"""Job handlers registered with the runner (imported once at startup)."""
from sqlalchemy.orm import Session

from app.services import jobs, money_executor, paypal_io


@jobs.register("EXECUTE_PLAN")
def execute_plan(db: Session, payload: dict) -> dict:
    """Run an approved plan. Retries (same idempotency keys) are safe; a refusal fails the job visibly."""
    plan = money_executor.execute(db, payload["plan_id"], paypal_io.get_writer())
    return {"plan_id": plan.id, "state": plan.state}
