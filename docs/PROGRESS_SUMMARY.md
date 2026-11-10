# Where the project stands (plain English, newest on top)

Written after every increment so you can see the state without reading code. The detailed task board is in `STATUS.md`.

---

## Increment 37 · The money plans screen (T-49) · Tue Nov 10

**What now exists**
- **Money plans page.** From the project's money box, people on the project open "See all the money plans". Every move of money is a *plan* (collect the pledges, release the holds, pay the builder, refund the pledgers), each with a plain-words state and the Payment Guardian's decision (ALLOW, HOLD, BLOCK, or "Not reviewed").
- **One plan in full.** Its steps in a table (what, who, how much, state, PayPal reference, any problem), then the Guardian's verdict: every safety rule with a tick or cross and a one-line reason, the rules that PayPal itself proved are tagged "verified with PayPal (APIMatic SDK)", cautions that need a human, and the AI's risk opinion (which can only make the Guardian more careful, never less).
- **Approval that cannot be cheated.** The button says why it is off ("Only the lead can approve this plan", "Write why it is safe to go ahead", "The Guardian blocked this plan"). A HOLD needs a written reason and shows when the earliest hold runs out. Approval is tied to the plan's exact fingerprint.
- **"Try to cheat" (demo).** The lead can make a tampered copy of a plan (swap the recipient, inflate the amount, add a recipient, collect a pledge twice, sneak a collection into a release) and watch the Guardian refuse it, with the failed rules in red. PayPal is never contacted and the real verdict is untouched.
- **Build and watch.** Buttons build a payout plan or a refund plan. A running plan updates itself every 5 seconds and has an "Ask PayPal now" button (this was a gap I had noted earlier, now closed).
- 309 front-end tests and 1,564 back-end tests pass. About 150 deliberate breakages: 33 slipped through the first time (mostly colours, hover texts and double-click protection that no test looked at; some code was simply unnecessary and was removed); all are now caught.

**What it does NOT do yet**
It cannot run in a real browser here (the tests simulate one), and the "not yet built" plan kind for renewing holds has no screen. The stepper steps are still not links.

**Progress:** 35 of ~45 tasks done or in review. Increment 37 of the 45 you asked for.

**Needed from you:** BLK-01/02/03, PayPal sandbox keys, Gemini key.

**Next increment:** BA Studio (T-16): the chat with the business analyst and the readiness score.

---

## Increment 36 · The AI audit trail as a table (T-51) · Tue Nov 10

**What now exists**
- **The AI audit trail page.** People on a project can open "Open the AI audit trail" from the project page. It lists every time an AI helper was asked something on that project, newest first: which helper ("Brief writer", "Verifier: judge", "Strategist"...), which model, which version of its instructions, how long it took, how many tokens it used, and how it ended (answered, replayed from a recording, malformed answer, or failed). Failed and malformed calls have a red row so they cannot hide.
- **Proof, not trust.** Each row has a short fingerprint of what the helper was given (the whole thing on hover), and "Details" shows exactly what came back, as plain text, so the AI can never run anything on the page. This is the screen that shows the AI only suggests and fixed rules decide.
- **Find things fast.** Chips pick one helper; a search box finds calls by plain words ("Failed", "Brief writer") or by the raw codes; columns sort and filter; a summary line says how many calls, how many failed, the average time and total tokens for what is shown.
- **Stays fresh** every 20 seconds while the tab is open, keeps old rows if an update fails, and says so.
- **Private.** Only members see it: someone not signed in is asked to sign in and nothing is requested; someone on another project sees the server's reason.
- **Small improvement to the ledger:** its search now also finds rows by the plain-words type ("Pledge collected"), not just the code.
- 234 front-end tests and 1,562 back-end tests pass. About 65 deliberate breakages: 25 slipped through the first time (most were missing tests: sort order, colours, hover texts, the refresh timer being stopped, the table staying on screen during a refresh, switching person); all are now caught.

**What it does NOT do yet**
It shows the newest 500 calls only (the server's limit); there is no way to download it; it is not yet tried in a real browser (the tests simulate one).

**Progress:** 34 of ~45 tasks done or in review. Increment 36 of the 45 you asked for.

**Needed from you:** BLK-01/02/03, PayPal sandbox keys, Gemini key.

**Next increment:** the money plans viewer (T-49): what the system plans to do with the money, the safety checks on each step, and a safe "tamper" demo.

---

## Increment 35 · The public ledger as a table (T-50) · Mon Nov 9

**What now exists**
- **The ledger page.** From a project's page, "Open the public ledger" shows every money and AI event in order, as a proper table (AG Grid, the grid the contest sponsor asks to see used): number, time, whether it is real money in the pool or just a memo, a plain-words type ("Pledge held", "Pledge collected", "Hold released", "Paid to the builder", "Safety check"...), who it concerns, the amount (green in, red out, a dash for notes: a hold is not money), the pool balance after it, a status, PayPal's reference (short, the whole thing on hover), and who did it.
- **Find things fast.** Clickable chips filter by type (only types that exist are offered), a search box looks across the table, columns sort and filter, and a bottom row always adds up what is shown ("Total of 2 rows $250.00") next to the real pool balance. Row "Details" opens the full record behind any line, shown as plain text so nothing in it can run.
- **Download it safely.** "Export CSV" saves exactly the rows you see. Any cell that could be mistaken for a spreadsheet formula (starting with `=`, `+`, `-` or `@`) is defused, so opening the file in Excel cannot run something nasty from a name or note.
- **"Check with PayPal".** For people on the project, one button asks PayPal about every charge, refund and payout and puts a tick (agrees), hourglass (not final yet) or cross (disagrees, or no such payment) on each row, with a one-line summary. The public never sees the button.
- **Stays fresh.** The table updates itself every 15 seconds while the tab is open (not when hidden), and keeps the old rows on screen if an update fails, with a note.
- **A real bug found on the way:** the server sends some times without a time zone, and the browser read them as local time, so 12:00 showed as 06:30 for me. They are now read as UTC and tested under four different time zones.
- 203 front-end tests and 1,559 back-end tests pass. About 55 deliberate breakages: seven slipped through the first time (two led to small improvements: the PayPal reference now has a proper hover text and a failed update now shows a note; five were weak tests); all are now caught.

**What it does NOT do yet**
The page's code is large (349 kB) because every grid feature is loaded; it can be trimmed. Only the 30 newest PayPal-backed rows are checked per click.

**Progress:** 33 of ~45 tasks done or in review. Increment 35 of the 45 you asked for.

**Needed from you:** BLK-01/02/03, PayPal sandbox keys, Gemini key.

**Next increment:** the AI audit trail table (T-51): every AI call with its model, version, speed and result.

---

## Increment 34 · The project page (stepper and money box) · Mon Nov 9

**What now exists**
- **Click a project card and you land on its page.** The page shows the project's name and place, where it stands in plain words, and a progress strip with the eight stages of the journey (Requirements, Brief, Contract, Campaign, Build, Verify, Payout, Ledger): finished stages ticked, the current one highlighted. Underneath, one sentence says what happens next ("Pledges are open. A pledge is only a hold: nobody is charged unless the goal is reached before the deadline.", "The goal was missed. Every hold was released and nobody was charged.").
- **What a visitor sees:** the campaign progress bar with the "only a hold" promise, the terms (budget, delivery time, whether a person approves the payment), and the people with their businesses and roles, plus a prompt to sign in. No contact details or PayPal addresses are ever shown, even to members.
- **The Money box, for people on the project:** what is really in the project pool, what is only pledged (held, not charged) with its latest deadline, the contract price, any money plans in progress in plain words, a note if a payment is waiting for the builder to claim it, and a red warning if PayPal reported something different from our records. With nothing happening it says so honestly. A signed-in outsider is told the box is for members.
- **Careful about who is asking.** The page waits until it knows who is signed in before asking for the project, and asks again when the demo person is switched, so switching from "visitor" to "Ravi" instantly adds the Money box.
- **Safe links:** a project link that is missing, not a whole number, negative or absurdly long shows "No project selected" and asks the server nothing.
- **Matches the back end by test:** more contract tests make sure every project state has a stage and an explanation, and that the page's data shapes equal what the API really sends (I even caught that a made-up field in the page's types would go unnoticed, and fixed the test).
- 124 front-end tests and 1,554 back-end tests pass; the static site builds with the new page. I broke about 40 things on this screen on purpose; eight weak tests were found and fixed, and the rest were caught or provably harmless.

**What it does NOT do yet**
The stages in the strip are not clickable yet (the other screens do not exist), the Money box only reads (it does not yet ask PayPal for a fresh check), and there is no ledger, campaign, requirements or verification screen.

**Progress:** 32 of ~45 tasks done or in review, with the web app now past its first screens. Increment 34 of the 40 you asked for.

**Needed from you:** BLK-01/02/03, PayPal sandbox keys, Gemini key.

**Next increment:** the public ledger as a table (AG Grid): every money and AI event, with running balance, filters, totals and CSV export.

---

## Increment 33 · The web app begins (T-05) · Mon Nov 9

**What now exists**
- **A real website, for the first time.** `frontend/` is a working web app. Open it and you see the headline "Pledge together. Pay only if we get there.", then a card for each project: its name and place, a plain-words state ("Collecting pledges", "Goal missed: nobody was charged", "Verified: ready to pay"), the budget, and for projects with a campaign a progress bar ("Pledged $150.00 of $400.00 by 1 person") with the promise that a pledge is only a hold.
- **Sign-in and the demo cast.** A sign-in page (email and name, no password: demo only), and a "Demo person" menu that switches between Lakshmi, Ravi, Meena and Arjun with one click, so the video can change roles quickly.
- **It never looks broken.** Every screen has a loading state, an error with a "Try again" button, and an empty state. If the free server is asleep and takes more than four seconds, the page says plainly: "Waking up the server. The free host sleeps when nobody is using it and needs about a minute." If the browser blocks its storage, the app still works for the session. If the server rejects the login token, the person is signed out; a sleeping server does not sign anyone out.
- **Money is always shown the same safe way** (whole cents turned into "$1,234.50"), and a number with a fraction of a cent is refused instead of displayed.
- **Kept honest against the back end.** Tests read the web app's source and fail if it drifts from the API: if a project state has no words, if the demo people differ from the seed data, if the data shapes differ from what the API really sends, or if an environment variable is undocumented. I planted 13 such drifts on purpose and every one is caught.
- **Real end-to-end check:** I started the actual API on a freshly built, seeded database and confirmed that a browser page at localhost:3000 is allowed to call it (including the permission check browsers do before sending a login token), the demo projects come back, and login works.
- **Ready to ship:** the deployment file now also builds the web app as a static site, the automatic checks on GitHub now test both halves (and use the same Python version as everything else), and the README and guides explain how to run it.
- 72 front-end tests and 1,550 back-end tests pass. I broke about 50 things in the front end on purpose; five weak tests were found and fixed, and everything is now caught.

**What it does NOT do yet**
Cards are not clickable yet: there is no project page, ledger, campaign or any other screen. Those come next, one per increment.

**Progress:** 32 of ~45 tasks done or in review. Increment 33 of the 40 you asked for.

**Needed from you:** BLK-01/02/03, PayPal sandbox keys, Gemini key.

**Next increment:** the project page (stepper and "Money" box), the hub the other screens hang from.

---

## Increment 32 · The Strategist finds its words, and every number is checked (T-47) · Mon Nov 9

**What now exists**
- **A readable forecast.** Besides the numbers, the lead now gets a headline ("$250 still needed, 40 hours left"), a short plain explanation that clearly says the chance is a rough estimate, a few risk points, and a ready-to-copy message for each person who has not pledged yet (for example Ravi, who said $100). Messages are friendly, mention that a pledge is only a hold, and end with the campaign link.
- **The AI is never trusted with a number.** The system works out every figure itself (amount still needed, hours left, how many pledges, the chance). The AI only phrases them. Then plain code reads every number in whatever the AI wrote and compares it to the real figures: one invented amount ("only $75 to go!", "you're at 90%") and that text is thrown away and replaced by a standard sentence built from the real figures, with a warning recorded. Even a sentence that mixes a correct number with a wrong one is rejected. Links the AI writes are removed; the real link is added by code.
- **It still works with no AI.** If the AI is off, out of quota or answers badly, the lead gets complete standard wording and standard messages for everyone, marked as such.
- **No spamming.** Nobody gets a new draft more than once a day: running the Strategist again within 24 hours shows the same draft for the same person.
- **Safe with strangers' text.** Names and the project title go to the AI only inside "this is data" wrappers; a planted fake closing tag is defused. Nothing is ever sent for the lead: they copy the message themselves.
- **A safety net for tests:** no test can accidentally start a real AI connection that writes into your own database (this was caught when the first test run tried exactly that).
- All automated tests pass (51 new). I broke about 40 things on purpose; six slipped through the first time, four were weak tests and two were needless code, and now everything is caught or simplified.

**What it does NOT do yet**
It has never talked to the real Gemini model (needs your key), so the wording quality is unknown. Numbers spelled out in words ("one hundred") are not caught. It cannot detect a tactless tone; the instructions forbid pressure, but code cannot check it.

**Progress:** 31 of ~45 tasks done or in review. Increment 32 of the 40 you asked for.

**Needed from you:** BLK-01/02/03, PayPal sandbox keys, Gemini key.

**Next increment:** the front end begins: a Next.js skeleton (T-05) so that the screens have a home.

---

## Increment 31 · What happens when the work fails for good · Mon Nov 9

**What now exists**
- **The "FAILED" path is finished.** After the freelancer's third attempt fails, the project used to just wait. Now the lead has three real choices, and every choice is written into the public ledger:
  1. **Give more attempts**: one to three at a time, six extra at most. The system then counts attempts correctly, so with two extra attempts the fourth try can still be sent back for changes, and the fifth is final again.
  2. **Cancel and refund**: builds the refund plan for all pledgers (reason "verification failed"). It then goes through the same safety review and human approval as any refund. Pressing it twice gives the same plan.
  3. **Override**: pay the freelancer anyway, but **only if every sponsor (the lead included) agrees**. Each sponsor votes; a sponsor can change their mind; one "no" at the end stops it. When everyone has agreed, the system saves a new report that says plainly it is an override, keeps the original failed findings, lists who approved and their notes, and moves the project to "payout ready".
- **An overridden payout gets extra caution.** The payment safety checker raises a new warning ("verification overridden") that forces a human hold: the approver must type an acknowledgement before the money can be released.
- **Nothing is hidden.** The real failing results stay in the report, and every vote shows in the public ledger with the person's name.
- All 1,484 automated tests pass (32 new). I broke about 40 things on purpose; the first pass found three weak spots which I covered, and the rest are caught or provably harmless.

**What it does NOT do yet**
There are no screens for these choices yet (UI work). A "no" vote that arrives after everyone else has said yes simply stops the override; sponsors cannot attach evidence to a vote.

**Progress:** 30 of ~45 tasks done or in review, plus this extra step. Increment 31 of the 40 you asked for.

**Needed from you:** BLK-01/02/03, PayPal sandbox keys, Gemini key.

**Next increment:** the Strategist's wording (T-47): the AI phrases the forecast and the nudge messages, and code checks that it did not invent any number.

---

## Increment 30 · Does the ledger agree with PayPal? (T-48) · Mon Nov 9

**What now exists**
- **A "check with PayPal" for the ledger.** For each money row (a charge, a refund, the freelancer's payout), the system can now ask PayPal about that exact payment and compare. Each row comes back as one of: **match** (PayPal confirms the same amount), **pending** (not final yet), **mismatch** (PayPal shows another amount, or says it was declined, failed or returned), **not found** (our ledger says it happened but PayPal has no such payment), or **unavailable** (PayPal could not be reached, so nothing is concluded).
- **Safe by design.** It only reads. It never changes the ledger, never raises alarms by itself, and asks PayPal about at most the 30 newest money rows per click. A payout batch is looked up once however many rows belong to it. The normal ledger view still never calls PayPal; the screen will merge the two.
- **Works before PayPal is connected:** every row simply says "unavailable".
- All automated tests pass (41 new). I broke 26 things on purpose; the first pass found three weak spots (the 30-row limit, the one-lookup-per-batch rule, and a refund row with no recorded id), I added tests, and now all are caught.

**What it does NOT do yet**
It uses PayPal's instant lookups rather than the Transaction Search report (which can lag and is unproven), and it has only seen pretend PayPal answers. The column in the grid is UI work.

**Progress:** 30 of ~45 tasks done or in review. Increment 30 of the 40 you asked for.

**Needed from you:** BLK-01/02/03, PayPal sandbox keys, Gemini key.

**Next increment:** what happens after a third failed verification: the lead's choices to extend, cancel and refund, or (with every sponsor's agreement) override.

---

## Increment 29 · Ready to deploy, and refusing to start unsafe (T-61) · Mon Nov 9

**What now exists**
- **A Render deployment file** for the back end (free plan): it applies the database migrations, starts the API, checks its health, makes up a strong login-signing secret by itself, and fixes the safe settings (production mode, **PayPal sandbox only**, Cloudinary for pictures). Every real secret is left blank on purpose: you type them in the Render dashboard.
- **A step-by-step guide** (`docs/DEPLOY.md`) for the parts only a person can do: creating the free database, Cloudinary and Gemini accounts, the PayPal sandbox app and webhook (with the exact list of events to subscribe to), loading the demo data, and warming the servers before the video.
- **The server now refuses to start in production with an unsafe setup**, and says why in the log (never printing a secret): a weak or default login secret, a throwaway SQLite database on a host that forgets files, anything other than PayPal's sandbox, half a set of PayPal keys, or Cloudinary chosen without its URL. Smaller weaknesses (no Gemini key, no webhook id, demo mode left on, localhost addresses) are logged as warnings.
- **The settings lists can't drift apart any more.** Four settings I had added earlier were missing from the example environment file and the spec; they are now there, and a test fails if the code, the example file, the spec or the deploy file ever disagree.
- **A safety moment worth knowing about:** while I was working, the deployment file was changed on disk from "sandbox" to "live" PayPal. I did not make that change. I stopped, told you, and restored "sandbox" at your word. The new start-up check and a test would now both catch this, and the app would refuse to run.
- All automated tests pass (35 new). I broke 22 things on purpose; 21 were caught and the last changes nothing.

**What it does NOT do yet**
Nothing is deployed: that needs your accounts and secrets. The web app's entry in the deployment file will be added once the web app exists.

**Progress:** 29 of ~45 tasks done or in review. Increment 29 of the 40 you asked for.

**Needed from you:** BLK-01/02/03, the accounts and keys listed in `docs/DEPLOY.md`.

**Next increment:** matching ledger entries to PayPal's own records (T-48), which fills the "PayPal match" column.

---

## Increment 28 · The README for judges (T-62) · Mon Nov 9

**What now exists**
- **A README a stranger can follow.** It explains the problem in plain words, how "Pledge-If" works and why a pledge is only a hold that costs nothing unless the goal is met, which steps are done by AI, which by plain code and which by a human, an architecture picture, how to run the project and load the demo data, the demo cast, the tools used (including the PayPal and APIMatic table the contest asks for), what was measured, and what the project is deliberately not (no real money, no production login, and so on).
- **Honest about what is missing.** A banner at the top says the back end is built and tested but the web screens, the hosted site and the video are not there yet, that three pieces are blocked, and that PayPal, Gemini and Cloudinary have only been tried against faithful fakes. Nothing in it claims a live URL or a recorded video.
- **The status page is tidy again.** Two summary rows on the project status page had been left garbled or out of date by earlier edits; they now say where the project really stands and what comes next.

**What it does NOT do yet**
The README still needs, before submission: the live links, the AI evaluation results table (needs your Gemini key), the video link, the short APIMatic screen capture, and a front-end section once the screens exist.

**Progress:** 28 of ~45 tasks done or in review. Increment 28 of the 40 you asked for.

**Needed from you:** the same: BLK-01/02/03, PayPal sandbox keys, Gemini key, optionally Cloudinary.

**Next increment:** deployment files for Render (T-61), so the backend can be started on the free host as soon as you create the account.

---

## Increment 27 · Ready-made demo data (T-52) · Mon Nov 9

**What now exists**
- **One command loads the demo story.** `scripts/seed.py` creates the Velugu Cove cast (Lakshmi, Ravi, Meena and the freelancer Arjun) and two projects, so the video does not need minutes of live setup:
  1. **"Velugu Cove tourism website"**: the first campaign missed its deadline. $300 of $400 was pledged, the Guardian checked the release plan and allowed it, all three holds were released, and **nothing was charged**. The project is waiting for Lakshmi to relaunch.
  2. **"... (build phase)"**: the same story one round on. $400 was pledged and captured, the contract is in force, and the freelancer submitted twice: the first attempt was rejected because the enquiry form was missing on the live site, the second was verified. The project is **ready for payout**, so the demo can build the payout, show the tampered-payout block, and approve it.
- **Built the honest way.** The data is created by the same code the app really runs (BRD approval and hashing, contract signing, campaigns, the Guardian's reviews, the verification rules and report), not typed in by hand, so the ledger, plans and reports are consistent. A test checks that all eight money rules pass on the seeded data, and that the real payout plan built from it is accepted by the Guardian.
- **Cannot touch PayPal.** Nothing is sent: steps are marked as done in the database, and any background job that would have executed them is switched off. Ids look like `SEED-...`.
- **Your real details can be plugged in:** the freelancer's real PayPal sandbox email (so the final payout goes to your test account), the sample site's address, repository and the two commit ids from the teammate's build.
- **Safe:** it only runs in demo mode, and running it twice changes nothing.
- A real bug found on the way: the app's login refuses fake addresses ending in `.test`, so the first version's cast could not have logged in. They now use `example.com`, which is reserved for examples.
- 1,376 automated tests pass (19 new). I broke 22 things on purpose; all are caught.

**What it does NOT do yet**
The seeded projects have no earlier requirements-analysis history (the "58 to 93" scoring shown live in the video comes from a fresh project). Recording the AI answers for replay (the other half of this task) needs your Gemini key.

**Progress:** 28 of ~45 tasks done or in review. Increment 27 of the 40 you asked for.

**Needed from you:** BLK-01/02/03, PayPal sandbox keys (and the freelancer's sandbox email), Gemini key (to record the replay fixtures).

**Next increment:** a README that gets a new reader from zero to the demo (T-62).

---

## Increment 26 · If PayPal's message never arrives (T-43/T-44) · Mon Nov 9

**What now exists**
- **A safety net for missed messages.** The free server goes to sleep, and PayPal's "this payment finished" messages can be missed. Now every 30 seconds while the server is awake, it asks PayPal itself about anything still waiting: captures (charges), voids (released holds), refunds and payout batches. The answers are turned into the very same events a PayPal message would have carried, so there is only one set of rules for what a captured, declined, refunded or paid-out result means. Receiving both a message and a poll is harmless.
- **Careful on purpose.** A step sent less than 20 seconds ago is left to its message first. If PayPal can't be reached, nothing is guessed or failed; it simply tries again later. A payout PayPal marks "unclaimed" is still treated as waiting, never as failed, so nobody can be paid twice. A charge for a different amount than approved is flagged, not booked. A payout batch is looked up once per pass however many items it has.
- **A "check now" for the money screen.** When a member opens the money screen, it can ask for an immediate check (only one at a time per project).
- **Read-only by design.** A test fails if the polling code ever mentions a PayPal write operation or an internet library.
- **Refunds and cancelling** already worked through the plan machinery; they are now also confirmed by polling, so a cancelled project reaches "cancelled" even if PayPal's messages are lost.
- 1,357 automated tests pass (55 new). I broke about 40 things on purpose; every one is caught except two that provably change nothing.

**What it does NOT do yet**
It has only been tested against pretend PayPal answers; the real PayPal field names are still unproven until sandbox keys exist (GAP-45). The screen that shows "checking..." is UI work.

**Progress:** 27 of ~45 tasks done or in review. Increment 26 of the 30 you asked for.

**Needed from you:** the same: BLK-01/02/03, PayPal sandbox keys, Gemini key, optionally Cloudinary.

**Next increment:** demo seed data (T-52): ready-made projects, including one whose first campaign failed with nobody charged and one ready for payout, so the demo needs little live setup.

---

## Increment 25 · The reviewer and the verification report (second half of T-34) · Mon Nov 9

**What now exists**
- **Asking for review.** Once the freelancer has answered every question, they (or the lead) press "ask for judging". It can be asked at most six times per submission, and only once at a time.
- **The AI reviewer sees everything in one go.** One call, all criteria, with the freelancer's notes, code, links and the screenshots themselves, each labelled with its evidence number. Screenshots that are missing, were changed after upload, or can't be read are simply not shown, and can't count as proof. If the freelancer pasted code and named the file, the system checks that the code really is in that file at that commit, and tells the reviewer.
- **The AI only proposes; fixed rules decide.** The rules from the last increment turn the proposals into the final verdict. If the AI is down, out of quota, or answers nonsense, nothing is decided and the freelancer can simply ask again.
- **What happens next:** VERIFIED moves the project to "payout ready" (so the payout plan can now be built, reviewed by the Guardian and approved by a human). NEEDS_CHANGES sends the project back to "in progress" so a new attempt (up to three) can be made. A third failed attempt is FAILED and waits for the lead. If some MUST criteria are only unclear, the freelancer gets exactly one follow-up round with a question that quotes the reviewer's reason; both rounds' evidence is judged together. If GitHub could not be reached, nothing changes and nobody is blamed (GitHub is also retried once automatically).
- **The saved report** lists every criterion with its verdict, who decided it (automatic check, AI, or rules), its flags and the evidence cited, plus the gates, any attempted trickery, and the percentages. Its summary sentence is written by the rules, not the AI, so it can never say "perfect" when the verdict is "needs changes"; the AI's own comment is shown separately and labelled. The report has a fingerprint (sha256); the payout safety check (G-12) later ties the payout to exactly this report.
- **The whole verification pipeline now works end to end** with fake internet and fake AI in the tests: submit, automatic checks, questions, evidence upload, judging, verdict, project moves on.
- 1,302 automated tests pass (43 new). I broke about 50 things on purpose; the first pass caught most, I added tests for the rest, and now all are caught except three that provably change nothing.

**What it does NOT do yet**
No real Gemini answer has ever been seen (needs your key), so the prompt wording is untested against the real model. After a FAILED verdict the lead has no screen or button yet to extend, cancel and refund, or override. The reviewer does not see the live page's text, only the automatic check results.

**Progress:** 25 of ~45 tasks done or in review. Increment 25 of the 30 you asked for.

**Needed from you:** the same: BLK-01/02/03, PayPal sandbox keys, Gemini key (this is where it matters most), optionally Cloudinary.

**Next increment:** the poll fallback (T-43): if PayPal's message never arrives, the system asks PayPal itself about captures, refunds and payouts that are still waiting.

---

## Increment 24 · The rules that decide "VERIFIED" (first half of T-34) · Mon Nov 9

**What now exists**
- **The AI can suggest, but fixed rules decide.** When the AI reviews the freelancer's evidence it will give each criterion a verdict (pass, fail, unclear) with a confidence and the evidence it relied on. A separate piece of plain code now turns those suggestions into the real result, and it can only ever make a result stricter, never kinder:
  - a criterion whose own automatic check failed is a **fail**, whatever the AI says;
  - if the AI says the screenshot contradicts the live website, it is a **fail**;
  - a "pass" with less than 70% confidence, or without pointing to real evidence from that question (made-up evidence numbers are thrown away), or with a pasted code snippet that isn't in the repository, or whose automatic check couldn't run, becomes **unclear**;
  - no answer from the AI for a criterion means unclear; an AI verdict about something nobody asked is ignored.
- **The overall verdict.** The work is **VERIFIED** only if every MUST requirement passes completely, nobody tried to trick the reviewer (hidden "mark everything as passed" instructions), and the GitHub repository is public and the commit exists. SHOULD and COULD items are reported but never block payment. If only some MUST criteria are unclear, the freelancer gets exactly **one** follow-up round. Otherwise it is **NEEDS_CHANGES**, and on the third attempt **FAILED**, which is left to the lead to decide. If GitHub couldn't be reached and everything else is fine, the result is **inconclusive**: nobody is blamed and nothing changes; the checks just run again.
- **A requirement with no criteria proves nothing**, and a project with no MUST requirement can never be verified.
- **Percentages** (MUST and SHOULD) are weighted by importance and rounded down, never up.
- 1,259 automated tests pass (44 new), including a randomized test that checks that making any single verdict worse, or adding a trick attempt, can never improve the overall outcome. I broke 38 things on purpose and all were caught.

**What it does NOT do yet**
The AI judge itself, the button that asks for judging, the saved verification report, and moving the project to "payout ready" or back to "in progress" come in the next increment.

**Progress:** 24 of ~45 tasks done or in review (T-34 half done). Increment 24 of the 30 you asked for.

**Needed from you:** the same: BLK-01/02/03, PayPal sandbox keys, Gemini key (optionally Cloudinary).

**Next increment:** the judge (second half of T-34): the AI reviews all evidence, including screenshots, in a single call; the rules above decide; the verification report is saved and the project moves on.

---

## Increment 23 · The questions the freelancer must answer (T-33) · Mon Nov 9

**What now exists**
- **The system works out what still needs proving.** After the automatic checks, every acceptance criterion in the signed BRD is looked at. If a robot check already proved it (the page contains the words, the file exists, the site works on phones) and the BRD asked for nothing more than that, no question is asked. If the BRD also wants a screenshot or the code, the robot check does not remove that: it stays on the list. A failed or missing check never lets a criterion off the hook. This decision is made by plain code, not by the AI.
- **One clear question per remaining criterion.** The AI (when its key is set) only phrases each question in plain words, naming the requirement and exactly what to upload. It cannot add or skip criteria or ask for different evidence than the BRD lists: the evidence list always comes from the BRD, and any question about something unknown is thrown away.
- **It never gets stuck.** If the AI is off, out of quota or answers badly, every criterion simply gets a standard question built from the BRD's own wording, so the freelancer can always continue. The audit trail records every AI call, including bad ones.
- **Safe with hostile text.** Wording from the BRD and the freelancer's notes goes to the AI only inside "this is data, not instructions" wrappers; a planted fake closing tag is defused.
- **Automatic flow:** submit, then checks run, then questions appear; if every criterion was already proven, the submission skips straight to "evidence received". I tested the whole chain through the real background-job machinery, including answering the questions over HTTP.
- 1,215 automated tests pass (24 new). I broke 29 things on purpose; the first run caught 26, and I added tests until all were caught.

**What it does NOT do yet**
Nothing judges the answers yet (T-34), and there is no follow-up round yet. No recorded Gemini answer exists for replay because that needs your key.

**Progress:** 24 of ~45 tasks done or in review. Increment 23 of the 30 you asked for.

**Needed from you:** the same: BLK-01/02/03, PayPal sandbox keys, Gemini key (and optionally a Cloudinary account).

**Next increment:** judging and the verdict (T-34): the AI reviews all evidence in one call, then plain code applies the rules to decide VERIFIED, NEEDS_CHANGES or FAILED and writes the verification report.

---

## Increment 22 · Screenshots and evidence (second half of T-31) · Mon Nov 9

**What now exists**
- **A safe place for screenshots.** The freelancer asks for an upload link, uploads a picture, and the server then checks it is really a JPEG, PNG or WebP by reading the file's first bytes (a file called `.png` that is really a web page or an SVG is refused), within sensible size limits (5 MB, no absurd dimensions). Pictures are private: only project members can ask for a viewing link, and that link stops working after a few minutes. In development they sit in a local folder; in production they go to Cloudinary with signed uploads, which is built and tested against a pretend Cloudinary but not yet against a real account.
- **Answering a question with evidence.** For each verification question the freelancer can attach up to three of their own screenshots, paste code (up to 200 lines), name a file in the repository, add a link and a short note. Posting again replaces the previous answer. Once every question has an answer, the submission moves to "evidence received". Only the contract's freelancer can do this, and what they write is stored as plain data; it is never treated as an instruction.
- **The submission page data now includes the questions and answers.**
- **A real bug found and fixed.** A pattern I used in several places (image ids, commit ids, repository paths, page paths) wrongly accepted a value with a trailing line break. All are now strict, with tests.
- 1,191 automated tests pass (136 new). I broke 51 things on purpose; 49 were caught and 2 change nothing in practice. I also added tests for the gaps those checks exposed.

**How we work now:** following your instruction, everything is committed straight to `main`; there are no more per-increment branches. `AGENTS.md` says so.

**What it does NOT do yet**
Nothing writes the verification questions yet (T-33), so the evidence form has nothing to answer in a real run. Cloudinary is unproven until an account exists. No limit yet on how many upload links one person can request.

**Progress:** 23 of ~45 tasks done or in review.

**Needed from you:** the same: BLK-01/02/03, PayPal sandbox keys, Gemini key. A free Cloudinary account (cloud name, key, secret in `.env` as `CLOUDINARY_URL`) would let me prove the image path.

**Next increment:** the Verification Agent's questions (T-33): one clear question per acceptance criterion that the automatic checks did not already settle.

---

## Increment 21 · The freelancer hands in the work (first half of T-31) · Mon Nov 9

**What now exists**
- **Submitting work.** Once a project is funded and in progress, the freelancer named in the contract can submit: the GitHub repository, the exact commit, the live website address and optional notes. Nobody else can. Only one submission is checked at a time, and there are at most three attempts; a fourth is refused and left to the lead. Bad input (a non-GitHub link, a made-up commit id, a non-https site, a password inside the link) is refused with a clear message and changes nothing.
- **Automatic checking starts by itself.** Submitting moves the project to "Verifying" (recorded in the ledger) and queues a background job. The job runs the checks from the last increment: repository public, commit exists, every page on the site map loads, and each requirement's own check from the signed BRD (a page contains given words, a file exists, mobile layout). Every result is saved with the requirement it belongs to, so the verification screen can show them next to each requirement. Each page is fetched once, however many requirements use it.
- **Honest about trouble.** A page that is missing or a repo that is private is recorded as a failure; a site that is down or GitHub refusing us (rate limit) is recorded as "couldn't check". Neither stops the process; both feed the later judging step. If the server restarts mid-run, the job redoes the checks cleanly with no duplicates.
- **Reading it back.** Any project member can open a submission to see its state and every check, or list all attempts.
- 1,055 automated tests pass (47 new), including a full run through the real background-job machinery. I broke 32 things on purpose; 31 were caught and the last changes nothing (its rule is checked twice).

**What it does NOT do yet**
After the checks a submission waits: nothing writes the evidence questions yet (T-33). Uploading screenshots and code as evidence, and the image storage behind it, is the second half of this task. Judging and the verdict come after that.

**Progress:** 21 of ~45 tasks done or in review, plus T-31 half done.

**Needed from you:** the same: BLK-01/02/03 decisions, PayPal sandbox keys, Gemini key. When deployed, set `APP_ENV=prod` so the server never fetches `localhost` addresses.

**Next increment:** image storage and the evidence upload (second half of T-31).

---

## Increment 20 · Checking the freelancer's work ourselves (T-32) · Mon Nov 9

**What now exists**
- **A safe way to look at the freelancer's website.** The freelancer types the web address, so we treat it as untrusted: it must be `https`, with no password in it, on the normal port. We look up the address ourselves, refuse anything that points inside our own network or to cloud-internal addresses, and then connect to exactly the address we checked. Redirects are followed at most three times and every hop is checked again. Pages over 2 MB or slower than 10 seconds are dropped. No cookies are kept.
- **Six automatic checks, no AI involved.** The site loads; a page contains specific words (only text a visitor can see, not hidden code); the GitHub repository exists and is public; the commit exists; a file exists at that commit (and a code snippet the freelancer pasted really is in it); the site declares a mobile layout.
- **Honest results.** Each check says PASS, FAIL or ERROR. ERROR means "we couldn't look" (site down, GitHub rate limit), which is neither a pass nor proof of failure.
- **A safety rule kept.** Only the PayPal module may open connections to PayPal. This fetcher is the one other module allowed to use the internet; a new test makes sure it can only read, never mentions PayPal, and is used only by the checks.
- 1,008 automated tests pass (117 new, none touch the real internet). I broke 33 things on purpose; 31 were caught and the other 2 change nothing on this Python version. I also caught myself writing an invisible stray character into one of the new tests, which would have made it useless; it's fixed and the test now fails when it should.

**What it does NOT do yet**
Nothing runs these checks for a real submission yet. The submission screen, saving results and the evidence upload are the next increment (T-31). Pages that build themselves in the browser will only show what the server sends.

**Progress:** 21 of ~45 tasks done or in review.

**Needed from you:** the same: a decision on BLK-01/02/03, PayPal sandbox keys, the Gemini key. A GitHub token (optional) would avoid GitHub's low anonymous limit.

**Next increment:** submissions and evidence (T-31): the freelancer submits repo, commit and live URL, the checks run in the background and the results are saved and shown.

---

## Increment 19 · The public ledger, money box and AI audit trail (back end of T-50/T-51) · Mon Nov 9

**What now exists**
- **The ledger as data for the grid.** Every money and AI event for a project, in order, each with the running pot balance, a plain chip (Held, Captured, Paid, Refunded...), the person's display name, the PayPal reference and who did it. A totals row sits at the bottom. Anyone with the link can read it; email addresses are removed for the public, while project members see the full row.
- **The "Money" box.** The pot balance, how many pledges are on hold and for how much (clearly labelled as not charged), the next deadline by which the holds must be honoured, open money plans, payouts waiting to be claimed, and any alerts.
- **The AI audit trail.** Every AI call for a project: which agent, model, version, how long, whether it was valid, and what it answered. Newest first, filterable.
- **A reconciliation report** that checks the eight money rules from the spec: the pot matches the pledges, is never negative and only pays the freelancer or refunds; captures add up to the goal exactly; the ledger has no gaps; no pledge is both charged and released; the platform's PayPal balance covers all pots (shown as "not checked" when PayPal can't be asked, never hidden); and holds are never counted as money. I planted a violation for each rule to prove the check actually fires.
- **Alerts now show.** When PayPal captures a different amount than we approved, or reverses a capture, a note is written to the ledger and appears in the Money box. Nothing is booked.
- 891 automated tests pass (20 new). I broke twenty things on purpose; all were caught. One real bug found by a test: my email-hiding also swallowed a comma after an address; fixed.

**What it does NOT do yet**
The grids themselves (UI) are not built. The "PayPal match" tick column is empty. The reconciliation report is open to any signed-in user in demo mode because there is no admin role yet.

**Progress:** 20 of ~45 tasks done or in review; back ends of T-50/T-51 done.

**Needed from you:** the same: a decision on BLK-01/02/03, PayPal sandbox keys, the Gemini key.

**Next increment:** submissions and automatic checks (T-31/T-32): the freelancer submits a repo and live URL, and the system checks them.

---

## Increment 18 · Webhooks: PayPal telling us what happened (T-21) · Mon Nov 9

**What now exists**
- **A door PayPal can knock on.** When PayPal finishes something (a capture, a void, a refund, a payout), it sends a message to our server. The server first asks PayPal itself whether the message is genuine; fakes are recorded and refused. Each message is accepted once only (PayPal sometimes sends the same one twice, even at the same instant). If PayPal can't be reached to check, the server says "try again later" and keeps nothing, so PayPal re-sends. The real work happens a moment later in the background, so PayPal never waits.
- **Turning messages into facts.** A completed capture confirms that step of the plan, which fills the project's pot and, once all are in, marks the campaign funded and the project in progress. A declined capture fails that step (the plan ends "partial", never pretending to be funded). A void we asked for confirms the release. A refund confirms that refund. A payout success marks the freelancer paid and empties the pot; a payout failure leaves the money in the pot and marks the payout failed.
- **Robust to the real world.** Messages that arrive before our own record is saved are retried a little later; messages about things we never sent are ignored; repeats change nothing; and a capture for a different amount than the approved plan is flagged, not booked. Processing a message never sends anything to PayPal.
- **A double-payment risk I caught in my own code.** A payout PayPal marks "UNCLAIMED" (the freelancer hasn't claimed it yet) has already left our account. My first draft treated it as a failure, which would have allowed a second payout. It is now treated as "waiting", with a test that proves a second payout can't start.
- **One full run through the real path:** plan approved, the background job sends three captures, three PayPal messages arrive, the background jobs process them, and the project ends funded and in progress.
- 871 automated tests pass (48 new). I broke seventeen rules on purpose; all were caught.

**What it does NOT do yet**
Two message types (a pledge's hold being placed, and a hold ending unexpectedly) are accepted but not acted on, because the small helper they need was blocked (BLK-03, added to the gaps file next to BLK-01 and BLK-02). The exact field names in PayPal's real messages are taken from PayPal's documentation and need checking against real sandbox messages.

**Progress:** 19 of ~45 tasks done or in review; 2 blocked (partial); plus BLK-03 inside T-21.

**Needed from you:** the same: a decision on BLK-01/02/03, the PayPal sandbox (and its webhook ID in `.env` as `PAYPAL_WEBHOOK_ID`), and the Gemini key.

**Next increment:** the ledger, money and AI-audit endpoints (T-50/T-51 back end): the data behind the public ledger grid and the AI audit trail, plus a reconciliation report that checks the money rules hold.

---

## Increment 17 · The Campaign Strategist's forecast (T-46) · Sun Nov 8

**What now exists**
- **A success forecast for the lead.** For a campaign being set up or running, the Strategist computes the chance the goal will be reached, using only plain arithmetic: what is already held, what each owner who hasn't pledged yet *said* they would give weighted by how likely they are to follow through (55% if they've opened the link, 30% if not, 0% if they declined), and how fast supporters have been pledging in the last 6 hours. It is clearly labelled "estimate (heuristic)": with no history it is an informed guess, not a promise. It goes to 100% once the goal is held and to 0% once time runs out short of the goal.
- **Deadline advice.** At setup: 48 hours by default, but if the opening forecast is weak (under 50%), it advises the longest campaign PayPal's 3-day hold guarantee allows (70 hours). While running: if the goal looks at risk (under 60%) with under a day left, it offers one extension to the longest allowed deadline, counted from when the campaign opened, never shortening it and never more than once.
- **Who to nudge.** The owners who haven't pledged and haven't declined, ranked by how likely and how much, each with a plain reason ("hasn't opened the link, said $150"). The freelancer is never on the list.
- **The lead can apply the advice.** The lead clicks apply (or sends a specific deadline) and the deadline changes, within the same rules. The extension can only be used once.
- **Private to the lead**, because it reveals what each sponsor said they would pledge.
- **A worked example from the demo:** before anyone pledges, with Lakshmi having opened the link (hoping $150) and Ravi ($150) and Meena ($100) not yet, the expected total is $157.50 of $400, a 2.6% chance, so the advice is the 70-hour campaign. I checked this by hand.
- 823 automated tests pass (52 new). I broke twenty-four rules on purpose; two slipped through, I added tests, and now all are caught. Two of my tests were also wrong at first (they assumed everyone had opened the link); the code was right.

**What it does NOT do yet**
The optional AI wording of the explanation and the ready-to-send nudge messages (T-47). It also cannot see real pledges until the pledge service (blocked, see below) exists; tests create pledge rows directly.

**Still blocked:** the pledge service (T-22) and the campaign clock (T-25), as recorded in the gaps file section 0. Everything else continues.

**Progress:** 18 of ~45 tasks done or in review; 2 blocked (partial).

**Needed from you:** unchanged: sandbox keys + running the PayPal check script, the Gemini key, and a decision on BLK-01/BLK-02.

**Next increment:** webhooks (T-21): the endpoint PayPal calls to say a hold was placed, a capture completed, a payout succeeded, and so on: verified with PayPal, de-duplicated, safe against out-of-order delivery.

---

## Increment 16 · Blockers recorded; the safe parts of pledging and the clock finished

**What happened.** While building pledging (T-22) and the campaign clock (T-25), an automated safety check stopped two of the files I was writing: the one that takes a pledge and creates the PayPal order, and the one that starts the capture or release plan. I was told not to produce that content again, even reworded, so I did not retry. I don't know what triggered it. Both files are code that starts money-related steps; the neighbouring pure-logic files went through without trouble. I wrote the blockers down (BLK-01 and BLK-02 in the gaps file, new "Blockers" section at the top) with the complete design, so a person can write those two files, or tell me how to proceed.

**What I finished around them (all tested).**
- **The Pledge Gate rules.** The freelancer can never fund their own job; only an open campaign before its deadline takes pledges; an amount must be at least the minimum and no more than what's still needed (and none once the goal is reached); a hold only counts if PayPal says it was placed, for exactly the amount asked; holds are guaranteed for 3 days and valid for 29; the public name is tidied and checked. A race that slightly over-pledges is allowed on purpose, because the capture is split fairly down to exactly the goal.
- **The capture-or-release decision.** One function answers what should happen to an open campaign: a lead cancel always releases; a funded campaign is captured at once (or at the deadline, if the lead chose that), or when the lead closes it; an unfunded campaign is released only at its deadline; closing an unfunded campaign changes nothing. It counts only holds PayPal still guarantees.
- **A separate "order" role for the PayPal connection**, so taking a pledge and moving money are different permissions.
- 771 automated tests pass (90 new for these pieces). I broke twenty-one rules on purpose and every one was caught.

**What this blocks.** Nobody can pledge yet, and no campaign is captured or released automatically. Everything else downstream (webhooks, execution, screens) can still be built and tested by creating pledge rows directly.

**What I need from you.** Either someone writes the two files from the design in `docs/GAPS_AND_FIXES.md` section 0 (BLK-01, BLK-02), or you tell me how you would like me to proceed. I'm carrying on with tasks that are not blocked.

**Progress:** 17 of ~45 tasks done or in review; 2 blocked (partial).

**Next increment:** the Strategist's deterministic forecast (T-46): the success probability, deadline suggestion and who-to-nudge ranking, all plain arithmetic and fully testable.

---

## Increment 15 · The real PayPal client (T-20) · Sun Nov 8

**What now exists**
- **The PayPal connection, built on PayPal's own official kit.** I installed the PayPal developer kit (the APIMatic-generated SDK the hackathon wants us to use) and read its real method and field names straight from the installed package rather than trusting memory. On top of it sits one module that is the only place in the whole codebase allowed to talk to PayPal. It can: look up a hold or a capture (for the Guardian), read the platform balance, capture, void, refund, send a payout, check a payout's status, check that a webhook really came from PayPal, and create and authorize a pledge order. Payouts and webhook checking use plain web calls because the kit doesn't cover them (as the spec expects).
- **Safe by construction.** It refuses anything but the PayPal sandbox. Without keys nothing is configured and every money action fails safely. Its printed form never shows the secret. Amounts are converted between cents and PayPal's text form with exact integer arithmetic, and only plain "123.45" style amounts are accepted.
- **Errors understood once.** Timeouts, "too many requests" and server errors are marked temporary, so the executor retries them under the same reference number. Declines and bad requests are final and carry PayPal's own error code and support number. If PayPal can't answer a lookup, the Guardian is told "unverified" and the plan is held for a human rather than blocked or allowed.
- **A bug that only real-model testing could find.** The PayPal kit leaves fields completely absent (not blank) when PayPal doesn't send them, so a normal response with no payer or no expiry time would have crashed my client. My first tests, which used blank values, hid this. Testing against the kit's real model classes exposed it and it's fixed, with a missing status now read as "UNKNOWN", which the Guardian never trusts.
- **Proven to fit together.** The real client, driven by the real executor and checked by the real Guardian, was tested with only the PayPal kit itself faked: same reference numbers, "final capture" set, retries reusing the same reference, declines recorded with PayPal's reason.
- **A sandbox proof script.** `backend/scripts/sandbox_check.py` will settle the assumptions the design rests on, the moment there are keys: that Payouts works, that capturing less than the hold with "final capture" releases the rest, that a captured hold can't be voided, that voids and refunds work. It pauses twice and prints a link for a human to approve a sandbox payment. I tested its whole flow against fakes, including what a failure looks like.
- 681 automated tests pass (89 new). I broke twenty-two rules on purpose; all caught. I also made the PayPal tests 8 times faster and made them impossible to accidentally hit the real internet.

**What it does NOT do yet**
Nothing has touched real PayPal: that needs your sandbox keys. The three open assumptions (Payouts enabled, final-capture releases the remainder, void behaviour) are still unproven until you run the script.

**A near miss worth knowing about:** one of the safety tests I added (that nothing but the PayPal module may use web-calling libraries) was silently toothless because my editing script turned a "\b" into an invisible backspace character. I caught it by planting a fake offending file to see whether the test would object; it didn't, so I fixed it, and now it does. It's recorded in the gaps file.

**Decision to know about:** D-033 (the full mapping, error rules and the three roles).

**Progress:** 17 of ~45 tasks done or in review.

**Needed from you:** please run the sandbox script when keys exist: (1) set up the PayPal sandbox (US personal buyer accounts, a business account, the app with Payouts and Transaction search enabled); (2) put the Client ID and Secret in `backend/.env`; (3) run `cd backend` then `.venv/Scripts/python scripts/sandbox_check.py --payout-to <Arjun's sandbox email>`; (4) approve the two links it prints; (5) paste the summary back to me. Any FAIL is exactly what I need to know before building more on top.

**Next increment:** T-22, pledging: the Pledge Gate rules (campaign open, amount within the minimum and what's still needed, right currency), creating the order, authorizing it once the supporter approves, recording the hold, and the public pledge board.

---

## Increment 14 · Campaign setup and launch (T-24) · Sun Nov 8

**What now exists**
- **Setting up the Pledge-If campaign.** After the freelancer signs, the lead sets the campaign's deadline (and optionally the smallest allowed pledge, a suggested share, and whether to close the moment the goal is reached or only at the deadline). **The goal is not typed in: it is the signed contract price plus any payout fee**, so there is never a surplus to refund. Setting up again simply updates the one draft campaign.
- **A deadline that PayPal can honour.** A PayPal hold is only guaranteed for 3 days. So a campaign must run at least 1 hour and at most 70 hours (72 minus a 2-hour safety margin) after it opens; that way even the very first hold is still guaranteed when the campaign ends. The rule is checked when you set it up and again at the moment you launch (so waiting too long after setup is caught). I tested it right down to the second on each edge, in other time zones, and with a property test that no hold can be older than the guarantee when the campaign ends.
- **Launch.** The lead clicks launch: the campaign opens, the clock starts, the project moves to the pledging stage and the ledger records both changes. A campaign can't be launched twice, and nobody but the lead can set up or launch.
- **The public campaign page data.** Anyone, without logging in, can see: the goal, the deadline and seconds left, how much has been pledged and by how many people, how much is still needed, and a flag saying money is "held, not charged" until the funds are actually captured. It counts only confirmed holds, not abandoned or cancelled ones, and it contains no emails.
- **Help for the lead.** The lead's view adds: whether launching is possible and, if not, the reasons in plain words (so a greyed-out button can explain itself), the allowed deadline range, and the earliest moment any hold stops being guaranteed.
- 592 automated tests pass (48 new). I broke nineteen rules on purpose; two slipped through, I added a test for them, and now all are caught.

**What it does NOT do yet**
Nobody can pledge yet: that needs the real PayPal connection (next), and there are no screens. The Strategist's suggested deadline isn't wired in.

**Decision to know about:** D-032 (the exact setup, window and public-view rules).

**Progress:** 16 of ~45 tasks done.

**Needed from you:** from here on PayPal is the critical path: the next two increments (the PayPal client, then pledging) are where the sandbox keys become essential. Please set up the sandbox accounts and app (all accounts US-based; Payouts and Transaction search enabled) and put the Client ID and Secret in your local `.env`.

**Next increment:** T-20, the real PayPal client built on the official SDK, with its method names taken from the installed package rather than memory, plus a sandbox script that will prove authorize, capture, void and payout work as assumed once your keys are in.

---

## Increment 13 · The conditional contract (T-30) · Sun Nov 8

**What now exists**
- **The offer.** Once the sponsors have locked the BRD, the lead offers the freelancer a price and a delivery time. The price must be positive and within the project budget and the sandbox payout limit; the time must be 1 to 90 days. The system writes the contract text itself from a template, in plain language: who the parties are, what will be built (the BRD version and its fingerprint), the price, the delivery time, and how payment happens. It says clearly that this is a demonstration agreement, not a legally binding contract.
- **"Effective only if the campaign funds."** The agreement states that it takes effect only if the funding goal is reached; if not, every pledge hold is released, nobody is charged and nothing is owed. It never says "escrow"; it says pooled funds are held by the platform until verified approval.
- **What the freelancer signs is a fingerprint** of the whole text and every number in it (price, days, BRD fingerprint, who). If the lead changes anything, the old fingerprint stops working and the freelancer must read and sign the new version. A signed contract can never be replaced.
- **Signing locks their PayPal email.** The freelancer confirms two fingerprints (the BRD and the terms) and the PayPal account to be paid. That email is locked from then on, so a later payout can only go there. The freelancer cannot name a sponsor's own account. Signing moves the project to the campaign stage and writes a ledger entry with the amounts and fingerprints but, deliberately, no email, because the ledger may be shown publicly.
- **Who can see it:** project members (including the freelancer) can read the contract; strangers cannot.
- 544 automated tests pass (25 new). I broke fifteen rules on purpose; all are caught or judged harmless.

**What it does NOT do yet**
No screen. The freelancer cannot decline an offer (the lead just makes a new one). Nothing about the campaign exists yet.

**Housekeeping note:** at the start of this step the repository's current-branch pointer had been blanked when the previous command was cut off mid-write. I checked first, confirmed all commits and files were intact, repaired only that one pointer, re-ran the whole suite and finished the merge. Nothing was lost. It's recorded in the gaps file.

**Decision to know about:** D-031 (what is signed, who can sign, and one added endpoint to read the contract).

**Progress:** 15 of ~45 tasks done.

**Needed from you:** unchanged: the Gemini key and the PayPal sandbox setup. The next steps (campaign, pledges) are where PayPal becomes essential.

**Next increment:** T-24, campaign setup and launch: the goal is fixed by the contract; the lead picks a deadline that respects PayPal's 3-day hold guarantee (72 hours maximum, minus a 2-hour safety margin), launches, and the project goes live for pledging.

---

## Increment 12 · BRD approvals (T-15) · Sun Nov 8

**What now exists**
- **Sponsors vote on the exact document they read.** Each sponsor (and the lead, who is also a sponsor) approves or rejects the BRD, and the vote only counts for the document fingerprint they actually saw. If the document changes, or they send an old fingerprint, the vote is refused with a clear message and nothing is saved. Votes never carry over from one version to the next.
- **Everyone must approve.** When the last sponsor approves, the BRD locks: it becomes APPROVED, gets a lock time, the ledger records "BRD locked" with the fingerprint, and the project moves on to the contract stage. After that nobody can approve, reject or change it.
- **Rejecting reopens the conversation.** A rejection needs a written reason. The reason becomes a new question to all sponsors in the BA conversation (for example: "Meena asked for changes to BRD v1: 'Add a page for boat safety'. How should the document change?"). The project goes back to the requirements stage, the transcript can be edited again, and once the question is answered the system re-scores, the lead generates version 2, and everyone approves afresh.
- **Small human touches that matter:** clicking approve twice does nothing extra; an approver who changes their mind can withdraw by rejecting with a reason; every decision is written to the ledger with who, which version, which fingerprint and any comment; the BRD page shows who has approved and who is still awaited.
- I ran the whole loop through the real endpoints: v1, one approval, one rejection, an answer, a re-score, v2, three approvals, lock.
- 519 automated tests pass (16 new). I broke thirteen rules on purpose; two slipped through at first, I added tests for them, and now all are caught.

**What it does NOT do yet**
There's no screen to vote on, and one risk is recorded: if a sponsor never responds, the project cannot move forward, and there's no way yet for the lead to remove them (GAP-28 in the gaps file).

**Decision to know about:** D-030 (the exact voting rules).

**Progress:** 14 of ~45 tasks done. The requirements side of the product (project, transcript, AI analysis, questions, BRD, approvals) is now complete in the API.

**Needed from you:** unchanged: the Gemini key and model name, and the PayPal sandbox setup. Both are now the main things that stand between this and a real end-to-end run.

**Next increment:** T-30, the conditional contract: the lead offers the freelancer a price and delivery time; the freelancer reviews the locked BRD and signs, which locks their PayPal email. The contract is tied to the approved BRD fingerprint and says it's "effective only if the campaign funds".

---

## Increment 11 · The BRD generator (T-14) · Sun Nov 8

**What now exists**
- **From finished analysis to a real document.** When the BA analysis is ready (90+ with every gate green) or the lead has finalized it, the lead clicks "Generate BRD". The AI drafts the document; code then assembles, checks, formats and fingerprints it. The result is a numbered Business Requirements Document: executive summary, goals, who needs what, audience, the page list, then the requirements as REQ-001, REQ-002 and so on. Each has a priority, a weight, who asked for it and testable acceptance criteria in plain "Given / When / Then" form, plus the evidence the freelancer should show, and, where the platform can check it mechanically, an automatic check ("the page /contact contains 'Send enquiry'").
- **Code, not the AI, guarantees the important things:** nothing from the analysis gets dropped (every requirement found earlier must be carried over); every MUST has at least one testable criterion; the numbering is sequential with MUSTs first; the budget and delivery time come from the project record, not from the AI; people are referenced only by real sponsor ids; references to transcript lines must point at lines that exist; things explicitly ruled out always stay ruled out; and anything still unsettled (a red gate, or a thinly covered topic after finalizing) is listed under "Open items" so sponsors approve with open eyes.
- **A fingerprint.** The document gets a SHA-256 hash computed from its canonical content, so the sponsors' approvals and the freelancer's contract can be tied to exactly this text. Anyone can recompute it.
- **Safe to publish.** The document text is formatted by a template, not written by the AI, and everything derived from user input is escaped, so a hostile name or description can't inject headings, links or HTML. I found and fixed a real hole here during testing: lines starting with `##` could slip through and become headings.
- **Reading it:** anyone can read the BRD and download it as a Markdown file, with no login (it contains no emails). It shows which sponsors have yet to approve. Generating a new version supersedes an unapproved older one but never an approved one.
- **After generation** the project moves to "BRD review".
- 503 automated tests pass (66 new). I broke fifteen rules on purpose; one slipped through at first, I added a test, and now all fifteen are caught.

**What it does NOT do yet**
Sponsors can't approve or reject yet (T-15), and no real Gemini call has been made, so the actual quality of the drafted BRDs is unseen. There is no screen.

**Also done this increment (as you asked, in a separate file):** `docs/GAPS_AND_FIXES.md` lists every gap and every fix found so far (21 open gaps, 11 fixes). Along the way I fixed two problems nobody had noticed: the dependency list pinned a library version that did not match the installed one (a teammate or the CI pipeline would have failed to install), and the README-for-assistants had its commands section unfilled. I also added the automatic test pipeline (GitHub Actions) the spec asks for.

**Decision to know about:** D-029 (what the AI drafts versus what code owns).

**Progress:** 13 of ~45 tasks done.

**Needed from you:** the Gemini key and model name are still the main unlock. Also see the High items in the gaps file: PayPal sandbox setup (GAP-01).

**Next increment:** T-15, BRD approvals: each sponsor approves the exact fingerprint they saw; all must approve to lock it; any rejection with a comment sends it back to the BA conversation as a new question and produces version 2.

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
