"""Guardian LLM risk review (SPEC 7.5.4). ESCALATE-ONLY: it can raise ALLOW to HOLD, never lower anything.

This module is an agent: it receives plain facts, returns a verdict, and imports nothing that moves money.
Facts are split into TRUSTED (computed by code) and UNTRUSTED (names and evidence text written by users).
"""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.llm_adapter import AgentError, LLMAdapter, TextPart
from app.agents.untrusted import UNTRUSTED_RULE, untrusted

PROMPT_VERSION = "guardian-llm-v1"
AGENT = "GUARDIAN_LLM"
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "guardian_llm.md").read_text(encoding="utf-8") + "\n\n" + UNTRUSTED_RULE

FindingType = Literal["SHILL_PLEDGING_SUSPECTED", "LAST_MINUTE_SURGE", "SELF_DEALING_SUSPECTED", "WEAK_EVIDENCE",
                      "VERDICT_EVIDENCE_MISMATCH", "INJECTION_SUSPECTED", "SCOPE_MISMATCH", "UNUSUAL_AMOUNT", "OTHER"]


class Finding(BaseModel):
    type: FindingType
    detail: str = Field(max_length=300)
    severity: Literal["low", "medium", "high"]


class GuardianLLMOutput(BaseModel):
    risk_level: Literal["low", "medium", "high"]
    findings: list[Finding] = Field(max_length=8)
    explanation_for_sponsors: str = Field(max_length=500)


class GuardianLLM:
    """Wraps an LLMAdapter. With no adapter every call raises AgentError, which the caller turns into a HOLD."""

    def __init__(self, adapter: LLMAdapter | None):
        self.adapter = adapter

    def review(self, facts: dict, project_id: int | None) -> tuple[GuardianLLMOutput, int | None]:
        """facts = {"trusted": {...}, "untrusted": {"names": {label: display_name}, "verification_summary": str}}"""
        if self.adapter is None:
            raise AgentError("the AI risk review is not configured")
        parts = [
            TextPart("TRUSTED FACTS (computed by code):\n" + json.dumps(facts["trusted"], sort_keys=True, indent=1)),
            TextPart("UNTRUSTED TEXT (written by users):\n" + untrusted("display-names", json.dumps(
                facts["untrusted"].get("names", {}), sort_keys=True, ensure_ascii=False))),
        ]
        if facts["untrusted"].get("verification_summary"):
            parts.append(TextPart(untrusted("verification-summary", facts["untrusted"]["verification_summary"])))
        run_ids: list[int] = []
        try:
            out = self.adapter.generate_json(system=SYSTEM_PROMPT, parts=parts, schema=GuardianLLMOutput, agent=AGENT,
                                             project_id=project_id, prompt_version=PROMPT_VERSION, temperature=0.0,
                                             run_ids=run_ids)
        except AgentError as e:
            e.run_id = run_ids[-1] if run_ids else None  # a failed call still has an audit row; keep the link
            raise
        return out, (run_ids[-1] if run_ids else None)


_default: GuardianLLM | None = None


def get_guardian_llm() -> GuardianLLM:
    """Built from settings on first use. If AI is not configured the review raises and the plan is HELD (fail safe)."""
    global _default
    if _default is None:
        from app.agents.llm_adapter import build_adapter
        from app.config import get_settings
        from app.db import SessionLocal
        try:
            _default = GuardianLLM(build_adapter(get_settings(), SessionLocal))
        except AgentError:
            return GuardianLLM(None)  # do not cache: configuration may be fixed without a restart
    return _default


def set_guardian_llm(llm: GuardianLLM | None) -> None:
    """Install a specific instance (startup wiring and tests)."""
    global _default
    _default = llm
