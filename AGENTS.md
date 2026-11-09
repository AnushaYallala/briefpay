# AGENTS.md: read this first (every AI assistant, every session)

This repo is built by two humans and several AI coding assistants (Claude, Gemini, Cursor, Copilot, etc.) taking turns. Any assistant must be able to pick up exactly where the previous one stopped. This file tells you how.

**Project:** BriefPay, for the PayPal AI Hackathon (deadline **Nov 12, 2026, 12:00 PM PST / Nov 13, 1:30 AM IST**).
Small businesses **pledge** money via PayPal to hire a freelancer (Pledge-If: pledges are authorization holds; goal missed → all holds released, nobody is charged). A BA Agent turns a meeting transcript into a scored BRD (asks questions until score ≥ 90). A Strategist forecasts the campaign. A Verification Agent checks the delivered work against the BRD. A Payment Guardian reviews every money plan before PayPal executes it.

---

## 1. Session start (do these in order, ~2 minutes)
1. Read `docs/STATUS.md` → §1 Snapshot and the newest 2–3 entries of §6 Handoff log.
2. Pick your task:
   - If the human named a task ID, take that.
   - Else continue any task `IN_PROGRESS` with **your** name, else take the "Next task to pick up" in the Snapshot, else the first `TODO` whose dependencies are `DONE`.
3. Mark it `IN_PROGRESS` with your name and branch in `docs/STATUS.md` and commit that change first (`T-xx: start`). This prevents two assistants doing the same task.
4. Read **only** the `docs/SPEC.md` sections listed in the task's "Spec" column, plus `docs/DECISIONS.md` if you touch contracts.
5. `git pull`, create/checkout branch `t-xx-short-name`.

## 2. While working
- **Contracts are fixed:** SPEC §6 (data model), §7 agent schemas, §10 API. If you must change one, update SPEC.md **and** add a `D-00N` entry to DECISIONS.md in the same commit, and mention it in your handoff.
- Money is **integer cents**. No floats. Ledger is append-only. Pledge holds are **not money** (they never appear in a bucket balance).
- **Money rule:** every PayPal write (capture, void, reauthorize, refund, payout) is a step in a `MoneyPlan` built by `PlanBuilder`, reviewed by the Guardian, approved by policy, and executed **only** by `MoneyExecutor`. Never call PayPal write methods from anywhere else. Plans are immutable; changed data means a new plan hash.
- Bucket: POOL (captured pledges) can only pay the freelancer or refund pledgers. There is no bond and no bonus (D-020).
- A pledge hold is only guaranteed for **3 days** (PayPal honor period): campaigns are capped at 72 h. Never say "escrow".
- Agents (BA, Strategist, Verifier, Guardian) never call PayPal write endpoints, never compute money, never build plans, never change state. Only `ProjectService` / `CampaignService` change state.
- Every LLM call goes through `LLMAdapter` and is logged in `agent_runs`. Untrusted text is wrapped in `<untrusted>` tags.
- Every mutating PayPal call sends `PayPal-Request-Id`.
- Pure logic (settlement, guardian rules, BA math, verification aggregation, state machine) gets unit tests.
- **Everything must stay on free tiers** (SPEC §5.5, D-012). Never add a paid service, a credit card, Gemini billing, AG Grid Enterprise-only features, or a Render paid instance. If something seems to need one, mark the task BLOCKED and propose a free alternative.
- Frontend is a **static export** (D-010): client components only, query-param routes, no Next API routes/rewrites. Auth is a Bearer token (D-009).
- Images go through `ImageStore` (Cloudinary in prod, local in dev; D-011). Never store image bytes in the DB.
- Never commit secrets. Use `.env` (gitignored); add any new variable to `.env.example` and SPEC §14.3.
- Small commits, message prefix `T-xx: …`.
- Don't refactor files outside your task unless required; if required, say so in the handoff.
- If you're blocked by a human-only step (sandbox accounts, API keys, Render dashboard), mark the task `BLOCKED`, write exactly what the human must do, and move to another task.

## 3. Session end (mandatory, even if you didn't finish)
1. Run the tests you touched; note results.
2. Update `docs/STATUS.md`:
   - Task row: state (`DONE` / `REVIEW` / still `IN_PROGRESS` / `BLOCKED`), notes.
   - Snapshot: "Last updated", "Next task to pick up", blockers, URLs if changed.
   - §3 Verified facts if you confirmed anything (API shape, model name, limit).
   - Prepend a Handoff log entry using the template (what you did, what's left, exact next step, gotchas).
3. Commit and push (`T-xx: handoff`). Merge to `main` only if tests pass and the app still starts.

If your context is about to run out, do step 3 **now**, before you lose the ability to.

## 4. Commands (fill these in as soon as they exist)
```
# backend (verified working; Windows paths shown, on macOS/Linux use .venv/bin/ instead of .venv/Scripts/)
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
cp ../.env.example .env                      # then fill in keys; never commit .env
.venv/Scripts/alembic upgrade head           # creates backend/briefpay_dev.db (SQLite) unless DATABASE_URL is set
.venv/Scripts/uvicorn app.main:app --reload --port 8000
.venv/Scripts/python -m pytest -q            # ~440 tests, ~25 s, no network and no keys needed
.venv/Scripts/python -m pytest -q tests/test_x.py -k name    # one test

# Gotchas for AI assistants: edit files with the Edit/Write tools, not with Python inside a shell heredoc when the text
# contains backslash escapes (it corrupted a test file once). Known gaps and fixes: docs/GAPS_AND_FIXES.md.

# frontend
cd frontend && npm install && npm run dev   # http://localhost:3000

# seed demo data
cd backend && python seed.py

# webhooks locally
cloudflared tunnel --url http://localhost:8000
```

## 5. Where things live
| Thing | Path |
|---|---|
| Spec | `docs/SPEC.md` |
| Status + handoff log | `docs/STATUS.md` |
| Decisions | `docs/DECISIONS.md` |
| Sample meeting transcript | `docs/samples/velugu_cove_meeting_transcript.txt` |
| Agent prompts | `backend/app/agents/prompts/` |
| Replay fixtures | `backend/fixtures/replay/<agent>/<input_hash>.json` |
| Freelancer test site | `sample-site/` |

## 6. PayPal reminders
- Sandbox only. All sandbox accounts are **US** (India↔India fails).
- Do **not** use `paypal-rest-sdk` or `paypal-checkout-server-sdk` (deprecated). Use `paypal-server-sdk` (Python) where it covers the endpoint, `httpx` otherwise.
- Webhooks are the source of truth for captures and payouts.
- **Before writing any PayPal code, configure the APIMatic Context Plugin (MCP) in your tool** (SPEC §9.6, task T-08) and take SDK method names from it, not from memory.
- Use `paypal-server-sdk` for Orders, Payments and Transaction Search; `httpx` only for Payouts and webhook verification. Only `services/paypal_client.py` imports the SDK.
- The PayPal AI Toolkit (`paypal-doctor`) is a useful extra check if your tool supports it.
