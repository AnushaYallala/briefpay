"""The freelancer's answer to a verification question (SPEC 7.3 step 3, 10). Flushes only; the caller owns the transaction.

One answer = screenshots (at most 3, the freelancer's own, from this project), a code snippet (at most 200 lines), a repo path,
a URL, and free text. Posting again REPLACES the earlier answer to that question until judging starts. The evidence is stored as
data: nothing in it is ever treated as an instruction, and nothing here calls an AI or the network. The snippet-in-repo
cross-check needs GitHub and happens when the work is judged.
"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Contract, Evidence, Image, ProjectMember, Submission, VerificationQuestion
from app.services.autochecks import PATH_OK
from app.services.submission_service import valid_deployed_url

MAX_IMAGES = 3
MAX_SNIPPET_LINES = 200
MAX_SNIPPET_CHARS = 20_000
MAX_TEXT = 2000
ANSWERABLE_STATES = ("QUESTIONING", "EVIDENCE_RECEIVED")


class EvidenceError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _sha(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _clean_path(path: str) -> str:
    p = (path or "").strip().lstrip("/")
    if not PATH_OK.match(p) or any(seg in ("", ".", "..") for seg in p.split("/")):
        raise EvidenceError("BAD_REPO_PATH", "The repository path must be a plain relative path like src/form.js", 422)
    return p


def load_question(db: Session, question_id: int) -> tuple[VerificationQuestion, Submission, Contract]:
    q = db.get(VerificationQuestion, question_id)
    if q is None:
        raise EvidenceError("QUESTION_NOT_FOUND", "No such question", 404)
    sub = db.get(Submission, q.submission_id)
    return q, sub, db.get(Contract, sub.contract_id)


def answer_question(db: Session, question: VerificationQuestion, sub: Submission, contract: Contract, member: ProjectMember, *,
                    image_ids: list[int], code_snippet: str | None, repo_path: str | None, url: str | None, text: str | None) -> list[Evidence]:
    if contract.freelancer_member_id != member.id:
        raise EvidenceError("NOT_THE_FREELANCER", "Only the freelancer of this contract can answer", 403)
    if sub.state not in ANSWERABLE_STATES:
        raise EvidenceError("SUBMISSION_STATE", f"Answers are accepted while the submission is being questioned (this one is {sub.state})")
    if question.status not in ("OPEN", "ANSWERED"):
        raise EvidenceError("QUESTION_CLOSED", "This question is closed")
    if len(set(image_ids)) != len(image_ids):
        raise EvidenceError("DUPLICATE_IMAGE", "The same screenshot was attached twice", 422)
    if len(image_ids) > MAX_IMAGES:
        raise EvidenceError("TOO_MANY_IMAGES", f"At most {MAX_IMAGES} screenshots per question", 422)
    snippet = (code_snippet or "").strip("\n")
    if snippet.strip() and (snippet.count("\n") + 1 > MAX_SNIPPET_LINES or len(snippet) > MAX_SNIPPET_CHARS):
        raise EvidenceError("SNIPPET_TOO_LONG", f"Code snippets are limited to {MAX_SNIPPET_LINES} lines", 422)
    note = (text or "").strip()
    if len(note) > MAX_TEXT:
        raise EvidenceError("TEXT_TOO_LONG", f"Text is limited to {MAX_TEXT} characters", 422)
    link = (url or "").strip()
    if link and not valid_deployed_url(link):
        raise EvidenceError("BAD_URL", "A link must be an https URL", 422)
    path = _clean_path(repo_path) if (repo_path or "").strip() else None
    if not (image_ids or snippet.strip() or path or link or note):
        raise EvidenceError("EMPTY_ANSWER", "Add a screenshot, code, a repository path, a link or a note", 422)

    images = []
    for image_id in image_ids:
        img = db.get(Image, image_id)
        if img is None or img.project_id != contract.project_id or img.uploaded_by != member.user_id:
            raise EvidenceError("BAD_IMAGE", f"Image {image_id} is not one of your uploads for this project", 422)
        images.append(img)

    db.execute(delete(Evidence).where(Evidence.question_id == question.id))       # a new answer replaces the old one
    rows = [Evidence(submission_id=sub.id, question_id=question.id, kind="SCREENSHOT", image_id=i.id,
                     sha256=i.sha256 or _sha("image", i.public_id)) for i in images]
    if snippet.strip():
        rows.append(Evidence(submission_id=sub.id, question_id=question.id, kind="CODE_SNIPPET", text=snippet, sha256=_sha("code", snippet)))
    if path:
        rows.append(Evidence(submission_id=sub.id, question_id=question.id, kind="REPO_PATH", text=path, sha256=_sha("path", path)))
    if link:
        rows.append(Evidence(submission_id=sub.id, question_id=question.id, kind="URL", url=link, sha256=_sha("url", link)))
    if note:
        rows.append(Evidence(submission_id=sub.id, question_id=question.id, kind="TEXT", text=note, sha256=_sha("text", note)))
    db.add_all(rows)
    question.status = "ANSWERED"
    db.flush()
    open_left = db.scalars(select(VerificationQuestion.id).where(
        VerificationQuestion.submission_id == sub.id, VerificationQuestion.status == "OPEN")).first()
    if open_left is None:
        sub.state = "EVIDENCE_RECEIVED"           # every question has an answer: the freelancer may ask for judging
    db.flush()
    return rows


def evidence_view(e: Evidence) -> dict:
    return {"id": e.id, "question_id": e.question_id, "kind": e.kind, "image_id": e.image_id, "text": e.text, "url": e.url,
            "sha256": e.sha256, "created_at": e.created_at.isoformat()}


def question_view(q: VerificationQuestion) -> dict:
    return {"id": q.id, "requirement_code": q.requirement_code, "criterion_id": q.criterion_id, "question": q.question,
            "expected_evidence": q.expected_evidence_json, "round": q.round, "status": q.status}
