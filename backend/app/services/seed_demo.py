"""Demo seed (T-52): the Velugu Cove story, built through the REAL services so the data is genuine, with a clock shifted into the past.

  Project A  "Velugu Cove tourism website"
             BRD approved by all three sponsors, contract signed, campaign round 1 launched, $300 of $400 pledged, the deadline
             missed. The Guardian reviewed the release plan (ALLOW), the three holds are voided, nothing was charged.
             Project state: CAMPAIGN_FAILED  (the lead relaunches in the demo).
  Project B  "Velugu Cove tourism website (build phase)"
             The same story one round on: $400 pledged and captured through a capture plan the Guardian allowed; the freelancer
             submitted twice (attempt 1 NEEDS_CHANGES: the enquiry form was missing on the live site; attempt 2 VERIFIED).
             Project state: PAYOUT_READY  (the demo builds, tampers with and approves the payout).

No PayPal call is made, ever: plan steps are marked as sent and then confirmed the same way a webhook does it. Ids that look like
PayPal ids start with SEED-. People are fictional and use the documentation domain `velugu.example.com`.
The freelancer's PayPal email is a placeholder unless the real sandbox account's email is passed (the payout goes there).
Only allowed when DEMO_MODE is on. Safe to run twice: the second run changes nothing.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (AutoCheck, BRD, Contract, Evidence, Job, MoneyPlanStep, Pledge, Project, ProjectMember, Submission, User,
                        VerificationQuestion)
from app.schemas.brd import BRDDraft
from app.schemas.verify import ACVerdict
from app.services import (brd_approvals, brd_service, campaign_ops, contract_service, ledger, plan_builder as pb, plan_lifecycle as lc,
                          project_ops, submission_service, verify_judge, verify_questions)
from app.services.brd_service import AssembleContext
from app.services.guardian_rules import PayPalObject
from app.services.state_machines import CampaignService, ProjectService
from app.services.verify_aggregate import aggregate

DOMAIN = "velugu.example.com"          # example.com is reserved for documentation (no real inbox) and, unlike .test, passes email validation
TITLE_A = "Velugu Cove tourism website"
TITLE_B = "Velugu Cove tourism website (build phase)"
GOAL_CENTS = 40000
TRANSCRIPT_LINES = 30
PEOPLE = {
    "lakshmi": ("Lakshmi", "LEAD", "Sea Breeze Homestay", "Homestay", 15000),
    "ravi": ("Ravi", "SPONSOR", "Ravi's Fish Kitchen", "Restaurant", 10000),
    "meena": ("Meena", "SPONSOR", "Cove Boat Tours", "Boat tours", 5000),
    "arjun": ("Arjun", "FREELANCER", None, None, None),
}
DEFAULT_REPO = "https://github.com/arjun-demo/velugu-cove-site"
DEFAULT_SITE = "https://velugu-cove-demo.example.com"
DEFAULT_COMMITS = ("1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d", "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432")


class SeedError(Exception):
    pass


def email(key: str) -> str:
    return f"{key}@{DOMAIN}"


# =============================== the BRD ===============================

def _ac(given, when, then, evidence, hint=None):
    return {"given": given, "when": when, "then": then, "evidence": list(evidence), "auto_check_hint": hint}


def _req(title, description, priority, weight, by, criteria, refs):
    return {"from_temp_ids": [], "title": title, "description": description, "priority": priority, "weight": weight,
            "requested_by": list(by), "acceptance_criteria": criteria, "source_refs": refs}


def draft(ids: dict[str, int]) -> BRDDraft:
    """Nine requirements, as in the demo: six MUST (the enquiry form comes out as REQ-006) and three SHOULD."""
    L, R, M = ids["lakshmi"], ids["ravi"], ids["meena"]
    live = ("LIVE_URL_CHECK",)
    must = [
        _req("Welcome page", "A home page that says what Velugu Cove is and links to everything.", "MUST", 3, [L, R, M],
             [_ac("a visitor opens the site", "the home page loads", "it welcomes them and links to every page", live, {"type": "URL_REACHABLE", "path": "/"})], ["L1-L4"]),
        _req("Homestay page", "Rooms and how to reach the homestay.", "MUST", 4, [L],
             [_ac("a visitor opens the stay page", "the page loads", "the homestay and its rooms are shown", live, {"type": "PAGE_CONTAINS", "path": "/stay", "text": "Sea Breeze Homestay"})], ["L5-L6"]),
        _req("Menu and timings", "The restaurant menu and opening hours.", "MUST", 3, [R],
             [_ac("a visitor opens the menu page", "the page loads", "the menu and timings are shown", live, {"type": "PAGE_CONTAINS", "path": "/menu", "text": "Ravi's Fish Kitchen"})], ["L7-L8"]),
        _req("Boat tours and safety", "The morning and sunset tours, with safety information.", "MUST", 4, [M],
             [_ac("a visitor opens the tours page", "the page loads", "both tours are listed", live, {"type": "PAGE_CONTAINS", "path": "/tours", "text": "Sunset tour"}),
              _ac("a worried visitor looks for safety information", "they read the tours page", "the safety information is clearly visible", ("SCREENSHOT",))], ["L9-L10"]),
        _req("Directions", "How to find the cove: the road is confusing.", "MUST", 3, [R],
             [_ac("a visitor opens the directions page", "the page loads", "clear directions are shown", live, {"type": "PAGE_CONTAINS", "path": "/getting-there", "text": "Directions"})], ["L8"]),
        _req("Enquiry form", "A form to contact the businesses; no online payments on the site.", "MUST", 5, [L, M],
             [_ac("a visitor opens the contact page", "they fill in the enquiry form and send it", "a confirmation message is shown",
                  ("LIVE_URL_CHECK", "SCREENSHOT", "CODE_SNIPPET"), {"type": "PAGE_CONTAINS", "path": "/contact", "text": "Send enquiry"})], ["L11-L13"]),
    ]
    should = [
        _req("WhatsApp button", "A button to message the businesses on WhatsApp.", "SHOULD", 2, [M],
             [_ac("a visitor is on the contact page", "they look for WhatsApp", "a WhatsApp button is shown", live, {"type": "PAGE_CONTAINS", "path": "/contact", "text": "WhatsApp"})], ["L22"]),
        _req("Works on phones", "Most visitors use phones.", "SHOULD", 3, [L],
             [_ac("a visitor uses a phone", "they open any page", "the layout fits the screen", live, {"type": "MOBILE_VIEWPORT"})], ["L21"]),
        _req("Photo gallery", "Photos of the cove and the sunset.", "SHOULD", 1, [L, R],
             [_ac("a visitor opens the gallery", "the page loads", "photos are shown", live, {"type": "URL_REACHABLE", "path": "/gallery"})], ["L14-L15"]),
    ]
    return BRDDraft.model_validate({
        "title": TITLE_A,
        "executive_summary": "One simple website that shows Velugu Cove's homestay, restaurant and boat tours, gives directions and lets visitors send an enquiry.",
        "business_goals": ["Help visitors find the cove's businesses", "Let visitors get in touch easily"],
        "success_measures": ["At least 20 enquiries a month in the first season"],
        "audience": "Tourists from nearby cities, mostly on phones, reading English.",
        "sitemap": [{"path": "/", "purpose": "Welcome and links to everything"}, {"path": "/stay", "purpose": "The homestay and its rooms"},
                    {"path": "/menu", "purpose": "The restaurant menu and timings"}, {"path": "/tours", "purpose": "Boat tours and safety"},
                    {"path": "/getting-there", "purpose": "Directions to the cove"}, {"path": "/contact", "purpose": "The enquiry form and WhatsApp"},
                    {"path": "/gallery", "purpose": "Photos"}],
        "non_functional": ["Works well on mobile phones", "English; Telugu may follow later"],
        "content_responsibilities": [{"item": "Room photos and prices", "owner_member_id": L, "due": "Nov 20"},
                                     {"item": "Menu and timings", "owner_member_id": R, "due": "Nov 20"},
                                     {"item": "Tour times and safety text", "owner_member_id": M, "due": "Nov 20"}],
        "out_of_scope": ["Online payments on the site", "Telugu translation"],
        "open_items": [], "glossary": [{"term": "Enquiry", "definition": "A message from a visitor asking about a stay, a meal or a tour."}],
        "requirements": must + should, "hosting": None, "domain": None,
    })


# =============================== a stand-in for PayPal's own records ===============================

class SeedReader:
    """What PayPal would say about the seeded holds and captures: it mirrors our own rows. Read-only."""

    def __init__(self, db: Session):
        self.db = db

    def get_authorization(self, authorization_id):
        p = self.db.scalars(select(Pledge).where(Pledge.paypal_authorization_id == authorization_id)).first()
        return None if p is None else PayPalObject("CREATED" if p.status == "AUTHORIZED" else "CAPTURED", p.amount_cents)

    def get_capture(self, capture_id):
        p = self.db.scalars(select(Pledge).where(Pledge.paypal_capture_id == capture_id)).first()
        return None if p is None else PayPalObject("COMPLETED", p.captured_cents)

    def get_refund(self, refund_id):
        return None

    def platform_balance_cents(self):
        return None


# =============================== building blocks ===============================

def _finish_plan(db: Session, plan, review, now: datetime) -> None:
    """Run an approved plan to its end WITHOUT touching PayPal: mark the steps sent, then confirm them the way a webhook does."""
    if plan.state != "APPROVED":
        failed = [r["id"] for r in review.rule_results_json if r.get("status") == "FAIL"]
        raise SeedError(f"the Guardian did not allow the {plan.kind} plan ({review.decision}); failed rules: {failed}")
    for job in db.scalars(select(Job).where(Job.type == "EXECUTE_PLAN")):
        if (job.payload_json or {}).get("plan_id") == plan.id:
            job.state, job.result_json = "DONE", {"seeded": True}            # nothing may ever execute this on the real writer
    plan.state = "EXECUTING"
    steps = list(db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id).order_by(MoneyPlanStep.seq)))
    for s in steps:
        s.state, s.paypal_ref = "SENT", f"SEED-{s.op}-{s.id}"
    db.flush()
    for s in steps:
        lc.confirm_step(db, s, paypal_ref=s.paypal_ref, now=now)


def _pledge(db: Session, campaign, member: ProjectMember, cents: int, at: datetime, tag: str) -> Pledge:
    user = db.get(User, member.user_id)
    p = Pledge(campaign_id=campaign.id, project_id=campaign.project_id, member_id=member.id, supporter_user_id=user.id,
               display_name=user.display_name, paypal_order_id=f"SEED-ORDER-{campaign.id}-{tag}", paypal_authorization_id=f"SEED-AUTH-{campaign.id}-{tag}",
               payer_email=user.email, payer_id=f"SEEDPAYER{tag.upper()}", amount_cents=cents, status="AUTHORIZED", authorized_at=at,
               honor_until=at + timedelta(hours=72))
    db.add(p)
    db.flush()
    ledger.append(db, campaign.project_id, "PLEDGE_AUTHORIZED", actor="paypal", ref_type="pledge", ref_id=p.id, meta={"authorization_id": p.paypal_authorization_id})
    return p


def _users(db: Session) -> dict[str, User]:
    out = {}
    for key, (name, *_rest) in PEOPLE.items():
        u = User(email=email(key), display_name=name)
        db.add(u)
        out[key] = u
    db.flush()
    return out


def _project_up_to_campaign(db: Session, users: dict[str, User], title: str, t0: datetime, deadline_hours: int, paypal_email: str) -> tuple[Project, dict[str, ProjectMember], object]:
    """Create the project, take it through BRD approval and the signed contract, and launch campaign round 1 at `t0`."""
    _name, _role, biz, kind, pledge = PEOPLE["lakshmi"]
    project = project_ops.create_project(db, users["lakshmi"], title=title, summary="One website for the businesses of Velugu Cove.",
                                         location_label="Velugu Cove", budget_cents=GOAL_CENTS, delivery_days=5, payout_release_policy="HUMAN",
                                         lead_business_name=biz, lead_business_type=kind, lead_expected_pledge_cents=pledge)
    members = {"lakshmi": db.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.role == "LEAD")).one()}
    for key in ("ravi", "meena", "arjun"):
        _n, role, biz, kind, pledge = PEOPLE[key]
        m = ProjectMember(project_id=project.id, user_id=users[key].id, role=role, business_name=biz, business_type=kind,
                          expected_pledge_cents=pledge, invite_status="VIEWED", joined_at=t0)
        db.add(m)
        members[key] = m
    db.flush()

    ProjectService.transition(db, project, "REQUIREMENTS", actor="seed", reason="transcript uploaded")
    ProjectService.transition(db, project, "BRD_REVIEW", actor="seed", reason="BA score 93, BRD generated")
    ids = {k: members[k].id for k in ("lakshmi", "ravi", "meena")}
    content = brd_service.assemble(draft(ids), AssembleContext(
        sponsor_ids=set(ids.values()), sponsor_business={members[k].id: members[k].business_name for k in ids}, line_count=TRANSCRIPT_LINES,
        answer_ids=set(), analysis_ids=[], out_of_scope=[], project={"title": title, "budget_cents": GOAL_CENTS, "currency": "USD", "delivery_days": 5},
        code_open_items=[]))
    brd = brd_service.store_brd(db, project, content, score=93)
    for key in ("lakshmi", "ravi", "meena"):
        brd_approvals.decide(db, project, brd, members[key], "APPROVE", brd.sha256, None)
    offer = contract_service.offer(db, project, GOAL_CENTS, 5)
    contract_service.accept(db, project, members["arjun"], paypal_email, brd.sha256, offer.sha256)
    campaign = campaign_ops.setup_campaign(db, project, members["lakshmi"], deadline_at=t0 + timedelta(hours=deadline_hours), close_policy=None,
                                           min_pledge_cents=None, suggested_share_cents=None, now=t0)
    campaign_ops.launch(db, project, campaign, now=t0)
    return project, members, campaign


def _failed_round(db: Session, users, now: datetime, paypal_email: str) -> Project:
    t0 = now - timedelta(hours=52)
    project, members, campaign = _project_up_to_campaign(db, users, TITLE_A, t0, 48, paypal_email)
    for tag, key, cents, h in (("lak", "lakshmi", 15000, 6), ("rav", "ravi", 10000, 20), ("mee", "meena", 5000, 30)):
        _pledge(db, campaign, members[key], cents, t0 + timedelta(hours=h), tag)
    CampaignService.transition(db, campaign, "FAILING", actor="system", fail_reason="DEADLINE_MISSED")
    plan = pb.save_proposed(db, pb.build_release_holds(db, campaign.id, "DEADLINE_MISSED"), proposed_by="system")
    review = lc.review_plan(db, plan, reader=SeedReader(db), now=now)
    _finish_plan(db, plan, review, now)
    return project


def _text_evidence(db: Session, sub: Submission, q: VerificationQuestion) -> list[Evidence]:
    rows = [Evidence(submission_id=sub.id, question_id=q.id, kind="TEXT", text=f"Screenshot of {q.requirement_code} / {q.criterion_id} on the live site (seed data: no image).",
                     sha256=f"seed-text-{sub.id}-{q.id}")]
    if q.requirement_code == "REQ-006":
        rows.append(Evidence(submission_id=sub.id, question_id=q.id, kind="REPO_PATH", text="src/contact.js", sha256=f"seed-path-{sub.id}-{q.id}"))
        rows.append(Evidence(submission_id=sub.id, question_id=q.id, kind="CODE_SNIPPET", text="form.addEventListener('submit', sendEnquiry);",
                             sha256=f"seed-code-{sub.id}-{q.id}"))
    db.add_all(rows)
    db.flush()
    return rows


def _submission(db: Session, project: Project, members, contract: Contract, attempt: int, repo: str, site: str, commit: str, now: datetime) -> Submission:
    """One attempt: automatic checks, questions and answers, verdicts, and the report, all through the real rules."""
    ProjectService.transition(db, project, "VERIFYING", actor=f"user:{members['arjun'].user_id}", reason=f"submission attempt {attempt}")
    sub = Submission(contract_id=contract.id, attempt_no=attempt, repo_url=repo, commit_sha=commit, deployed_url=site,
                     notes="Seed data: the sample site is built by the demo freelancer.", state="AUTO_CHECKING")
    db.add(sub)
    db.flush()
    brd = db.get(BRD, contract.brd_id)
    checks = []
    for item in submission_service.plan_checks(brd.content_json, sub):
        broken = attempt == 1 and item["check_type"] == "PAGE_CONTAINS" and item["requirement_code"] == "REQ-006"
        row = AutoCheck(submission_id=sub.id, check_type=item["check_type"], requirement_code=item["requirement_code"],
                        input_json={**item["inputs"], **({"criterion_id": item["criterion_id"]} if item["criterion_id"] else {})},
                        result="FAIL" if broken else "PASS", detail_json={"seed": True, **({"found": False} if broken else {})})
        db.add(row)
        checks.append(row)
    db.flush()

    asked, verdicts = {}, []
    for c in verify_questions.needed_criteria(brd.content_json, checks):
        q = VerificationQuestion(submission_id=sub.id, requirement_code=c["requirement_code"], criterion_id=c["criterion_id"],
                                 question=verify_questions.template_question(c), expected_evidence_json=c["evidence_needed"], round=1, status="ANSWERED")
        db.add(q)
        db.flush()
        rows = _text_evidence(db, sub, q)
        asked[(q.requirement_code, q.criterion_id)] = {e.id for e in rows}
        bad = attempt == 1 and q.requirement_code == "REQ-006"
        verdicts.append(ACVerdict(
            requirement_code=q.requirement_code, criterion_id=q.criterion_id, verdict="fail" if bad else "pass", confidence=0.92,
            rationale=("The screenshot shows the Stay page, not the enquiry form; the live contact page has no form." if bad
                       else f"The evidence shows {q.requirement_code} / {q.criterion_id} working on the live site."),
            evidence_ids=sorted(asked[(q.requirement_code, q.criterion_id)])[:1], contradicts_auto_check=bad))
    agg = aggregate(brd.content_json["requirements"], verify_judge.check_dicts(checks), verdicts, asked, set(), attempt_no=attempt, followup_done=False)
    expected = "NEEDS_CHANGES" if attempt == 1 else "VERIFIED"
    if agg.overall != expected:
        raise SeedError(f"seeded attempt {attempt} came out {agg.overall}, expected {expected}: {agg.reasons}")
    verify_judge.save_report(db, sub, project, agg, ai_summary="Seed data: written by the demo script, not by a model.", facts=[], run_id=None)
    return sub


def _funded_project(db: Session, users, now: datetime, repo: str, site: str, commits: tuple[str, str], paypal_email: str) -> Project:
    t0 = now - timedelta(hours=40)
    project, members, campaign = _project_up_to_campaign(db, users, TITLE_B, t0, 36, paypal_email)
    for tag, key, cents, h in (("lak", "lakshmi", 15000, 4), ("rav", "ravi", 15000, 10), ("mee", "meena", 10000, 18)):
        _pledge(db, campaign, members[key], cents, t0 + timedelta(hours=h), tag)
    plan = pb.save_proposed(db, pb.build_capture_pledges(db, campaign.id, now), proposed_by="system")
    review = lc.review_plan(db, plan, reader=SeedReader(db), now=now)      # the Guardian looks while the campaign is still OPEN
    CampaignService.transition(db, campaign, "CAPTURING", actor="system")
    campaign.goal_reached_at = t0 + timedelta(hours=18)
    _finish_plan(db, plan, review, now)

    contract = contract_service.get_contract(db, project.id)
    _submission(db, project, members, contract, 1, repo, site, commits[0], now)
    _submission(db, project, members, contract, 2, repo, site, commits[1], now)
    return project


def seed_demo(db: Session, *, now: datetime | None = None, repo_url: str = DEFAULT_REPO, site_url: str = DEFAULT_SITE,
              commits: tuple[str, str] = DEFAULT_COMMITS, freelancer_paypal_email: str | None = None) -> dict:
    if not get_settings().demo_mode:
        raise SeedError("the demo seed only runs with DEMO_MODE on")
    if db.scalars(select(User.id).where(User.email == email("lakshmi"))).first() is not None:
        return {"already_seeded": True, "projects": [p.id for p in db.scalars(select(Project).where(Project.title.in_((TITLE_A, TITLE_B))).order_by(Project.id))]}
    now = now or datetime.now(timezone.utc)
    users = _users(db)
    paypal_email = (freelancer_paypal_email or f"arjun-sandbox@{DOMAIN}").strip().lower()
    a = _failed_round(db, users, now, paypal_email)
    b = _funded_project(db, users, now, repo_url, site_url, commits, paypal_email)
    db.flush()
    return {"already_seeded": False, "failed_round_project_id": a.id, "payout_ready_project_id": b.id,
            "login_emails": {k: email(k) for k in PEOPLE}, "freelancer_paypal_email": paypal_email}
