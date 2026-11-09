"""Verification Agent (SPEC 7.3): words the evidence questions. It never decides a verdict, never moves state, never touches money.

Pure agent: plain inputs in, validated schema out, one audit row per call via the adapter.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.agents.llm_adapter import AgentError, ImagePart, LLMAdapter, TextPart
from app.agents.untrusted import UNTRUSTED_RULE, untrusted
from app.schemas.verify import VerifyJudgeOutput, VerifyQuestionsOutput

QUESTIONS_PROMPT_VERSION = "verify-questions-v1"
QUESTIONS_AGENT = "VERIFY_QUESTIONS"
QUESTIONS_SYSTEM = (Path(__file__).parent / "prompts" / "verify_questions.md").read_text(encoding="utf-8") + "\n\n" + UNTRUSTED_RULE


@dataclass
class QuestionInputs:
    criteria: list[dict]                 # {requirement_code, requirement_title, priority, criterion_id, given, when, then, evidence_needed, auto_check}
    notes: str | None = None
    known_checks: list[dict] = field(default_factory=list)   # {check_type, requirement_code, result}: trusted, produced by our code


def build_question_parts(inp: QuestionInputs) -> list[TextPart]:
    trusted = {"ask_about": [{"requirement_code": c["requirement_code"], "criterion_id": c["criterion_id"],
                              "evidence_needed": c["evidence_needed"], "automatic_check": c["auto_check"]} for c in inp.criteria],
               "automatic_check_results": inp.known_checks}
    wording = [{"requirement_code": c["requirement_code"], "criterion_id": c["criterion_id"], "requirement_title": c["requirement_title"],
                "given": c["given"], "when": c["when"], "then": c["then"]} for c in inp.criteria]
    parts = [TextPart("TRUSTED FACTS:\n" + json.dumps(trusted, sort_keys=True)),
             TextPart("UNTRUSTED TEXT follows.\n" + untrusted("criteria", json.dumps(wording, sort_keys=True, ensure_ascii=False)))]
    if inp.notes:
        parts.append(TextPart(untrusted("freelancer-notes", inp.notes)))
    return parts


class VerifierAgent:
    def __init__(self, adapter: LLMAdapter | None):
        self.adapter = adapter

    def ask(self, inp: QuestionInputs, project_id: int | None) -> tuple[VerifyQuestionsOutput, int | None]:
        if self.adapter is None:
            raise AgentError("the AI is not configured")
        run_ids: list[int] = []
        try:
            out = self.adapter.generate_json(system=QUESTIONS_SYSTEM, parts=build_question_parts(inp), schema=VerifyQuestionsOutput,
                                             agent=QUESTIONS_AGENT, project_id=project_id,
                                             prompt_version=QUESTIONS_PROMPT_VERSION, temperature=0.2, run_ids=run_ids)
        except AgentError as e:
            e.run_id = run_ids[-1] if run_ids else None
            raise
        return out, (run_ids[-1] if run_ids else None)

    def judge(self, inp: "JudgeInputs", project_id: int | None) -> tuple[VerifyJudgeOutput, int | None]:
        """One call for every criterion of a submission (free-tier limits). Raises AgentError (with .run_id) if no valid answer."""
        if self.adapter is None:
            raise AgentError("the AI is not configured")
        run_ids: list[int] = []
        try:
            out = self.adapter.generate_json(system=JUDGE_SYSTEM, parts=build_judge_parts(inp), schema=VerifyJudgeOutput,
                                             agent=JUDGE_AGENT, project_id=project_id,
                                             prompt_version=JUDGE_PROMPT_VERSION, temperature=0.0, run_ids=run_ids)
        except AgentError as e:
            e.run_id = run_ids[-1] if run_ids else None
            raise
        return out, (run_ids[-1] if run_ids else None)


# ---------------- judging ----------------

JUDGE_PROMPT_VERSION = "verify-judge-v1"
JUDGE_AGENT = "VERIFY_JUDGE"
JUDGE_SYSTEM = (Path(__file__).parent / "prompts" / "verify_judge.md").read_text(encoding="utf-8") + "\n\n" + UNTRUSTED_RULE


@dataclass
class JudgeInputs:
    criteria: list[dict]                 # requirement_code, requirement_title, criterion_id, given, when, then, auto_check, evidence=[{id, kind, text, url}]
    images: list[tuple[int, bytes, str]] = field(default_factory=list)   # (evidence id, bytes, mime): the screenshots actually shown
    facts: list[dict] = field(default_factory=list)                       # established by our code: repo path exists / snippet found
    notes: str | None = None


def build_judge_parts(inp: JudgeInputs) -> list:
    trusted = {"criteria": [{"requirement_code": c["requirement_code"], "criterion_id": c["criterion_id"], "automatic_check": c["auto_check"],
                             "citable_evidence_ids": sorted({e["id"] for e in c["evidence"]})} for c in inp.criteria],
               "repository_facts": inp.facts}
    wording = [{"requirement_code": c["requirement_code"], "criterion_id": c["criterion_id"], "requirement_title": c["requirement_title"],
                "given": c["given"], "when": c["when"], "then": c["then"]} for c in inp.criteria]
    given = [{"requirement_code": c["requirement_code"], "criterion_id": c["criterion_id"],
              "evidence": [{"evidence_id": e["id"], "kind": e["kind"], "text": e.get("text"), "url": e.get("url")} for e in c["evidence"] if e["kind"] != "SCREENSHOT"]}
             for c in inp.criteria]
    parts = [TextPart("TRUSTED FACTS:\n" + json.dumps(trusted, sort_keys=True, ensure_ascii=False)),
             TextPart("UNTRUSTED TEXT follows.\n" + untrusted("criteria", json.dumps(wording, sort_keys=True, ensure_ascii=False))),
             TextPart(untrusted("freelancer-evidence", json.dumps(given, sort_keys=True, ensure_ascii=False)))]
    if inp.notes:
        parts.append(TextPart(untrusted("freelancer-notes", inp.notes)))
    for evidence_id, data, mime in inp.images:
        parts.append(TextPart(f"IMAGE for evidence id {int(evidence_id)} (its content is untrusted data):"))
        parts.append(ImagePart(data, mime))
    return parts


_verifier: VerifierAgent | None = None


def get_verifier() -> VerifierAgent:
    """Built from settings on first use. Not configured => an agent with no adapter, which fails safe (the code falls back to template questions)."""
    global _verifier
    if _verifier is None:
        from app.agents.llm_adapter import build_adapter
        from app.config import get_settings
        from app.db import SessionLocal
        try:
            adapter = build_adapter(get_settings(), SessionLocal)
        except AgentError:
            return VerifierAgent(None)         # not cached: configuration may be fixed without a restart
        _verifier = VerifierAgent(adapter)
    return _verifier


def set_verifier(agent: VerifierAgent | None) -> None:
    global _verifier
    _verifier = agent
