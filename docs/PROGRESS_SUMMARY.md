# Where the project stands (plain English, newest on top)

Written after every increment so you can see the state without reading code. The detailed task board is in `STATUS.md`.

---

## Increment 1 · Backend foundation (T-04) · Sun Nov 8

**What now exists**
- A working backend app (FastAPI) in `backend/` that starts and answers `GET /api/healthz` with `{"status":"ok","db":"ok"}`.
- The full database design from the spec: all **32 tables** (users, projects, BRDs, campaigns, pledges, money plans, ledger, jobs, AI run logs, ...) as code, plus a migration that creates them. No bond or bonus tables (per D-020).
- Settings come from environment variables; defaults let it run locally on a throwaway SQLite file, with PostgreSQL (Aiven/Neon) used in production by changing one variable.
- 4 automated tests pass (health check, all 32 tables present, money stored as integer cents).
- The docs were moved to the layout the spec expects (`docs/`, `AGENTS.md`, `.env.example` at the repo root) and an MIT licence was added.

**What it does NOT do yet**
Nothing user-visible: no login, no projects, no AI, no PayPal, no screens. This is the foundation everything else sits on.

**Progress:** 1 of ~45 tasks done, but it unblocks most of the others.

**What I need from you / your teammate**
- **PayPal sandbox keys (needed at the next PayPal step, T-20):** Client ID and Secret of the sandbox app under the Business "Platform" account, plus the sandbox emails of the Supporter and Arjun accounts. All accounts must be country **US**. Paste them into a local `.env` file, never into chat or git. T-02 in STATUS.md lists exactly what to create (Payouts and Transaction search must be enabled on the app).
- **Teammate's freelancer demo project (T-60):** one version missing the contact form (should be rejected) and one complete (accepted). Ask them to publish it as a public GitHub repo and send the two commit SHAs plus the live URLs; they go in STATUS.md section 4.

**Next increment:** T-40 + T-07: the pure money-math (split pledges so captures sum exactly to the goal), the project/campaign state machines, and the append-only ledger. All testable without any keys.
