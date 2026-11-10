"""What can be done after a submission ends FAILED (SPEC 7.3: "the lead decides: extend, cancel and refund, or override"). Flushes only.

The project waits in VERIFYING with the latest submission FAILED. Three ways forward:

  extend        the lead gives the freelancer more attempts (1 to 3 at a time, 6 extra at most); the project returns to IN_PROGRESS
  cancel-refund the lead has the refund plan built (reason VERIFICATION_FAILED_FINAL); it then goes through the normal Guardian review
                and human approval like every refund
  override      EVERY sponsor (the lead included) must approve paying anyway; a new report marked as an override and VERIFIED is
                saved (so the payout rules apply unchanged), the project becomes PAYOUT_READY, and the Guardian raises soft flag S-04

Every decision is an APPROVAL memo in the append-only ledger, so the history is public and cannot be edited. Nothing else is stored.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contract, LedgerEntry, MoneyPlan, Project, ProjectMember, Submission, User, VerificationReport
from app.services import ba_service, ledger, plan_builder as pb
from app.services.state_machines import ProjectService
from app.services.verify_aggregate import MAX_ATTEMPTS

KIND_EXTEND = "EXTEND_ATTEMPTS"
KIND_REFUND = "CANCEL_REFUND_REQUESTED"
KIND_OVERRIDE = "VERIFICATION_OVERRIDE"
MAX_EXTRA_AT_ONCE = 3
MAX_EXTRA_TOTAL = 6
MAX_NOTE = 300
REFUND_REASON = "VERIFICATION_FAILED_FINAL"


class DecisionError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ---------------- what has been decided (read from the ledger) ----------------

def _memos(db: Session, project_id: int, kind: str) -> list[LedgerEntry]:
    return [e for e in db.scalars(select(LedgerEntry).where(LedgerEntry.project_id == project_id, LedgerEntry.type == "APPROVAL",
                                                           LedgerEntry.ref_type == "submission").order_by(LedgerEntry.seq))
            if (e.meta_json or {}).get("kind") == kind]


def extra_attempts(db: Session, contract: Contract) -> int:
    return sum(int((e.meta_json or {}).get("extra", 0)) for e in _memos(db, contract.project_id, KIND_EXTEND))


def allowed_attempts(db: Session, contract_id: int) -> int:
    contract = db.get(Contract, contract_id)
    return MAX_ATTEMPTS + (extra_attempts(db, contract) if contract else 0)


def override_votes(db: Session, sub: Submission, project_id: int) -> dict[int, dict]:
    """The latest vote of each sponsor on this submission's override: {member_id: {"decision", "note", "seq"}}."""
    votes: dict[int, dict] = {}
    for e in _memos(db, project_id, KIND_OVERRIDE):
        m = e.meta_json
        if m.get("submission_id") == sub.id:
            votes[int(m["member_id"])] = {"decision": m["decision"], "note": m.get("note"), "seq": e.seq}
    return votes


# ---------------- the situation ----------------

def _situation(db: Session, sub: Submission) -> tuple[Contract, Project]:
    contract = db.get(Contract, sub.contract_id)
    project = db.get(Project, contract.project_id)
    latest = db.scalars(select(Submission).where(Submission.contract_id == contract.id).order_by(Submission.attempt_no.desc())).first()
    if sub.state != "FAILED" or latest.id != sub.id:
        raise DecisionError("NOT_FAILED", f"Only the latest submission can be decided on, and only once it is FAILED (this one is {sub.state})")
    if project.state != "VERIFYING":
        raise DecisionError("PROJECT_STATE", f"The project must be waiting in VERIFYING (it is {project.state})")
    return contract, project


def _lead_only(member: ProjectMember) -> None:
    if member.role != "LEAD":
        raise DecisionError("FORBIDDEN", "Only the lead can make this decision", 403)


def _clean_note(note: str | None) -> str | None:
    note = " ".join((note or "").split())
    if len(note) > MAX_NOTE:
        raise DecisionError("NOTE_TOO_LONG", f"Keep the note under {MAX_NOTE} characters", 422)
    return note or None


def options(db: Session, sub: Submission, project_id: int) -> dict:
    contract = db.get(Contract, sub.contract_id)
    project = db.get(Project, project_id)
    attempts_used = db.query(Submission).filter(Submission.contract_id == contract.id).count()
    extra = extra_attempts(db, contract)
    open_ = sub.state == "FAILED" and project.state == "VERIFYING"
    voters = ba_service.sponsor_members(db, project_id)
    votes = override_votes(db, sub, project_id)
    names = {m.id: db.get(User, m.user_id).display_name for m in voters}
    return {"submission_id": sub.id, "state": sub.state, "open": open_, "attempts_used": attempts_used,
            "attempts_allowed": MAX_ATTEMPTS + extra, "extra_attempts_given": extra, "extra_attempts_left": max(MAX_EXTRA_TOTAL - extra, 0),
            "extend": {"max_now": min(MAX_EXTRA_AT_ONCE, max(MAX_EXTRA_TOTAL - extra, 0))},
            "override": {"needed": len(voters), "approved": sum(1 for m in voters if votes.get(m.id, {}).get("decision") == "APPROVE"),
                         "sponsors": [{"member_id": m.id, "name": names[m.id], "vote": votes.get(m.id, {}).get("decision", "WAITING"),
                                       "note": votes.get(m.id, {}).get("note")} for m in voters]}}


# ---------------- the three decisions ----------------

def extend(db: Session, sub: Submission, member: ProjectMember, extra: int, note: str | None) -> dict:
    _lead_only(member)
    contract, project = _situation(db, sub)
    already = extra_attempts(db, contract)
    if not 1 <= extra <= MAX_EXTRA_AT_ONCE:
        raise DecisionError("BAD_EXTRA", f"Give between 1 and {MAX_EXTRA_AT_ONCE} more attempts at a time", 422)
    if already + extra > MAX_EXTRA_TOTAL:
        raise DecisionError("EXTENSION_LIMIT", f"At most {MAX_EXTRA_TOTAL} extra attempts can be given in total ({already} already given)")
    note = _clean_note(note)
    ledger.append(db, project.id, "APPROVAL", actor=f"user:{member.user_id}", ref_type="submission", ref_id=sub.id,
                  meta={"kind": KIND_EXTEND, "submission_id": sub.id, "extra": extra, "attempts_allowed": MAX_ATTEMPTS + already + extra, "note": note})
    ProjectService.transition(db, project, "IN_PROGRESS", actor=f"user:{member.user_id}", reason=f"lead extended the attempts by {extra}")
    return {"attempts_allowed": MAX_ATTEMPTS + already + extra}


def cancel_refund(db: Session, sub: Submission, member: ProjectMember) -> MoneyPlan:
    _lead_only(member)
    contract, project = _situation(db, sub)
    try:
        plan = pb.save_proposed(db, pb.build_refund_captured(db, project.id, REFUND_REASON), proposed_by=f"user:{member.user_id}")
    except pb.PlanBuildError as e:
        raise DecisionError("NOTHING_TO_REFUND", str(e)) from e
    if not any((e.meta_json or {}).get("plan_id") == plan.id for e in _memos(db, project.id, KIND_REFUND)):
        ledger.append(db, project.id, "APPROVAL", actor=f"user:{member.user_id}", ref_type="submission", ref_id=sub.id,
                      meta={"kind": KIND_REFUND, "submission_id": sub.id, "plan_id": plan.id, "reason": REFUND_REASON})
    return plan


def vote_override(db: Session, sub: Submission, member: ProjectMember, decision: str, note: str | None) -> dict:
    if decision not in ("APPROVE", "REJECT"):
        raise DecisionError("BAD_DECISION", "decision must be APPROVE or REJECT", 422)
    if member.role not in ("LEAD", "SPONSOR"):
        raise DecisionError("FORBIDDEN", "Only the sponsors (the lead included) vote on an override", 403)
    contract, project = _situation(db, sub)
    note = _clean_note(note)
    ledger.append(db, project.id, "APPROVAL", actor=f"user:{member.user_id}", ref_type="submission", ref_id=sub.id,
                  meta={"kind": KIND_OVERRIDE, "submission_id": sub.id, "member_id": member.id, "decision": decision, "note": note,
                        "attempt_no": sub.attempt_no})
    voters = ba_service.sponsor_members(db, project.id)
    votes = override_votes(db, sub, project.id)
    if all(votes.get(m.id, {}).get("decision") == "APPROVE" for m in voters):
        _apply_override(db, sub, project, contract, voters, votes)
        return {"applied": True, "project_state": project.state}
    return {"applied": False, "approved": sum(1 for m in voters if votes.get(m.id, {}).get("decision") == "APPROVE"), "needed": len(voters)}


def _apply_override(db: Session, sub: Submission, project: Project, contract: Contract, voters: list[ProjectMember], votes: dict) -> None:
    from app.services.verify_judge import report_sha
    failed = db.scalars(select(VerificationReport).where(VerificationReport.submission_id == sub.id).order_by(VerificationReport.id.desc())).first()
    base = dict(failed.verdicts_json or {}) if failed else {}
    names = [db.get(User, m.user_id).display_name for m in voters]
    payload = {**base, "reasons": sorted(set(base.get("reasons", [])) | {"SPONSOR_OVERRIDE"}),
               "override": {"approved_by": names, "member_ids": [m.id for m in voters], "notes": [votes[m.id]["note"] for m in voters if votes[m.id]["note"]],
                           "failed_report_sha256": failed.sha256 if failed else None, "failed_overall": failed.overall if failed else None}}
    summary = (f"Override: verification FAILED on attempt {sub.attempt_no}, and every sponsor ({', '.join(names)}) approved paying anyway. "
               f"The original result was {failed.must_pass_pct if failed else 0}% of MUST requirements met.")
    must, should = (failed.must_pass_pct, failed.should_pass_pct) if failed else (0, 0)
    db.add(VerificationReport(submission_id=sub.id, verdicts_json=payload, overall="VERIFIED", must_pass_pct=must, should_pass_pct=should,
                              summary=summary, sha256=report_sha(payload, "VERIFIED", must, should, summary), agent_run_id=None))
    sub.state = "OVERRIDDEN"
    ProjectService.transition(db, project, "PAYOUT_READY", actor="sponsors", reason=f"every sponsor approved an override of attempt {sub.attempt_no}")
    db.flush()
