# BriefPay: Build Status & Handoff Log

> **This is the single source of truth for what is done.** Every AI assistant and human updates it at the end of every session (see `/AGENTS.md` §3).
> Times in **IST**. Deadline: **Fri Nov 13, 1:30 AM IST** (Nov 12, 12:00 PM PST). Internal submit target: **Thu Nov 12, 6:00 PM IST**.

---

## 1. Snapshot

| Field | Value |
|---|---|
| Last updated | 2026-11-08 by Claude: T-04 backend foundation done |
| Overall phase | **Day 0: backend skeleton + schema built; no features yet** (plain-English summary: `docs/PROGRESS_SUMMARY.md`) |
| Current day goal (Sun Nov 8) | `/healthz` live on Render; a sandbox script proves authorize→capture, authorize→void and a payout |
| Next task to pick up | Track A: **T-40**, then **T-07**, **T-06** · Track B: **T-02** (human, sandbox keys), **T-08**, then **T-20** |
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
| T-06 | LLM adapter (`GeminiModel`, `ReplayModel`), `agent_runs` logging, in-process DB job runner + `GET /jobs/{id}` | §7.0 |  | TODO |  | Verify Gemini model name (A-4). No HF adapter (D-019) |
| T-07 | `ProjectService` + `CampaignService` state machines (+ illegal-transition tests); `LedgerService` (append-only, gapless seq, POOL bucket) | §6.1, §6.3 | Claude | IN_PROGRESS | t-40-settlement-state-ledger | |
| T-08 | Configure the **APIMatic Context Plugin** (MCP) in every AI coding tool used; add exact setup steps to AGENTS.md §6; claim free APIMatic subscription | §9.7 |  | TODO |  | Before T-20 |

### Track A1: Requirements (BA Agent + BRD)
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-10 | Projects + members (sponsors, supporters, freelancer) API | §10 |  | TODO |  | |
| T-11 | Transcript upload (text/file), line numbering | §7.1 |  | TODO |  | Sample: `docs/samples/velugu_cove_meeting_transcript.txt` |
| T-12 | BA scoring: prompt, `BAScoreOutput`, code-side total, gates, cap 89, source_refs downgrade + unit tests | §7.1 |  | TODO |  | |
| T-13 | BA questions: prompt, `BAQuestionsOutput`, answer/skip endpoints, rounds, MAX_ROUNDS + finalize | §7.1 |  | TODO |  | |
| T-14 | BRD generator: prompt, `BRDContent`, REQ codes, Jinja Markdown, sha256 | §7.2 |  | TODO |  | |
| T-15 | BRD approvals (hash-bound, unanimous), reject → new BA round + version bump | §7.2 |  | TODO |  | |
| T-16 | UI: BA Studio | §11 #4 |  | TODO |  | |
| T-17 | UI: BRD page (AG Grid requirements, approve/reject, download) | §11 #5 |  | TODO |  | |

### Track B1: Pledge-If (campaigns, holds, webhooks)
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-20 | `PayPalClient`: SDK for Orders (create `AUTHORIZE`, authorize), Payments (authorization get/capture/void/reauthorize, capture get, refund), Transaction Search; `httpx` for Payouts + webhook verify. **Plus a sandbox script:** authorize→capture (partial, `final_capture`), authorize→void, payout | §9.2–9.4, §9.7 |  | TODO |  | Resolves A-1, A-2, A-8, A-9. Use the Context Plugin for method names |
| T-21 | Webhook endpoint: signature verify, dedupe, job enqueue, monotonic processors for authorization/capture/refund/payout events (§9.5 table) | §9.5 |  | TODO |  | Save real event samples to `backend/tests/fixtures/webhooks/` |
| T-22 | Pledge Gate + pledge service: `pledges/order`, `pledges/authorize`, webhook effects, progress, goal-reached trigger | §8.2, §9.2 |  | TODO |  | |
| T-23 | UI: public campaign page (progress "held, not charged", countdown, PayPal button `intent=authorize`, pledge board AG Grid) | §11 #8 |  | TODO |  | A-11 |
| T-24 | Campaign setup API + launch (needs signed contract); deadline rule (`≤ opens_at + 72h − 2h`) | §8.2, §6.1 |  | TODO |  | |
| T-25 | Campaign outcome engine + clock job (every 60 s): goal reached / deadline → enqueue plan builds; `demo/campaigns/{id}/expire`; honor-period warnings; relaunch | §8.2, §6.1 |  | TODO |  | `decide_campaign_outcome` is a pure function with tests |
| T-27 | UI: campaign setup + lead panel (close and capture, cancel, relaunch, simulate deadline) | §11 #7, #8 |  | TODO |  | |

### Track A2: Contract, build & verify
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-30 | Conditional contract: offer, accept (BRD hash, PayPal email lock), `effective_at` on capture | §6.2, §10 |  | TODO |  | UI is screen #6 |
| T-31 | Submissions + `ImageStore` (Cloudinary signed upload, `POST /images`, signed URLs; `LocalImageStore` for dev) + evidence API | §7.3, §10, §12 |  | TODO |  | Verifier fetches image bytes server-side for Gemini |
| T-32 | AutoChecks: SSRF-safe fetcher, URL/page/repo/commit/file/viewport checks + SSRF tests | §7.3 |  | TODO |  | |
| T-33 | Verifier questions: prompt, `VerifyQuestion`, skip ACs settled by auto checks | §7.3 |  | TODO |  | |
| T-34 | Verifier judge (vision) + snippet-in-repo check + deterministic aggregation + follow-up round + attempts | §7.3 |  | TODO |  | One judge call per submission |
| T-35 | UI: freelancer portal (contract, submit, evidence uploaders) | §11 #6, #9 |  | TODO |  | |
| T-36 | UI: verification report with AG Grid matrix | §11 #10 |  | TODO |  | |

### Track B2: Money core, Guardian, payouts
| ID | Task | Spec | Owner | State | Branch | Notes |
|---|---|---|---|---|---|---|
| T-40 | Settlement engine (pure): `split_pro_rata`, `plan_captures`, `plan_refunds`, `plan_freelancer_payout`, `plan_hash` + tests (incl. property tests) | §8.3 | Claude | IN_PROGRESS | t-40-settlement-state-ledger | Do this early; everything depends on it |
| T-26 | `PlanBuilder` (pure, reads DB): `CAPTURE_PLEDGES`, `RELEASE_HOLDS`, `FREELANCER_PAYOUT`, `REFUND_CAPTURED` specs + steps + idempotency keys + tests | §7.5.1, §8.3 |  | TODO |  | Depends on T-40 |
| T-45 | `MoneyExecutor` + plan lifecycle + approvals API (`plans`, `review`, `approve`) + executor tests (refuses unapproved/mismatched/foreign steps) | §8.4, §8.5, §10 |  | TODO |  | Only module allowed to call PayPal writes |
| T-41 | Guardian rules G-01…G-13 + soft flags S-01…S-03 (pure; SDK mocked) + one pass/fail test per rule + tamper mutations | §7.5.2–7.5.3, §7.5.6 |  | TODO |  | G-06/G-08 use SDK reads |
| T-42 | Guardian LLM review (escalate-only) + decision logic + release policies (auto vs human) | §7.5.4–7.5.5 |  | TODO |  | |
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
