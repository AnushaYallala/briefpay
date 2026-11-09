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
