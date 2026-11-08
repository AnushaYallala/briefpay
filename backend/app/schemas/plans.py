"""MoneyPlan contract (SPEC 7.5.1). Changing this is a contract change: update SPEC + DECISIONS."""
from typing import Literal

from pydantic import BaseModel


class PlanStep(BaseModel):
    seq: int
    phase: int
    op: Literal["CAPTURE_AUTH", "VOID_AUTH", "REAUTH_AUTH", "PAYOUT_ITEM", "REFUND_CAPTURE"]
    target_type: Literal["PLEDGE", "CAPTURE", "CONTRACT"]
    target_id: int
    amount_cents: int
    bucket: Literal["POOL", "NONE"]
    receiver_email: str | None = None  # PAYOUT_ITEM only
    idempotency_key: str  # f"{plan_hash[:16]}-{seq}"


class MoneyPlanSpec(BaseModel):
    kind: Literal["CAPTURE_PLEDGES", "RELEASE_HOLDS", "FREELANCER_PAYOUT", "REFUND_CAPTURED", "REAUTH_PLEDGES"]
    project_id: int
    campaign_id: int | None = None
    contract_id: int | None = None
    reason: str | None = None
    inputs: dict
    steps: list[PlanStep]
