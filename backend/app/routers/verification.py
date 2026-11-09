"""Verification evidence endpoint (SPEC 10): the freelancer answers one question."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, require_member
from app.db import get_db
from app.models import User
from app.services import evidence_service as svc

router = APIRouter()


class EvidenceIn(BaseModel):
    image_ids: list[int] = Field(default=[], max_length=10)
    code_snippet: str | None = Field(default=None, max_length=40_000)
    repo_path: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=600)
    text: str | None = Field(default=None, max_length=5000)


@router.post("/verification/questions/{question_id}/evidence", status_code=201)
def answer(question_id: int, body: EvidenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        question, sub, contract = svc.load_question(db, question_id)
        member = require_member(db, contract.project_id, user, ("FREELANCER",))
        rows = svc.answer_question(db, question, sub, contract, member, image_ids=body.image_ids, code_snippet=body.code_snippet,
                                   repo_path=body.repo_path, url=body.url, text=body.text)
    except svc.EvidenceError as e:
        db.rollback()
        raise api_error(e.status, e.code, e.message) from e
    db.commit()
    return {"question": svc.question_view(question), "submission_state": sub.state, "evidence": [svc.evidence_view(r) for r in rows]}
