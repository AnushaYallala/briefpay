from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_token, current_user
from app.db import get_db
from app.models import ProjectMember, User

router = APIRouter()


class LoginIn(BaseModel):
    email: EmailStr
    display_name: str


def user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    email = body.email.lower()
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(email=email, display_name=body.display_name.strip() or email)
        db.add(user)
        db.commit()
    return {"token": create_token(user), "user": user_dict(user)}


@router.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    members = db.scalars(select(ProjectMember).where(ProjectMember.user_id == user.id))
    return {"user": user_dict(user),
            "memberships": [{"member_id": m.id, "project_id": m.project_id, "role": m.role} for m in members]}
