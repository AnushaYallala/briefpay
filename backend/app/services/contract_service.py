"""Conditional freelancer contract (SPEC 6.2, 10, D-015): offer -> accept (sign).

The terms are rendered by code from a template and hashed together with the key numbers; the freelancer signs that hash
and the BRD hash. Signing locks their PayPal email. The contract is `conditional`: it takes effect only when the capture
plan is DONE (`effective_at`, set in plan_lifecycle). Flushes only; the caller owns the transaction.
"""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import BRD, Contract, Project, ProjectMember, User
from app.services import ledger
from app.services.brd_render import inline, money
from app.services.settlement import canonical_json
from app.services.state_machines import ProjectService

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


class ContractError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def get_contract(db: Session, project_id: int) -> Contract | None:
    return db.scalars(select(Contract).where(Contract.project_id == project_id).order_by(Contract.id.desc())).first()


def freelancer_member(db: Session, project_id: int) -> ProjectMember | None:
    return db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.role == "FREELANCER")).first()


def approved_brd(db: Session, project_id: int) -> BRD | None:
    return db.scalars(select(BRD).where(BRD.project_id == project_id, BRD.status == "APPROVED").order_by(BRD.version.desc())).first()


def _name(db: Session, member: ProjectMember) -> str:
    u = db.get(User, member.user_id)
    return f"{u.display_name} ({member.business_name})" if member.business_name else u.display_name


def render_terms(db: Session, project: Project, brd: BRD, freelancer: ProjectMember, amount_cents: int, delivery_days: int) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False, trim_blocks=True, lstrip_blocks=True,
                      keep_trailing_newline=True, undefined=StrictUndefined)
    env.filters.update(money=money)
    sponsors = [inline(_name(db, m)) for m in db.scalars(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.role.in_(("LEAD", "SPONSOR"))).order_by(ProjectMember.id))]
    return env.get_template("contract.md.j2").render(
        sponsors=sponsors, freelancer=inline(_name(db, freelancer)), project=inline(project.title), brd_version=brd.version,
        brd_sha256=brd.sha256, amount=amount_cents, currency=project.currency, delivery_days=delivery_days).rstrip() + "\n"


def terms_hash(*, terms_md: str, project_id: int, brd_sha256: str, amount_cents: int, currency: str, delivery_days: int,
               freelancer_member_id: int) -> str:
    """What the freelancer actually signs: the text plus the numbers it states, so neither can change alone."""
    payload = {"terms_md": terms_md, "project_id": project_id, "brd_sha256": brd_sha256, "amount_cents": amount_cents,
               "currency": currency, "delivery_days": delivery_days, "freelancer_member_id": freelancer_member_id, "conditional": True}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def offer(db: Session, project: Project, amount_cents: int, delivery_days: int) -> Contract:
    """The lead offers the invited freelancer a price and delivery time. Re-offering replaces an unsigned offer."""
    if project.state != "CONTRACTING":
        raise ContractError("PROJECT_STATE", f"A contract is offered while the project is in CONTRACTING (it is {project.state})")
    brd = approved_brd(db, project.id)
    if brd is None:
        raise ContractError("NO_APPROVED_BRD", "The BRD must be approved by every sponsor first")
    fm = freelancer_member(db, project.id)
    if fm is None:
        raise ContractError("NO_FREELANCER", "Invite the freelancer before making an offer")
    cap = min(project.budget_cents, get_settings().payout_max_cents)
    if not 0 < amount_cents <= cap:
        raise ContractError("BAD_AMOUNT", f"The price must be between 1 and {cap} cents (the project budget and the sandbox payout limit)", 422)
    if not 1 <= delivery_days <= 90:
        raise ContractError("BAD_DELIVERY", "Delivery time must be between 1 and 90 days", 422)

    existing = get_contract(db, project.id)
    if existing is not None and existing.signed_at is not None:
        raise ContractError("CONTRACT_SIGNED", "The contract is already signed and can no longer change")
    terms = render_terms(db, project, brd, fm, amount_cents, delivery_days)
    digest = terms_hash(terms_md=terms, project_id=project.id, brd_sha256=brd.sha256, amount_cents=amount_cents,
                        currency=project.currency, delivery_days=delivery_days, freelancer_member_id=fm.id)
    c = existing or Contract(project_id=project.id, conditional=True)
    c.brd_id, c.brd_sha256, c.freelancer_member_id = brd.id, brd.sha256, fm.id
    c.amount_cents, c.currency, c.delivery_days = amount_cents, project.currency, delivery_days
    c.terms_md, c.sha256 = terms, digest
    c.freelancer_paypal_email, c.signed_at, c.effective_at = None, None, None
    db.add(c)
    db.flush()
    return c


def accept(db: Session, project: Project, member: ProjectMember, paypal_email: str, brd_sha256: str, terms_sha256: str) -> Contract:
    """The freelancer signs: both hashes must match what is stored, and the PayPal email is locked from here on."""
    if member.role != "FREELANCER":
        raise ContractError("FORBIDDEN", "Only the invited freelancer can sign", 403)
    c = get_contract(db, project.id)
    if c is None:
        raise ContractError("NO_CONTRACT", "There is no offer to sign yet", 404)
    if c.signed_at is not None:
        raise ContractError("CONTRACT_SIGNED", "This contract is already signed")
    if project.state != "CONTRACTING":
        raise ContractError("PROJECT_STATE", f"A contract is signed while the project is in CONTRACTING (it is {project.state})")
    if c.freelancer_member_id != member.id:
        raise ContractError("FORBIDDEN", "This offer was made to another freelancer", 403)
    brd = db.get(BRD, c.brd_id)
    if brd is None or brd.status != "APPROVED" or brd.sha256 != c.brd_sha256:
        raise ContractError("BRD_CHANGED", "The approved BRD is no longer the one this offer was made for")
    if brd_sha256 != c.brd_sha256:
        raise ContractError("HASH_MISMATCH", "That is not the BRD this offer is bound to. Reload and read it again.")
    if terms_sha256 != c.sha256:
        raise ContractError("HASH_MISMATCH", "That is not the version of the terms on offer. Reload and read them again.")

    email = paypal_email.strip().lower()
    clash = db.scalars(select(User.id).join(ProjectMember, ProjectMember.user_id == User.id).where(
        ProjectMember.project_id == project.id, ProjectMember.role.in_(("LEAD", "SPONSOR")), User.email == email)).first()
    if clash is not None:
        raise ContractError("EMAIL_CONFLICT", "That PayPal email belongs to one of the sponsors; the freelancer must be paid to their own account")
    c.freelancer_paypal_email, c.signed_at = email, datetime.now(timezone.utc)
    member.paypal_email = email
    ledger.append(db, project.id, "CONTRACT_SIGNED", actor=f"user:{member.user_id}", ref_type="contract", ref_id=c.id,
                  meta={"amount_cents": c.amount_cents, "delivery_days": c.delivery_days, "brd_sha256": c.brd_sha256,
                        "terms_sha256": c.sha256, "conditional": True})  # no email: the ledger can be shown publicly
    ProjectService.transition(db, project, "CAMPAIGN_SETUP", actor=f"user:{member.user_id}", reason="conditional contract signed")
    db.flush()
    return c


def contract_view(db: Session, c: Contract, *, show_email: bool) -> dict:
    brd = db.get(BRD, c.brd_id)
    out = {"id": c.id, "status": "SIGNED" if c.signed_at else "OFFERED", "amount_cents": c.amount_cents, "currency": c.currency,
           "delivery_days": c.delivery_days, "conditional": c.conditional, "terms_md": c.terms_md, "terms_sha256": c.sha256,
           "brd_version": brd.version, "brd_sha256": c.brd_sha256, "freelancer_member_id": c.freelancer_member_id,
           "signed_at": c.signed_at.isoformat() if c.signed_at else None,
           "effective_at": c.effective_at.isoformat() if c.effective_at else None}
    if show_email:
        out["freelancer_paypal_email"] = c.freelancer_paypal_email
    return out
