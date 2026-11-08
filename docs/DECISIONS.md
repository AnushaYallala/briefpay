# Decision Log

Short records of decisions that affect contracts or architecture. Append new decisions at the bottom with the next number. Never delete; mark superseded ones.

Format:
```
## D-00N · Title · YYYY-MM-DD · Status: Accepted | Superseded by D-00M
Context: …
Decision: …
Consequences: …
```

---

## D-001 · Three agents with separated authority · 2026-11-08 · Accepted
Context: The idea has a BA agent, a verification agent, and an agent that checks payments. Judges reward agentic AI but money movement must be safe.
Decision: BA Agent (requirements → BRD), Verification Agent (work vs. BRD), Payment Guardian (payout correctness). No agent can call PayPal write endpoints, compute money, or change state. Guardian = deterministic rules + an LLM that can only escalate (ALLOW→HOLD), never relax.
Consequences: All money decisions are unit-testable; the "AI checks the AI" story is credible.

## D-002 · PostgreSQL on Aiven instead of MySQL · 2026-11-08 · Accepted
Context: The team planned MySQL on Aiven's free tier. Aiven has retired the free MySQL plan for new services (MySQL now starts at the paid Developer tier); a free PostgreSQL plan is still offered.
Decision: Use Aiven free PostgreSQL. Keep the schema portable (SQLAlchemy generic types, `JSON`, `BIGINT`, no PG-only features) so MySQL works if someone already has a free MySQL service.
Consequences: `DATABASE_URL` uses `postgresql+psycopg://`. Neon's free plan is the drop-in fallback. Render's free Postgres is rejected because it expires after 30 days, which would fall inside the judging period.

## D-003 · In-process job runner, no separate worker · 2026-11-08 · Accepted
Context: Render has no free background worker instance type; free web services sleep when idle.
Decision: LLM and webhook processing run as rows in a `jobs` table, executed by an asyncio task started in FastAPI's lifespan. UI polls `/api/jobs/{id}`.
Consequences: Jobs survive restarts; a sleeping service resumes jobs on wake. Poll fallback needed for PayPal status.

## D-004 · Images stored in the database · 2026-11-08 · Superseded by D-011
Context: Render free has no persistent disk; avoiding another vendor saves setup time.
Decision: `blobs` table behind a `BlobStore` interface; images re-encoded to ≤ 1600 px, ≤ 400 KB.
Consequences: Fits Aiven's ~1 GB free storage for demo volumes. Swap to object storage later by implementing `BlobStore`.

## D-005 · Gemini as primary LLM with replay fixtures · 2026-11-08 · Accepted
Context: Team prefers Gemini or an open model; demo must be reliable.
Decision: `GeminiModel` (structured JSON output, vision) primary; `HuggingFaceModel` optional text fallback; `ReplayModel` serves recorded outputs keyed by input hash; `replay_or_real` records missing fixtures.
Consequences: Demo can run fully offline from the LLM. Prompt changes bump `PROMPT_VERSION` and invalidate fixtures for that agent.

## D-006 · BA score: LLM judges coverage, code computes the number · 2026-11-08 · Accepted
Context: "Ask until score ≥ 90" needs a stable, explainable score.
Decision: 10 weighted dimensions with 5 coverage levels from the LLM; code sums, applies 5 hard gates (cap 89), and downgrades claims without source references.
Consequences: Score is reproducible and each point is traceable to transcript lines or answers.

## D-007 · Single payout per contract in MVP; milestones optional · 2026-11-08 · Superseded by D-019
Context: 4.5 days of build time.
Decision: One implicit 100% milestone. The `milestones` table exists for the SHOULD feature.
Consequences: Settlement and Guardian logic already take `milestone_id` so adding milestones later doesn't change contracts.

## D-008 · Never use the word "escrow" in judge-facing text · 2026-11-08 · Accepted
Context: PayPal Orders capture is not escrow; funds sit in the platform account.
Decision: Say "pooled funds held by the platform until verified approval."
Consequences: README states production boundaries (SPEC §19.3).

## D-009 · Bearer-token auth instead of cookies · 2026-11-08 · Accepted
Context: `*.onrender.com` subdomains are separate sites, and the frontend is a static site (D-010) that can't proxy `/api`.
Decision: `POST /auth/login` returns a JWT; the frontend keeps it in memory + `sessionStorage` and sends `Authorization: Bearer`. API enables CORS for `CORS_ORIGINS`.
Consequences: No cookie/CSRF issues. Acceptable for a sandbox demo; production would need proper auth.

## D-010 · Next.js static export on a Render static site · 2026-11-08 · Accepted
Context: Must be 100% free. Render free web services sleep after 15 min and share 750 instance hours/month; static sites are free and don't sleep.
Decision: `output: "export"`; every page is a client component; dynamic pages use query params (`/project?id=12`); no Next API routes, server actions or rewrites.
Consequences: Only the API can sleep; the UI loads instantly and shows a wake-up message while the API starts.

## D-011 · Cloudinary for images · 2026-11-08 · Accepted (supersedes D-004)
Context: Team chose Cloudinary; its free plan needs no card. Keeps images out of the ~1 GB free database.
Decision: Signed direct browser uploads (backend signs folder, random `public_id`, `type=authenticated`, allowed formats, incoming size-limit transformation). `POST /images` verifies the asset via the Admin API before it can be used as evidence. Delivery via short-lived signed URLs. The verifier downloads image bytes server-side (Cloudinary host only) to send to Gemini. `LocalImageStore` for dev/tests without an account.
Consequences: Images never pass through the sleeping API on upload; API secret stays server-side.

## D-012 · Free tier only · 2026-11-08 · Accepted
Context: The team requires everything to cost $0.
Decision: Render Hobby (1 free web service + static sites), Aiven free Postgres, Cloudinary free, Gemini free tier (no billing), PayPal sandbox, GitHub public repo + Actions, AG Grid Community, cloudflared quick tunnels. No credit card on any service. See SPEC §5.5.
Consequences: Design around sleep/cold starts, Gemini rate limits (replay fixtures, batched judge calls), and AG Grid Community features. A task needing a paid feature is marked BLOCKED with a free alternative proposed.

## D-013 · APIMatic: Context Plugin + SDK + PayPal-side verification · 2026-11-08 · Accepted
Context: APIMatic is a sponsor with its own prize. The APIMatic-generated Python SDK covers Orders, Payments, Transaction Search, Subscriptions and Vault, but not Payouts or webhook verification.
Decision: (1) All AI coding tools use the APIMatic Context Plugin for PayPal. (2) `PayPalClient` uses the SDK for Orders, Payments and Transaction Search; `httpx` only for Payouts and webhook verification. (3) Payment Guardian adds G-13 (each counted contribution has a COMPLETED capture in PayPal's records) and sources G-09's platform balance from Transaction Search. (4) A reconciliation job matches our ledger to PayPal's transactions. (5) Care plan via Subscriptions is COULD.
Consequences: APIMatic use is part of the safety story, not decoration. Search data can lag, so "not indexed yet" never fails a rule.

## D-014 · Pledge-If (dominant assurance) replaces direct-capture funding · 2026-11-08 · Accepted
Context: Many group projects fail because nobody wants to pay first. PayPal supports authorize-then-capture-or-void.
Decision: Pledges are Orders `AUTHORIZE` holds. Goal reached → capture all (pro-rata so Σ = goal). Deadline missed or lead cancels → void all holds (nobody is charged). *Amended by D-020: no bond, no bonus.* Goal = contract amount + fees (no surplus).
Consequences: Uses Orders, Payments authorizations, Payouts. The v1 states `FUNDING`/`FUNDED` and the `contributions` table are removed. Campaigns have rounds; relaunch is supported.

## D-015 · Conditional freelancer contract before the campaign · 2026-11-08 · Accepted
Context: Pledgers should know who they fund and for how much; capturing money with no freelancer is a bad failure case.
Decision: BRD approved → freelancer signs a conditional contract (BRD hash, price, locked PayPal email) → campaign setup → pledging.
Consequences: Goal is fixed by the contract; the freelancer's email is known to Guardian rules from the start.

## D-016 · MoneyPlan + MoneyExecutor chokepoint; Guardian reviews every plan · 2026-11-08 · Accepted
Context: Captures, voids, payouts and refunds all move or release money and need the same safety story.
Decision: Every PayPal write is a step in an immutable, hash-identified MoneyPlan built by pure code (`PlanBuilder`), reviewed by the Guardian (15 rules, 4 soft flags, escalate-only LLM), approved by policy (auto on ALLOW for capture/failure plans; human for freelancer payout and refunds) and executed only by `MoneyExecutor`.
Consequences: One audit path; tamper simulations for every plan kind; a unit test enforces that no other module calls PayPal write methods.

## D-017 · Organizer bond and POOL/BOND buckets · 2026-11-08 · Superseded by D-020
Context: The bonus promise must be backed by real money, and cancelling must not dodge it.
Decision: The lead authorizes a bond (= bonus pool, 1–10% of goal) before launch. Success → void. Failure or lead cancel → capture and pay pro-rata to pledgers. Ledger buckets keep bond money separate from pledge money.
Consequences: Guardian rules G-07/G-13 prove bond money only pays bonuses and pool money only pays the freelancer or refunds.

## D-018 · 72-hour campaign cap · 2026-11-08 · Accepted
Context: A PayPal authorization is valid 29 days but only guaranteed for a 3-day honor period; later capture depends on risk and funds. Reauthorization rules are ambiguous in the docs.
Decision: `PLEDGE_MAX_HOURS = 72`; deadline ≤ `opens_at + 72h − 2h` (amended by D-020: no bond); default close policy `EARLY_ON_GOAL`; reauthorization is SHOULD.
Consequences: Campaigns are short by design. The UI explains why the deadline picker is limited.

## D-019 · Scope cuts for v2 · 2026-11-08 · Accepted
Decision: Cut milestone payouts (supersedes D-007), surplus-refund logic, the Hugging Face adapter (amends D-005: Gemini + Replay only), "Ask the ledger", care-plan subscriptions, and the generated API client. Strategist LLM nudges are first in the cut order.
Consequences: APIMatic use now rests on authorizations/captures/refunds, Transaction Search and the Context Plugin (D-013 still applies).

## D-020 · Remove organizer bond and bonus; plain assurance contract · 2026-11-08 · Accepted (supersedes D-017)
Context: A bonus paid to pledgers on failure is a pure loss for the organizer, so nobody would fund it. The user asked to remove it.
Decision: No bond, no bonus, no BOND bucket. Failure or lead cancel → void all holds and nobody is charged (settlement kind `RELEASE_HOLDS`, was `FAIL_SETTLEMENT`). Launch needs only a signed contract. Deadline ≤ `opens_at + PLEDGE_MAX_HOURS − HONOR_SAFETY_MARGIN`. Guardian: 13 hard rules, 3 soft flags. `BONUS_*` env vars, `bonds` table and bond endpoints are removed.
Consequences: This is a standard all-or-nothing assurance contract, not a dominant one: no financial incentive to pledge early, only the no-risk guarantee. Pitch language must not say "dominant assurance" or "you can't lose and may gain".

## D-021 · plan_hash excludes step idempotency keys · 2026-11-08 · Accepted
Context: SPEC 7.5.1 derives each step's `idempotency_key` from `plan_hash[:16]`, but also defines `plan_hash` over the whole `MoneyPlanSpec` including those keys. That is circular.
Decision: `plan_hash` is computed over the canonical spec with every step's `idempotency_key` removed. Keys are then derived as `f"{plan_hash[:16]}-{seq}"` and stored on the steps. Implemented in `services/settlement.py`.
Consequences: Any change to kind, inputs, recipient, amount, op or step order still changes the hash (tested). Keys cannot be chosen independently of the plan, so they stay deterministic across retries.

## D-022 · Retry attempts are part of plan inputs · 2026-11-08 · Accepted
Context: SPEC 8.6 says a failed payout is retried by building "a new plan (new hash, new review)". But a rebuilt plan with unchanged database state is byte-identical, so it has the same `plan_hash`, the same step idempotency keys (UNIQUE), and would collide with the failed plan.
Decision: `PlanBuilder` adds `inputs.attempt = N` when N earlier plans of the same kind and scope (project, plus campaign if any) ended `FAILED`, `PARTIAL` or `BLOCKED`. First attempts have no `attempt` key, so their hash is unchanged. When rebuilding an existing plan (Guardian G-01, executor), that plan is excluded from the count so it never counts itself.
Consequences: Each retry gets fresh idempotency keys and a fresh Guardian review. PayPal-side idempotency still protects a re-run of the *same* plan after a crash, because that reuses the same keys.

## D-023 · How the Guardian rules interpret the spec's open points · 2026-11-08 · Accepted
Context: SPEC 7.5.2 leaves a few checks open to interpretation. Rules are a safety contract, so the choices are recorded.
Decision: (1) "Live-valid" hold = our DB says AUTHORIZED, it has an authorization id, `honor_until > now`, and PayPal reports `CREATED` with the same amount. (2) "Lead closed" (G-09) = the plan was proposed by a `user:<id>`; a `system` proposer needs `EARLY_ON_GOAL` or a passed deadline. (3) G-13 "required approvals": a refund plan must be proposed by the project's lead (`user:<lead_user_id>`); the approval click itself is enforced at approve time (T-45). (4) G-12's "all-sponsor override" is not implemented yet (no override table); only a `VERIFIED` report passes. (5) G-10's "captures flagged `final_capture`" cannot be seen in a plan spec; `MoneyExecutor` hardcodes it and T-45 tests it. (6) PayPal unreachable never FAILs a rule: G-06/G-09 become `UNVERIFIED`, G-08 `SKIPPED`, and soft flag S-03 forces HOLD. A PayPal record that disagrees with ours is a FAIL.
Consequences: Any change to these needs a new D entry. Rules receive PayPal data only through the `PayPalReader` protocol, so the real SDK reader (T-20) plugs in without touching the rules.

## D-024 · Executor, confirmation and approval rules · 2026-11-08 · Accepted
Context: SPEC 8.5 describes the executor but leaves the boundary with webhooks, the retry budget and who may approve what to the implementer.
Decision: (1) `MoneyExecutor.execute` marks a step `SENT` and commits **before** calling PayPal, retries only transient errors at most twice with the **same** idempotency key, and never marks a step `CONFIRMED`; only `plan_lifecycle.confirm_step` (webhook handlers / poll fallback, T-21/T-43) does, and that is where pledge, ledger, campaign and project effects happen. (2) A resumed `EXECUTING` plan re-sends its `SENT` steps with their original keys and skips `CONFIRMED`/`FAILED` ones; the run-time `PlanBuilder.rebuild` hash check applies only to the first start (afterwards the campaign has legitimately moved to `CAPTURING`). (3) Before every run the executor re-verifies: an approval bound to the current hash, a non-simulated Guardian review of that hash that is not BLOCK (HOLD needs an ack note), HUMAN plans approved by a `user:`, the stored `plan_json` hashing to `plan_hash`, and DB step rows equal to the plan's steps. (4) Approval roles: payout needs LEAD or SPONSOR; refunds and any HOLD on a capture/release plan need the LEAD; the system may approve only an ALLOW on an `AUTO_ON_ALLOW` plan. (5) A failed payout marks its batch/item `FAILED` so G-12 doesn't see it as pending; G-02/G-12 accept `PAYOUT_FAILED` so the retry plan (D-022) can run. (6) Errors use the SPEC 10 shape at the top level (`{"error": {...}}`).
Consequences: A crash at any point is recoverable without a duplicate PayPal operation. Webhook handlers must call `confirm_step` and nothing else. `REAUTH_AUTH` is not executable yet.

## D-025 · Guardian LLM review: typed findings, fail-safe HOLD, facts boundary · 2026-11-08 · Accepted
Context: SPEC 7.5.4 defines `GuardianLLMOutput.findings` as `list[dict]` and says an LLM error means HOLD. Gemini structured output works far better with typed objects than free dicts, and the review needs a clear rule for what the model may see.
Decision: (1) `findings` is `list[Finding]` where `Finding = {type (the SPEC's nine types), detail <= 300 chars, severity low|medium|high}`; same JSON shape as the spec, stricter validation; at most 8 findings, `explanation_for_sponsors` <= 500 chars. (2) Final decision = `max(rules decision, LLM floor)`: a hard-rule BLOCK is final and the model is **not called**; `risk_level == "high"` => HOLD; a model error, schema failure or missing configuration => HOLD with finding `GUARDIAN_LLM_UNAVAILABLE`; "low"/"medium" never change a decision. (3) When a caller passes no LLM (`llm=None`) the review is rules-only (used by tests and tooling); the API and system callers always pass one, so an unconfigured AI shows up as a HOLD, never as a silent pass. (4) The model sees only: plan kind/reason/step amounts, labelled parties (P1, P2, FREELANCER), campaign timeline, failed/unverified rules, soft flag ids and, for payouts, the verification outcome with auto-check results. Display names and the verification summary are passed only inside `<untrusted>` fences. No emails, no images. (5) Temperature 0.0; prompt `guardian-llm-v1` in `agents/prompts/guardian_llm.md`.
Consequences: Recorded fixtures replay the review deterministically (the facts are deterministic). A bumped prompt version invalidates them. The review row stores `llm_review_json` and the `agent_runs` id (also for failed calls).
