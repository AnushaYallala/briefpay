"""All SPEC section 6.2 tables. This is a contract: change SPEC + DECISIONS together."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigInt, created, pk, utcnow


def fk(target: str, nullable: bool = False):
    return mapped_column(BigInt, ForeignKey(target), nullable=nullable)


def ts():
    return mapped_column(nullable=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = pk()
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = created()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = pk()
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lead_user_id: Mapped[int] = fk("users.id")
    budget_cents: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    state: Mapped[str] = mapped_column(String(32), default="DRAFT")
    payout_release_policy: Mapped[str] = mapped_column(String(32), default="HUMAN")
    delivery_days: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)
    id: Mapped[int] = pk()
    project_id: Mapped[int] = fk("projects.id")
    user_id: Mapped[int] = fk("users.id")
    role: Mapped[str] = mapped_column(String(16))  # LEAD|SPONSOR|SUPPORTER|FREELANCER
    business_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_pledge_cents: Mapped[int | None] = mapped_column(nullable=True)
    invite_status: Mapped[str] = mapped_column(String(16), default="INVITED")
    last_seen_at: Mapped[datetime | None] = ts()
    paypal_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invited_at: Mapped[datetime] = created()
    joined_at: Mapped[datetime | None] = ts()


class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[int] = pk()
    project_id: Mapped[int] = fk("projects.id")
    uploaded_by: Mapped[int] = fk("users.id")
    source_name: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    line_count: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created()


class BASession(Base):
    __tablename__ = "ba_sessions"
    id: Mapped[int] = pk()
    project_id: Mapped[int] = fk("projects.id")
    state: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    round: Mapped[int] = mapped_column(default=0)
    current_score: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class BAQuestion(Base):
    __tablename__ = "ba_questions"
    id: Mapped[int] = pk()
    session_id: Mapped[int] = fk("ba_sessions.id")
    round: Mapped[int]
    dimension: Mapped[str] = mapped_column(String(8))
    question: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    addressed_to_json: Mapped[list] = mapped_column(JSON)
    suggested_options_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="OPEN")
    created_at: Mapped[datetime] = created()


class BAAnswer(Base):
    __tablename__ = "ba_answers"
    id: Mapped[int] = pk()
    question_id: Mapped[int] = fk("ba_questions.id")
    member_id: Mapped[int] = fk("project_members.id")
    answer_text: Mapped[str] = mapped_column(Text)
    selected_option: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = created()


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = pk()
    project_id: Mapped[int | None] = fk("projects.id", True)
    agent: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(16))
    input_hash: Mapped[str] = mapped_column(String(64))
    latency_ms: Mapped[int] = mapped_column(default=0)
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created()


class BAScore(Base):
    __tablename__ = "ba_scores"
    id: Mapped[int] = pk()
    session_id: Mapped[int] = fk("ba_sessions.id")
    round: Mapped[int]
    total: Mapped[int]
    dimensions_json: Mapped[list] = mapped_column(JSON)
    gates_json: Mapped[dict] = mapped_column(JSON)
    capped: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted_requirements_json: Mapped[list] = mapped_column(JSON)
    conflicts_json: Mapped[list] = mapped_column(JSON)
    agent_run_id: Mapped[int | None] = fk("agent_runs.id", True)
    created_at: Mapped[datetime] = created()


class BRD(Base):
    __tablename__ = "brds"
    id: Mapped[int] = pk()
    project_id: Mapped[int] = fk("projects.id")
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    content_json: Mapped[dict] = mapped_column(JSON)
    content_md: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    score_at_generation: Mapped[int]
    open_items_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = created()
    locked_at: Mapped[datetime | None] = ts()


class BRDRequirement(Base):
    __tablename__ = "brd_requirements"
    id: Mapped[int] = pk()
    brd_id: Mapped[int] = fk("brds.id")
    code: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(8))
    weight: Mapped[int] = mapped_column(default=1)
    acceptance_criteria_json: Mapped[list] = mapped_column(JSON)
    evidence_types_json: Mapped[list] = mapped_column(JSON, default=list)
    source_refs_json: Mapped[list] = mapped_column(JSON, default=list)


class BRDApproval(Base):
    __tablename__ = "brd_approvals"
    __table_args__ = (UniqueConstraint("brd_id", "member_id"),)
    id: Mapped[int] = pk()
    brd_id: Mapped[int] = fk("brds.id")
    member_id: Mapped[int] = fk("project_members.id")
    decision: Mapped[str] = mapped_column(String(8))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    brd_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created()


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = pk()
    project_id: Mapped[int] = fk("projects.id")
    brd_id: Mapped[int] = fk("brds.id")
    brd_sha256: Mapped[str] = mapped_column(String(64))
    freelancer_member_id: Mapped[int] = fk("project_members.id")
    freelancer_paypal_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    delivery_days: Mapped[int]
    conditional: Mapped[bool] = mapped_column(Boolean, default=True)
    terms_md: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    signed_at: Mapped[datetime | None] = ts()
    effective_at: Mapped[datetime | None] = ts()


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (UniqueConstraint("project_id", "number"),)
    id: Mapped[int] = pk()
    project_id: Mapped[int] = fk("projects.id")
    number: Mapped[int]
    proposer_member_id: Mapped[int] = fk("project_members.id")
    goal_cents: Mapped[int]
    fee_reserve_cents: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    min_pledge_cents: Mapped[int] = mapped_column(default=500)
    suggested_share_cents: Mapped[int | None] = mapped_column(nullable=True)
    close_policy: Mapped[str] = mapped_column(String(16), default="EARLY_ON_GOAL")
    opens_at: Mapped[datetime | None] = ts()
    deadline_at: Mapped[datetime]
    goal_reached_at: Mapped[datetime | None] = ts()
    closed_at: Mapped[datetime | None] = ts()
    state: Mapped[str] = mapped_column(String(16), default="SETUP")
    fail_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = created()


class Pledge(Base):
    __tablename__ = "pledges"
    id: Mapped[int] = pk()
    campaign_id: Mapped[int] = fk("campaigns.id")
    project_id: Mapped[int] = fk("projects.id")
    member_id: Mapped[int | None] = fk("project_members.id", True)
    supporter_user_id: Mapped[int | None] = fk("users.id", True)
    display_name: Mapped[str] = mapped_column(String(120))
    paypal_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    paypal_authorization_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    payer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_cents: Mapped[int]
    captured_cents: Mapped[int] = mapped_column(default=0)
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    refunded_cents: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(12), default="CREATED")
    authorized_at: Mapped[datetime | None] = ts()
    honor_until: Mapped[datetime | None] = ts()
    valid_until: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created()


class StrategistReport(Base):
    __tablename__ = "strategist_reports"
    id: Mapped[int] = pk()
    campaign_id: Mapped[int] = fk("campaigns.id")
    forecast_json: Mapped[dict] = mapped_column(JSON)
    suggestions_json: Mapped[dict] = mapped_column(JSON)
    narrative_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    nudges_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    agent_run_id: Mapped[int | None] = fk("agent_runs.id", True)
    created_at: Mapped[datetime] = created()


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = pk()
    contract_id: Mapped[int] = fk("contracts.id")
    attempt_no: Mapped[int]
    repo_url: Mapped[str] = mapped_column(String(500))
    commit_sha: Mapped[str] = mapped_column(String(64))
    deployed_url: Mapped[str] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="SUBMITTED")
    created_at: Mapped[datetime] = created()


class AutoCheck(Base):
    __tablename__ = "auto_checks"
    id: Mapped[int] = pk()
    submission_id: Mapped[int] = fk("submissions.id")
    check_type: Mapped[str] = mapped_column(String(24))
    requirement_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    input_json: Mapped[dict] = mapped_column(JSON)
    result: Mapped[str] = mapped_column(String(8))
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = created()


class VerificationQuestion(Base):
    __tablename__ = "verification_questions"
    id: Mapped[int] = pk()
    submission_id: Mapped[int] = fk("submissions.id")
    requirement_code: Mapped[str] = mapped_column(String(16))
    criterion_id: Mapped[str] = mapped_column(String(32))
    question: Mapped[str] = mapped_column(Text)
    expected_evidence_json: Mapped[list] = mapped_column(JSON, default=list)
    round: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(12), default="OPEN")
    created_at: Mapped[datetime] = created()


class Image(Base):
    __tablename__ = "images"
    id: Mapped[int] = pk()
    project_id: Mapped[int] = fk("projects.id")
    uploaded_by: Mapped[int] = fk("users.id")
    provider: Mapped[str] = mapped_column(String(12))
    public_id: Mapped[str] = mapped_column(String(255), unique=True)
    delivery_type: Mapped[str] = mapped_column(String(16), default="authenticated")
    format: Mapped[str | None] = mapped_column(String(8), nullable=True)
    bytes: Mapped[int | None] = mapped_column(nullable=True)
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = created()


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = pk()
    submission_id: Mapped[int] = fk("submissions.id")
    question_id: Mapped[int | None] = fk("verification_questions.id", True)
    kind: Mapped[str] = mapped_column(String(16))
    image_id: Mapped[int | None] = fk("images.id", True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created()


class VerificationReport(Base):
    __tablename__ = "verification_reports"
    id: Mapped[int] = pk()
    submission_id: Mapped[int] = fk("submissions.id")
    verdicts_json: Mapped[list] = mapped_column(JSON)
    overall: Mapped[str] = mapped_column(String(16))
    must_pass_pct: Mapped[int]
    should_pass_pct: Mapped[int]
    summary: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    agent_run_id: Mapped[int | None] = fk("agent_runs.id", True)
    created_at: Mapped[datetime] = created()


class MoneyPlan(Base):
    __tablename__ = "money_plans"
    id: Mapped[int] = pk()
    project_id: Mapped[int] = fk("projects.id")
    campaign_id: Mapped[int | None] = fk("campaigns.id", True)
    contract_id: Mapped[int | None] = fk("contracts.id", True)
    kind: Mapped[str] = mapped_column(String(24))
    plan_json: Mapped[dict] = mapped_column(JSON)
    plan_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="PROPOSED")
    reason: Mapped[str | None] = mapped_column(String(48), nullable=True)
    proposed_by: Mapped[str] = mapped_column(String(32))
    release_policy: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class MoneyPlanStep(Base):
    __tablename__ = "money_plan_steps"
    id: Mapped[int] = pk()
    plan_id: Mapped[int] = fk("money_plans.id")
    seq: Mapped[int]
    phase: Mapped[int] = mapped_column(default=1)
    op: Mapped[str] = mapped_column(String(16))
    target_type: Mapped[str] = mapped_column(String(12))
    target_id: Mapped[int]
    amount_cents: Mapped[int]
    bucket: Mapped[str] = mapped_column(String(8))
    receiver_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paypal_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(12), default="PENDING")
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class GuardianReview(Base):
    __tablename__ = "guardian_reviews"
    id: Mapped[int] = pk()
    plan_id: Mapped[int] = fk("money_plans.id")
    plan_hash: Mapped[str] = mapped_column(String(64))
    rule_results_json: Mapped[list] = mapped_column(JSON)
    soft_flags_json: Mapped[list] = mapped_column(JSON, default=list)
    llm_review_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decision: Mapped[str] = mapped_column(String(8))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    sha256: Mapped[str] = mapped_column(String(64))
    agent_run_id: Mapped[int | None] = fk("agent_runs.id", True)
    created_at: Mapped[datetime] = created()


class PlanApproval(Base):
    __tablename__ = "plan_approvals"
    id: Mapped[int] = pk()
    plan_id: Mapped[int] = fk("money_plans.id")
    plan_hash: Mapped[str] = mapped_column(String(64))
    guardian_review_id: Mapped[int] = fk("guardian_reviews.id")
    approver: Mapped[str] = mapped_column(String(32))
    ack_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created()


class PayoutBatch(Base):
    __tablename__ = "payout_batches"
    id: Mapped[int] = pk()
    plan_id: Mapped[int] = fk("money_plans.id")
    sender_batch_id: Mapped[str] = mapped_column(String(64), unique=True)
    paypal_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    created_at: Mapped[datetime] = created()


class PayoutItem(Base):
    __tablename__ = "payout_items"
    id: Mapped[int] = pk()
    batch_id: Mapped[int] = fk("payout_batches.id")
    step_id: Mapped[int] = fk("money_plan_steps.id")
    purpose: Mapped[str] = mapped_column(String(16), default="FREELANCER")
    pledge_id: Mapped[int | None] = fk("pledges.id", True)
    receiver_email: Mapped[str] = mapped_column(String(255))
    amount_cents: Mapped[int]
    sender_item_id: Mapped[str] = mapped_column(String(64), unique=True)
    paypal_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[int] = pk()
    pledge_id: Mapped[int] = fk("pledges.id")
    step_id: Mapped[int] = fk("money_plan_steps.id")
    amount_cents: Mapped[int]
    paypal_refund_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    reason: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    created_at: Mapped[datetime] = created()


class LedgerEntry(Base):
    """Append-only (enforced by LedgerService, T-07). seq is gapless per project (I-4)."""

    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("project_id", "seq"),)
    id: Mapped[int] = pk()
    project_id: Mapped[int] = fk("projects.id")
    seq: Mapped[int]
    bucket: Mapped[str] = mapped_column(String(8))
    type: Mapped[str] = mapped_column(String(24))
    amount_cents: Mapped[int]
    ref_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor: Mapped[str] = mapped_column(String(48))
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = created()


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[int] = pk()
    paypal_event_id: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = ts()
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created()


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = pk()
    type: Mapped[str] = mapped_column(String(48))
    payload_json: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(10), default="QUEUED")
    attempts: Mapped[int] = mapped_column(default=0)
    run_after: Mapped[datetime] = mapped_column(default=utcnow)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
