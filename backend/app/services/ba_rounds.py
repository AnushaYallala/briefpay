"""BA question loop (SPEC 7.1): score -> ask -> answer / skip -> next round, up to BA_MAX_ROUNDS.

Rounds are numbered from 0 (round 0 = the first scoring of the meeting). A round is complete when every question
asked in it is answered or skipped; then `session.round` advances and a BA_RUN job scores the new round.
All functions flush only; the caller owns the transaction.
"""
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.ba_agent import BAAgent, BAQuestionsAgent, QuestionInputs
from app.agents.llm_adapter import AgentError
from app.config import get_settings
from app.models import BAAnswer, BAQuestion, BAScore, BASession, Job, Project, ProjectMember
from app.services import jobs
from app.services import project_ops as ops
from app.services.ba_scoring import DIMENSION_NAMES, WEIGHTS
from app.services.ba_service import (
    BAError, build_inputs, get_or_create_session, get_session, latest_score, score_round,
)

MAX_QUESTIONS = 5
RUNS_PER_HOUR = 8

# Used only when the AI returns questions but every one is a repeat or off-topic, so the loop can never stall.
FALLBACK_QUESTIONS = {
    "D1": "What is the main goal of the website, and how will you know after six months that it worked?",
    "D2": "Who should the website be for, where are they from, and which languages do they read?",
    "D3": "What does your own business most need from the website?",
    "D4": "Which pages should the website have, and what is each page for?",
    "D5": "Which features must the website have, such as an enquiry form, a map or a photo gallery?",
    "D6": "For the most important feature, what should a visitor see when it works correctly?",
    "D7": "Who will provide the text and photos, and by what date?",
    "D8": "How should the website look? Name any colours, styles or sites you like.",
    "D9": "Should the website work well on phones, load fast and be easy to find on Google?",
    "D10": "Who will look after the website after it is built, and what is it not expected to do?",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def session_questions(db: Session, session_id: int, round_: int | None = None) -> list[BAQuestion]:
    q = select(BAQuestion).where(BAQuestion.session_id == session_id).order_by(BAQuestion.id)
    if round_ is not None:
        q = q.where(BAQuestion.round == round_)
    return list(db.scalars(q))


def answers_for(db: Session, question_id: int) -> list[BAAnswer]:
    return list(db.scalars(select(BAAnswer).where(BAAnswer.question_id == question_id).order_by(BAAnswer.id)))


# ---------------- generating questions ----------------

def build_question_inputs(db: Session, project: Project, session: BASession, row: BAScore) -> QuestionInputs:
    base, _ = build_inputs(db, project, session)
    cov = {d["dimension"]: d["coverage_effective"] for d in row.dimensions_json}
    gaps = sorted(({"dimension": d, "name": DIMENSION_NAMES[d], "weight": WEIGHTS[d], "coverage": c,
                    "importance": WEIGHTS[d] * (1 - c)} for d, c in cov.items() if c < 1),
                  key=lambda g: (-g["importance"], g["dimension"]))
    red = [{"id": k, "title": v["title"], "detail": v["detail"]} for k, v in row.gates_json.items()
           if k.startswith("GT") and not v["passed"]]
    return QuestionInputs(
        base=base, gaps=gaps, red_gates=red,
        open_conflicts=[c for c in row.conflicts_json if not (c.get("resolved") and (c.get("resolution") or "").strip())],
        requirements=[{"temp_id": r["temp_id"], "title": r["title"], "priority": r["priority"]}
                      for r in row.extracted_requirements_json],
        asked=[{"question": q.question, "status": q.status} for q in session_questions(db, session.id)])


def filter_questions(proposed, *, gap_dims: set[str], sponsor_ids: set[int], already_asked: list[str]) -> list[dict]:
    """Code-side guardrails on the AI's questions: real sponsors only, only dimensions that still have a gap,
    no repeats of any earlier question, at most five. The prompt asks for conflicts first; order is kept."""
    seen = {_norm(t) for t in already_asked}
    out = []
    for q in proposed:
        if q.dimension not in gap_dims or _norm(q.question) in seen:
            continue
        to = [a for a in q.addressed_to if a == "ALL" or a in sponsor_ids]
        if "ALL" in to or not to:
            to = ["ALL"]
        seen.add(_norm(q.question))
        out.append({"dimension": q.dimension, "question": q.question, "rationale": q.rationale, "addressed_to": to,
                    "suggested_options": q.suggested_options})
        if len(out) == MAX_QUESTIONS:
            break
    return out


def generate_questions(db: Session, project: Project, session: BASession, row: BAScore,
                       qagent: BAQuestionsAgent) -> list[BAQuestion]:
    inp = build_question_inputs(db, project, session, row)
    sponsor_ids = {m["member_id"] for m in inp.base.members}
    try:
        proposed, _ = qagent.ask(inp, project.id)
    except AgentError as e:
        raise BAError("AI_UNAVAILABLE", f"The BA Agent could not write questions: {e}", 503) from e
    chosen = filter_questions(proposed.questions, gap_dims={g["dimension"] for g in inp.gaps}, sponsor_ids=sponsor_ids,
                              already_asked=[a["question"] for a in inp.asked])
    if not chosen and inp.gaps:  # never stall the loop
        top = inp.gaps[0]["dimension"]
        chosen = [{"dimension": top, "question": FALLBACK_QUESTIONS[top],
                   "rationale": "Standard follow-up (no new question could be generated).",
                   "addressed_to": ["ALL"], "suggested_options": None}]
    rows = [BAQuestion(session_id=session.id, round=session.round, dimension=c["dimension"], question=c["question"],
                       rationale=c["rationale"], addressed_to_json=c["addressed_to"],
                       suggested_options_json=c["suggested_options"], status="OPEN") for c in chosen]
    db.add_all(rows)
    db.flush()
    return rows


def run_round(db: Session, project: Project, agent: BAAgent, qagent: BAQuestionsAgent) -> dict:
    """One full BA step for the current round. Repeating it is safe: unchanged input is never re-scored
    and a round never gets a second set of questions, so a failed job can simply be retried."""
    session = get_or_create_session(db, project)
    t = ops.latest_transcript(db, project.id)
    row = latest_score(db, session.id)
    fresh = (row is not None and row.round == session.round and t is not None
             and row.gates_json.get("observations", {}).get("transcript_sha256") == t.sha256)
    if not fresh:
        row = score_round(db, project, agent)
        db.commit()
    info = {"score": row.total, "round": session.round}
    if session.state == "READY":
        return {**info, "state": session.state, "questions": 0}
    if session.round >= get_settings().ba_max_rounds:
        session.state = "MAX_ROUNDS"
        db.flush()
        return {**info, "state": session.state, "questions": 0}
    existing = session_questions(db, session.id, session.round)
    made = existing or generate_questions(db, project, session, row, qagent)
    return {**info, "state": session.state, "questions": len(made)}


# ---------------- answering, skipping, completing a round ----------------

def can_answer(q: BAQuestion, member: ProjectMember) -> bool:
    return member.role in ("LEAD", "SPONSOR") and ("ALL" in q.addressed_to_json or member.id in q.addressed_to_json)


def question_done(db: Session, q: BAQuestion) -> bool:
    """Addressed to named people: all of them must answer. Addressed to ALL: any one sponsor is enough."""
    answered = {a.member_id for a in answers_for(db, q.id)}
    if "ALL" in q.addressed_to_json:
        return bool(answered)
    return set(q.addressed_to_json) <= answered


def enqueue_run(db: Session, project_id: int) -> int:
    return jobs.enqueue(db, "BA_RUN", {"project_id": project_id}).id


def _maybe_complete_round(db: Session, session: BASession) -> bool:
    qs = session_questions(db, session.id, session.round)
    if not qs or any(q.status == "OPEN" for q in qs):
        return False
    session.round += 1  # the next scoring is a new round
    db.flush()
    enqueue_run(db, session.project_id)
    return True


def answer_question(db: Session, q: BAQuestion, member: ProjectMember, text: str, option: str | None) -> dict:
    session = db.get(BASession, q.session_id)
    if q.status != "OPEN" or q.round != session.round or session.state not in ("ACTIVE", "READY"):
        raise BAError("QUESTION_CLOSED", "This question is no longer open")
    if not can_answer(q, member):
        raise BAError("NOT_ADDRESSED", "This question is not addressed to you", 403)
    if any(a.member_id == member.id for a in answers_for(db, q.id)):
        raise BAError("ALREADY_ANSWERED", "You have already answered this question")
    text = (text or "").strip()
    if not text:
        raise BAError("EMPTY_ANSWER", "Please write an answer", 422)
    if option is not None and q.suggested_options_json and option not in (*q.suggested_options_json, "Other"):
        raise BAError("BAD_OPTION", "selected_option must be one of the suggestions or 'Other'", 422)
    db.add(BAAnswer(question_id=q.id, member_id=member.id, answer_text=text[:2000], selected_option=option))
    db.flush()
    if question_done(db, q):
        q.status = "ANSWERED"
    db.flush()
    return {"question_status": q.status, "round_complete": _maybe_complete_round(db, session)}


def skip_question(db: Session, q: BAQuestion) -> dict:
    session = db.get(BASession, q.session_id)
    if q.status != "OPEN" or q.round != session.round:
        raise BAError("QUESTION_CLOSED", "This question is no longer open")
    q.status = "SKIPPED"
    db.flush()
    return {"question_status": q.status, "round_complete": _maybe_complete_round(db, session)}


# ---------------- manual run, finalize ----------------

def recent_runs(db: Session, project_id: int) -> int:
    since = _now() - timedelta(hours=1)
    recent = db.scalars(select(Job).where(Job.type == "BA_RUN", Job.created_at >= since))
    return sum(1 for j in recent if j.payload_json.get("project_id") == project_id)


def request_run(db: Session, project: Project) -> int:
    """Manual 'Run BA Agent' (lead). Rate limited; refuses when it could not make progress."""
    if ops.latest_transcript(db, project.id) is None:  # first, so a new project is told what to do, not its state name
        raise BAError("NO_TRANSCRIPT", "Upload the meeting transcript first")
    if project.state != "REQUIREMENTS":
        raise BAError("PROJECT_STATE", f"The BA Agent runs while the project is in REQUIREMENTS (it is {project.state})")
    session = get_or_create_session(db, project)
    if session.state in ("BRD_GENERATED", "FINALIZED", "MAX_ROUNDS"):
        raise BAError("BA_DONE", f"The analysis is {session.state}; nothing more to run")
    if any(q.status == "OPEN" for q in session_questions(db, session.id, session.round)):
        raise BAError("QUESTIONS_OPEN", "Answer or skip the open questions first; the next round starts by itself")
    if recent_runs(db, project.id) >= RUNS_PER_HOUR:
        raise BAError("RATE_LIMITED", f"At most {RUNS_PER_HOUR} BA runs per project per hour", 429)
    return enqueue_run(db, project.id)


def finalize(db: Session, project: Project) -> BASession:
    """Lead accepts the remaining gaps once the round limit is reached. They become open items in the BRD (T-14)."""
    session = get_session(db, project.id)
    if session is None or session.state != "MAX_ROUNDS":
        raise BAError("NOT_FINALIZABLE", "Finalizing is only possible after the round limit is reached without a ready score")
    for q in session_questions(db, session.id):
        if q.status == "OPEN":
            q.status = "SKIPPED"
    session.state = "FINALIZED"
    db.flush()
    return session
