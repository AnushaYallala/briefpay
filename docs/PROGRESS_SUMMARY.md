# Where the project stands (plain English, newest on top)

Written after every increment so you can see the state without reading code. The detailed task board is in `STATUS.md`.

---

## Increment 5 · Guardian rules (T-41) · Sun Nov 8

**What now exists**
- **The Guardian's checklist, in code:** 13 hard rules that look at a proposed money plan and say pass or fail, plus 3 softer warning flags. Examples: is this exactly the plan the system would build right now? Does every payment belong to this project? Does PayPal's own record agree with ours? Does the payout go to the email locked in the contract, for the contract amount, after a verified report? Do refunds go back to the original payers only?
- **Decision logic:** any failed hard rule means **BLOCK**. Otherwise any warning flag (the freelancer funding their own job, one person providing 60% or more of the goal, a late surge of pledges, or PayPal being unreachable) means **HOLD** for a human. Otherwise **ALLOW**. PayPal being down never counts as a failure; it just forces a human look.
- **"Simulate tampered plan":** the five demo attacks (swap the recipient, inflate the amount, add an extra recipient, capture twice, capture inside a release plan) are built and every one is caught. The attacks are re-fingerprinted like a careful attacker would, and the Guardian still blocks them on substance. A simulation writes nothing and never touches PayPal.
- **Checked the checker:** I deliberately broke two rules to confirm the tests notice. They did.
- 165 automated tests pass (63 new).

**What it does NOT do yet**
Nothing executes. The Guardian's AI risk review (it can only make things stricter) is next, as is the executor that actually moves money. PayPal lookups use a stand-in until the real PayPal connection exists (T-20).

**Decision to know about:** the spec left a few checks open to interpretation (what counts as a "live" hold, who may request a refund, and so on). I fixed them conservatively and logged them as D-023.

**Progress:** 6 of ~45 tasks done (T-04, T-40, T-07, T-06, T-26, T-41).

**Needed from you:** nothing new. Pending as before: sandbox keys (T-20), a Gemini key (not blocking), your teammate's demo repo (T-60).

**Next increment:** T-45, the MoneyExecutor: the only code allowed to call PayPal writes. It refuses anything unapproved or changed, runs the steps in order with safe retries, and is tested against a fake PayPal. After that, T-42 (the AI risk review and release policies).

---

## Increment 4 · Plan builder (T-26) · Sun Nov 8

**What now exists**
- **The plan builder:** given the current state of a campaign or project, it writes out the exact list of PayPal actions needed, as a fixed "money plan" with a fingerprint. Plain code, no AI. It covers all four plans:
  - **Capture:** the goal is reached, so charge each pledger their share. The shares add up to exactly the goal, and no one is charged more than they pledged.
  - **Release:** the deadline was missed or the lead cancelled, so cancel every hold and charge nobody. It refuses to run if anything was already charged.
  - **Freelancer payout:** only after the latest submission is verified, only to the PayPal email locked into the contract, only the contract amount, and only if the pool really holds that money.
  - **Refund:** give captured money back to the original payments, and only while the pool still holds it.
- **Safety by construction:** a hold that has passed its 3-day guarantee is not counted. If anything changes after a plan is previewed (a pledger voids, a hold lapses, the recipient email is edited), rebuilding gives a different fingerprint, which is how the Guardian and the executor will notice.
- **Retries:** a failed plan can be retried as a new plan with fresh keys instead of clashing with the old one. I found this gap while reviewing my own tests; it is logged as D-022.
- 102 automated tests pass (39 new).

**What it does NOT do yet**
Nothing is reviewed or executed. No Guardian rules, no approvals, no PayPal calls. Plans can be built and stored as "proposed", and that is all.

**Progress:** 5 of ~45 tasks done (T-04, T-40, T-07, T-06, T-26).

**Needed from you:** nothing new. Still pending as before: a Gemini key (not blocking), sandbox keys (needed at T-20), and your teammate's demo repo (T-60).

**Next increment:** T-41, the Guardian's 13 deterministic rules plus soft flags and the "simulate tampered plan" mutations. It builds directly on this and needs no keys. After that, the MoneyExecutor (T-45).

---

## Increment 3 · AI adapter, replay mode, job runner (T-06) · Sun Nov 8

**What now exists**
- **One door to the AI:** every agent will talk to Gemini through a single adapter. It checks the answer matches the expected shape, retries once if not, and if it still fails it stops safely instead of guessing.
- **Audit trail:** every AI call is recorded (which agent, model, how long, tokens, success or failure). This will feed the "AI audit trail" screen. The record is kept even if the surrounding operation is cancelled.
- **Replay mode:** AI answers can be recorded once and played back later, so the demo video doesn't depend on Gemini being fast or within its free limits. If a recording is missing it calls Gemini once and saves it. Changing a prompt makes old recordings stop matching on purpose.
- **Prompt-injection guard:** a helper that wraps anything users type (transcripts, evidence) so the AI treats it as data, not instructions.
- **Background jobs:** slow work (AI calls, webhooks) runs in the background. The app returns a job id, and `GET /api/jobs/{id}` says queued, running, done or failed. Failed jobs retry up to 3 times, and jobs interrupted by a restart start again. I ran the real app and watched a job complete.
- 63 automated tests pass (24 new).

**What it does NOT do yet**
No real Gemini call has been made, because there is no key or model name configured. The Gemini code is tested against a fake client only. The first real call is the moment we learn whether Gemini accepts our output shapes (assumption A-4 in the spec).

**Progress:** 4 of ~45 tasks done (T-04, T-40, T-07, T-06).

**Needed from you (when convenient, not blocking):**
- **Gemini key:** create one at Google AI Studio **without enabling billing**, and tell me which Flash model name it shows. Put it in your local `.env` as `GEMINI_API_KEY` and `AI_MODEL`. I'll run one real test call then.
- Sandbox keys (T-20) and the teammate's demo repo (T-60) are still pending as before.

**Next increment:** T-26 PlanBuilder (turns pledges and a goal into the exact list of capture, void and payout steps, using the money math), or login plus projects so the app has its first real endpoints. I'll start with PlanBuilder unless you prefer the latter.

---

## Increment 2 · Money math, state machines, ledger (T-40, T-07) · Sun Nov 8

**What now exists**
- **Money math:** given the pledges that are held and the goal, the code works out exactly how much to capture from each so the total equals the goal to the cent (for example $400 goal, holds of $150/$150/$100/$20 become captures that sum to exactly $400, none above its hold). It never uses decimals. Tested with the spec's worked examples plus thousands of random cases.
- **Tamper-proof fingerprint:** every money plan gets a hash. Change the recipient or the amount by one cent and the hash changes, which is what the Guardian and approvals will rely on.
- **Project and campaign state machines:** the legal journey (draft -> requirements -> BRD -> contract -> campaign -> pledging -> in progress -> verifying -> paid, plus the failure and relaunch loops). Every illegal jump is rejected, tested pair by pair.
- **Ledger:** append-only (rows can't be edited or deleted), numbered with no gaps, one pot of captured money (POOL) that can never go below zero. A pledge hold is recorded but counts as $0 because it isn't money yet.
- 39 automated tests pass.

**What it does NOT do yet**
Still no screens, login, AI or PayPal calls. These are the rules and safety rails the later features plug into.

**Decision to know about:** the spec had a circular definition of the plan fingerprint and its step keys; I resolved it (D-021) and logged it.

**Progress:** 3 of ~45 tasks done (T-04, T-40, T-07).

**Needed from you:** still nothing new. Sandbox keys are needed at T-20; the teammate's demo repo at T-60.

**Next increment:** T-06 (AI adapter with recorded-replay mode, AI call logging, background job runner), then T-26 (builds the capture/void/payout plans using the money math).

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
