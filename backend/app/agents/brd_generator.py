"""BRD Generator agent (SPEC 7.2): drafts the BRD content. Code assigns codes, validates, renders and hashes.

Pure agent: plain inputs in, validated schema out, one audit row per call via the adapter. No state, no money.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from app.agents.ba_agent import BAInputs, build_parts
from app.agents.llm_adapter import AgentError, LLMAdapter, TextPart
from app.agents.untrusted import UNTRUSTED_RULE, untrusted
from app.schemas.brd import BRDDraft

PROMPT_VERSION = "brd-gen-v1"
AGENT = "BRD_GEN"
SYSTEM = (Path(__file__).parent / "prompts" / "brd_gen.md").read_text(encoding="utf-8") + "\n\n" + UNTRUSTED_RULE


@dataclass
class BRDInputs:
    base: BAInputs                  # project basics, sponsors, numbered transcript, all Q&A
    requirements: list[dict]        # the analysis requirements (temp_id R1...)
    conflicts: list[dict]           # with their resolutions
    out_of_scope: list[str]


def build_brd_parts(inp: BRDInputs) -> list[TextPart]:
    trusted = {"sponsors": [{"member_id": m["member_id"], "role": m["role"]} for m in inp.base.members],
               "analysis_requirement_ids": [r["temp_id"] for r in inp.requirements]}
    parts = build_parts(inp.base)[1:]  # project, people, transcript, answers (all untrusted blocks)
    parts = [p for p in parts if "previous-extraction" not in p.text]
    parts.insert(0, TextPart("TRUSTED FACTS:\n" + json.dumps(trusted, sort_keys=True)))
    parts.append(TextPart(untrusted("analysis", json.dumps(
        {"requirements": inp.requirements, "conflicts": inp.conflicts, "out_of_scope": inp.out_of_scope},
        sort_keys=True, ensure_ascii=False))))
    return parts


class BRDGenerator:
    def __init__(self, adapter: LLMAdapter | None):
        self.adapter = adapter

    def draft(self, inp: BRDInputs, project_id: int | None) -> tuple[BRDDraft, int | None]:
        if self.adapter is None:
            raise AgentError("the AI is not configured")
        run_ids: list[int] = []
        try:
            out = self.adapter.generate_json(system=SYSTEM, parts=build_brd_parts(inp), schema=BRDDraft, agent=AGENT,
                                             project_id=project_id, prompt_version=PROMPT_VERSION, temperature=0.2,
                                             run_ids=run_ids)
        except AgentError as e:
            e.run_id = run_ids[-1] if run_ids else None
            raise
        return out, (run_ids[-1] if run_ids else None)


_generator: BRDGenerator | None = None


def get_brd_generator() -> BRDGenerator:
    """Built from settings on first use; unconfigured => a generator that fails safe (503, nothing changes)."""
    global _generator
    if _generator is None:
        from app.agents.llm_adapter import build_adapter
        from app.config import get_settings
        from app.db import SessionLocal
        try:
            _generator = BRDGenerator(build_adapter(get_settings(), SessionLocal))
        except AgentError:
            return BRDGenerator(None)
    return _generator


def set_brd_generator(g: BRDGenerator | None) -> None:
    global _generator
    _generator = g
