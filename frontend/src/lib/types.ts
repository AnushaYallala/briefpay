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
