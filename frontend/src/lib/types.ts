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
