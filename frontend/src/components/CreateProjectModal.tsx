"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useOptionalAuth } from "@/lib/auth";
import type { ProjectDetail } from "@/lib/types";

interface Invitee {
  email: string;
  display_name: string;
  role: "SPONSOR" | "FREELANCER";
  business_name?: string;
  business_type?: string;
  expected_pledge_cents?: number;
}

const VELUGU_COVE_PRESET = {
  title: "Velugu Cove tourism website",
  location_label: "Velugu Cove",
  budget: "400.00",
  delivery_days: "5",
  summary: "A joint website for the local businesses of Velugu Cove to promote tourism, homestays, fresh seafood, and boat tours with WhatsApp enquiries.",
  lead_business_name: "Sea Breeze Homestay",
  lead_business_type: "Hospitality",
  lead_expected_pledge: "150.00",
  members: [
    {
      email: "ravi@velugu.example.com",
      display_name: "Ravi",
      role: "SPONSOR" as const,
      business_name: "Ravi's Fish Kitchen",
      business_type: "Restaurant",
      expected_pledge_cents: 15000,
    },
    {
      email: "meena@velugu.example.com",
      display_name: "Meena",
      role: "SPONSOR" as const,
      business_name: "Cove Boat Tours",
      business_type: "Activities",
      expected_pledge_cents: 10000,
    },
    {
      email: "arjun@velugu.example.com",
      display_name: "Arjun",
      role: "FREELANCER" as const,
      business_name: "Full Stack Builder",
      business_type: "Web Development",
    },
  ],
};

export function CreateProjectModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated?: (p: ProjectDetail) => void;
}) {
  const router = useRouter();
  const auth = useOptionalAuth();
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [budget, setBudget] = useState("400.00");
  const [deliveryDays, setDeliveryDays] = useState("5");
  const [summary, setSummary] = useState("");
  const [leadBusinessName, setLeadBusinessName] = useState("");
  const [leadBusinessType, setLeadBusinessType] = useState("");
  const [expectedPledge, setExpectedPledge] = useState("150.00");
  const [members, setMembers] = useState<Invitee[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function loadPreset() {
    setTitle(VELUGU_COVE_PRESET.title);
    setLocation(VELUGU_COVE_PRESET.location_label);
    setBudget(VELUGU_COVE_PRESET.budget);
    setDeliveryDays(VELUGU_COVE_PRESET.delivery_days);
    setSummary(VELUGU_COVE_PRESET.summary);
    setLeadBusinessName(VELUGU_COVE_PRESET.lead_business_name);
    setLeadBusinessType(VELUGU_COVE_PRESET.lead_business_type);
    setExpectedPledge(VELUGU_COVE_PRESET.lead_expected_pledge);
    setMembers(VELUGU_COVE_PRESET.members);
    setError(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);

    try {
      // If not logged in, log in as lead organizer
      if (auth && auth.status !== "authed") {
        await auth.login("lakshmi@velugu.example.com", "Lakshmi");
      }

      const budgetCents = Math.round(parseFloat(budget || "0") * 100);
      const leadPledgeCents = Math.round(parseFloat(expectedPledge || "0") * 100);
      const days = deliveryDays ? parseInt(deliveryDays, 10) : null;

      const payload = {
        title: title.trim(),
        summary: summary.trim() || undefined,
        location_label: location.trim() || undefined,
        budget_cents: budgetCents,
        delivery_days: days,
        payout_release_policy: "HUMAN",
        lead_business_name: leadBusinessName.trim() || undefined,
        lead_business_type: leadBusinessType.trim() || undefined,
        lead_expected_pledge_cents: leadPledgeCents,
        members: members.map((m) => ({
          email: m.email.trim().toLowerCase(),
          display_name: m.display_name.trim(),
          role: m.role,
          business_name: m.business_name || undefined,
          business_type: m.business_type || undefined,
          expected_pledge_cents: m.expected_pledge_cents || undefined,
        })),
      };

      const res = await api<ProjectDetail>("/projects", {
        method: "POST",
        body: payload,
      });

      if (onCreated) {
        onCreated(res);
      }
      onClose();
      router.push(`/ba?id=${res.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err instanceof Error ? err.message : "Failed to create project"));
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs overflow-y-auto">
      <div className="relative w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xl my-8">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 pb-4 mb-6">
          <div>
            <div className="inline-flex items-center gap-1.5 rounded-full bg-sea-50 px-2.5 py-0.5 text-xs font-semibold text-sea-700 ring-1 ring-inset ring-sea-600/20 mb-1.5">
              <span>Pledge-If Assurance Protocol</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
              Start a Community Initiative
            </h2>
            <p className="mt-1 text-xs sm:text-sm text-slate-500">
              Create a shared project, invite local sponsors, and start requirements drafting with the AI BA.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="mb-6 rounded-xl border border-sea-200/80 bg-sea-50/60 p-3.5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs font-bold text-sea-900">Need a quick walkthrough?</div>
            <div className="text-xs text-sea-700">Pre-fill the Velugu Cove tourism website story with 3 local sponsors and a builder in 1 click.</div>
          </div>
          <button
            type="button"
            onClick={loadPreset}
            className="rounded-lg bg-sea-700 px-3 py-1.5 text-xs font-semibold text-white shadow-2xs hover:bg-sea-800 transition"
          >
            Pre-fill Velugu Cove Initiative
          </button>
        </div>

        {error && (
          <div role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-800">
            {error}
          </div>
        )}

        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 sm:col-span-2">
              <span>Initiative Title *</span>
              <input
                type="text"
                required
                placeholder="e.g. Velugu Cove tourism website"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="mt-1 block w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
              />
            </label>

            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              <span>Location / Region</span>
              <input
                type="text"
                placeholder="e.g. Velugu Cove"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="mt-1 block w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
              />
            </label>

            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              <span>Target Budget ($ USD) *</span>
              <input
                type="number"
                step="0.01"
                min="10"
                max="10000"
                required
                placeholder="400.00"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                className="mt-1 block w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
              />
            </label>

            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              <span>Delivery Timeline (Days)</span>
              <input
                type="number"
                min="1"
                max="90"
                placeholder="5"
                value={deliveryDays}
                onChange={(e) => setDeliveryDays(e.target.value)}
                className="mt-1 block w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
              />
            </label>

            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              <span>Lead Organizer Business</span>
              <input
                type="text"
                placeholder="e.g. Sea Breeze Homestay"
                value={leadBusinessName}
                onChange={(e) => setLeadBusinessName(e.target.value)}
                className="mt-1 block w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
              />
            </label>

            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 sm:col-span-2">
              <span>Summary / Objectives</span>
              <textarea
                rows={3}
                placeholder="Briefly describe what the community initiative plans to accomplish..."
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                className="mt-1 block w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
              />
            </label>
          </div>

          {members.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 mt-2">
              <div className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                Included Stakeholders &amp; Pledges ({members.length})
              </div>
              <ul className="space-y-1.5 text-xs text-slate-600">
                {members.map((m) => (
                  <li key={m.email} className="flex items-center justify-between">
                    <span>
                      <strong>{m.display_name}</strong> ({m.business_name ?? m.role})
                    </span>
                    <span className="font-semibold text-slate-800">
                      {m.expected_pledge_cents ? `$${(m.expected_pledge_cents / 100).toFixed(2)}` : m.role}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || !title.trim()}
              className="rounded-xl bg-sea-700 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-sea-800 transition disabled:opacity-50"
            >
              {busy ? "Creating Initiative..." : "Create Initiative & Launch BA Studio"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
