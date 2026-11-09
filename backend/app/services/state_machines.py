"""Project and Campaign state machines (SPEC 6.1).

ProjectService.transition / CampaignService.transition are the ONLY places these states change.
Each transition writes a STATE_CHANGE ledger row in the caller's transaction.
"""
from sqlalchemy.orm import Session

from app.models import Campaign, Project
from app.services import ledger


class IllegalTransition(Exception):
    pass


PROJECT_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"REQUIREMENTS"},
    "REQUIREMENTS": {"BRD_REVIEW"},
    "BRD_REVIEW": {"CONTRACTING", "REQUIREMENTS"},  # REQUIREMENTS = a sponsor rejected the BRD
    "CONTRACTING": {"CAMPAIGN_SETUP"},
    "CAMPAIGN_SETUP": {"PLEDGING"},
    "PLEDGING": {"IN_PROGRESS", "CAMPAIGN_FAILED"},
    "CAMPAIGN_FAILED": {"CAMPAIGN_SETUP"},  # relaunch
    "IN_PROGRESS": {"VERIFYING", "REFUNDING"},
    "VERIFYING": {"PAYOUT_READY", "IN_PROGRESS", "REFUNDING"},  # IN_PROGRESS = NEEDS_CHANGES
    "PAYOUT_READY": {"PAYOUT_PENDING", "REFUNDING"},
    "PAYOUT_PENDING": {"PAID", "PAYOUT_FAILED"},
    "PAYOUT_FAILED": {"PAYOUT_PENDING"},  # retry builds a new plan
    "REFUNDING": {"CANCELLED"},
    "PAID": set(),
    "CANCELLED": set(),
}

CAMPAIGN_TRANSITIONS: dict[str, set[str]] = {
    "SETUP": {"OPEN", "CANCELLED"},
    "OPEN": {"CAPTURING", "FAILING"},  # FAILING = deadline missed or lead cancel
    "CAPTURING": {"CAPTURED"},
    "FAILING": {"FAILED"},
    "CAPTURED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}

CAMPAIGN_FAIL_REASONS = {"DEADLINE_MISSED", "LEAD_CANCEL"}


def _check(table: dict[str, set[str]], kind: str, current: str, to: str) -> None:
    if current not in table:
        raise IllegalTransition(f"unknown {kind} state {current}")
    if to not in table[current]:
        raise IllegalTransition(f"{kind} cannot go {current} -> {to}")


class ProjectService:
    @staticmethod
    def transition(db: Session, project: Project, to: str, *, actor: str, reason: str | None = None) -> Project:
        _check(PROJECT_TRANSITIONS, "project", project.state, to)
        frm, project.state = project.state, to
        ledger.append(
            db, project.id, "STATE_CHANGE", actor=actor, ref_type="project", ref_id=project.id,
            meta={"from": frm, "to": to, "reason": reason},
        )
        return project


class CampaignService:
    @staticmethod
    def transition(
        db: Session, campaign: Campaign, to: str, *, actor: str, fail_reason: str | None = None
    ) -> Campaign:
        _check(CAMPAIGN_TRANSITIONS, "campaign", campaign.state, to)
        if to == "FAILING":
            if fail_reason not in CAMPAIGN_FAIL_REASONS:
                raise IllegalTransition("FAILING needs fail_reason DEADLINE_MISSED or LEAD_CANCEL")
            campaign.fail_reason = fail_reason
        frm, campaign.state = campaign.state, to
        ledger.append(
            db, campaign.project_id, "STATE_CHANGE", actor=actor, ref_type="campaign", ref_id=campaign.id,
            meta={"from": frm, "to": to, "fail_reason": fail_reason},
        )
        return campaign
