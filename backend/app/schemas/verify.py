"""Verification Agent schemas (SPEC 7.3). A contract: change SPEC + DECISIONS together."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class VerifyQuestion(BaseModel):
    requirement_code: str = Field(max_length=16)
    criterion_id: str = Field(max_length=32)
    question: str = Field(min_length=10, max_length=300)
    expected_evidence: list[str] = Field(default=[], max_length=5)   # the model may fill it; code replaces it with the BRD's own list

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 10:
            raise ValueError("a question needs real words")
        return v


class VerifyQuestionsOutput(BaseModel):
    questions: list[VerifyQuestion] = Field(max_length=40)


class ACVerdict(BaseModel):
    requirement_code: str = Field(max_length=16)
    criterion_id: str = Field(max_length=32)
    verdict: Literal["pass", "fail", "unclear"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=300)          # must cite evidence ids
    evidence_ids: list[int] = Field(default=[], max_length=20)
    contradicts_auto_check: bool = False            # e.g. a screenshot shows the form but the live page has none
    injection_attempts: list[str] = Field(default=[], max_length=10)


class VerifyJudgeOutput(BaseModel):
    verdicts: list[ACVerdict] = Field(max_length=60)
    summary_for_sponsors: str = Field(max_length=600)   # plain language
