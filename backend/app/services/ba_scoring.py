"""BA completeness score: the LLM judges coverage, CODE computes the number (SPEC 7.1, D-006). Pure, no DB.

total = round-half-up(sum(weight * coverage)) in exact integer arithmetic (coverage in quarters), so the same
judgements always give the same score. A coverage claim without a valid source reference is downgraded one level.
Any failing hard gate caps the total at 89, so 90 can never be reached while a gate is red.
"""
from dataclasses import dataclass, field

from app.schemas.ba import DIMENSIONS, REF_PATTERN, BAScoreOutput

WEIGHTS: dict[str, int] = {"D1": 12, "D2": 8, "D3": 10, "D4": 12, "D5": 15, "D6": 13, "D7": 8, "D8": 5, "D9": 7, "D10": 10}
assert sum(WEIGHTS.values()) == 100
DIMENSION_NAMES = {
    "D1": "Business goals & success measures", "D2": "Target audience", "D3": "Stakeholder needs",
    "D4": "Scope: pages & sections", "D5": "Functional requirements", "D6": "Acceptance criteria quality",
    "D7": "Content & assets ownership", "D8": "Look & feel", "D9": "Non-functional", "D10": "Constraints & handover",
}
GATE_CAP = 89
GATE_TITLES = {
    "GT-1": "Budget and delivery deadline are stated",
    "GT-2": "Every MUST requirement has an acceptance criterion",
    "GT-3": "No unresolved conflict between sponsors",
    "GT-4": "Out-of-scope list has at least one item",
    "GT-5": "Every sponsor has a need captured",
}


def to_quarters(coverage: float) -> int:
    q = round(coverage * 4)
    assert q / 4 == coverage and 0 <= q <= 4, f"bad coverage {coverage}"
    return q


def total_from_quarters(quarters: dict[str, int]) -> int:
    """round-half-up of sum(weight * coverage), exactly: (sum(weight * quarters) + 2) // 4."""
    return (sum(WEIGHTS[d] * quarters[d] for d in DIMENSIONS) + 2) // 4


def valid_refs(refs: list[str], line_count: int, answer_ids: set[int]) -> list[str]:
    """Keep references that point at something real: transcript lines in range, or an answer that exists."""
    ok = []
    for r in refs:
        if not REF_PATTERN.match(r):
            continue
        if r.startswith("answer:"):
            if int(r.split(":")[1]) in answer_ids:
                ok.append(r)
            continue
        a, _, b = r[1:].partition("-L")
        lo, hi = int(a), int(b) if b else int(a)
        if 1 <= lo <= hi <= line_count:
            ok.append(r)
    return ok


@dataclass
class DimensionResult:
    dimension: str
    weight: int
    coverage_claimed: float
    coverage_effective: float
    downgraded: bool
    justification: str
    source_refs: list[str]  # only the valid ones


@dataclass
class GateResult:
    id: str
    title: str
    passed: bool
    detail: str


@dataclass
class ScoreResult:
    total: int          # after the gate cap
    total_uncapped: int
    capped: bool
    dimensions: list[DimensionResult]
    gates: list[GateResult]
    requirements: list[dict]
    conflicts: list[dict]
    observations: dict = field(default_factory=dict)

    @property
    def failed_gates(self) -> list[str]:
        return [g.id for g in self.gates if not g.passed]

    @property
    def gaps(self) -> list[tuple[str, float]]:
        """(dimension, weight * (1 - coverage)) largest first: what the question generator should ask about."""
        gaps = [(d.dimension, d.weight * (1 - d.coverage_effective)) for d in self.dimensions if d.coverage_effective < 1]
        return sorted(gaps, key=lambda g: (-g[1], g[0]))


def evaluate_gates(out: BAScoreOutput, *, budget_known: bool, deadline_known: bool, sponsor_member_ids: set[int],
                   known_member_ids: set[int]) -> list[GateResult]:
    must = [r for r in out.requirements if r.priority == "MUST"]
    unfinished = [r.temp_id for r in must if not any(c.strip() for c in r.acceptance_criteria)]
    open_conflicts = [c.topic for c in out.conflicts if not (c.resolved and (c.resolution or "").strip())]
    covered = {m for r in out.requirements for m in r.requested_by if m in known_member_ids}
    missing = sorted(sponsor_member_ids - covered)
    scope = [s for s in out.out_of_scope if s.strip()]
    return [
        GateResult("GT-1", GATE_TITLES["GT-1"], budget_known and deadline_known,
                   "budget and deadline are known" if budget_known and deadline_known else
                   "missing: " + ", ".join(n for n, k in (("budget", budget_known), ("delivery deadline", deadline_known)) if not k)),
        GateResult("GT-2", GATE_TITLES["GT-2"], bool(must) and not unfinished,
                   "no MUST requirement has been captured yet" if not must else
                   (f"MUST without criteria: {', '.join(unfinished)}" if unfinished else f"{len(must)} MUST requirement(s) all testable")),
        GateResult("GT-3", GATE_TITLES["GT-3"], not open_conflicts,
                   f"unresolved: {'; '.join(open_conflicts)}" if open_conflicts else "no open conflicts"),
        GateResult("GT-4", GATE_TITLES["GT-4"], bool(scope), f"{len(scope)} item(s)" if scope else "nothing is marked out of scope"),
        GateResult("GT-5", GATE_TITLES["GT-5"], not missing,
                   f"no need captured yet for member(s) {missing}" if missing else "every sponsor is represented"),
    ]


def score(out: BAScoreOutput, *, line_count: int, answer_ids: set[int], known_member_ids: set[int],
          sponsor_member_ids: set[int], project_has_budget: bool, project_has_deadline: bool) -> ScoreResult:
    dims, quarters = [], {}
    for d in out.dimensions:
        refs = valid_refs(d.source_refs, line_count, answer_ids)
        claimed = to_quarters(d.coverage)
        eff = max(0, claimed - 1) if (claimed > 0 and not refs) else claimed  # no evidence => one level lower
        quarters[d.dimension] = eff
        dims.append(DimensionResult(d.dimension, WEIGHTS[d.dimension], d.coverage, eff / 4, eff != claimed,
                                    d.justification, refs))
    dims.sort(key=lambda r: DIMENSIONS.index(r.dimension))

    uncapped = total_from_quarters(quarters)
    gates = evaluate_gates(out, budget_known=project_has_budget or out.budget_stated,
                           deadline_known=project_has_deadline or out.deadline_stated,
                           sponsor_member_ids=sponsor_member_ids, known_member_ids=known_member_ids)
    capped = any(not g.passed for g in gates) and uncapped > GATE_CAP
    total = GATE_CAP if capped else uncapped

    reqs = []
    for r in out.requirements:
        item = r.model_dump()
        item["requested_by"] = [m for m in r.requested_by if m in known_member_ids]
        item["source_refs"] = valid_refs(r.source_refs, line_count, answer_ids)
        reqs.append(item)
    return ScoreResult(
        total=total, total_uncapped=uncapped, capped=capped, dimensions=dims, gates=gates, requirements=reqs,
        conflicts=[c.model_dump() for c in out.conflicts],
        observations={"out_of_scope": out.out_of_scope, "injection_attempts": out.injection_attempts,
                      "budget_stated": out.budget_stated, "deadline_stated": out.deadline_stated,
                      "project_has_budget": project_has_budget, "project_has_deadline": project_has_deadline})
