"""Strategist wording agent (SPEC 7.4): puts numbers that CODE computed into words and drafts nudges. Advisory only.

It never sees or decides money: the facts it is given are already final, and every number in its answer is checked against them
by `services/strategist_words.py` before anything is stored.
"""
import json
from pathlib import Path

from app.agents.llm_adapter import AgentError, LLMAdapter, TextPart
from app.agents.untrusted import UNTRUSTED_RULE, untrusted
from app.schemas.strategist import StrategistOutput

PROMPT_VERSION = "strategist-v1"
AGENT = "STRATEGIST"
SYSTEM = (Path(__file__).parent / "prompts" / "strategist.md").read_text(encoding="utf-8") + "\n\n" + UNTRUSTED_RULE


def build_parts(facts: dict, project_title: str) -> list[TextPart]:
    trusted = {**facts, "targets": [{"member_id": t["member_id"], "expected_formatted": t["expected_formatted"], "viewed": t["viewed"]} for t in facts["targets"]]}
    names = [{"member_id": t["member_id"], "name": t["name"]} for t in facts["targets"]]
    return [TextPart("TRUSTED FACTS:\n" + json.dumps(trusted, sort_keys=True, ensure_ascii=False)),
            TextPart("UNTRUSTED TEXT follows.\n" + untrusted("project-title", project_title)),
            TextPart(untrusted("people", json.dumps(names, sort_keys=True, ensure_ascii=False)))]


class StrategistAgent:
    def __init__(self, adapter: LLMAdapter | None):
        self.adapter = adapter

    def words(self, facts: dict, project_title: str, project_id: int | None) -> tuple[StrategistOutput, int | None]:
        if self.adapter is None:
            raise AgentError("the AI is not configured")
        run_ids: list[int] = []
        try:
            out = self.adapter.generate_json(system=SYSTEM, parts=build_parts(facts, project_title), schema=StrategistOutput, agent=AGENT,
                                             project_id=project_id, prompt_version=PROMPT_VERSION, temperature=0.4, run_ids=run_ids)
        except AgentError as e:
            e.run_id = run_ids[-1] if run_ids else None
            raise
        return out, (run_ids[-1] if run_ids else None)


_agent: StrategistAgent | None = None


def get_strategist() -> StrategistAgent:
    """Built from settings on first use. Not configured => an agent with no adapter: the code writes the template wording instead."""
    global _agent
    if _agent is None:
        from app.agents.llm_adapter import build_adapter
        from app.config import get_settings
        from app.db import SessionLocal
        try:
            adapter = build_adapter(get_settings(), SessionLocal)
        except AgentError:
            return StrategistAgent(None)         # not cached: configuration may be fixed without a restart
        _agent = StrategistAgent(adapter)
    return _agent


def set_strategist(agent: StrategistAgent | None) -> None:
    global _agent
    _agent = agent
