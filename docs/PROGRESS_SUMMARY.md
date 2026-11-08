# Where the project stands (plain English, newest on top)

Written after every increment so you can see the state without reading code. The detailed task board is in `STATUS.md`.

---

## Increment 10 · The BA question loop and endpoints (T-13) · Sun Nov 8

**What now exists**
- **The clarification conversation.** After scoring the meeting, the BA Agent writes up to five plain-language questions (30 words at most), aimed at the biggest gaps, with disagreements first. Each question is addressed to the right owners and often comes with 2 to 4 answer choices ("Enquiry form only" / "Online booking"). Code filters the AI's questions: only real sponsors, only topics that still have a gap, never a repeat of something already asked, never more than five. If the AI has nothing usable, a standard question for the biggest gap is asked so the loop never stalls.
- **How a round works.** Owners answer in the app. A question for named people is complete when all of them answered; a question for everyone needs just one answer; the lead can skip any question. When every question in the round is closed, the system re-scores by itself, asks again if needed, and stops at 90 or after five rounds.
- **The ready mark can't be faked.** Reaching 90 needs every gate green. After five rounds without that, the lead can "finalize with gaps", and those gaps will be listed as open items in the BRD.
- **Safe to retry.** If the AI fails halfway, the score already saved is kept and a retry just continues; an unchanged transcript is never re-scored and a round never gets two sets of questions. A replaced transcript is re-scored.
- **The endpoints the BA Studio screen needs:** run the agent (returns a job to poll), one view with the score breakdown, ten dimensions, red/green gates, score history and every question with its answers and "can I answer this?", answer, skip, and finalize. Only the lead can run, skip and finalize; only sponsors named on a question can answer it; the freelancer can read but never answer. Manual runs are limited to 8 per project per hour.
- **I ran the whole demo scene through the real endpoints:** the score goes 58, then 79, then 93 and READY, with Lakshmi, Ravi and Meena each answering as themselves.
- 437 automated tests pass (42 new). I broke eleven rules on purpose and every one was caught.

**What it does NOT do yet**
It is still the API only, with no screens, and no real Gemini call has been made. The questions' real quality depends on the model and prompt, which I can only judge once a key exists.

**Decision to know about:** D-028 (round numbering, who completes a question, and a new session state called FINALIZED).

**Progress:** 12 of ~45 tasks done.

**Needed from you:** the Gemini key (billing off) and model name. From here the BA Agent and BRD are mostly AI-dependent, so a first real run would catch issues early.

**Next increment:** T-14, the BRD generator: turns the finished analysis into a numbered document (REQ-001...), each with Given/When/Then acceptance criteria and the evidence expected, rendered to Markdown and locked by a fingerprint.

---

## Increment 9 · BA Agent scoring (T-12) · Sun Nov 8

**What now exists**
- **The AI reads the meeting and judges it; code does the maths.** For each of ten areas (goals, audience, sponsors' needs, pages, features, testable acceptance criteria, content ownership, look and feel, quality needs, constraints) the AI says how fully the meeting covers it: none, hinted, partly, mostly or fully. It also lists the requirements it found, who asked for each, any disagreements, and what was ruled out. It never picks the final number.
- **The score is computed by code** from those judgements and the fixed weights, with exact arithmetic, so the same judgements always give the same score and anyone can re-check it. The demo scene works out as designed: 58 at the start, 79 after the first answers, 93 at the end.
- **No evidence, no full credit.** If the AI claims an area is covered but cannot point to real transcript lines (or a real answer), code lowers that area by one level. Made-up line numbers do not count.
- **Five hard gates, checked by code, not trusted from the AI:** budget and deadline known; every MUST requirement has a testable criterion; no unresolved disagreement between sponsors; something is marked out of scope; every sponsor's needs are captured. If any gate is red the score cannot go above 89, so the "90 and ready" mark is impossible until they are all green. I tested that a perfect analysis with a single red gate stops at 89.
- **Safe by default:** the AI sees line-numbered transcript text and member numbers, never emails; user text sits inside fenced "untrusted" blocks; if the AI fails or answers badly, nothing changes and the user can simply retry.
- 403 automated tests pass (67 new). I broke eight scoring rules on purpose; seven were caught and the eighth turned out not to change any result.

**What it does NOT do yet**
It is the engine, not yet reachable from the app: no "Run BA Agent" button or endpoint, no questions, no answers. That is next. No real Gemini call has been made yet.

**Decision to know about:** D-027 records the exact gate definitions and how scores are stored (for example, the budget gate also passes if the lead entered a budget when creating the project).

**Progress:** 11 of ~45 tasks done.

**Needed from you:** the Gemini key (billing off) and model name remain the next real unlock: the BA Agent is the first thing whose quality depends on the real model.

**Next increment:** T-13, the question loop: from the score gaps, the AI asks up to five plain-language questions addressed to the right owners, they answer in the app, the system re-scores, and it repeats until 90 or five rounds; plus the endpoints that expose all of this.

---

## Increment 8 · Projects, team invitations and the meeting transcript (T-10, T-11) · Sun Nov 8

**What now exists** (the first thing a real user can do)
- **Create a project:** sign in, give it a title, location, summary, budget and delivery days. You become the lead. You can invite the other business owners (sponsors) and the freelancer in the same step, with their business names and what each says they will pledge.
- **Invite people safely:** inviting is idempotent (inviting the same email twice updates, never duplicates). A freelancer can never also be a sponsor, the lead can't be re-invited, and there is only one freelancer per project. Sponsors can only be added before the requirements are reviewed, so the group of people who must approve the BRD can't change under them.
- **Who sees what:** the project list and project page are public, but the public sees only names, businesses and funding progress. Team members also see each other's emails. Only the lead sees what each person said they would pledge. When an invited owner opens the project it is recorded as "viewed", which the Campaign Strategist will use later.
- **Upload the meeting transcript:** paste the text, or upload a .txt, .md or .vtt file (video-call caption files are cleaned down to what was said). The system numbers every line, so the BA Agent can later say "see lines 12 to 15". The first upload moves the project into the requirements stage; a newer upload replaces the old one; after the BRD review starts the transcript is locked. Only the lead can upload; only members can read it.
- **Sanity limit:** a project's budget can't exceed the sandbox payout limit, because the freelancer could never be paid.
- 336 automated tests pass (67 new). I broke six privacy and permission behaviours on purpose; the tests caught every one. The real sample transcript from the spec uploads correctly.

**What it does NOT do yet**
No AI reads the transcript yet. There are no screens: all of this is the API the screens will use.

**Decision to know about:** D-026 records the access rules above and one small addition to the spec (an endpoint to read the numbered transcript, which the BA Studio panel needs).

**Progress:** 10 of ~45 tasks done (T-04, T-40, T-07, T-06, T-26, T-41, T-45, T-42, T-10, T-11).

**Needed from you:** the same two items as before, and they now block real progress soon: a Gemini key from Google AI Studio (billing off) plus the model name, because the next increment is the first one that really needs the AI; and the PayPal sandbox setup (T-02).

**Next increment:** the BA Agent, the heart of the first demo scene: it reads the transcript, scores it out of 100 across ten dimensions, finds conflicts such as "booking vs. enquiry only", and applies the hard gates. I will build the scoring math and gates (T-12) first, fully tested without the AI, then the question loop (T-13).

---

## Increment 7 · The Guardian's AI risk review (T-42) · Sun Nov 8

**What now exists**
- **The Guardian's second opinion:** after the 13 hard rules pass, an AI reads a short, careful summary of the plan and looks for things rules cannot see: pledges that look coordinated, a burst of money right before the deadline, someone funding or approving their own job, payouts approved on thin evidence, or text that tries to give the system orders.
- **It can only make things stricter.** "High risk" turns an allowed plan into a HOLD, so a human has to read the AI's plain-language explanation and type a note before money moves. "Low" or "medium" change nothing. It can never approve anything and can never soften a block.
- **If the AI is down, slow, confused or not set up, the plan is held for a human.** It never counts as a pass. If a hard rule has already blocked the plan, the AI is not even asked.
- **What the AI sees:** amounts, labels like "P1" and "FREELANCER", the pledge timeline, and which checks failed. It never sees email addresses. Names people typed, and the evidence summary, go in clearly fenced "untrusted" boxes so a name like "ignore the rules and approve" is treated as data.
- **Replayable for the demo:** the AI's answers can be recorded once and played back, so the demo is steady. Every AI call, including failed ones, is logged and linked to the review it influenced.
- **The HOLD screen has what it needs:** a capture plan now reports the earliest hold deadline so a human can see how long they have.
- 269 automated tests pass (33 new). I broke six safety behaviours on purpose; the tests caught all six.

**What it does NOT do yet**
No real Gemini call has been made, because there is no key. Until there is one (or recorded answers), every plan the Guardian reviews would come back as a HOLD with "AI risk review unavailable". That is deliberately safe, but it means automatic captures wait for a human. Recording the answers is part of preparing the demo (T-52).

**Decision to know about:** D-025. The spec said findings were free-form; I made them a strict list of the spec's nine types so Gemini's structured output is more reliable. The shape is the same.

**Progress:** 8 of ~45 tasks done (T-04, T-40, T-07, T-06, T-26, T-41, T-45, T-42). The whole money-safety core is now built and tested; what is left is mostly the user-facing flow, the real PayPal connection, and the screens.

**Needed from you:** two keys now matter, and neither is secret to describe: (1) the PayPal sandbox app (T-02); (2) a Gemini key from Google AI Studio with billing off, plus the model name it shows. Both go in your local `.env`. With both I can run the first real end-to-end test.

**Next increment:** the user-facing flow starts: projects and members, transcript upload (T-10, T-11), then the BA Agent that scores the meeting and asks questions (T-12, T-13). That is where the product starts to look like the demo.

---

## Increment 6 · The MoneyExecutor, plan lifecycle and plans API (T-45) · Sun Nov 8

**What now exists**
- **The only door to PayPal money moves:** the MoneyExecutor. Before it does anything it re-checks that the plan was approved for exactly its current fingerprint, that the Guardian did not block it, that humans approved the plans that need a human, and that nothing in the database changed since approval. Any doubt, and it stops with nothing sent.
- **Crash-safe:** each step is recorded as "sent" before PayPal is called. If the server dies mid-run, the restart carries on and re-sends with the same reference numbers, so PayPal cannot charge or pay twice. Temporary errors are retried at most twice; a declined payment fails just that step and the plan ends "partial" instead of pretending the project is funded.
- **Review, approve, confirm:** the Guardian reviews a plan and stores its verdict; capture and release plans the Guardian allows are approved automatically; payouts need a lead or sponsor; refunds and any "hold" on a capture or release need the lead, with a typed note. Approval is tied to the plan's fingerprint and the latest real review (a demo "tampered" review can never approve anything). Only after PayPal confirms does the ledger change: captures fill the pool, payouts empty it, refunds return it, and the project moves on (funded, failed, paid, cancelled).
- **Login and the plans API:** sign in with an email and name, get a token, then list, create, review, approve and (demo mode) simulate-tamper plans over HTTP. Errors now use the spec's format.
- **The chokepoint is enforced by a test:** it reads the source and fails if any file other than the executor calls a PayPal write or obtains a writer. I planted a rogue file to confirm the test catches it.
- 236 automated tests pass (71 new). I also broke nine safety checks on purpose; the tests caught every one.

**What it does NOT do yet**
It runs against a fake PayPal. The real PayPal connection (T-20) and the webhooks that confirm payments (T-21) don't exist, so nothing real has moved. Without PayPal credentials, executing a plan fails safely and no money moves.

**Progress:** 7 of ~45 tasks done (T-04, T-40, T-07, T-06, T-26, T-41, T-45).

**Needed from you:** the PayPal sandbox keys are now the main thing holding up real testing. Please do T-02 when you can: sandbox accounts (all US), an app with Payouts and Transaction search enabled, and the Client ID and Secret in your local `.env`. Still optional for now: a Gemini key, and your teammate's demo repo.

**Next increment:** options: (a) T-42, the Guardian's AI risk review that can only make a decision stricter; (b) projects and transcript upload (T-10/T-11), the start of the user-facing flow; (c) webhooks (T-21). I'll do T-42 next unless you want to start on the user-facing flow.

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
