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

## D-026 · Projects, members and transcripts: access, staging and one added endpoint · 2026-11-08 · Accepted
Context: SPEC 10 lists the project, member and transcript endpoints but leaves privacy, who can be invited when, and how repeat uploads behave open. The BA Studio also needs to read the numbered transcript, which §10 does not list.
Decision: (1) Reads of `GET /projects` and `GET /projects/{id}` are public (no token); a present-but-bad token is a 401. Public view shows display names, business names/types and campaign progress only. Members additionally see emails, invite status, last seen and the freelancer's PayPal email; only the **lead** sees `expected_pledge_cents`. (2) A member opening the project marks them `VIEWED` and sets `joined_at`/`last_seen_at` (Strategist input). (3) `PUT /projects/{id}/members` is an idempotent upsert by lower-cased email: it never removes or changes a role (a freelancer can never also be a sponsor; the lead cannot be re-invited); one freelancer per project; sponsors can be invited only in DRAFT/REQUIREMENTS (approvers must be fixed before the BRD is reviewed), the freelancer up to CONTRACTING. (4) The transcript is accepted as JSON text or a multipart `file` (.txt/.vtt/.md, 300 KB, 5000 lines, UTF-8). Plain text keeps every line; WebVTT is reduced to spoken lines with `<v Name>` turned into `Name: `. The **latest** upload supersedes earlier ones (history kept in `transcripts`); the first moves DRAFT -> REQUIREMENTS; uploads are refused after REQUIREMENTS. (5) **New endpoint** `GET /projects/{id}/transcript` (member): numbered lines for the transcript panel, added to SPEC 10. (6) `budget_cents` may not exceed `PAYOUT_MAX_CENTS`, because a larger project could never be paid out (Guardian G-05).
Consequences: The BA Agent must number lines exactly as `services/transcripts.numbered` does. Re-uploading changes line numbers, which is why it is blocked once the BRD is under review.

## D-027 · BA scoring: schema tightening, gate definitions and where results are stored · 2026-11-08 · Accepted
Context: SPEC 7.1 fixes the rubric, gates and cap but leaves some details to the implementer, and two of its schema shapes (`Literal` floats, `list[dict]`) are unreliable for Gemini structured output.
Decision: (1) `DimensionScore.coverage` is a `float` snapped to {0, .25, .5, .75, 1} by a validator, and `Conflict.positions` is a typed `list[Position{member_id, position}]`; the JSON is the same as the spec's. (2) The total is exact integer arithmetic: `(sum(weight * coverage_in_quarters) + 2) // 4`, i.e. round-half-up, so a score is reproducible and independently checkable. (3) A coverage claim above 0 with no **valid** `source_refs` is lowered one level; valid means a transcript range `L<a>[-L<b>]` inside the transcript or an `answer:<id>` that exists. (4) Gates are computed in code: GT-1 passes if the budget is stated by the project record **or** the meeting (same for the delivery deadline); GT-2 needs at least one MUST requirement and every MUST to have a non-blank criterion; GT-3 needs every conflict `resolved` **with** a resolution text; GT-4 needs a non-blank out-of-scope item; GT-5 needs every lead/sponsor id in some requirement's `requested_by`. Any red gate caps the total at 89. (5) Sponsors for GT-5 are the LEAD and SPONSOR members; unknown member ids in `requested_by` are dropped. (6) Storage in the existing columns: `ba_scores.dimensions_json` = per-dimension {claimed, effective, downgraded, valid refs, weight, name}; `gates_json` = {GT-1..GT-5: {title, passed, detail}, `observations`: {out_of_scope, injection_attempts, budget/deadline flags}, `total_uncapped`}. (7) A failed AI call changes nothing (no score row, session untouched).
Consequences: Prompt `ba-score-v1` lives in `agents/prompts/ba_score.md`; bumping it invalidates BA replay fixtures. READY is only reachable with every gate green and a total >= `BA_TARGET_SCORE`.

## D-028 · BA question loop: rounds, completion rules, FINALIZED state · 2026-11-08 · Accepted
Context: SPEC 7.1 describes the loop (up to 5 questions per round, re-score when all are answered or skipped, stop at 90 or round 5, lead can finalize) but leaves the mechanics open.
Decision: (1) Rounds are numbered from 0: round 0 is the first scoring; each fully closed set of questions advances `ba_sessions.round` by one and queues a `BA_RUN` job (score, then questions). When `round >= BA_MAX_ROUNDS` after scoring and the score is not READY, the session becomes `MAX_ROUNDS` and no more questions are asked. (2) A question addressed to named sponsors is ANSWERED when all of them have answered; one addressed to `ALL` is ANSWERED by any one sponsor or the lead; the lead can SKIP any open question. Only LEAD/SPONSOR members can answer; each member answers a question once. (3) `BA_RUN` is idempotent: unchanged input (same transcript hash, same round) is never re-scored and a round never gets a second set of questions, so a failed job is simply retried. A replaced transcript triggers a re-score in the same round. (4) The AI's questions are filtered in code: only sponsor ids (otherwise `ALL`), only dimensions that still have a gap, no repeat of any earlier question (normalised text), at most five; if nothing usable remains a fixed fallback question for the top gap is used so the loop cannot stall. (5) Manual runs are limited to 8 BA_RUN jobs per project per hour (automatic ones count) and are refused while questions are open. (6) **New session state `FINALIZED`** (MAX_ROUNDS -> FINALIZED -> BRD_GENERATED): finalize skips open questions and closes the analysis; the spec's text implied this state without naming it. (7) `GET /projects/{id}/ba` returns the session, latest score breakdown, history, all questions with answers and per-viewer `can_answer`, plus `can_run` / `can_finalize`.
Consequences: Prompt `ba-questions-v1` (`agents/prompts/ba_questions.md`) feeds replay fixtures; bumping it invalidates them. T-14 reads the latest score's gaps and requirements; a finalized session carries its red gates into the BRD open items.

## D-029 · BRD generation: what the model drafts, what code owns, and when it runs · 2026-11-08 · Accepted
Context: SPEC 7.2 says the model drafts `BRDContent`, code assigns REQ codes, validates MUST criteria, renders Markdown with a template and hashes it. It does not say how traceability, constraints, open items, versions or escaping work.
Decision: (1) The model returns a `BRDDraft` (no REQ codes, no AC ids, no constraints, plus `from_temp_ids`); code assembles the canonical `BRDContent`. The spec's loose dicts are typed models with the same JSON keys (`AutoCheckHint`, `Stakeholder`, `SitemapEntry`, `ContentResponsibility`, `Constraints`, `GlossaryEntry`). Auto-check hints are limited to URL_REACHABLE, PAGE_CONTAINS, FILE_EXISTS and MOBILE_VIEWPORT and must be complete. (2) Code rules, each a hard failure (`BRD_INVALID`, nothing stored): every analysis requirement id must appear in some `from_temp_ids` (nothing silently dropped), there is at least one MUST, every MUST has at least one criterion. Requirements are ordered MUST, SHOULD, COULD (draft order within a priority) and numbered REQ-001...; criteria AC-1... per requirement. (3) Facts the model must not decide come from our records: budget, currency and delivery days from the project; people only as sponsor member ids (unknown ids dropped; missing sponsors backfilled from what they requested); `source_refs` kept only if they point at real transcript lines or answers; scope exclusions from the analysis are always kept. (4) `open_items` = red BA gates + (when finalized, below target or a gate is red) every dimension at or below half coverage + the model's own, de-duplicated, max 20. (5) Markdown comes only from `templates/brd.md.j2`; every user-derived string is escaped (`<`, `>`, `&` become entities, newlines collapse, pipes escaped in table cells, and any line that starts with a Markdown structure character gets a leading backslash). Names are looked up from the database at render time. (6) `sha256 = sha256(canonical_json(content))` with sorted keys and compact separators, so any component can recompute it. (7) Generation needs project `REQUIREMENTS` and a `READY` or `FINALIZED` analysis. On success: BRD `PENDING_APPROVAL`, older `DRAFT`/`PENDING_APPROVAL` BRDs `SUPERSEDED` (an `APPROVED` one never is), session `BRD_GENERATED`, project `BRD_REVIEW`. The job is idempotent. (8) `GET /projects/{id}/brd` and the `.md` download are public (no emails inside).
Consequences: Prompt `brd-gen-v1` (`agents/prompts/brd_gen.md`) feeds replay fixtures. The UI must render the Markdown with a renderer that does not allow raw HTML. Approvals (T-15) bind to `sha256`.

## D-030 · BRD approvals: voters, hash binding, withdrawal and what a rejection resets · 2026-11-08 · Accepted
Context: SPEC 7.2 and 6.1 say each sponsor approves the hash they saw, approval is unanimous, and a rejection with a comment becomes a new BA question and sends the project back to REQUIREMENTS. Several details were left open.
Decision: (1) **Voters** are the LEAD and all SPONSOR members (the lead is a sponsor); the freelancer and supporters never vote; the voter set cannot change once the BRD is under review (sponsors can only be invited in DRAFT/REQUIREMENTS, D-026). (2) **Hash binding:** `POST /projects/{id}/brd/{version}/decision` must carry the BRD's current `sha256`; a different hash is `HASH_MISMATCH` (409, with `details.current_sha256`) and stores nothing; only decisions whose stored hash equals the document's hash count, so a decision can never be carried to different content. Approvals never carry over to a new version. (3) **State rules:** decisions are accepted only while the project is `BRD_REVIEW` and the BRD is `PENDING_APPROVAL`; otherwise `PROJECT_STATE` or `BRD_CLOSED`. (4) **One row per member** (UNIQUE brd_id+member_id): repeating the same APPROVE is a harmless no-op (`changed: false`); an approver may **withdraw only by rejecting** (the row is updated). (5) **Unanimity** (every voter has APPROVE on the current hash) locks the BRD: status `APPROVED`, `locked_at`, ledger `BRD_LOCKED` (amount 0, meta version + hash), project `BRD_REVIEW -> CONTRACTING`. (6) **A rejection needs a non-blank comment (<= 1000 chars)**; it marks that BRD `SUPERSEDED`, moves the project to `REQUIREMENTS`, sets the BA session back to `ACTIVE` with `round + 1`, and creates one OPEN question addressed to `ALL` whose text quotes the comment, with `dimension = "BRD"` (not a rubric dimension) so the normal answer, re-score and regenerate loop applies. (7) Every decision writes an `APPROVAL` ledger memo (decision, version, hash, comment). (8) `GET /projects/{id}/brd` shows only decisions on the current hash plus who is still `awaiting`.
Consequences: The contract (T-30) binds to the `APPROVED` BRD's `sha256`. A sponsor who never responds blocks approval; see GAP-28.

## D-031 · Conditional contract: what is signed, who can sign, what it locks · 2026-11-08 · Accepted
Context: SPEC 6.2/10 and D-015 define a conditional contract bound to the BRD hash, the price and the freelancer's PayPal email, but not how the terms are produced, hashed, replaced or signed.
Decision: (1) **Offer** (`POST /projects/{id}/contract/offer`, lead): needs project `CONTRACTING`, an `APPROVED` BRD and an invited freelancer; `0 < amount <= min(project budget, PAYOUT_MAX_CENTS)` and `1 <= delivery_days <= 90`. The terms are rendered from `templates/contract.md.j2` (escaped like the BRD), say plainly that it is a **demonstration agreement, not a legally binding contract**, name the BRD version and hash, are conditional on funding, and use "pooled funds held by the platform until verified approval" (never "escrow", D-008). (2) **What is signed** is `terms_sha256 = sha256(canonical_json({terms_md, project_id, brd_sha256, amount_cents, currency, delivery_days, freelancer_member_id, conditional: true}))`, so the text and every number it states cannot change independently. The contract row is bound to `brd_id`/`brd_sha256`. (3) A re-offer **replaces an unsigned offer in place** (new hash, so a signature on the old terms is refused); a signed contract can never be replaced, even if the project state were rewound. (4) **Accept** (`POST /projects/{id}/contract/accept`, the invited freelancer only): both `brd_sha256` and `terms_sha256` must match the stored values (`HASH_MISMATCH` otherwise) and the BRD must still be `APPROVED`; the PayPal email is lower-cased, must be a valid email and must **not** be the login email of the lead or a sponsor (the freelancer is paid to their own account); signing sets `signed_at`, locks `freelancer_paypal_email` on the contract and the member, writes a `CONTRACT_SIGNED` ledger memo (amounts and hashes only, **no email**, because the ledger can be public) and moves the project `CONTRACTING -> CAMPAIGN_SETUP`. (5) `effective_at` stays null until the capture plan is DONE (already implemented in `plan_lifecycle`). (6) **New endpoint** `GET /projects/{id}/contract` (members only), added to SPEC 10.
Consequences: Guardian G-12 and the payout builder read the locked email, amount and BRD hash from this row. There is no 'decline' action; the lead simply re-offers (GAP-32).
