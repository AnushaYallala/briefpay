"""Deterministic aggregation of verification verdicts (SPEC 7.3). Pure: no database, no AI, no network.

The model's verdicts are only INPUT. This module decides, with fixed rules, what each criterion finally is and whether the
work is VERIFIED. Fail-safe throughout: anything missing, uncited, low-confidence or contradicted can only make a result
worse, never better.
"""
from dataclasses import dataclass, field

from app.schemas.verify import ACVerdict

CONFIDENCE_FLOOR = 0.7
MAX_ATTEMPTS = 3
GATES = ("COMMIT_EXISTS", "REPO_PUBLIC")


@dataclass
class AcResult:
    requirement_code: str
    criterion_id: str
    verdict: str                      # pass | fail | unclear
    source: str                       # AUTO_CHECK | AI | CODE
    confidence: float | None = None
    rationale: str = ""
    evidence_ids: list[int] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"requirement_code": self.requirement_code, "criterion_id": self.criterion_id, "verdict": self.verdict,
                "source": self.source, "confidence": self.confidence, "rationale": self.rationale,
                "evidence_ids": self.evidence_ids, "flags": self.flags}


@dataclass
class Aggregation:
    overall: str                      # VERIFIED | NEEDS_CHANGES | FAILED | NEEDS_FOLLOWUP | INCONCLUSIVE
    must_pass_pct: int
    should_pass_pct: int
    criteria: list[AcResult]
    requirements: list[dict]
    gates: dict
    injection_attempts: list[str]
    followup: list[tuple[str, str]]   # criteria to ask about once more (only when overall == NEEDS_FOLLOWUP)
    reasons: list[str]


def _pct(reqs: list[dict]) -> int:
    total = sum(r["weight"] for r in reqs)
    return 100 if total == 0 else sum(r["weight"] for r in reqs if r["passed"]) * 100 // total


def _own_check(checks: list[dict], req: str, crit: str, hint_type: str | None) -> str | None:
    for c in checks:
        if c["requirement_code"] == req and c.get("criterion_id") == crit and c["check_type"] == hint_type:
            return c["result"]
    return None


def _gate(checks: list[dict], name: str) -> str:
    results = [c["result"] for c in checks if c["check_type"] == name and not c.get("requirement_code")]
    if not results:
        return "NOT_RUN"
    return "FAIL" if "FAIL" in results else "ERROR" if "ERROR" in results else "PASS"


def judge_criterion(req_code: str, crit: dict, own_result: str | None, verdict: ACVerdict | None, valid_evidence: set[int] | None,
                    snippet_flagged: bool) -> AcResult:
    """The final verdict for one criterion. `valid_evidence` is None when no question was asked (an automatic check settled it)."""
    cid = crit["id"]
    if valid_evidence is None:                                  # settled by its automatic check, no human evidence needed
        if own_result == "PASS":
            return AcResult(req_code, cid, "pass", "AUTO_CHECK", rationale="Proven by the automatic check.")
        return AcResult(req_code, cid, "unclear", "CODE", rationale="Not asked and not proven.", flags=["NOT_SETTLED"])
    if verdict is None:
        return AcResult(req_code, cid, "unclear", "CODE", rationale="The reviewer gave no verdict for this criterion.", flags=["NO_VERDICT"])

    cited = [i for i in verdict.evidence_ids if i in valid_evidence]
    res = AcResult(req_code, cid, verdict.verdict, "AI", verdict.confidence, verdict.rationale.strip(), cited)
    if own_result == "FAIL":                                   # a failed automatic check overrides the model, whatever it says
        res.verdict, res.source = "fail", "CODE"
        res.flags.append("AUTO_CHECK_FAILED")
    if verdict.contradicts_auto_check:
        res.verdict, res.source = "fail", "CODE"
        res.flags.append("EVIDENCE_CONTRADICTS_LIVE_SITE")
    if res.verdict == "pass":                                  # a pass has to survive every doubt, each can only lower it
        if own_result == "ERROR":
            res.verdict = "unclear"
            res.flags.append("AUTO_CHECK_COULD_NOT_RUN")
        if snippet_flagged:
            res.verdict = "unclear"
            res.flags.append("SNIPPET_NOT_IN_REPO")
        if verdict.confidence < CONFIDENCE_FLOOR:
            res.verdict = "unclear"
            res.flags.append("LOW_CONFIDENCE")
        if not cited:
            res.verdict = "unclear"
            res.flags.append("NO_EVIDENCE_CITED")
    return res


def aggregate(requirements: list[dict], checks: list[dict], verdicts: list[ACVerdict], asked: dict[tuple[str, str], set[int]],
              snippet_flags: set[tuple[str, str]], *, attempt_no: int, followup_done: bool, max_attempts: int = MAX_ATTEMPTS) -> Aggregation:
    by_key: dict[tuple[str, str], ACVerdict] = {}
    for v in verdicts:
        by_key.setdefault((v.requirement_code, v.criterion_id), v)         # the first verdict for a criterion counts; extras are ignored

    results: list[AcResult] = []
    req_rows: list[dict] = []
    for req in requirements:
        crit_results = []
        for crit in req.get("acceptance_criteria", []):
            key = (req["code"], crit["id"])
            hint = crit.get("auto_check_hint") or {}
            own = _own_check(checks, req["code"], crit["id"], hint.get("type")) if hint else None
            crit_results.append(judge_criterion(req["code"], crit, own, by_key.get(key), asked.get(key), key in snippet_flags))
        results.extend(crit_results)
        if not crit_results:                                   # a requirement with no criteria proves nothing
            status = "unclear"
        elif all(r.verdict == "pass" for r in crit_results):
            status = "pass"
        elif any(r.verdict == "fail" for r in crit_results):
            status = "fail"
        else:
            status = "unclear"
        req_rows.append({"code": req["code"], "priority": req["priority"], "weight": int(req.get("weight") or 1), "status": status,
                         "passed": status == "pass", "criteria": len(crit_results)})

    injection = sorted({a.strip() for v in verdicts for a in v.injection_attempts if a and a.strip()})
    musts = [r for r in req_rows if r["priority"] == "MUST"]
    gates = {name: _gate(checks, name) for name in GATES}
    reasons: list[str] = []
    must_ok = bool(musts) and all(r["passed"] for r in musts)
    if not musts:
        reasons.append("NO_MUST_REQUIREMENTS")
    if injection:
        reasons.append("INJECTION_ATTEMPT")
    gate_fail = [g for g, r in gates.items() if r == "FAIL"]
    gate_error = [g for g, r in gates.items() if r in ("ERROR", "NOT_RUN")]       # never ran = we could not look, not the freelancer's fault
    reasons += [f"GATE_{g}_FAILED" for g in gate_fail] + [f"GATE_{g}_COULD_NOT_BE_CHECKED" for g in gate_error]

    followup: list[tuple[str, str]] = []
    if must_ok and not injection and not gate_fail and not gate_error:
        overall = "VERIFIED"
    elif must_ok and not injection and not gate_fail:
        overall = "INCONCLUSIVE"                               # all good, but GitHub could not be asked: do not blame the freelancer
    else:
        must_codes = {r["code"] for r in musts}
        any_must_fail = any(r["status"] == "fail" for r in musts)
        unclear = [(r.requirement_code, r.criterion_id) for r in results if r.requirement_code in must_codes and r.verdict == "unclear"]
        if any_must_fail:
            reasons.append("MUST_REQUIREMENT_FAILED")
        if unclear and not any_must_fail and not injection and not gate_fail and not followup_done and musts:
            overall, followup = "NEEDS_FOLLOWUP", unclear      # nothing is wrong that we know of: one more round of evidence
            reasons.append("UNCLEAR_CRITERIA")
        else:
            if unclear and not any_must_fail:
                reasons.append("STILL_UNCLEAR_AFTER_FOLLOWUP")
            overall = "FAILED" if attempt_no >= max_attempts else "NEEDS_CHANGES"

    return Aggregation(overall, _pct(musts), _pct([r for r in req_rows if r["priority"] == "SHOULD"]), results, req_rows, gates,
                       injection, followup, reasons)
