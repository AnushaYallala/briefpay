"""Bearer-token auth (D-009): email + display name -> signed JWT. No passwords; sandbox/demo scope only."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import ProjectMember, User

TOKEN_HOURS = 24


def api_error(status: int, code: str, message: str, details: dict | None = None) -> HTTPException:
    """SPEC 10 error shape: {"error": {"code", "message", "details"}} (unwrapped by the handler in main.py)."""
    return HTTPException(status, {"error": {"code": code, "message": message, "details": details or {}}})


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user.id), "exp": exp}, get_settings().jwt_secret, algorithm="HS256")


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise api_error(401, "UNAUTHENTICATED", "Send Authorization: Bearer <token>")
    try:
        claims = jwt.decode(authorization[7:], get_settings().jwt_secret, algorithms=["HS256"])
        user = db.get(User, int(claims["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        user = None
    if user is None:
        raise api_error(401, "BAD_TOKEN", "Token is invalid or expired")
    return user


def require_member(db: Session, project_id: int, user: User, roles: tuple[str, ...] | None = None) -> ProjectMember:
    m = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                               ProjectMember.user_id == user.id)).first()
    if m is None:
        raise api_error(403, "NOT_A_MEMBER", "You are not a member of this project")
    if roles and m.role not in roles:
        raise api_error(403, "FORBIDDEN", f"Requires role {' or '.join(roles)}")
    return m
