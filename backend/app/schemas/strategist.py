"""Strategist wording schemas (SPEC 7.4). A contract: change SPEC + DECISIONS together."""
from typing import Literal

from pydantic import BaseModel, Field


class NudgeDraft(BaseModel):
    member_id: int
    channel: Literal["WHATSAPP", "EMAIL", "SMS"] = "WHATSAPP"
    message: str = Field(min_length=5, max_length=280)       # friendly, no pressure tactics; the link is added by code


class StrategistOutput(BaseModel):
    headline: str = Field(min_length=3, max_length=120)
    explanation: str = Field(min_length=3, max_length=400)    # plain language
    risk_factors: list[str] = Field(default=[], max_length=4)
    nudges: list[NudgeDraft] = Field(default=[], max_length=20)  # only for member_ids in facts.targets
