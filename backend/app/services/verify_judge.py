"""Judging a submission (SPEC 7.3 steps 3-6). Flushes only; the caller owns the transaction.

  request_judge   the API side: who may ask, in which state, at most 6 times per submission
  judge           the VERIFY_JUDGE job: gather evidence, check pasted code against the repo, ONE model call, then the fixed rules
                  of `verify_aggregate` decide, a report is saved, and the submission and project move on

The model only proposes verdicts. What the project becomes (payout ready, back to work, waiting for the lead) is decided by code.
"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm_adapter import AgentError, canonical_json
from app.agents.verifier import JudgeInputs, VerifierAgent
from app.models import AutoCheck, BRD, Contract, Evidence, Image, Job, ProjectMember, Project, Submission, VerificationQuestion, VerificationReport
from app.schemas.verify import ACVerdict
from app.services import image_meta, image_store, jobs
from app.services.autochecks import AutoChecker, snippet_in_file
from app.services.image_store import ImageStoreUnavailable
from app.services.state_machines import ProjectService
from app.services.verify_aggregate import GATES, aggregate

MAX_JUDGE_RUNS = 6
MAX_IMAGES_SHOWN = 20
JUDGEABLE = ("EVIDENCE_RECEIVED", "JUDGING")
FOLLOWUP_ROUND = 2


class JudgeError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _now() -> datetime:
    return datetime.now(timezone.utc)


# =============================== asking for a judgement ===============================

def judge_runs(db: Session, submission_id: int) -> int:
    return sum(1 for j in db.scalars(select(Job).where(Job.type == "VERIFY_JUDGE")) if (j.payload_json or {}).get("submission_id") == submission_id)


def request_judge(db: Session, sub: Submission, member: ProjectMember) -> Job:
    contract = db.get(Contract, sub.contract_id)
    if member.role != "LEAD" and not (member.role == "FREELANCER" and contract.freelancer_member_id == member.id):
        raise JudgeError("FORBIDDEN", "Only the freelancer of this contract or the lead can ask for judging", 403)
    if sub.state != "EVIDENCE_RECEIVED":
        raise JudgeError("SUBMISSION_STATE", f"Judging starts once every question has an answer (this submission is {sub.state})")
    if db.scalars(select(VerificationQuestion.id).where(VerificationQuestion.submission_id == sub.id, VerificationQuestion.status == "OPEN")).first():
        raise JudgeError("QUESTIONS_OPEN", "Some questions still have no answer")
    if judge_runs(db, sub.id) >= MAX_JUDGE_RUNS:
        raise JudgeError("JUDGE_LIMIT", f"This submission has already been judged {MAX_JUDGE_RUNS} times", 429)
    sub.state = "JUDGING"
    return jobs.enqueue(db, "VERIFY_JUDGE", {"submission_id": sub.id})


# =============================== gathering what the judge sees ===============================

def check_dicts(checks: list[AutoCheck]) -> list[dict]:
    return [{"check_type": c.check_type, "requirement_code": c.requirement_code, "criterion_id": (c.input_json or {}).get("criterion_id"), "result": c.result}
            for c in checks]


def refresh_gates(checker: AutoChecker, sub: Submission, checks: list[AutoCheck]) -> None:
    """GitHub may have been busy when the checks ran: try a gate that ERRORed once more, now, so nobody is blamed for a timeout."""
    for c in checks:
        if c.check_type in GATES and not c.requirement_code and c.result == "ERROR":
            r = checker.repo_public(sub.repo_url) if c.check_type == "REPO_PUBLIC" else checker.commit_exists(sub.repo_url, sub.commit_sha)
            if r.result != "ERROR":
                c.result, c.detail_json = r.result, r.detail


def snippet_facts(sub: Submission, evidence: list[Evidence], questions: dict[int, VerificationQuestion], checker: AutoChecker):
    """SPEC 7.3 step 3: a snippet that cites a repo path must be in that file. -> (flagged criteria, facts for the judge)."""
    by_question: dict[int, list[Evidence]] = {}
    for e in evidence:
        if e.question_id in questions:
            by_question.setdefault(e.question_id, []).append(e)
    flagged: set[tuple[str, str]] = set()
    facts: list[dict] = []
    for qid, items in by_question.items():
        q = questions[qid]
        paths = [e for e in items if e.kind == "REPO_PATH"]
        snippets = [e for e in items if e.kind == "CODE_SNIPPET"]
        texts: list[str] = []
        for p in paths:
            result, text = checker.file_at_commit(sub.repo_url, sub.commit_sha, p.text or "", q.requirement_code)
            state = {"PASS": "exists", "FAIL": "does_not_exist", "ERROR": "could_not_check"}[result.result]
            facts.append({"evidence_id": p.id, "fact": f"repository path {state} at the submitted commit"})
            if text is not None:
                texts.append(text)
        if texts:
            for s in snippets:
                found = any(snippet_in_file(s.text or "", t) for t in texts)
                facts.append({"evidence_id": s.id, "fact": "pasted code " + ("is in the repository file" if found else "is NOT in the repository file")})
                if not found:
                    flagged.add((q.requirement_code, q.criterion_id))
    return flagged, facts


def load_images(db: Session, evidence: list[Evidence]) -> tuple[list[tuple[int, bytes, str]], set[int], list[dict]]:
    """Screenshots as bytes, read through the image store. Returns (images shown, evidence ids shown, facts about unusable images)."""
    store = image_store.get_image_store()
    shown, ids, facts = [], set(), []
    for e in evidence:
        if e.kind != "SCREENSHOT" or e.image_id is None:
            continue
        if len(shown) >= MAX_IMAGES_SHOWN:
            facts.append({"evidence_id": e.id, "fact": "screenshot not shown to the reviewer (limit reached)"})
            continue
        img = db.get(Image, e.image_id)
        data = store.read_bytes(img.public_id, img.format) if store.provider == "CLOUDINARY" else store.read_bytes(img.public_id)
        if data is None or (img.sha256 and hashlib.sha256(data).hexdigest() != img.sha256):
            facts.append({"evidence_id": e.id, "fact": "screenshot missing or changed since upload; not shown"})
            continue
        info = image_meta.sniff(data)
        if info is None:
            facts.append({"evidence_id": e.id, "fact": "screenshot is not a readable image; not shown"})
            continue
        shown.append((e.id, data, info.mime))
        ids.add(e.id)
    return shown, ids, facts


def followup_text(code: str, criterion: str, rationale: str) -> str:
    why = " ".join((rationale or "").split())[:140]
    # at most 16 + 32 characters of ids and 140 of the reviewer's words, so this always fits the 300-character question column rule
    return f"{code} / {criterion}: The reviewer could not be sure ({why or 'the evidence was not clear enough'}). Please add clearer evidence for this criterion."


def report_sha(payload: dict, overall: str, must_pct: int, should_pct: int, summary: str) -> str:
    return hashlib.sha256(canonical_json({"verdicts": payload, "overall": overall, "must": must_pct, "should": should_pct, "summary": summary}).encode()).hexdigest()


def plain_summary(agg, attempt_no: int) -> str:
    """The report's words come from the rules, not from the model, so they can never claim more than the verdict."""
    musts = [r for r in agg.requirements if r["priority"] == "MUST"]
    head = {"VERIFIED": "Verified: every MUST requirement is met.", "NEEDS_CHANGES": "Needs changes: not every MUST requirement is met.",
            "FAILED": f"Failed: attempt {attempt_no} did not meet every MUST requirement; the lead decides what happens next."}[agg.overall]
    lines = [head, f"MUST requirements met: {sum(1 for r in musts if r['passed'])} of {len(musts)} ({agg.must_pass_pct}% by weight). SHOULD: {agg.should_pass_pct}%."]
    problems = [f"{r.requirement_code}/{r.criterion_id} {r.verdict}" + (f" ({', '.join(r.flags)})" if r.flags else "") for r in agg.criteria if r.verdict != "pass"]
    if problems:
        lines.append("Not met: " + "; ".join(problems[:12]) + ("; ..." if len(problems) > 12 else "") + ".")
    if agg.injection_attempts:
        lines.append("The evidence contained instructions aimed at the reviewer; they were ignored.")
    if agg.reasons:
        lines.append("Reasons: " + ", ".join(agg.reasons) + ".")
    return " ".join(lines)


# =============================== the job ===============================

def save_report(db: Session, sub: Submission, project: Project, agg, *, ai_summary: str, facts: list, run_id: int | None) -> VerificationReport:
    """Store the report for a decided submission and move the submission and the project on (D-043). Shared with the demo seed."""
    payload = {"criteria": [c.as_dict() for c in agg.criteria], "requirements": agg.requirements, "gates": agg.gates,
               "injection_attempts": agg.injection_attempts, "reasons": agg.reasons, "attempt_no": sub.attempt_no,
               "ai_summary": " ".join((ai_summary or "").split())[:600], "facts": facts}
    summary = plain_summary(agg, sub.attempt_no)
    report = VerificationReport(submission_id=sub.id, verdicts_json=payload, overall=agg.overall, must_pass_pct=agg.must_pass_pct,
                                should_pass_pct=agg.should_pass_pct, summary=summary,
                                sha256=report_sha(payload, agg.overall, agg.must_pass_pct, agg.should_pass_pct, summary), agent_run_id=run_id)
    db.add(report)
    sub.state = agg.overall
    if agg.overall == "VERIFIED":
        ProjectService.transition(db, project, "PAYOUT_READY", actor="agent:verifier", reason=f"verification report, attempt {sub.attempt_no}")
    elif agg.overall == "NEEDS_CHANGES":
        ProjectService.transition(db, project, "IN_PROGRESS", actor="agent:verifier", reason=f"attempt {sub.attempt_no} needs changes")
    db.flush()                                      # FAILED: the project stays VERIFYING until the lead decides (GAP-70)
    return report


def judge(db: Session, submission_id: int, agent: VerifierAgent, checker: AutoChecker) -> dict:
    sub = db.get(Submission, submission_id)
    if sub is None:
        return {"effect": "SKIPPED", "why": "unknown submission"}
    if sub.state not in JUDGEABLE:
        return {"effect": "ALREADY_DONE", "state": sub.state}
    contract = db.get(Contract, sub.contract_id)
    brd = db.get(BRD, contract.brd_id)
    project = db.get(Project, contract.project_id)
    if project.state != "VERIFYING":                 # e.g. a refund started meanwhile: nothing to decide any more
        return {"effect": "SKIPPED", "why": f"project is {project.state}"}
    sub.state = "JUDGING"

    checks = list(db.scalars(select(AutoCheck).where(AutoCheck.submission_id == sub.id).order_by(AutoCheck.id)))
    refresh_gates(checker, sub, checks)
    questions = {q.id: q for q in db.scalars(select(VerificationQuestion).where(VerificationQuestion.submission_id == sub.id).order_by(VerificationQuestion.id))}
    evidence = list(db.scalars(select(Evidence).where(Evidence.submission_id == sub.id).order_by(Evidence.id)))
    followup_done = any(q.round >= FOLLOWUP_ROUND for q in questions.values())

    flagged, facts = snippet_facts(sub, evidence, questions, checker)
    try:
        images, shown_images, image_facts = load_images(db, evidence)
    except ImageStoreUnavailable as e:
        sub.state = "EVIDENCE_RECEIVED"
        return {"effect": "JUDGE_UNAVAILABLE", "why": f"images could not be read: {e}"}
    facts += image_facts
    visible = {e.id for e in evidence if e.kind != "SCREENSHOT" or e.id in shown_images}

    # what each asked criterion is judged on: all evidence given for it, in every round, that the reviewer can actually see
    asked: dict[tuple[str, str], set[int]] = {}
    evidence_of: dict[tuple[str, str], list[dict]] = {}
    qtext: dict[tuple[str, str], VerificationQuestion] = {}
    for q in questions.values():
        key = (q.requirement_code, q.criterion_id)
        qtext[key] = q
        asked.setdefault(key, set())
        evidence_of.setdefault(key, [])
    for e in evidence:
        q = questions.get(e.question_id)
        if q is not None and e.id in visible:
            key = (q.requirement_code, q.criterion_id)
            asked[key].add(e.id)
            evidence_of[key].append({"id": e.id, "kind": e.kind, "text": e.text, "url": e.url})

    reqs = brd.content_json.get("requirements", [])
    criteria = []
    for req in reqs:
        for crit in req.get("acceptance_criteria", []):
            key = (req["code"], crit["id"])
            if key not in asked:
                continue
            hint = crit.get("auto_check_hint") or {}
            result = next((c["result"] for c in check_dicts(checks) if c["requirement_code"] == req["code"] and c["criterion_id"] == crit["id"]
                           and c["check_type"] == hint.get("type")), None)
            criteria.append({"requirement_code": req["code"], "requirement_title": req["title"], "criterion_id": crit["id"], "given": crit["given"],
                             "when": crit["when"], "then": crit["then"], "auto_check": {"type": hint.get("type"), "result": result or "NOT_RUN"} if hint else None,
                             "evidence": evidence_of[key]})

    verdicts: list[ACVerdict] = []
    ai_summary, run_id = "", None
    if criteria:
        try:
            out, run_id = agent.judge(JudgeInputs(criteria=criteria, images=images, facts=facts, notes=sub.notes), contract.project_id)
        except AgentError as e:                    # nothing is decided on a model failure: the freelancer may ask again
            sub.state = "EVIDENCE_RECEIVED"
            return {"effect": "JUDGE_UNAVAILABLE", "why": str(e)[:200], "agent_run_id": getattr(e, "run_id", None)}
        verdicts, ai_summary = out.verdicts, out.summary_for_sponsors

    agg = aggregate(reqs, check_dicts(checks), verdicts, asked, flagged, attempt_no=sub.attempt_no, followup_done=followup_done)

    if agg.overall == "INCONCLUSIVE":
        sub.state = "EVIDENCE_RECEIVED"
        return {"effect": "INCONCLUSIVE", "gates": agg.gates, "why": "GitHub could not be asked; try again shortly", "agent_run_id": run_id}

    if agg.overall == "NEEDS_FOLLOWUP":
        rationale = {(v.requirement_code, v.criterion_id): v.rationale for v in verdicts}
        for key in agg.followup:
            src = qtext[key]
            db.add(VerificationQuestion(submission_id=sub.id, requirement_code=key[0], criterion_id=key[1],
                                        question=followup_text(key[0], key[1], rationale.get(key, "")),
                                        expected_evidence_json=src.expected_evidence_json, round=FOLLOWUP_ROUND, status="OPEN"))
        sub.state = "QUESTIONING"
        db.flush()
        return {"effect": "FOLLOWUP_ASKED", "questions": len(agg.followup), "agent_run_id": run_id}

    report = save_report(db, sub, project, agg, ai_summary=ai_summary, facts=facts, run_id=run_id)
    return {"effect": agg.overall, "report_id": report.id, "must_pass_pct": agg.must_pass_pct, "should_pass_pct": agg.should_pass_pct, "agent_run_id": run_id}
