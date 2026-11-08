from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import (
    BRD, Campaign, Contract, Pledge, Project, ProjectMember, Submission, User, VerificationReport,
)
from app.services import ledger

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
GOAL = 40000


class World:
    """One Velugu Cove project with a signed contract and an OPEN campaign."""

    def __init__(self, db, tag=""):
        self.db = db
        self.tag = tag
        lead = User(email=f"lakshmi{tag}@x.com", display_name="Lakshmi")
        db.add(lead)
        db.flush()
        self.project = Project(title="Velugu Cove", lead_user_id=lead.id, state="PLEDGING", currency="USD")
        db.add(self.project)
        db.flush()
        self.lead = ProjectMember(project_id=self.project.id, user_id=lead.id, role="LEAD")
        arjun = User(email=f"arjun{tag}@x.com", display_name="Arjun")
        db.add_all([self.lead, arjun])
        db.flush()
        fm = ProjectMember(project_id=self.project.id, user_id=arjun.id, role="FREELANCER", paypal_email=f"arjun{tag}@sandbox.com")
        db.add(fm)
        db.flush()
        brd = BRD(project_id=self.project.id, version=1, status="APPROVED", content_json={}, content_md="",
                  sha256="b" * 64, score_at_generation=93, locked_at=NOW)
        db.add(brd)
        db.flush()
        self.contract = Contract(project_id=self.project.id, brd_id=brd.id, brd_sha256=brd.sha256,
                                 freelancer_member_id=fm.id, freelancer_paypal_email=f"arjun{tag}@sandbox.com",
                                 amount_cents=GOAL, delivery_days=5, terms_md="t", sha256="c" * 64, signed_at=NOW)
        self.campaign = Campaign(project_id=self.project.id, number=1, proposer_member_id=self.lead.id, goal_cents=GOAL,
                                 deadline_at=NOW + timedelta(hours=40), state="OPEN", opens_at=NOW - timedelta(hours=8))
        db.add_all([self.contract, self.campaign])
        db.flush()
        self.n = 0

    def pledge(self, cents, status="AUTHORIZED", honor_hours=60, campaign=None, **kw) -> Pledge:
        self.n += 1
        c = campaign or self.campaign
        p = Pledge(campaign_id=c.id, project_id=self.project.id, display_name=f"P{self.n}", amount_cents=cents,
                   paypal_order_id=f"ORDER{self.tag}{self.n}", paypal_authorization_id=f"AUTH{self.tag}{self.n}", status=status,
                   authorized_at=NOW, honor_until=NOW + timedelta(hours=honor_hours), **kw)
        self.db.add(p)
        self.db.flush()
        return p

    def capture_all(self):
        """Pretend the capture plan ran: pledges CAPTURED, POOL funded, campaign CAPTURED."""
        for p in self.db.scalars(select(Pledge).where(Pledge.status == "AUTHORIZED")):
            p.status, p.captured_cents, p.paypal_capture_id = "CAPTURED", p.amount_cents, f"CAP{p.id}"
            ledger.append(self.db, self.project.id, "PLEDGE_CAPTURED", p.amount_cents, actor="paypal")
        self.campaign.state = "CAPTURED"
        self.db.flush()

    def verified_report(self, overall="VERIFIED", attempt=1):
        sub = Submission(contract_id=self.contract.id, attempt_no=attempt, repo_url="r", commit_sha="s", deployed_url="u")
        self.db.add(sub)
        self.db.flush()
        rep = VerificationReport(submission_id=sub.id, verdicts_json=[], overall=overall, must_pass_pct=100,
                                 should_pass_pct=100, summary="ok", sha256=("d" if overall == "VERIFIED" else "e") * 64)
        self.db.add(rep)
        self.db.flush()
        return rep


