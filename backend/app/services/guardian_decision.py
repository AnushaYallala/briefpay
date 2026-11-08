"""Combine deterministic rules with the LLM review. The LLM can only RAISE the decision (SPEC 7.5.4)."""
from app.agents.guardian_llm import GuardianLLMOutput

ORDER = {"ALLOW": 0, "HOLD": 1, "BLOCK": 2}


def combine(rules_decision: str, llm: GuardianLLMOutput | None, llm_error: str | None, llm_expected: bool) -> tuple[str, dict | None]:
    """Return (final decision, llm_review_json). final >= rules_decision always.

    - hard-rule BLOCK is final; the LLM is not consulted and cannot soften it
    - an LLM error / schema failure when a review was expected => HOLD (GUARDIAN_LLM_UNAVAILABLE)
    - LLM risk_level "high" => HOLD
    """
    if rules_decision == "BLOCK":
        return "BLOCK", ({"status": "SKIPPED", "reason": "blocked by a hard rule"} if llm_expected else None)
    if not llm_expected:
        return rules_decision, None
    if llm_error is not None or llm is None:
        record = {"status": "UNAVAILABLE", "risk_level": None, "explanation_for_sponsors":
                  "The AI risk review could not run, so a human must look at this plan before money moves.",
                  "findings": [{"type": "GUARDIAN_LLM_UNAVAILABLE", "detail": (llm_error or "no result")[:300], "severity": "high"}]}
        floor = "HOLD"
    else:
        record = {"status": "OK", "risk_level": llm.risk_level, "explanation_for_sponsors": llm.explanation_for_sponsors,
                  "findings": [f.model_dump() for f in llm.findings]}
        floor = "HOLD" if llm.risk_level == "high" else "ALLOW"
    final = max(rules_decision, floor, key=ORDER.__getitem__)
    return final, record
