"""Build the facts the Guardian LLM sees (SPEC 7.5.4): amounts and labels only, never emails or raw images.

TRUSTED = computed from our own records. UNTRUSTED = display names and the AI-written verification summary,
both of which can contain text a user chose. People are labelled P1, P2 ... and FREELANCER in the trusted part.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AutoCheck, Campaign, MoneyPlan, Pledge, Submission, VerificationReport
from app.schemas.plans import MoneyPlanSpec
from app.services import plan_builder as pb
from app.services.guardian_rules import Evaluation


def _iso(dt):
    return pb._aware(dt).isoformat() if dt else None


def build_facts(db: Session, plan: MoneyPlan, spec: MoneyPlanSpec, ev: Evaluation) -> dict:
    labels: dict[int, str] = {}
    names: dict[str, str] = {}

    def label(pledge: Pledge) -> str:
        if pledge.id not in labels:
            labels[pledge.id] = f"P{len(labels) + 1}"
            names[labels[pledge.id]] = pledge.display_name
        return labels[pledge.id]

    steps = []
    for s in spec.steps:
        who = "FREELANCER" if s.op == "PAYOUT_ITEM" else None
        if s.target_type in ("PLEDGE", "CAPTURE"):
            p = db.get(Pledge, s.target_id)
            who = label(p) if p else "UNKNOWN"
        steps.append({"op": s.op, "amount_cents": s.amount_cents, "party": who})

    trusted: dict = {
        "plan": {"kind": spec.kind, "reason": spec.reason, "steps": len(spec.steps),
                 "total_cents": sum(s.amount_cents for s in spec.steps), "currency": spec.inputs.get("currency")},
        "steps": steps,
        "hard_rules": {"failed": ev.failed_ids, "unverified": [r.id for r in ev.results if r.status == "UNVERIFIED"]},
        "soft_flags": [f["id"] for f in ev.soft_flags],
    }

    camp = db.get(Campaign, spec.campaign_id) if spec.campaign_id else None
    if camp:
        pledges = list(db.scalars(select(Pledge).where(Pledge.campaign_id == camp.id).order_by(Pledge.authorized_at, Pledge.id)))
        trusted["campaign"] = {"goal_cents": camp.goal_cents, "state": camp.state, "opens_at": _iso(camp.opens_at),
                               "deadline_at": _iso(camp.deadline_at)}
        trusted["timeline"] = [{"party": label(p), "amount_cents": p.amount_cents, "status": p.status,
                                "authorized_at": _iso(p.authorized_at)} for p in pledges if p.status != "CREATED"]

    untrusted = {"names": names}
    if spec.kind == "FREELANCER_PAYOUT" and spec.inputs.get("submission_id"):
        sub = db.get(Submission, spec.inputs["submission_id"])
        rep = db.scalars(select(VerificationReport).where(VerificationReport.submission_id == sub.id)
                         .order_by(VerificationReport.id.desc())).first() if sub else None
        checks = list(db.scalars(select(AutoCheck).where(AutoCheck.submission_id == sub.id).order_by(AutoCheck.id))) if sub else []
        if rep:
            trusted["verification"] = {"overall": rep.overall, "must_pass_pct": rep.must_pass_pct,
                                       "should_pass_pct": rep.should_pass_pct, "attempt": sub.attempt_no,
                                       "auto_checks": [{"type": c.check_type, "result": c.result} for c in checks]}
            untrusted["verification_summary"] = rep.summary
    return {"trusted": trusted, "untrusted": untrusted}
