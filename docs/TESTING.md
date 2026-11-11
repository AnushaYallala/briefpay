# How to run BriefPay and test it by hand

For someone who wants to click through the demo. No coding needed once it is running. Everything below was checked on a real running copy (an automatic check script confirms the data and every page is served); **nobody has yet clicked through it in a real browser**, so you are the first. Please write down anything odd.

## 1. Start it

You need Python 3.13 and Node 22. Open two terminals in the project folder.

**Terminal 1: the server and the demo data** (Windows paths; on macOS/Linux use `.venv/bin/...`):

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp ../.env.example .env            # the defaults are fine; no keys are needed for this guide
.venv/Scripts/alembic upgrade head
.venv/Scripts/python scripts/seed.py
.venv/Scripts/uvicorn app.main:app --port 8000
```

**Terminal 2: the web app:**

```bash
cd frontend
npm install
npm run dev                         # http://localhost:3000
```

Open <http://localhost:3000>. To start again from a clean slate: stop the server, delete `backend/briefpay_dev.db`, and repeat the `alembic` and `seed.py` lines.

**Check it automatically** (optional, 5 seconds). With both running:

```bash
cd backend
.venv/Scripts/python scripts/smoke.py --api http://localhost:8000/api --web http://localhost:3000
```

You should see 22 lines starting `[ OK ]` and "22 of 22 checks passed." A `[FAIL]` line says in words which fact is wrong.

## 2. The cast

Use the **person drop-down in the top bar** (its hidden label is "Switch demo person"; it lists Lakshmi, Ravi, Meena and Arjun) to become someone (no passwords in the demo). It only appears in demo mode; `npm run dev` turns that on by itself (from `frontend/.env.development`), a production build does not:

| Person | Role | Why |
|---|---|---|
| Lakshmi | Lead (organiser) | sees everything, builds plans, runs the campaign |
| Ravi, Meena | Sponsors | decide on the brief and the payout |
| Arjun | Freelancer | builds the website, submits work |
| (nobody signed in) | Visitor | sees only the public parts |

The demo has two projects: **"Velugu Cove tourism website"** (project 1, the first campaign **missed its goal**: nobody was charged) and **"... (build phase)"** (project 2, funded, work rejected once then verified, ready to be paid).

## 3. What to try, and what you should see

Replace `2` with `1` where it says "round one". Pages take the project number in the address, for example `http://localhost:3000/ledger/?id=2`.

### As a visitor (nobody signed in)
1. **Home** `/`: two project cards with state and progress.
2. **Project 2** `/project/?id=2`: a progress stepper, a plain "what happens next" sentence, the campaign card (**funded, $400 of $400**), terms, the people. The money box says to sign in.
3. **Campaign** `/campaign/?id=2`: "Funded. The pledged money has been collected." and a **pledge board** with three people shown as *Collected* with their amounts. Try project 1 `/campaign/?id=1`: "The goal was missed. Every hold was released: nobody was charged." and the pledgers shown as *Released*.
4. **Ledger** `/ledger/?id=2`: every money event in order, never edited. Click the chips to filter, type in the search box, click **Details** on a row, **Export CSV**. The bottom row adds up what is shown. No email addresses anywhere.
5. **Brief** `/brd/?id=2`: the written requirements document (nine requirements), its fingerprint and status ("Approved and locked"), a table of requirements.
6. Try `/plans/?id=2` and `/audit/?id=2`: you should be asked to **sign in** (members only).

### As Lakshmi (lead)
7. **Project 2**: the money box shows **$400.00 in the pool**; links to BA Studio, the AI audit trail and the campaign page.
8. **Money plans** `/plans/?id=2`: the finished "Collect the pledges" plan: steps in a table and the Guardian's rules with ✓ marks, the ones PayPal itself proves tagged "verified with PayPal".
   * Press **Build a payout plan**: a plan paying the builder $400 appears.
   * Press **Run the Guardian check**. Without PayPal and AI keys expect the decision **HOLD**: "the AI risk review could not run" and one rule "not checked" (it cannot ask PayPal for the balance). That is the safe behaviour: it asks a person.
   * Under **Try to cheat (demo only)** press *Swap the recipient*: the Guardian answers **BLOCK** with the rules that caught it in red (G-01, G-03, G-12), labelled as a simulation; PayPal is never contacted.
   * **Do not press "Approve and run"** unless you have PayPal sandbox keys: this guide does not cover what happens then.
9. **Ledger** again: **Check with PayPal** needs PayPal keys; without them it says so in words.
10. **AI audit trail** `/audit/?id=2`: every AI call (may be short or empty without a key); click **Details**.
11. **BA Studio** `/ba/?id=2`: the score history, the checks, the transcript, the requirements. **Running a new analysis needs a Gemini key**; without one the page shows the server's reason.
12. **Submit** `/submit/?id=2` and **Verify** `/verify/?id=2`: the two attempts (first "needs changes", second verified), the automatic checks with what each looked at (for example "PAGE_CONTAINS: /menu contains “...”"), the verification matrix.
13. **Campaign** `/campaign/?id=2` as Lakshmi: an extra **"For the organiser"** panel with greyed-out buttons (*Close and collect now, Cancel, Start another round, Try the deadline early*) and a note that they are not built yet.

### As Ravi or Meena (sponsor)
14. Same pages; the organiser panel and the plan-building buttons are **not** there. On the brief page a sponsor would be offered *Approve* / *Ask for changes* only while a version is waiting for decisions (this one is already approved, so none).

### As Arjun (freelancer) and as a stranger
15. Arjun sees the contract and submit pages. A signed-in person who is not on a project sees "Only the people on this project can see its money box."

### The numbers behind it (no clicking)
* `docs/EVAL_RESULTS.md`: what we measured (Guardian 8/8 and so on).
* `python -m pytest -q` in `backend` and `npm run check` in `frontend` run the automatic tests.

## 4. What is NOT working yet (so you do not report it as a bug)

* **Making a pledge** works only once the PayPal sandbox client id is in `frontend/.env.local` (`NEXT_PUBLIC_PAYPAL_CLIENT_ID=...`, the same value as `PAYPAL_CLIENT_ID` in `backend/.env`) and both servers were restarted. Without it the box says "PayPal is not set up on this site yet". It has never been run against real PayPal, so tell us what you see.
* **Closing, cancelling and restarting a campaign** work from the organiser panel; "Try the deadline early" appears only in demo mode. These also need PayPal to actually collect or release money.
* **Anything that needs keys:** the real PayPal sandbox (paying out, "Check with PayPal"), the live AI (running the BA analysis, generating the brief, judging evidence, the Strategist's wording). The Strategist forecast works without a key and says "Worded by a template".
* **Cloudinary** image uploads use local files in this setup.
* **Not yet deployed** to the internet; this guide runs on your own computer.

## 5. If something looks wrong

Write down: the page address, who you were signed in as, what you did, what you saw, what you expected. If a page is blank, open the browser's console (F12) and copy the red text. The server's own words for refusing something are shown on the page; those are meant to be read.
