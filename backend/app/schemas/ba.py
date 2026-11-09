"""BA Agent schemas (SPEC 7.1). A contract: change SPEC + DECISIONS together.

Two deliberate tightenings of the spec's shapes, same JSON on the wire (D-027):
`coverage` is a float snapped to {0, .25, .5, .75, 1} by a validator (Gemini handles that better than a numeric
Literal), and `Conflict.positions` is a typed list instead of `list[dict]`.
"""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DIMENSIONS = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10"]
COVERAGE_LEVELS = (0.0, 0.25, 0.5, 0.75, 1.0)
REF_PATTERN = re.compile(r"^(L\d+(-L\d+)?|answer:\d+)$")


class DimensionScore(BaseModel):
    dimension: Literal["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10"]
    coverage: float
    justification: str = Field(max_length=200)
    source_refs: list[str] = []

    @field_validator("coverage")
    @classmethod
    def snap(cls, v: float) -> float:
        if v not in COVERAGE_LEVELS:
            raise ValueError(f"coverage must be one of {COVERAGE_LEVELS}, got {v}")
        return float(v)


class ExtractedRequirement(BaseModel):
    temp_id: str
    title: str
    description: str
    priority: Literal["MUST", "SHOULD", "COULD"]
    requested_by: list[int] = []  # member_ids
    acceptance_criteria: list[str] = []  # Given/When/Then; may be empty in early rounds
    source_refs: list[str] = []


class Position(BaseModel):
    member_id: int
    position: str


class Conflict(BaseModel):
    topic: str
    positions: list[Position] = []
    resolved: bool
    resolution: str | None = None


class BAScoreOutput(BaseModel):
    dimensions: list[DimensionScore]  # exactly 10, one per dimension
    requirements: list[ExtractedRequirement]
    conflicts: list[Conflict]
    out_of_scope: list[str]
    budget_stated: bool
    deadline_stated: bool
    injection_attempts: list[str] = []

    @model_validator(mode="after")
    def exactly_ten_dimensions(self):
        got = sorted(d.dimension for d in self.dimensions)
        if got != sorted(DIMENSIONS):
            raise ValueError(f"dimensions must contain each of D1..D10 exactly once, got {sorted(got)}")
        ids = [r.temp_id for r in self.requirements]
        if len(set(ids)) != len(ids):
            raise ValueError("requirement temp_id values must be unique")
        return self


class BAQuestion(BaseModel):
    dimension: Literal["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10"]
    question: str = Field(min_length=5, max_length=300)
    rationale: str = Field(max_length=300)
    addressed_to: list[int | Literal["ALL"]]
    suggested_options: list[str] | None = None

    @field_validator("question")
    @classmethod
    def plain_and_short(cls, v: str) -> str:
        if len(v.split()) > 30:
            raise ValueError("a question must be at most 30 words")
        return v.strip()

    @field_validator("suggested_options")
    @classmethod
    def two_to_four_options(cls, v: list[str] | None) -> list[str] | None:
        if v is None or v == []:
            return None
        v = [o.strip() for o in v if o and o.strip()]
        if not 2 <= len(v) <= 4 or any(len(o) > 80 for o in v):
            raise ValueError("suggested_options must be 2 to 4 short options")
        return v


class BAQuestionsOutput(BaseModel):
    questions: list[BAQuestion] = Field(min_length=1, max_length=5)
