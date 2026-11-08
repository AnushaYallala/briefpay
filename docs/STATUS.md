# BriefPay: Build Status & Handoff Log

> **This is the single source of truth for what is done.** Every AI assistant and human updates it at the end of every session (see `/AGENTS.md` §3).
> Times in **IST**. Deadline: **Fri Nov 13, 1:30 AM IST** (Nov 12, 12:00 PM PST). Internal submit target: **Thu Nov 12, 6:00 PM IST**.

---

## 1. Snapshot

| Field | Value |
|---|---|
| Last updated | 2026-11-08 by Claude: T-20 PayPal client built (REVIEW: needs sandbox keys to verify) |
| Overall phase | **Day 0: backend skeleton, schema, money math, state machines, ledger built; no features yet** (plain-English summary: `docs/PROGRESS_SUMMARY.md`) |
| Current day goal (Sun Nov 8) | `/healthz` live on Render; a sandbox script proves authorize→capture, authorize→void and a payout |
| Next task to pick up | Track B: **T-22** (pledge gate + service, using `PayPalClient.create_authorize_order/authorize_order`), then **T-21** (webhooks: `verify_webhook_signature` exists), **T-25** (outcome engine + clock) · **Human:** run `backend/scripts/sandbox_check.py` once keys exist · see also `docs/GAPS_AND_FIXES.md` · Track B: **T-02** (human, sandbox keys), **T-08**, then **T-20** |
| Blockers | None yet |
| Deployed URLs | API: _not deployed_ · Web: _not deployed_ · Sample site: _not deployed_ |
| Repo | https://github.com/AnushaYallala/briefpay (origin; T-01 still needs LICENSE visible in About + secret scanning) |
| Demo video | _not recorded_ |
| Devpost submission | _not started_ |

### Legend
`TODO` · `IN_PROGRESS` · `REVIEW` (built, needs a human to try it) · `DONE` · `BLOCKED` · `CUT`
Owner examples: `Nush`, `Teammate`, `Claude`, `Gemini`, `Cursor`, `Copilot`. A task `IN_PROGRESS` must have an owner and a branch.

---

## 2. Task board

### Track 0: Setup
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-01 | Create GitHub repos (`briefpay`, `velugu-cove-site`), MIT LICENSE, copy docs, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.env.example`, `.gitignore`; enable secret scanning | §5.4 |  | TODO |  | Licence must show in repo About |
| T-02 | **Human:** PayPal sandbox accounts (all **US**): Platform business + Lakshmi, Ravi, Meena, Supporter, Arjun (personal); app credentials; enable **Payouts** and **Transaction search**; create webhook pointing at the Render API URL (subscribe to the §9.5 events) | §9.1, §9.5 |  | TODO |  | Record sandbox emails in §4 below (no passwords) |
| T-03 | **Human:** free accounts, **no credit card anywhere**: Aiven free PostgreSQL (CA cert), Cloudinary free plan, Gemini key (AI Studio, no billing), GitHub fine-grained token, Render Hobby workspace | §5.5, §14.3 |  | TODO |  | Note Cloudinary credits + Gemini RPM/RPD in §4 |
| T-04 | Backend skeleton: FastAPI, config, SQLAlchemy models for **all §6.2 tables**, Alembic initial migration, `/api/healthz` | §6, §10 | Claude | DONE | t-04-backend-foundation | 32 tables, migration 0001, 4 tests pass. SQLite default for local dev; set `DATABASE_URL` for Postgres |
| T-05 | Frontend skeleton: Next.js static export, Tailwind, query-param routes, API client with Bearer token, login + `/auth/me`, persona switcher, wake-up screen | §5.2, §11, §14.4, §14.5 |  | TODO |  | `npm run build` must produce `out/` |
| T-06 | LLM adapter (`GeminiModel`, `ReplayModel`), `agent_runs` logging, in-process DB job runner + `GET /jobs/{id}` | §7.0 | Claude | DONE | t-06-llm-adapter-jobs | LLMAdapter + GeminiBackend + ReplayBackend (record on miss), agent_runs logging, DB job runner with retry/backoff + `GET /api/jobs/{id}`. 24 tests. **A-4 still open**: no real Gemini call made yet (needs key + model name) |
| T-07 | `ProjectService` + `CampaignService` state machines (+ illegal-transition tests); `LedgerService` (append-only, gapless seq, POOL bucket) | §6.1, §6.3 | Claude | DONE | t-40-settlement-state-ledger | Project + campaign state machines (every illegal pair tested), append-only gapless POOL ledger, pool can't go negative. LedgerService has no bond/bonus types (D-020) |
| T-08 | Configure the **APIMatic Context Plugin** (MCP) in every AI coding tool used; add exact setup steps to AGENTS.md §6; claim free APIMatic subscription | §9.7 |  | TODO |  | Before T-20 |

### Track A1: Requirements (BA Agent + BRD)
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-10 | Projects + members (sponsors, supporters, freelancer) API | §10 | Claude | DONE | t-10-projects-transcripts | Create/list/get project, idempotent member invites, public vs member views, viewed-tracking. 31 tests (D-026) |
| T-11 | Transcript upload (text/file), line numbering | §7.1 | Claude | DONE | t-10-projects-transcripts | JSON or file upload (.txt/.vtt/.md), VTT cleaning, line numbering, `GET /projects/{id}/transcript` (added to SPEC 10). 25 tests; mutation-checked (D-026) |
| T-12 | BA scoring: prompt, `BAScoreOutput`, code-side total, gates, cap 89, source_refs downgrade + unit tests | §7.1 | Claude | DONE | t-12-ba-scoring | Schemas, pure scoring + gates + cap, prompt `ba-score-v1`, `BAAgent`, `ba_service.score_round`. 67 tests; mutation-checked; demo scene scores 58/79/93. No endpoint yet (T-13). No real Gemini call yet (A-4) (D-027) |
| T-13 | BA questions: prompt, `BAQuestionsOutput`, answer/skip endpoints, rounds, MAX_ROUNDS + finalize | §7.1 | Claude | DONE | t-13-ba-questions | Question agent + code-side filtering, rounds, answer/skip/finalize, run/view endpoints, `BA_RUN` job, rate limit. 83 tests; mutation-checked (11/11). Whole 58->79->93 scene passes over HTTP. No real Gemini call yet (D-028) |
| T-14 | BRD generator: prompt, `BRDContent`, REQ codes, Jinja Markdown, sha256 | §7.2 | Claude | DONE | t-14-brd-generator | Schemas, prompt `brd-gen-v1`, `BRDGenerator`, code-side assembly, Jinja renderer with escaping, sha256, `BRD_GENERATE` job, generate/read/download endpoints. 75 tests; mutation-checked (15/15 after one added test). Approvals are T-15. No real Gemini call yet (D-029) |
| T-15 | BRD approvals (hash-bound, unanimous), reject → new BA round + version bump | §7.2 | Claude | DONE | t-15-brd-approvals | Hash-bound unanimous decisions, lock + ledger + CONTRACTING, rejection reopens BA with a question for ALL, withdraw-by-reject, stale/foreign hash refused. 16 tests; mutation-checked (all caught after 2 added tests). (D-030) |
| T-16 | UI: BA Studio | §11 #4 |  | TODO |  | |
| T-17 | UI: BRD page (AG Grid requirements, approve/reject, download) | §11 #5 |  | TODO |  | |

### Track B1: Pledge-If (campaigns, holds, webhooks)
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-20 | `PayPalClient`: SDK for Orders (create `AUTHORIZE`, authorize), Payments (authorization get/capture/void/reauthorize, capture get, refund), Transaction Search; `httpx` for Payouts + webhook verify. **Plus a sandbox script:** authorize→capture (partial, `final_capture`), authorize→void, payout | §9.2–9.4, §9.7 | Claude | REVIEW | t-20-paypal-client | Client built on SDK 2.4.0 (reader, writer, order gateway, payouts, webhook verify, balances) + `scripts/sandbox_check.py`. 89 tests incl. real-model fakes; mutation-checked 22/22. **Needs a human:** run the script with sandbox keys to resolve A-1, A-2, A-8, A-9 (D-033) |
| T-21 | Webhook endpoint: signature verify, dedupe, job enqueue, monotonic processors for authorization/capture/refund/payout events (§9.5 table) | §9.5 |  | TODO |  | Save real event samples to `backend/tests/fixtures/webhooks/` |
| T-22 | Pledge Gate + pledge service: `pledges/order`, `pledges/authorize`, webhook effects, progress, goal-reached trigger | §8.2, §9.2 |  | TODO |  | |
| T-23 | UI: public campaign page (progress "held, not charged", countdown, PayPal button `intent=authorize`, pledge board AG Grid) | §11 #8 |  | TODO |  | A-11 |
| T-24 | Campaign setup API + launch (needs signed contract); deadline rule (`≤ opens_at + 72h − 2h`) | §8.2, §6.1 | Claude | DONE | t-24-campaign-setup | Setup (goal from contract + fees), launch (window re-checked), public view with lead controls and plain-words blockers. 48 tests; mutation-checked 19/19 after one added test (D-032). UI is screen #7/#8, not built |
| T-25 | Campaign outcome engine + clock job (every 60 s): goal reached / deadline → enqueue plan builds; `demo/campaigns/{id}/expire`; honor-period warnings; relaunch | §8.2, §6.1 |  | TODO |  | `decide_campaign_outcome` is a pure function with tests |
| T-27 | UI: campaign setup + lead panel (close and capture, cancel, relaunch, simulate deadline) | §11 #7, #8 |  | TODO |  | |

### Track A2: Contract, build & verify
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-30 | Conditional contract: offer, accept (BRD hash, PayPal email lock), `effective_at` on capture | §6.2, §10 | Claude | DONE | t-30-contract | Offer (replaces unsigned), accept (both hashes, locks PayPal email), GET for members; terms rendered from template; ledger CONTRACT_SIGNED without email. 25 tests; mutation-checked (D-031). UI is screen #6 (not built) |
| T-31 | Submissions + `ImageStore` (Cloudinary signed upload, `POST /images`, signed URLs; `LocalImageStore` for dev) + evidence API | §7.3, §10, §12 |  | TODO |  | Verifier fetches image bytes server-side for Gemini |
| T-32 | AutoChecks: SSRF-safe fetcher, URL/page/repo/commit/file/viewport checks + SSRF tests | §7.3 |  | TODO |  | |
| T-33 | Verifier questions: prompt, `VerifyQuestion`, skip ACs settled by auto checks | §7.3 |  | TODO |  | |
| T-34 | Verifier judge (vision) + snippet-in-repo check + deterministic aggregation + follow-up round + attempts | §7.3 |  | TODO |  | One judge call per submission |
| T-35 | UI: freelancer portal (contract, submit, evidence uploaders) | §11 #6, #9 |  | TODO |  | |
| T-36 | UI: verification report with AG Grid matrix | §11 #10 |  | TODO |  | |

### Track B2: Money core, Guardian, payouts
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-40 | Settlement engine (pure): `split_pro_rata`, `plan_captures`, `plan_refunds`, `plan_freelancer_payout`, `plan_hash` + tests (incl. property tests) | §8.3 | Claude | DONE | t-40-settlement-state-ledger | 13 tests incl. hypothesis property tests; worked examples 1-3 from SPEC 8.3 verified. `plan_hash` excludes idempotency keys (D-021) |
| T-26 | `PlanBuilder` (pure, reads DB): `CAPTURE_PLEDGES`, `RELEASE_HOLDS`, `FREELANCER_PAYOUT`, `REFUND_CAPTURED` specs + steps + idempotency keys + tests | §7.5.1, §8.3 | Claude | DONE | t-26-plan-builder | Four plan kinds + `save_proposed` + `rebuild` + release policies. 39 tests. Retry attempts in inputs (D-022). `REAUTH_PLEDGES` not built (SHOULD) |
| T-45 | `MoneyExecutor` + plan lifecycle + approvals API (`plans`, `review`, `approve`) + executor tests (refuses unapproved/mismatched/foreign steps) | §8.4, §8.5, §10 | Claude | DONE | t-45-money-executor | `MoneyExecutor` + `plan_lifecycle` (review/approve/confirm) + `/auth/login`,`/auth/me` + plans API (list/create/get/review/approve/simulate-tamper) + EXECUTE_PLAN job + chokepoint scan test. 71 tests; mutation-checked. Fake writer only: real PayPal writer is T-20/T-43 (D-024) |
| T-41 | Guardian rules G-01…G-13 + soft flags S-01…S-03 (pure; SDK mocked) + one pass/fail test per rule + tamper mutations | §7.5.2–7.5.3, §7.5.6 | Claude | DONE | t-41-guardian-rules | G-01..G-13 + S-01..S-03 + 5 tamper mutations, 63 tests incl. one pass/fail per rule; mutation-checked. PayPal reads go through an injected `PayPalReader` (real one arrives with T-20). Interpretations in D-023 |
| T-42 | Guardian LLM review (escalate-only) + decision logic + release policies (auto vs human) | §7.5.4–7.5.5 | Claude | DONE | t-42-guardian-llm | `GuardianLLM` agent + `guardian_facts` + `guardian_decision.combine` wired into `review_plan` and the review endpoint. 33 tests; mutation-checked. Never called on BLOCK; failure => HOLD (D-025). No real Gemini call made yet (A-4) |
| T-43 | Execution paths: capture/void steps, freelancer payout batch; webhooks + poll fallback; PAID / PAYOUT_FAILED | §8.5, §9.3–9.4 |  | TODO |  | |
| T-44 | `REFUND_CAPTURED` execution + cancel flow (builder in T-26) | §8.1 M7 |  | TODO |  | UI is cut-order #5 |
| T-46 | Strategist (deterministic): forecast, deadline suggestion, nudge target ranking + tests; API + forecast card | §7.4 |  | TODO |  | MVP |
| T-47 | Strategist LLM narrative + nudge drafts + numbers validator | §7.4 |  | TODO |  | SHOULD (cut order #1) |
| T-48 | Ledger ↔ PayPal reconciliation job (SDK Transaction Search) + "PayPal match" column | §9.7 |  | TODO |  | SHOULD |
| T-49 | UI: money plans viewer (steps grid, rule rows, risk card, decision, approve, simulate tamper) | §11 #11 |  | TODO |  | |

### Track C: Ledger, polish, ship
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-50 | UI: ledger AG Grid Community (type chips, pinned totals, filters, CSV, meta modal, live refresh) | §11 #12 |  | TODO |  | No Enterprise features |
| T-51 | UI: AI audit trail AG Grid | §11 #13 |  | TODO |  | |
| T-52 | `seed.py`: Velugu Cove project through BRD + contract; **a project whose round 1 has failed** (holds voided, nothing charged); **a project at `PAYOUT_READY`**; record replay fixtures | §16 |  | TODO |  | Don't pre-authorize live pledges more than ~2 days before recording |
| T-60 | Sample site v1 (missing form) + v2 (complete) in its own public repo; record both commit SHAs in §4 | §15 |  | TODO |  | |
| T-61a | Deploy hello-world API to Render (gets webhook URL early) | §14 |  | TODO |  | |
| T-61 | Full Render deploy via `render.yaml` (free API + 2 static sites) + env vars + Aiven CA secret file | §14 |  | TODO |  | Everything on free plans (§5.5) |
| T-62 | README (problem, Pledge-If explained, architecture diagram, setup, demo personas, tools used, eval results, production boundaries) | §18, §19.3 |  | TODO |  | |
| T-63 | AI eval mini-set + results table (BA, Verifier, Guardian, Strategist) | §13.3 |  | TODO |  | |
| T-64 | Rehearse E2E on Render, record video (<3 min), upload public to YouTube | §16 |  | TODO |  | |
| T-65 | Devpost submission (description, tools, sponsor tracks, links) | §18 |  | TODO |  | Target Thu 6 PM IST |

### Dependency hints
`T-04, T-06, T-07, T-40` first. `T-20` before any PayPal UI. `T-26` needs `T-40`. `T-41` and `T-45` need `T-26`. `T-25` needs `T-22`, `T-24`, `T-26`. `T-43` needs `T-45`. UI tasks need their API task `REVIEW` or better.

---

## 3. Verified facts & environment notes
_Add things you confirmed so the next AI doesn't re-verify. Include date and who verified._

| Date | Fact | Verified by |
|---|---|---|
| 2026-11-08 | Aiven: free MySQL is retired for new services; free PostgreSQL available (→ D-002) | Claude (web) |
| 2026-11-08 | Render: free web services spin down after ~15 min idle (~1 min wake); no free background workers | Claude (web) |
| 2026-11-08 | Render free Postgres expires after 30 days → not used (judging is after the deadline). 750 free instance h/month shared across free web services → only 1 free web service | Claude (web) |
| 2026-11-08 | Neon free plan: 1 GB storage/project, 100 CU-h/month, scales to zero after 5 min → valid fallback DB | Claude (Neon docs) |
| 2026-11-08 | Gemini free-tier per-model limits are only listed at aistudio.google.com/rate-limit; limits are per project | Claude (web) |
| 2026-11-08 | PayPal Python Server SDK (`paypal-server-sdk`, Python 3.7+) covers Orders v2, Payments v2, Vault v3, Transaction Search v1, Subscriptions v1. **Not** Payouts or webhooks → `httpx` for those | Claude (SDK README) |
| 2026-11-08 | APIMatic sponsor: Context Plugin (MCP) for PayPal; participants who use it get 1 month APIMatic Basic free, winners 6 months Business; no extra credentials needed | Claude (Devpost sponsor page) |
| 2026-11-08 | PayPal authorization: valid **29 days**, but PayPal recommends capturing within a **3-day honor period**; capture success depends on risk and funds. Orders must be `APPROVED` before `authorize`. JS SDK needs `intent=authorize` | Claude (PayPal docs) |
| 2026-11-08 | Reauthorize: blocked in the first 3 days (`REAUTHORIZATION_TOO_SOON`), new authorization ID each time; docs conflict on once vs multiple → unverified (A-10) | Claude (PayPal docs) |
| 2026-11-08 | Webhook event names confirmed: `PAYMENT.AUTHORIZATION.CREATED`, `PAYMENT.AUTHORIZATION.VOIDED` (manual or expiry), `PAYMENT.CAPTURE.COMPLETED/DECLINED/PENDING/REFUNDED/REVERSED`, `PAYMENT.PAYOUTSBATCH.*`, `PAYMENT.PAYOUTS-ITEM.*` (incl. `CANCELED`). Batch payout webhooks carry no item details | Claude (PayPal event list) |
| 2026-11-08 | **Not yet verified:** `final_capture` on partial capture releases the rest of the hold (A-8); void endpoint behaviour on partially captured holds | Open (T-20 script) |
| 2026-11-08 | Hackathon requires: meaningful PayPal + AI use, working demo (hosted URL or run instructions), public repo with visible OSS licence, public YouTube video < 3 min, tools list | Claude (Devpost page) |

## 4. Sandbox & demo data (no secrets here)
| Item | Value |
|---|---|
| Platform business sandbox email | _TBD_ |
| Supporter sandbox email | _TBD_ |
| Sponsor A (Lakshmi / Sea Breeze Homestay) | _TBD_ |
| Sponsor B (Ravi / Ravi's Fish Kitchen) | _TBD_ |
| Sponsor C (Meena / Cove Boat Tours) | _TBD_ |
| Freelancer (Arjun) | _TBD_ |
| Sample site v1 commit SHA | _TBD_ |
| Sample site v2 commit SHA | _TBD_ |
| Gemini model in use | _TBD_ |
| Gemini free RPM / RPD for that model | _TBD_ |
| Cloudinary free monthly credits / max file size | _TBD_ |

## 5. Known issues / tech debt
| ID | Issue | Severity | Noted by |
|---|---|---|---|
| — | — | — | — |

---

## 6. Handoff log (append newest at the TOP; never edit old entries)

Template:
```
### YYYY-MM-DD HH:MM IST · <who> · <tasks touched>
- Did: …
- State now: T-xx DONE, T-yy IN_PROGRESS (branch t-yy-…, what's left: …)
- Tests: `pytest backend/tests/test_x.py` passing / failing (why)
- Contract changes: none | see D-00N
- Next step for whoever picks up: …
- Gotchas: …
```

### 2026-11-08 · Claude · T-20
- Did: installed `paypal-server-sdk==2.4.0` and read its real controllers/models; `services/paypal_client.py` (`PayPalClient`: reader `get_authorization/get_capture/platform_balance_cents`; writer `capture_authorization/void_authorization/refund_capture/create_payout_batch`; `get_payout_batch`; `verify_webhook_signature`; order gateway `create_authorize_order/authorize_order/get_order`; `configure_from_settings` called from the app lifespan); `scripts/sandbox_check.py` (interactive sandbox proof); chokepoint tests extended (order calls only from `pledge_service.py`, only the client imports an HTTP library); `requirements.txt` pins the SDK.
- State now: T-20 REVIEW (code and fake-backed tests done; the real sandbox run needs keys). Resolves nothing in section 3 yet.
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 681 passed (89 new: 59 client, 15 integration with executor + Guardian, 13 script, 2 chokepoint). Mutation-checked: 22 breakages, all caught.
- Contract changes: D-033 (no SPEC changes).
- **Human step (when sandbox keys exist):** put `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET` in `backend/.env`, then `cd backend && .venv/Scripts/python scripts/sandbox_check.py --payout-to <Arjun's sandbox email>`. It pauses twice and prints a link: open it, log in as a US sandbox *personal* buyer, approve, press Enter. Paste its summary into section 3 and report any FAIL (especially A-8: does a final partial capture release the remainder?).
- Next step: T-22: `services/pledge_service.py` (the only caller of `create_authorize_order`/`authorize_order`): Pledge Gate checks (campaign OPEN and before deadline, `min_pledge <= amount <= remaining_need`, currency), `POST /campaigns/{id}/pledges/order` and `/pledges/authorize`, pledge rows `CREATED -> AUTHORIZED` from PayPal's response (amount must equal the order amount; store authorization id, payer email/id, `authorized_at`, `honor_until = +3 d`, `valid_until = +29 d`), `GET /campaigns/{id}/pledges` (no emails publicly), goal-reached trigger. The webhook (T-21) is the source of truth; the authorize response only updates the UI optimistically.
- Gotchas: (1) The SDK leaves unset optional fields as missing attributes; use `_opt`. (2) Authorization statuses in the SDK enum are CREATED, CAPTURED, PARTIALLY_CAPTURED, VOIDED, DENIED, PENDING (no EXPIRED): anything other than CREATED is a mismatch in G-06. (3) `void_payment` returns 204 with no body; the client reports `{"status": "VOIDED"}`. (4) Fakes must be built from real SDK models; never from dicts. (5) A shell heredoc with Python can eat backslashes (`\b` became a backspace and silently disarmed a guard test); edit files with the Edit/Write tools.

### 2026-11-08 · Claude · T-24
- Did: `services/campaign_rules.py` (pure: `goal_for`, `deadline_window`, `validate_deadline`, `validate_terms`, `CampaignParams`), `services/campaign_ops.py` (`setup_campaign`, `launch`, `blocker_details`, `blockers`, `pledge_totals`, `campaign_view`), `routers/campaigns.py` (`POST /projects/{id}/campaigns`, `GET /campaigns/{id}` public, `POST /campaigns/{id}/launch`).
- State now: T-24 DONE (branch t-24-campaign-setup). A launched campaign is `OPEN` with `opens_at` set and the project is `PLEDGING`.
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 592 passed (48 new: 17 pure, 31 API). Mutation-checked: 19 breakages; 2 survived at first (contract-unsigned guard, live-campaign guard), a test now forces both; all caught.
- Contract changes: D-032 (no SPEC text changes).
- Next step: T-20: install `paypal-server-sdk`, introspect its real controllers (orders create/authorize, payments authorizations get/capture/void/reauthorize, captures get/refund, transaction search) instead of relying on memory; implement `services/paypal_client.py` as the ONLY module importing the SDK, with a `PayPalReader` (G-06/G-08 reads) and `PayPalWriter` (executor writes) implementation plus `httpx` for Payouts and webhook verification; unit-test with mocked HTTP; write the sandbox script (needs keys) and `paypal_io.configure(...)` wiring at startup. Then T-22 uses an `OrderGateway` for the buyer-side order/authorize calls.
- Gotchas: (1) `held_not_charged` is derived from the campaign state, not from pledges. (2) The deadline is stored in UTC; SQLite returns it naive, so always pass it through `campaign_rules.as_utc`. (3) `launch` re-validates the window against the real opening time, so a lead who waits too long gets `DEADLINE_TOO_SOON`. (4) The default 48 h deadline suggestion (Strategist, T-46) is not in the API yet; the lead picks. (5) Relaunch after FAILED is T-25.

### 2026-11-08 · Claude · T-30
- Did: `services/contract_service.py` (`offer`, `accept`, `render_terms`, `terms_hash`, `contract_view`, `approved_brd`, `freelancer_member`, `get_contract`), `templates/contract.md.j2`, `routers/contract.py` (`POST /projects/{id}/contract/offer`, `GET /projects/{id}/contract`, `POST /projects/{id}/contract/accept`). SPEC 10 gained the GET row.
- State now: T-30 DONE (branch t-30-contract). A signed contract has `signed_at`, a locked `freelancer_paypal_email`, `conditional = true`, `effective_at = null`, and the project is in `CAMPAIGN_SETUP`.
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 544 passed (25 new in `tests/test_contract.py`). Mutation-checked: 15 breakages; 13 caught at first, 1 needed a new test (signed contract replaced after a state rewind), 1 is an equivalent mutant (redundant role check).
- Contract changes: D-031 and one SPEC 10 row.
- Next step: T-24: `POST /projects/{id}/campaigns {deadline_at, close_policy, min_pledge_cents?, suggested_share_cents?}` (lead; project `CAMPAIGN_SETUP`; needs the signed contract) creates a `SETUP` campaign with `goal_cents = contract.amount_cents + fee_reserve_cents` (`FEE_RESERVE_PER_ITEM_CENTS` x 1 payout item); `POST /campaigns/{cid}/launch` sets `opens_at = now`, validates `deadline_at <= opens_at + PLEDGE_MAX_HOURS - HONOR_SAFETY_MARGIN_HOURS` (and `> opens_at`), `OPEN`, project CAMPAIGN_SETUP -> PLEDGING; `GET /campaigns/{cid}` public view; relaunch after FAILED is T-25.
- Gotchas: (1) The lead's and sponsors' login emails cannot be the freelancer's PayPal email, but their future PayPal payer emails are unknown until they pledge (Guardian S-01 covers that). (2) `terms_sha256` covers the text and the numbers; the PayPal email is NOT in it (it is supplied at signing). (3) The contract view shows the freelancer's PayPal email to every member, which is intended. (4) A freelancer cannot decline (GAP-32).

### 2026-11-08 · Claude · T-15
- Did: `services/brd_approvals.py` (`decide`, `decisions_on`, `voters`, locking, rejection-reopens-BA), `POST /projects/{id}/brd/{version}/decision` in `routers/brd.py` (`DecisionIn`), tests `tests/test_brd_approvals.py` (16).
- State now: T-15 DONE (branch t-15-brd-approvals). A locked BRD (`status APPROVED`, `locked_at`, project `CONTRACTING`) is what T-30 binds to.
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 519 passed (16 new). Mutation-checked: 13 deliberate breakages; 2 survived at first (old-hash rows counting, freelancer vote at service level), two tests added, all caught.
- Contract changes: D-030 (no change to SPEC text; a rejection question uses `dimension = "BRD"`).
- Next step: T-30: `POST /projects/{id}/contract/offer {amount_cents, delivery_days}` (lead, project CONTRACTING, a FREELANCER member must exist, amount <= budget and <= `PAYOUT_MAX_CENTS`) creates a `contracts` row bound to the APPROVED BRD (`brd_id`, `brd_sha256`), `terms_md` rendered by code, `sha256`; `POST /projects/{id}/contract/accept {paypal_email, brd_sha256, terms_sha256}` (the freelancer) checks both hashes, locks `freelancer_paypal_email`, sets `signed_at`, moves the project CONTRACTING -> CAMPAIGN_SETUP, ledger `CONTRACT_SIGNED`; `effective_at` is set later by the capture plan (already done in `plan_lifecycle._on_done`). G-12 already compares `contract.brd_sha256` with the locked BRD hash.
- Gotchas: (1) Approvals count only on the exact hash, never on a version number. (2) A rejection adds `round` and an OPEN ALL question with dimension `BRD`; the UI must show a null `dimension_name` as 'BRD feedback'. (3) Every sponsor must approve, so an unresponsive sponsor blocks the project (GAP-28). (4) The `BRD_LOCKED` ledger row is the first thing created for a project's money-adjacent audit trail; its meta has the hash.

### 2026-11-08 · Claude · T-14
- Did: `schemas/brd.py` (BRDDraft/BRDContent + typed pieces), `agents/prompts/brd_gen.md` + `agents/brd_generator.py` (`BRDGenerator`, `get_brd_generator`/`set_brd_generator`, prompt `brd-gen-v1`), `templates/brd.md.j2` + `services/brd_render.py` (escaping filters, `render_markdown`, `content_hash`), `services/brd_service.py` (`assemble`, `open_items_from_score`, `generate_brd`, `request_generation`, `generate_once`, `latest_brd`, `member_names`), `routers/brd.py` (`POST /projects/{id}/brd/generate` 202, `GET /projects/{id}/brd[?version=]`, `GET /projects/{id}/brd/{version}.md`), `BRD_GENERATE` job. Also: `docs/GAPS_AND_FIXES.md` created, `AGENTS.md` commands filled in, `.github/workflows/ci.yml` added, `requirements.txt` pins corrected (pydantic 2.14.3) and `jinja2` added.
- State now: T-14 DONE (branch t-14-brd-generator).
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 503 passed (66 new). Verified a fresh virtualenv install of `requirements.txt` passes the whole suite. Mutation-checked: 15 deliberate breakages, all caught (one needed an extra test pinning the hash algorithm).
- Contract changes: D-029. SPEC 10 already listed these endpoints.
- Next step: T-15: `POST /projects/{id}/brd/{version}/decision {decision, brd_sha256, comment?}` for sponsors (the lead is a sponsor): decision counts only if `brd_sha256` equals the BRD's current hash; unanimous APPROVE across LEAD+SPONSOR members -> BRD `APPROVED`, `locked_at`, ledger `BRD_LOCKED`, project BRD_REVIEW -> CONTRACTING; any REJECT with a comment -> comment becomes a new BA question addressed to ALL, project BRD_REVIEW -> REQUIREMENTS, BA session back to ACTIVE with `round + 1`, BRD stays for history (to be SUPERSEDED when v+1 is generated). `GET /projects/{id}/brd` already returns `approvals` and `awaiting` (only decisions made on the current hash count).
- Gotchas: (1) The shared `World` test fixture pre-creates an APPROVED BRD and a contract; BRD tests delete them. (2) A BRD for a FINALIZED analysis carries its red gates in `open_items`. (3) `BRD_INVALID` is raised after a successful AI call, so each job retry calls the model again (see GAP-24). (4) The render is deterministic but names come from the database, so the Markdown can change while the content hash does not (renaming a user); the hash is of the JSON content only. (5) UI must not render the Markdown as raw HTML.

### 2026-11-08 · Claude · T-13
- Did: `services/ba_rounds.py` (`run_round`, `generate_questions`, `filter_questions`, `answer_question`, `skip_question`, `request_run`, `finalize`, fallback questions), `agents/ba_agent.py` additions (`BAQuestionsAgent`, `QuestionInputs`, `get_ba_agents`/`set_ba_agents`, prompt `ba-questions-v1`), `agents/prompts/ba_questions.md`, `routers/ba.py` (`POST /projects/{id}/ba/run` 202, `GET /projects/{id}/ba`, `POST /ba/questions/{qid}/answers|skip`, `POST /projects/{id}/ba/finalize`), `BA_RUN` job handler, stricter `BAQuestion` schema (30 words, 2 to 4 options).
- State now: T-13 DONE (branch t-13-ba-questions).
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 437 passed (34 new in `test_ba_rounds.py`, 8 in `test_ba_api.py`). Mutation-checked: 11 deliberate breakages, all caught (one needed an extra defence-in-depth test).
- Contract changes: D-028 (rounds numbering, completion rules, new `FINALIZED` session state).
- Next step: T-14 BRD generator: input is the latest `BAScore` (`extracted_requirements_json`, `conflicts_json`, `gates_json.observations.out_of_scope`) plus all Q&A (`ba_rounds.answers_for`); output `BRDContent`; code assigns REQ codes, validates every MUST has an AC, renders Markdown with Jinja, hashes with sha256. `score_at_generation` and `open_items` come from the session score/gaps (a FINALIZED session must list its red gates and dimensions below 1.0). Set the session to `BRD_GENERATED` and project to BRD_REVIEW only when approvals start (T-15 handles the REQUIREMENTS<->BRD_REVIEW loop).
- Gotchas: (1) A question's answers are shared with every member (names attached). (2) `session.round` increments only when a round fully closes; the `BA_RUN` job then scores the new round. (3) Answers for round N are fed to the scorer as `answer:<id>` references; fabricated ids are downgraded. (4) With no AI configured `POST /ba/run` still returns 202; the job retries and records `not configured`. (5) The default `get_ba_agents()` builds from settings and is only cached when it succeeded. (6) Tests must call `set_ba_agents(...)` and reset it with `set_ba_agents(None)`, otherwise the real engine is used.

### 2026-11-08 · Claude · T-12
- Did: `schemas/ba.py` (BAScoreOutput etc. incl. BAQuestion/BAQuestionsOutput for T-13), `services/ba_scoring.py` (pure: weights, exact integer total, valid-ref downgrade, GT-1..GT-5, cap 89, `gaps`), `agents/prompts/ba_score.md` + `agents/ba_agent.py` (`BAAgent.judge`, `BAInputs`, prompt `ba-score-v1`), `services/ba_service.py` (`get_or_create_session`, `build_inputs`, `score_round`, `qa_pairs`, `latest_score`). Test helpers: `tests/ba_factory.py`, `scripted_adapter` in `tests/factories.py`.
- State now: T-12 DONE (branch t-12-ba-scoring).
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 403 passed (67 new). Mutation-checked: 7 of 8 breakages caught; the survivor (unknown member ids in GT-5) is an equivalent mutant, the behaviour it touches (stripping unknown ids from stored requirements) is tested separately.
- Contract changes: D-027 (float coverage with validator, typed positions, gate definitions, storage layout).
- Next step: T-13: question generation using `ScoreResult.gaps` (rank = weight x (1 - coverage), conflicts first), `BAQuestionsOutput` (already defined), endpoints `POST /projects/{id}/ba/run` (202 job: score + questions), `GET /projects/{id}/ba`, `POST /ba/questions/{qid}/answers`, `/skip`, `POST /projects/{id}/ba/finalize`, round advance + MAX_ROUNDS; rate limit 8 runs/project/hour. `session.round` is incremented by T-13 when a round's questions are all answered or skipped.
- Gotchas: (1) `score_round` needs project state REQUIREMENTS and a transcript. (2) Re-scoring reuses `session.round`; T-13 must bump it before the next score or two scores share a round. (3) A different input (e.g. new answers or the previous extraction) means a different replay hash, so fixtures are per round. (4) The model never sees emails or the freelancer; only LEAD/SPONSOR members appear as people. (5) No real Gemini call yet: the nested schema (lists of objects, enums) may need flattening on first live use (A-4). (6) GT-1 also passes from the project record, so a lead who entered a budget and delivery days satisfies it even if the meeting never said so.

### 2026-11-08 · Claude · T-10, T-11
- Did: `routers/projects.py` (create/list/get project, `PUT /members`, `POST /transcripts` JSON or multipart, `GET /transcript`), `services/project_ops.py` (create, `upsert_invitees`, `touch_member`, `campaign_summary`, `add_transcript`), `services/transcripts.py` (pure `normalize`, VTT cleaning, `numbered`), `optional_user` in `auth.py`, `python-multipart` pinned. `docs/SPEC.md` section 10 gained the `GET /projects/{id}/transcript` row.
- State now: T-10 DONE, T-11 DONE (branch t-10-projects-transcripts).
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 336 passed (67 new). Mutation-checked: six deliberate breakages (email leak, pledge-plan leak, any-member upload, upload after BRD review, freelancer-as-sponsor, signed-out transcript read) were all caught.
- Contract changes: D-026 and one new SPEC 10 row.
- Next step: T-12 BA scoring must number lines with `services.transcripts.numbered` and read `project_ops.latest_transcript`; T-13 questions are addressed to `project_members.id`s (the API already returns them in `members[].id`). Creating the `ba_sessions` row is left to T-12/T-13 (`POST /projects/{id}/ba/run`).
- Gotchas: (1) `GET /projects/{id}` writes (viewed-tracking) when a member calls it. (2) Members are looked up by lower-cased email, so a person who logs in with the invited email is automatically a member. (3) Do not edit test files with Python inside a bash heredoc when the text contains backslash escapes; a previous attempt corrupted a test file with a NUL byte (fixed by deleting and rewriting it). (4) A project's transcript cannot change after REQUIREMENTS, so a lead who needs to re-upload after BRD review must reject the BRD (which returns the project to REQUIREMENTS, T-15). (5) Supporters are not members until they pledge (T-22).

### 2026-11-08 · Claude · T-42
- Did: `agents/guardian_llm.py` (`GuardianLLM`, `GuardianLLMOutput`, `Finding`, `get_guardian_llm`, `set_guardian_llm`, prompt `guardian-llm-v1`), `agents/prompts/guardian_llm.md`, `services/guardian_facts.py` (`build_facts`), `services/guardian_decision.py` (`combine`, escalate-only), `review_plan(..., llm=)` in `plan_lifecycle.py`, review endpoint injects `get_guardian_llm`; plan detail now includes `earliest_honor_until` for capture plans; `LLMAdapter.generate_json(run_ids=[...])` reports the `agent_runs` id.
- State now: T-42 DONE (branch t-42-guardian-llm). The Guardian is complete: 13 rules + 3 flags + escalate-only AI + release policies.
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 269 passed (33 new in `tests/test_guardian_llm.py`). Mutation-checked: six deliberate breakages (AI high ignored, AI failure treated as pass, AI softens a BLOCK, AI called on BLOCK, names leaking into trusted facts, untrusted fence removed) were all caught.
- Contract changes: D-025 (typed `Finding`, decision floor, facts boundary).
- Next step: T-25 clock/outcome engine and T-27 campaign UI will call `review_plan(..., llm=get_guardian_llm())` for system capture/release plans; a real Gemini call (A-4) is still outstanding and may need the `GuardianLLMOutput` schema flattened if Gemini rejects it.
- Gotchas: (1) With `AI_PROVIDER=replay_or_real` and no key or fixture, every review is a HOLD (`GUARDIAN_LLM_UNAVAILABLE`); record fixtures with a key before the demo (T-52) or capture/release plans will wait for a human. (2) The facts must stay deterministic or replay fixtures will miss; do not add timestamps like "now". (3) Any change to `guardian_llm.md` needs `PROMPT_VERSION` bumped. (4) `get_guardian_llm()` is cached only when the adapter built successfully. (5) The AI call writes its own `agent_runs` row in a separate session/commit.

### 2026-11-08 · Claude · T-45
- Did: `services/money_executor.py` (`execute`, `ExecutionRefused`), `services/plan_lifecycle.py` (`review_plan`, `approve_plan`, `simulate_tamper`, `confirm_step`, `fail_step`, `refresh_plan_state`, `latest_review`), `services/paypal_io.py` (`PayPalWriter` protocol, `PayPalWriteError`, `Unconfigured*` placeholders, `configure()`), `services/job_handlers.py` (`EXECUTE_PLAN`), `auth.py` + `routers/auth.py` (JWT login, `/auth/me`, `require_member`), `routers/plans.py`, top-level SPEC 10 error shape in `main.py`. Guardian G-02/G-12 now accept `PAYOUT_FAILED` for retries.
- State now: T-45 DONE (branch t-45-money-executor). Also delivers the backend part of login (`/auth/login`, `/auth/me`) needed by T-05.
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 236 passed (71 new). Mutation-checked: 8 of 9 deliberate breakages of executor/lifecycle safety checks were caught by the executor suite and the 9th (HOLD without ack at approval) by the lifecycle suite.
- Contract changes: none to SPEC; D-024 records the executor/confirmation/approval rules. API error responses are now top-level `{"error": {...}}` (was FastAPI's `{"detail": ...}`).
- Next step: T-21 webhooks must verify the signature, dedupe, then call `plan_lifecycle.confirm_step` / `fail_step` and nothing else; T-43 wires the real writer (`paypal_io.configure(writer=...)`) and the payout/refund poll fallback; T-42 adds the Guardian LLM + persists `llm_review_json`.
- Gotchas: (1) The executor commits the session it is given (needed so SENT survives a crash). (2) `PlanBuilder` for captures needs the campaign `OPEN`, which is why the executor rebuilds only on first start. (3) `confirm_step` is the only place pledge/ledger/project state changes after PayPal writes. (4) With no PayPal credentials the default writer fails every step as non-transient: the plan ends FAILED and nothing moves. (5) `REAUTH_AUTH` is refused by both builder and executor. (6) `/jobs/{id}` still has no auth check. (7) A PARTIAL capture leaves the campaign `CAPTURING` and the project `PLEDGING` by design; the lead repair path (refund the captured, or rebuild) is not built. (8) Do not hand a `PayPalWriter` to anything except `execute`; `tests/test_chokepoint.py` enforces this by scanning the source.

### 2026-11-08 · Claude · T-41
- Did: `services/guardian_rules.py` (`evaluate(db, plan, spec=None, now, reader, params)` -> `Evaluation` with per-rule results, soft flags and `rule_decision`; `PayPalReader` protocol, `PayPalObject`, `PayPalUnavailable`, `GuardianParams`), `services/guardian_tamper.py` (`apply_mutation`, `MUTATIONS` table with expected failing rules). `tests/factories.py` now holds the shared `World` fixture builder.
- State now: T-41 DONE (branch t-41-guardian-rules).
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 165 passed (63 new in `tests/test_guardian_rules.py`). Mutation-checked: disabling G-12's recipient check and G-03's receiver check makes the targeted tests fail.
- Contract changes: none to SPEC; interpretations logged in D-023.
- Next step: T-45 MoneyExecutor (must call `plan_builder.rebuild` and refuse a hash mismatch, and hardcode `final_capture=true`), then T-42 (Guardian LLM review + `decision` combining rules, flags and LLM; persist `guardian_reviews`; release policies).
- Gotchas: (1) Rules re-run `PlanBuilder.rebuild` with the supplied `now`, so G-01 fails if a hold lapses or a pledge is voided after the preview; this is intended. (2) `rebuild` needs the campaign `OPEN` for captures, so the executor must verify BEFORE moving the campaign to `CAPTURING`. (3) Nothing persists a `guardian_reviews` row yet (T-42). (4) Simulated reviews (demo tamper) must be stored with `simulated=true` and use a no-network reader; the API for that is T-49/T-42. (5) The real PayPal reader (SDK `authorizations get`, `captures get`, Transaction Search balance) is part of T-20; map PayPal statuses to `PayPalObject.status` (`CREATED` for a live hold, `COMPLETED` for a capture). (6) S-01/S-02 only look at pledges with a `payer_email`, which comes from PayPal at authorize time.

### 2026-11-08 · Claude · T-26
- Did: `services/plan_builder.py`: `build_capture_pledges`, `build_release_holds`, `build_freelancer_payout`, `build_refund_captured`, `build` (dispatch), `rebuild` (for Guardian G-01 and the executor), `release_policy_for`, `save_proposed` (idempotent), `live_valid_pledges`. Each returns `BuiltPlan(spec, plan_hash)` with step idempotency keys derived from the hash.
- State now: T-26 DONE (branch t-26-plan-builder).
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 102 passed (39 new in `tests/test_plan_builder.py`).
- Contract changes: D-022 (`inputs.attempt` on retried plans). SPEC 8.6 and 7.5.1 are otherwise unchanged.
- Next step: T-41 Guardian rules (use `plan_builder.rebuild` for G-01) and T-45 MoneyExecutor (re-run `rebuild` before every execution).
- Gotchas: (1) "live-valid" = AUTHORIZED + authorization id + `honor_until > now`; stricter than the 29-day validity on purpose. (2) Plans depend on `now`, so callers pass `now`; never read the clock inside a rule. (3) A pledge whose pro-rata capture rounds to 0 gets no step and stays held; unreachable with min pledge 500 but untested. (4) The builder only checks things it needs to compute the plan; deadline, success-condition and approval rules stay in the Guardian (G-09, G-11, G-12). (5) `RELEASE_HOLDS` is allowed from OPEN or FAILING, and voids every AUTHORIZED hold including lapsed ones. (6) Pledge `CREATED` rows never hold money and are ignored everywhere.

### 2026-11-08 · Claude · T-06
- Did: `agents/llm_adapter.py` (TextPart/ImagePart, `input_hash`, `ReplayBackend` with record-on-miss, `GeminiBackend` via google-genai 3.0.0 with JSON schema output, `LLMAdapter` with one validation retry and an `agent_runs` row per call, `build_adapter` for `AI_PROVIDER`), `agents/untrusted.py` (`untrusted()` wrapper + `UNTRUSTED_RULE`), `services/jobs.py` (`@register`, `enqueue`, `run_one`, `JobRunner`, crash recovery), `routers/jobs.py`, lifespan wiring in `main.py`.
- State now: T-06 DONE (branch t-06-llm-adapter-jobs).
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 63 passed. Also smoke-tested the real app: enqueued a job, runner completed it, `/api/jobs/{id}` returned DONE.
- Contract changes: none. `generate_json` takes an extra `prompt_version` argument (needed for the input hash).
- Next step: T-26 PlanBuilder (T-40 is done), or auth + projects (T-10/T-11) so jobs and endpoints can be role-checked.
- Gotchas: (1) **A-4 unverified**: no real Gemini call has been made; set `GEMINI_API_KEY` and `AI_MODEL` and run one call before relying on structured output with the BA schemas (`list[dict]` fields may need flattening). (2) `GET /jobs/{id}` has no auth yet (TODO in code); add membership check once auth exists. (3) `agent_runs` rows are written in their own session so they survive a caller rollback. (4) Agents must wrap user text with `untrusted()` and include `UNTRUSTED_RULE` in the system prompt. (5) Replay fixtures are keyed by prompt text, so any prompt edit needs `PROMPT_VERSION` bumped or fixtures silently miss.

### 2026-11-08 · Claude · T-40, T-07
- Did: `services/settlement.py` (split_pro_rata, plan_captures, plan_refunds, plan_freelancer_payout, canonical_json, plan_hash, idempotency_key), `schemas/plans.py` (PlanStep, MoneyPlanSpec), `services/ledger.py` (append-only via ORM event guards, gapless seq, pool balance, sign rules per type, pool never negative), `services/state_machines.py` (ProjectService/CampaignService.transition writing STATE_CHANGE rows).
- State now: T-40 DONE, T-07 DONE (branch t-40-settlement-state-ledger).
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` -> 39 passed.
- Contract changes: D-021 (plan_hash excludes idempotency keys; the spec was circular).
- Next step: T-06 (LLMAdapter, ReplayModel, agent_runs logging, job runner) or T-26 PlanBuilder (needs T-40, now available).
- Gotchas: services only `flush`; the caller commits. Append-only is enforced at ORM level (not DB triggers), so raw SQL can still alter rows; add a DB trigger if time allows. Campaign `FAILING` requires `fail_reason`. Deadline rule and `decide_campaign_outcome` are NOT built yet (T-24/T-25).

### 2026-11-08 · Claude · T-04
- Did: moved docs to the spec layout (root `AGENTS.md`, `.env.example`, `docs/`); added `.gitignore`, MIT `LICENSE`; built `backend/` (FastAPI app, `config.py`, `db.py`, `/api/healthz`), SQLAlchemy models for all 32 §6.2 tables (`app/models/tables.py`), Alembic migration `0001`, pytest setup.
- State now: T-04 DONE (branch t-04-backend-foundation). Part of T-01 done (LICENSE, .gitignore, docs); GitHub About/secret scanning still manual.
- Tests: `cd backend && .venv/Scripts/python -m pytest -q` → 4 passed.
- Contract changes: none.
- Next step: T-40 settlement engine (pure + hypothesis tests), then T-07 state machines + LedgerService.
- Gotchas: IDs use `BigInteger` with an Integer variant on SQLite (SQLite only autoincrements INTEGER PKs). Migration was autogenerated on SQLite; re-check it once against real Postgres (T-61a). Windows: venv is `backend/.venv/Scripts/`. The `AI-Toolkit/` folder is an embedded git repo (gitlink), not our code.

### 2026-11-08 · Claude (spec author) · SPEC v2.1 (bond and bonus removed)
- Did: removed the organizer bond and the failure bonus (D-020) because the bonus was a pure loss for the organizer. Failure now means `RELEASE_HOLDS` (void all holds, nobody charged). Removed the `bonds` table, bonus fields, BOND bucket, bond endpoints/UI, bonus payout batches, `BONUS_*` env vars. Guardian is now 13 hard rules (G-01…G-13) and 3 soft flags (S-01…S-03); money-map rows renumbered M1…M6. Deadline rule is `opens_at + 72h − 2h`.
- State now: all tasks still TODO. Task rows updated to match.
- Next step: unchanged (T-20 sandbox script, then T-40).
- Gotchas: the mechanism is now a plain assurance contract, not a dominant one. Do not write "dominant assurance", "no-lose" or "bonus" in the pitch, UI or README. Old rule IDs G-12/G-14/G-15 are now G-11/G-12/G-13.

### 2026-11-08 12:10 IST · Claude (spec author) · SPEC v2.0 (Pledge-If)
- Did: integrated Pledge-If dominant assurance campaigns. Funding is now authorize→capture-or-void with an organizer bond; added conditional contract, Campaign Strategist, MoneyPlan + MoneyExecutor, Guardian generalised to 15 rules + 4 soft flags across plan kinds, POOL/BOND ledger buckets, 72 h campaign cap. Cut milestones, surplus refunds, HF adapter, Ask-the-ledger, care plan. See SPEC Appendix B and D-014…D-019.
- State now: all tasks TODO; task board rewritten (new IDs T-22…T-27, T-40…T-49).
- Next step: T-20 script first (it resolves A-1, A-8, A-9 and decides whether `final_capture` partial capture works as specced).
- Gotchas: a pledge hold is only guaranteed for 3 days; authorize fresh live pledges within ~2 days of recording. `MoneyExecutor` is the only module allowed to call PayPal write endpoints.

### 2026-11-08 11:35 IST · Claude (spec author) · docs (APIMatic)
- Did: added APIMatic integration (SPEC §9.6, D-013): Context Plugin for all AI coders (T-08), SDK for Orders/Payments/Transaction Search, new Guardian rule G-13 and SDK-backed G-09, reconciliation job (T-46), optional care plan via Subscriptions (T-47).
- Next step: do T-08 before any PayPal code.

### 2026-11-08 11:20 IST · Claude (spec author) · docs
- Did: switched images to Cloudinary (D-004 v2), frontend to a static export with Bearer auth (D-009, D-010), added free-tier budget (SPEC §5.5), AG Grid Community only.
- State now: all tasks TODO.
- Next step: T-03 now includes Cloudinary and the "no credit card" rule.
- Gotchas: don't add an uptime pinger (shared 750 free hours). Don't use Render's free Postgres (expires in 30 days).

### 2026-11-08 11:30 IST · Claude (spec author) · docs
- Did: wrote `docs/SPEC.md`, `docs/STATUS.md`, `docs/DECISIONS.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.env.example`, sample transcript.
- State now: all tasks TODO.
- Next step: humans do T-01/T-02/T-03 in parallel; an AI starts T-04 (backend skeleton) and another starts T-05 (frontend skeleton).
- Gotchas: create every PayPal sandbox account with country **US** (India↔India fails with UNSUPPORTED_PAYEE_CURRENCY). Use PostgreSQL on Aiven, not MySQL (D-002).
