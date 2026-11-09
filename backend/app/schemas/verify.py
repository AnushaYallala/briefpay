"""Verification Agent schemas (SPEC 7.3). A contract: change SPEC + DECISIONS together."""
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
