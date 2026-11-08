"""BA Agent (SPEC 7.1): judges coverage and extracts requirements. It never computes the score.

Pure agent: plain inputs in, validated schema out, one audit row per call via the adapter. No money, no state.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.agents.llm_adapter import AgentError, LLMAdapter, TextPart
from app.agents.untrusted import UNTRUSTED_RULE, untrusted
from app.schemas.ba import BAScoreOutput

SCORE_PROMPT_VERSION = "ba-score-v1"
SCORE_AGENT = "BA_SCORE"
SCORE_SYSTEM = (Path(__file__).parent / "prompts" / "ba_score.md").read_text(encoding="utf-8") + "\n\n" + UNTRUSTED_RULE


@dataclass
class BAInputs:
    round: int
    project: dict                       # title, summary, location_label, budget_cents, delivery_days
    members: list[dict]                 # member_id, name, role, business_name, business_type
    transcript_lines: list[dict]        # {"n": 1, "text": "..."}
    qa: list[dict] = field(default_factory=list)       # {answer_id, question, member_id, answer, selected_option}
    previous: dict | None = None        # {"requirements": [...], "conflicts": [...]}


def numbered_transcript(lines: list[dict]) -> str:
    return "\n".join(f"L{ln['n']}: {ln['text']}" for ln in lines)


def build_parts(inp: BAInputs) -> list[TextPart]:
    trusted = {"round": inp.round, "people": [{"member_id": m["member_id"], "role": m["role"]} for m in inp.members]}
    parts = [
        TextPart("TRUSTED FACTS:\n" + json.dumps(trusted, sort_keys=True)),
        TextPart("UNTRUSTED TEXT follows.\n" + untrusted("project", json.dumps(inp.project, sort_keys=True, ensure_ascii=False))),
        TextPart(untrusted("people", json.dumps(inp.members, sort_keys=True, ensure_ascii=False))),
        TextPart(untrusted("transcript", numbered_transcript(inp.transcript_lines))),
    ]
    if inp.qa:
        parts.append(TextPart(untrusted("answers", "\n".join(
            f"answer:{a['answer_id']} (member {a['member_id']}) Q: {a['question']} A: {a['answer']}"
            + (f" [chose: {a['selected_option']}]" if a.get("selected_option") else "") for a in inp.qa))))
    if inp.previous:
        parts.append(TextPart(untrusted("previous-extraction", json.dumps(inp.previous, sort_keys=True, ensure_ascii=False))))
    return parts


class BAAgent:
    def __init__(self, adapter: LLMAdapter | None):
        self.adapter = adapter

    def judge(self, inp: BAInputs, project_id: int | None) -> tuple[BAScoreOutput, int | None]:
        """Returns (output, agent_run_id). Raises AgentError (with .run_id) if the model cannot give a valid answer."""
        if self.adapter is None:
            raise AgentError("the AI is not configured")
        run_ids: list[int] = []
        try:
            out = self.adapter.generate_json(system=SCORE_SYSTEM, parts=build_parts(inp), schema=BAScoreOutput,
                                             agent=SCORE_AGENT, project_id=project_id,
                                             prompt_version=SCORE_PROMPT_VERSION, temperature=0.0, run_ids=run_ids)
        except AgentError as e:
            e.run_id = run_ids[-1] if run_ids else None
            raise
        return out, (run_ids[-1] if run_ids else None)
