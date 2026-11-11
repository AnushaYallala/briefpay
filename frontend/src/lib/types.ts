/** Shapes returned by the API (SPEC 10). Only what the screens use so far; amounts are always whole cents. */
export type User = { id: number; email: string; display_name: string };
export type Membership = { member_id: number; project_id: number; role: "LEAD" | "SPONSOR" | "SUPPORTER" | "FREELANCER" };

export type CampaignSummary = {
  id: number;
  number: number;
  state: string;
  goal_cents: number;
  pledged_cents: number;
  pledge_count: number;
  deadline_at: string | null;
};

export type ProjectCard = {
  id: number;
  title: string;
  summary: string | null;
  location_label: string | null;
  state: string;
  budget_cents: number;
  currency: string;
  campaign: CampaignSummary | null;
};

export type Member = {
  id: number;
  role: "LEAD" | "SPONSOR" | "SUPPORTER" | "FREELANCER";
  display_name: string;
  business_name: string | null;
  business_type: string | null;
  // present for signed-in members only (the screens do not show contact details)
  email?: string;
  invite_status?: string;
  last_seen_at?: string | null;
  paypal_email?: string | null;
  expected_pledge_cents?: number | null;
};

export type ProjectDetail = ProjectCard & {
  delivery_days: number | null;
  payout_release_policy: string;
  created_at: string;
  members: Member[];
  viewer: { role: Membership["role"]; member_id: number } | null;
  transcript?: { id: number; source_name: string; line_count: number; uploaded_at: string } | null;
};

export type Money = {
  project_id: number;
  pool_balance_cents: number;
  holds: { count: number; total_cents: number; note: string };
  next_honor_deadline: string | null;
  campaign: { id: number; number: number; state: string; goal_cents: number; deadline_at: string } | null;
  contract_amount_cents: number | null;
  open_plans: { id: number; kind: string; state: string }[];
  unclaimed_payouts: number;
  alerts: { seq: number; created_at: string; meta: Record<string, unknown> }[];
};

export type LedgerRow = {
  seq: number;
  created_at: string;
  bucket: "POOL" | "NONE";
  type: string;
  counterparty: string | null;
  amount_cents: number;
  running_balance_cents: number;
  status: string | null;
  paypal_ref: string | null;
  actor: string;
  actor_name: string;
  ref_type: string | null;
  ref_id: string | null;
  paypal_match: null;
  alert: boolean;
  meta: Record<string, unknown>;
};

export type CampaignView = {
  id: number;
  project_id: number;
  project_title: string;
  number: number;
  state: string;
  goal_cents: number;
  fee_reserve_cents: number;
  currency: string;
  min_pledge_cents: number;
  suggested_share_cents: number | null;
  close_policy: string;
  opens_at: string | null;
  deadline_at: string;
  seconds_left: number;
  pledged_cents: number;
  pledge_count: number;
  remaining_need_cents: number;
  goal_reached_at: string | null;
  held_not_charged: boolean;
  fail_reason: string | null;
  lead?: { launch_blockers: string[]; can_launch: boolean; deadline_earliest: string; deadline_latest: string; earliest_honor_until: string | null };
};

export type Nudge = { member_id: number; name: string; channel: string; message: string; source: string; flags: string[]; reused: boolean };
export type StrategistReport = {
  id: number;
  created_at: string;
  forecast: {
    label: string; goal_cents: number; pledged_cents: number; gap_cents: number; hours_left: number;
    expected_invitees_cents: number; expected_open_cents: number; projected_cents: number; ratio: number; probability: number;
  };
  suggestions: {
    kind: string | null;
    deadline: { deadline_at: string; reason: string; hours?: number; initial_probability?: number } | null;
    nudge_targets: { member_id: number; name: string; invite_status: string; expected_pledge_cents: number; score: number; reason: string }[];
    campaign_state: string;
    applied_extension?: { from: string; to: string; at: string };
  };
  narrative: { headline: string; explanation: string; risk_factors: string[]; source: string; label: string; flags: string[] };
  nudges: Nudge[];
};

export type BrdCriterion = {
  id: string;
  given: string;
  when: string;
  then: string;
  evidence: string[];
  auto_check_hint: { type: string; path: string | null; text: string | null } | null;
};
export type BrdRequirement = {
  code: string;
  title: string;
  description: string;
  priority: string;
  weight: number;
  requested_by: number[];
  acceptance_criteria: BrdCriterion[];
  source_refs: string[];
};
export type BrdContent = {
  title: string;
  executive_summary: string;
  business_goals: string[];
  success_measures: string[];
  stakeholders: { member_id: number; business_name: string | null; needs: string[] }[];
  audience: string;
  sitemap: { path: string; purpose: string }[];
  non_functional: string[];
  content_responsibilities: { item: string; owner_member_id: number | null; due: string | null }[];
  out_of_scope: string[];
  open_items: string[];
  glossary: { term: string; definition: string }[];
  requirements: BrdRequirement[];
  constraints: { budget_cents: number; currency: string; delivery_days: number | null; hosting: string | null; domain: string | null };
};
export type BrdView = {
  id: number;
  version: number;
  status: string;
  sha256: string;
  score_at_generation: number | null;
  content: BrdContent;
  markdown: string;
  open_items: string[];
  approvals: { member_id: number; member_name: string | null; decision: string; comment: string | null; created_at: string }[];
  awaiting: { member_id: number; member_name: string | null }[];
  created_at: string;
  locked_at: string | null;
  versions: { version: number; status: string; sha256: string }[];
};
export type BrdDecisionResult = { changed: boolean; brd_version: number; brd_status: string; project_state: string; approved: number; required: number; locked: boolean };

export type BaDimension = {
  dimension: string;
  name: string;
  weight: number;
  coverage_claimed: number;
  coverage_effective: number;
  downgraded: boolean;
  justification: string;
  source_refs: string[];
};
export type BaGate = { id: string; title: string; passed: boolean; detail: string };
export type BaRequirement = {
  temp_id: string;
  title: string;
  description: string;
  priority: string;
  requested_by: number[];
  acceptance_criteria: string[];
  source_refs: string[];
};
export type BaConflict = { topic: string; positions: { member_id: number; position: string }[]; resolved: boolean; resolution: string | null };
export type BaScore = {
  round: number;
  total: number;
  capped: boolean;
  total_uncapped: number | null;
  dimensions: BaDimension[];
  gates: BaGate[];
  requirements: BaRequirement[];
  conflicts: BaConflict[];
  out_of_scope: string[];
  injection_attempts: string[];
  created_at: string;
};
export type BaHistory = { round: number; total: number; capped: boolean; created_at: string };
export type BaAnswer = { id: number; member_id: number; member_name: string | null; answer_text: string; selected_option: string | null };
export type BaQuestion = {
  id: number;
  round: number;
  dimension: string;
  dimension_name: string | null;
  question: string;
  rationale: string;
  addressed_to: (number | string)[];
  suggested_options: string[] | null;
  status: string;
  answers: BaAnswer[];
  can_answer: boolean;
};
export type BaView = {
  session: { id: number; state: string; round: number; current_score: number; target_score: number; max_rounds: number } | null;
  score: BaScore | null;
  history: BaHistory[];
  questions: BaQuestion[];
  can_run: boolean;
  can_finalize: boolean;
};
export type TranscriptResponse = {
  id: number;
  source_name: string;
  line_count: number;
  sha256: string;
  uploaded_at: string;
  lines: { n: number; text: string }[];
};
export type JobStatus = { state: string; result: Record<string, unknown> | null; error: string | null; attempts: number };

export type PlanListItem = {
  id: number;
  project_id: number;
  campaign_id: number | null;
  kind: string;
  state: string;
  reason: string | null;
  plan_hash: string;
  release_policy: string;
  proposed_by: string;
  created_at: string;
  decision: string | null;
};

export type PlanStep = {
  seq: number;
  phase: number;
  op: string;
  target_type: string;
  target_id: number;
  amount_cents: number;
  bucket: string;
  receiver_email: string | null;
  state: string;
  paypal_ref: string | null;
  error: Record<string, unknown> | null;
};

export type GuardianRule = { id: string; title: string; status: string; detail: string; paypal_verified: boolean };
export type SoftFlag = { id: string; title: string; detail: string };
export type LlmFinding = { type: string; detail: string; severity: string };
export type LlmReview = { status: string; risk_level?: string | null; explanation_for_sponsors?: string; findings?: LlmFinding[]; reason?: string };

export type GuardianReview = {
  id: number;
  plan_hash: string;
  decision: string;
  simulated: boolean;
  rules: GuardianRule[];
  soft_flags: SoftFlag[];
  llm: LlmReview | null;
  agent_run_id: number | null;
  created_at: string;
};

export type PlanApproval = { approver: string; plan_hash: string; ack_note: string | null; created_at: string };

export type PlanDetail = PlanListItem & {
  inputs: Record<string, unknown>;
  earliest_honor_until?: string | null;
  steps: PlanStep[];
  reviews: GuardianReview[];
  approvals: PlanApproval[];
};

export type PlansResponse = { plans: PlanListItem[] };
export type TamperResponse = { simulation: true; mutation: string; review: GuardianReview };

export type AgentRun = {
  id: number;
  created_at: string;
  agent: string;
  provider: string;
  model: string;
  prompt_version: string;
  input_hash: string;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  status: string;
  output: Record<string, unknown> | null;
  error: string | null;
};

export type AgentRunsResponse = { project_id: number; rows: AgentRun[] };

export type LedgerResponse = {
  project_id: number;
  public: boolean;
  rows: LedgerRow[];
  totals: { pool_in_cents: number; pool_out_cents: number; pool_balance_cents: number; rows: number };
};

export type MatchStatus = "MATCH" | "PENDING" | "MISMATCH" | "NOT_FOUND" | "UNAVAILABLE";
export type MatchResponse = {
  project_id: number;
  results: Record<string, { status: MatchStatus; detail: string; paypal_ref?: string; paypal_status?: string; paypal_cents?: number }>;
  counts: Record<MatchStatus, number>;
  limited: boolean;
  all_match: boolean;
};

export type BADimension = {
  dimension: string;
  name: string;
  coverage: number;
  justification: string;
  source_refs: string[];
};

export type BAGate = {
  id: string;
  name: string;
  passed: boolean;
  reason?: string;
};

export type BAQuestionAnswer = {
  id: number;
  member_id: number;
  member_name: string;
  answer_text: string;
  selected_option: string | null;
};

export type BAQuestionItem = {
  id: number;
  round: number;
  dimension: string;
  dimension_name: string;
  question: string;
  rationale: string;
  addressed_to: (number | "ALL")[];
  suggested_options: string[] | null;
  status: "OPEN" | "ANSWERED" | "SKIPPED";
  answers: BAQuestionAnswer[];
  can_answer: boolean;
};

export type BAHistoryItem = {
  round: number;
  total: number;
  capped: boolean;
  created_at: string;
};

export type BAResponse = {
  session: {
    id: number;
    state: "ACTIVE" | "READY" | "MAX_ROUNDS";
    round: number;
    current_score: number;
    target_score: number;
    max_rounds: number;
  } | null;
  score: {
    round: number;
    total: number;
    capped: boolean;
    total_uncapped?: number;
    dimensions: BADimension[];
    gates: BAGate[];
    conflicts: { topic: string; positions: { member_id: number; position: string }[]; resolved: boolean; resolution: string | null }[];
    out_of_scope: string[];
    injection_attempts: string[];
    created_at: string;
  } | null;
  history: BAHistoryItem[];
  questions: BAQuestionItem[];
  can_run: boolean;
  can_finalize: boolean;
};

export type BRDRequirementItem = {
  code: string;
  title: string;
  description: string;
  priority: "MUST" | "SHOULD" | "COULD";
  weight: number;
  requested_by: number[];
  acceptance_criteria: { id: string; given: string; when: string; then: string; evidence: string[] }[];
  source_refs: string[];
};

export type BRDApprovalItem = {
  member_id: number;
  member_name: string;
  decision: "APPROVE" | "REJECT";
  comment: string | null;
  created_at: string;
};

export type BRDResponse = {
  id: number;
  version: number;
  status: "DRAFT" | "LOCKED" | "APPROVED" | "REJECTED";
  sha256: string;
  score_at_generation: number;
  content: {
    title: string;
    executive_summary: string;
    business_goals: string[];
    success_measures: string[];
    requirements: BRDRequirementItem[];
  };
  markdown: string;
  open_items: string[];
  approvals: BRDApprovalItem[];
  awaiting: { member_id: number; member_name: string }[];
  created_at: string;
  locked_at: string | null;
  versions: { version: number; status: string; sha256: string }[];
};

export type ContractResponse = {
  id: number;
  status: "OFFERED" | "SIGNED";
  amount_cents: number;
  currency: string;
  delivery_days: number;
  conditional: boolean;
  terms_md: string;
  terms_sha256: string;
  brd_version: number;
  brd_sha256: string;
  freelancer_member_id: number;
  signed_at: string | null;
  effective_at: string | null;
  freelancer_paypal_email?: string | null;
};

export type AutoCheckItem = {
  id: number;
  check_type: string;
  target: string;
  result: "PASS" | "FAIL" | "ERROR";
  latency_ms: number;
  details: Record<string, unknown>;
  created_at: string;
};

export type EvidenceItem = {
  id: number;
  question_id: number;
  kind: string;
  image_id: number | null;
  text: string | null;
  url: string | null;
  sha256: string;
  created_at: string;
};

export type VerificationQuestionItem = {
  id: number;
  requirement_code: string;
  criterion_id: string;
  question: string;
  expected_evidence: string[];
  round: number;
  status: "PENDING" | "ANSWERED" | "WAIVED";
};

export type VerificationReportItem = {
  id: number;
  overall: "VERIFIED" | "NEEDS_CHANGES" | "FAILED";
  must_pass_pct: number;
  should_pass_pct: number;
  summary: string;
  sha256: string;
  details: Record<string, unknown>;
  created_at: string;
};

export type SubmissionDetail = {
  id: number;
  contract_id: number;
  attempt_no: number;
  state: string;
  repo_url: string;
  commit_sha: string;
  deployed_url: string;
  notes: string | null;
  created_at: string;
  auto_checks: AutoCheckItem[];
  auto_check_summary: { PASS: number; FAIL: number; ERROR: number };
  questions: VerificationQuestionItem[];
  evidence: EvidenceItem[];
  report: VerificationReportItem | null;
};

export type SubmissionListItem = {
  id: number;
  attempt_no: number;
  state: string;
  commit_sha: string;
  deployed_url: string;
  created_at: string;
};

