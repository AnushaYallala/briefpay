"""BRD schemas (SPEC 7.2). A contract: change SPEC + DECISIONS together.

`BRDDraft` is what the model writes (no REQ codes, no AC ids, no constraints, from_temp_ids for traceability).
`BRDContent` is the canonical document that code assembles, renders and hashes.
Typed models replace the spec's loose dicts (same JSON keys) so Gemini's structured output is reliable (D-029).
"""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Priority = Literal["MUST", "SHOULD", "COULD"]
EvidenceType = Literal["SCREENSHOT", "LIVE_URL_CHECK", "CODE_SNIPPET", "REPO_PATH", "TEXT"]
PATH_PATTERN = re.compile(r"^/[a-z0-9/_-]*$")


class AutoCheckHint(BaseModel):
    """A mechanical check the platform can run itself (SPEC 7.3). Only these four kinds can be hinted per criterion."""
    type: Literal["URL_REACHABLE", "PAGE_CONTAINS", "FILE_EXISTS", "MOBILE_VIEWPORT"]
    path: str | None = Field(default=None, max_length=200)
    text: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def complete_for_type(self):
        if self.type in ("URL_REACHABLE", "PAGE_CONTAINS", "FILE_EXISTS") and not self.path:
            raise ValueError(f"{self.type} needs a path")
        if self.type == "PAGE_CONTAINS" and not (self.text or "").strip():
            raise ValueError("PAGE_CONTAINS needs the text to look for")
        if self.type in ("URL_REACHABLE", "PAGE_CONTAINS") and not PATH_PATTERN.match(self.path or ""):
            raise ValueError("a page path must look like /stay or /getting-there")
        return self


class DraftCriterion(BaseModel):
    given: str = Field(min_length=3, max_length=400)
    when: str = Field(min_length=3, max_length=400)
    then: str = Field(min_length=3, max_length=400)
    evidence: list[EvidenceType] = Field(min_length=1, max_length=5)
    auto_check_hint: AutoCheckHint | None = None


class AcceptanceCriterion(DraftCriterion):
    id: str  # "AC-1", unique within the requirement, assigned by code


class DraftRequirement(BaseModel):
    from_temp_ids: list[str] = []  # which analysis requirements (R1, R2 ...) this covers; checked by code
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=800)
    priority: Priority
    weight: int = Field(ge=1, le=5)
    requested_by: list[int] = []
    acceptance_criteria: list[DraftCriterion] = Field(default=[], max_length=8)
    source_refs: list[str] = []


class BRDRequirement(BaseModel):
    code: str  # "REQ-001", assigned by code
    title: str
    description: str
    priority: Priority
    weight: int
    requested_by: list[int]
    acceptance_criteria: list[AcceptanceCriterion]
    source_refs: list[str]


class Stakeholder(BaseModel):
    member_id: int
    business_name: str | None = None
    needs: list[str] = []


class SitemapEntry(BaseModel):
    path: str = Field(max_length=100)
    purpose: str = Field(min_length=3, max_length=300)

    @field_validator("path")
    @classmethod
    def looks_like_a_path(cls, v: str) -> str:
        if not PATH_PATTERN.match(v):
            raise ValueError("a sitemap path must look like / or /stay or /getting-there")
        return v


class ContentResponsibility(BaseModel):
    item: str = Field(min_length=3, max_length=200)
    owner_member_id: int | None = None
    due: str | None = Field(default=None, max_length=60)


class Constraints(BaseModel):
    budget_cents: int
    currency: str
    delivery_days: int | None = None
    hosting: str | None = None
    domain: str | None = None


class GlossaryEntry(BaseModel):
    term: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=3, max_length=300)


class _Body(BaseModel):
    title: str = Field(default="", max_length=200)
    executive_summary: str = Field(min_length=10, max_length=1500)
    business_goals: list[str] = Field(min_length=1, max_length=10)
    success_measures: list[str] = Field(default=[], max_length=10)
    stakeholders: list[Stakeholder] = []
    audience: str = Field(min_length=3, max_length=600)
    sitemap: list[SitemapEntry] = Field(min_length=1, max_length=20)
    non_functional: list[str] = Field(default=[], max_length=15)
    content_responsibilities: list[ContentResponsibility] = Field(default=[], max_length=20)
    out_of_scope: list[str] = Field(default=[], max_length=20)
    open_items: list[str] = Field(default=[], max_length=20)
    glossary: list[GlossaryEntry] = Field(default=[], max_length=20)


class BRDDraft(_Body):
    requirements: list[DraftRequirement] = Field(min_length=1, max_length=30)
    hosting: str | None = Field(default=None, max_length=200)
    domain: str | None = Field(default=None, max_length=200)


class BRDContent(_Body):
    requirements: list[BRDRequirement]
    constraints: Constraints
