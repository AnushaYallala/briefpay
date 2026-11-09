"""Which acceptance criteria need a question, and writing them down (SPEC 7.3 step 2). Flushes only; the caller owns the transaction.

CODE decides which criteria are asked about and what evidence each question expects. The model only chooses the wording; a
criterion it forgets, or the whole list if it is unavailable or invalid, gets a template question. So the pipeline never
stalls and the model can neither skip a criterion nor ask for something the signed BRD did not call for.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm_adapter import AgentError
from app.agents.verifier import QuestionInputs, VerifierAgent
from app.models import AutoCheck, BRD, Contract, Submission, VerificationQuestion

MAX_QUESTIONS = 25
PRIORITY_ORDER = {"MUST": 0, "SHOULD": 1, "COULD": 2}
# what a PASSED automatic check proves, in the BRD's own evidence vocabulary
SATISFIES = {"PAGE_CONTAINS": {"LIVE_URL_CHECK"}, "URL_REACHABLE": {"LIVE_URL_CHECK"}, "MOBILE_VIEWPORT": {"LIVE_URL_CHECK"},
             "FILE_EXISTS": {"REPO_PATH"}}
WORDS = {"SCREENSHOT": "a screenshot", "CODE_SNIPPET": "the code that does it", "REPO_PATH": "the file path in the repository",
         "LIVE_URL_CHECK": "the live page address", "TEXT": "a short written note"}


def passed_hint(criterion: dict, checks: list[AutoCheck], req_code: str) -> tuple[dict | None, str | None]:
    """(the hint, its result) for this criterion, using the check saved for exactly this requirement and criterion."""
    hint = criterion.get("auto_check_hint")
    if not hint:
        return None, None
    for c in checks:
        if c.requirement_code == req_code and (c.input_json or {}).get("criterion_id") == criterion["id"] and c.check_type == hint.get("type"):
            return hint, c.result
    return hint, None


def remaining_evidence(criterion: dict, result: str | None, hint: dict | None) -> list[str]:
    """The evidence a human still has to show. A passed check removes only the evidence types it really proves."""
    needed = list(criterion.get("evidence") or [])
    if hint and result == "PASS":
        needed = [e for e in needed if e not in SATISFIES.get(hint.get("type"), set())]
    return needed


def needed_criteria(brd_content: dict, checks: list[AutoCheck]) -> list[dict]:
    """Every criterion that still needs a human answer, MUST first, in BRD order within a priority, capped. Pure."""
    out = []
    for req in brd_content.get("requirements", []):
        for crit in req.get("acceptance_criteria", []):
            hint, result = passed_hint(crit, checks, req["code"])
            remaining = remaining_evidence(crit, result, hint)
            if hint and result == "PASS" and not remaining:
                continue                                    # settled by the automatic check: nothing to ask
            out.append({"requirement_code": req["code"], "requirement_title": req["title"], "priority": req["priority"],
                        "criterion_id": crit["id"], "given": crit["given"], "when": crit["when"], "then": crit["then"],
                        "evidence_needed": remaining or list(crit.get("evidence") or ["TEXT"]),
                        "auto_check": None if not hint else {"type": hint.get("type"), "result": result or "NOT_RUN"}})
    out.sort(key=lambda c: PRIORITY_ORDER.get(c["priority"], 3))      # stable: BRD order is kept inside a priority
    return out[:MAX_QUESTIONS]


def template_question(c: dict) -> str:
    asks = ", ".join(WORDS.get(e, e.lower()) for e in c["evidence_needed"])
    text = f"{c['requirement_code']} / {c['criterion_id']}: {c['requirement_title']}. Given {c['given']}, when {c['when']}, then {c['then']}. Please give: {asks}."
    return text if len(text) <= 300 else text[:297].rstrip() + "..."


def generate(db: Session, submission_id: int, agent: VerifierAgent) -> dict:
    """The VERIFY_QUESTIONS job. Safe to retry: a submission that already has questions, or has moved on, is left alone."""
    sub = db.get(Submission, submission_id)
    if sub is None:
        return {"effect": "SKIPPED", "why": "unknown submission"}
    if sub.state != "QUESTIONING" or db.scalars(select(VerificationQuestion.id).where(VerificationQuestion.submission_id == sub.id)).first():
        return {"effect": "ALREADY_DONE", "state": sub.state}
    contract = db.get(Contract, sub.contract_id)
    brd = db.get(BRD, contract.brd_id)
    checks = list(db.scalars(select(AutoCheck).where(AutoCheck.submission_id == sub.id).order_by(AutoCheck.id)))
    criteria = needed_criteria(brd.content_json, checks)
    if not criteria:                                        # everything was proven by the automatic checks
        sub.state = "EVIDENCE_RECEIVED"
        db.flush()
        return {"effect": "NO_QUESTIONS", "questions": 0}

    wording: dict[tuple[str, str], str] = {}
    source, run_id, note = "TEMPLATE", None, None
    try:
        out, run_id = agent.ask(QuestionInputs(criteria=criteria, notes=sub.notes,
                                               known_checks=[{"check_type": c.check_type, "requirement_code": c.requirement_code, "result": c.result}
                                                             for c in checks]), contract.project_id)
        wanted = {(c["requirement_code"], c["criterion_id"]) for c in criteria}
        for q in out.questions:
            key = (q.requirement_code, q.criterion_id)
            if key in wanted and key not in wording:        # unknown or repeated criteria from the model are dropped
                wording[key] = q.question
        source = "AI" if len(wording) == len(wanted) else "AI+TEMPLATE" if wording else "TEMPLATE"
    except AgentError as e:                                 # unavailable, over quota or invalid twice: the pipeline still goes on
        run_id = getattr(e, "run_id", None)
        note = str(e)[:200]

    for c in criteria:
        text = wording.get((c["requirement_code"], c["criterion_id"])) or template_question(c)
        db.add(VerificationQuestion(submission_id=sub.id, requirement_code=c["requirement_code"], criterion_id=c["criterion_id"],
                                    question=text, expected_evidence_json=c["evidence_needed"], round=1, status="OPEN"))
    db.flush()
    return {"effect": "ASKED", "questions": len(criteria), "source": source, "agent_run_id": run_id, **({"ai_error": note} if note else {})}
