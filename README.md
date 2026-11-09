# BriefPay

**Neighbours pool money for one shared project. Nobody is charged unless the goal is reached. The builder is paid only after an AI-assisted, code-checked review says the work matches what was agreed, and a human approves the payout.**

BriefPay was built for the PayPal AI hackathon. Everything runs on **PayPal sandbox money** and fictional people (the Velugu Cove demo). It is not a payments product and moves no real money.

> **Honest status (see [docs/STATUS.md](docs/STATUS.md) for the live board):** the whole back end is built and tested (1,376 automated tests at the time of writing, no network or keys needed). The web front end, the hosted Render deployment and the demo video are **not built yet**. Three back-end pieces are blocked and described in [docs/GAPS_AND_FIXES.md](docs/GAPS_AND_FIXES.md) section 0. PayPal, Gemini and Cloudinary have only been exercised against faithful fakes so far, because no sandbox keys have been supplied.

---

## The problem

Five shop owners in a small beach town want one website. Nobody trusts a stranger with $400 up front, nobody can write a clear brief, and nobody can judge whether the delivered site matches what was discussed. BriefPay turns a rambling meeting into a signed brief, collects pledges that cost nothing unless the goal is met, checks the delivered work against the brief, and pays the builder only then.

## How "Pledge-If" works (and why a pledge is only a hold)

1. **A pledge is a PayPal authorization, not a payment.** A supporter approves a hold (`intent=AUTHORIZE`). No money moves. PayPal only guarantees such a hold for about three days, so campaigns are capped at 72 hours.
2. **All or nothing.**
   * Goal reached: the system captures the holds **pro rata so the total equals the goal exactly** (never more than any one hold).
   * Goal missed or the lead cancels: every hold is **voided**. Nobody is charged.
3. **Captured money sits in a per-project pool** recorded in an append-only ledger. The pool can only do two things: pay the freelancer or refund the pledgers. Projects never touch each other's money.
4. **The freelancer is paid only after verification passes and a human approves the payout** (a PayPal Payouts batch to the email locked into the signed contract).

We say "hold" and "pooled funds held until verified approval". We never say "escrow".

## What is AI, what is plain code, what is human

| Step | Who decides |
|---|---|
| Scoring how complete the requirements are, asking clarifying questions | **AI proposes** (Gemini); the score, the gates and the 90 threshold are **computed by code** |
| Drafting the BRD (the signed brief) | **AI drafts**; code assigns requirement codes, checks every MUST is testable, renders it and **hashes it**; every sponsor approves that exact hash |
| Contract | Code: the freelancer signs the BRD hash, the price and their PayPal email. It is conditional: effective only if the campaign funds |
| Which hold to capture or void, how much, to whom | **Code only** (settlement math, property-tested) |
| Is a set of PayPal operations safe to run? | The **Payment Guardian**: 13 deterministic rules plus soft flags, and an AI risk review that can only **escalate**, never relax. It outputs ALLOW / HOLD / BLOCK and cannot execute anything |
| Calling PayPal to move money | **One chokepoint, `MoneyExecutor`**, enforced by a test that fails if any other module calls a PayPal write method |
| Is the delivered work done? | Automatic checks (the live site, the GitHub repo and commit), freelancer evidence (screenshots, code), an **AI reviewer that only proposes verdicts**, then **fixed rules decide** (a pass needs real cited evidence and confidence of at least 70%; a failed automatic check beats the AI; hidden instructions in the evidence block verification) |
| Releasing the payout | **A human** approves a plan bound to its exact hash. The Guardian has already reviewed it |

Every AI call is logged with its prompt version, input hash, status and output, and is shown in an audit trail. Text written by users is passed to the model inside `<untrusted>` tags and is never treated as an instruction.

## Architecture

```
 Browser (static Next.js, planned)                      PayPal sandbox
        |  HTTPS JSON, Bearer token                      ^   |  webhooks
        v                                                |   v
 +------------------------------ FastAPI (backend/app) ------------------------------+
 |  routers: auth projects ba brd contract campaigns strategist submissions images    |
 |           verification plans ledger webhooks jobs                                  |
 |                                                                                    |
 |  AI agents (Gemini, behind LLMAdapter: logs every call, replayable)                |
 |     BA scoring + questions | BRD generator | Strategist | Verifier | Guardian LLM  |
 |                                                                                    |
 |  Deterministic core                                                                |
 |     settlement | pledge gate | campaign rules | verify_aggregate | state machines  |
 |     PlanBuilder -> Guardian (G-01..G-13) -> approval -> MoneyExecutor -> PayPal    |
 |     ledger (append-only, POOL bucket) | webhook_processing | poll fallback         |
 |                                                                                    |
 |  AutoChecks (SSRF-safe fetcher, GitHub API) | ImageStore | JobRunner (DB jobs)     |
 +--------------------------------------+---------------------------------------------+
                                        |
                       SQLAlchemy 2 + Alembic: SQLite (dev), PostgreSQL (prod)
```

* **Money is integer cents everywhere.** The ledger is append-only (a database listener refuses updates and deletes), gapless per project, and a reconciliation report checks eight invariants (pool balance, no double capture, captures sum to the goal, holds are never money, and so on).
* **Jobs run in-process** from a database table (the free host has no background workers). The same runner polls PayPal every 30 seconds for steps whose webhook never arrived.
* **Webhooks** are verified with PayPal itself, stored once, and processed by a job. A payout PayPal marks *unclaimed* is treated as waiting, never as failed, so nobody is paid twice.
* **Fetching user-supplied URLs** goes through one hardened fetcher (https only, public addresses only, pinned connections, redirect re-checks, size and time limits). A test pins it as read-only.

## Run it

Requirements: Python 3.13. No keys are needed to run the tests or to explore the API with the demo data.

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # on macOS/Linux use .venv/bin/python
cp ../.env.example .env                                      # keys are optional for local use; never commit .env
.venv/Scripts/alembic upgrade head                           # creates backend/briefpay_dev.db (SQLite)
.venv/Scripts/python scripts/seed.py                         # loads the Velugu Cove demo data (see below)
.venv/Scripts/uvicorn app.main:app --reload --port 8000      # API at http://localhost:8000/api, docs at /docs
.venv/Scripts/python -m pytest -q                            # 1,376 tests, about a minute, no network
```

### Demo data and personas

`scripts/seed.py` (demo mode only) loads two projects through the real services, without any PayPal call:

* **"Velugu Cove tourism website"**: the first campaign missed its deadline ($300 of $400 pledged); the Guardian allowed the release plan; three holds were voided; **nothing was charged**.
* **"Velugu Cove tourism website (build phase)"**: $400 captured, contract in force, the freelancer's first submission **rejected** (the enquiry form was missing on the live site), the second **verified**. Ready for the payout.

Sign in with an email only (this is demo authentication, not production auth): `lakshmi@velugu.example.com` (lead), `ravi@...`, `meena@...` (sponsors), `arjun@...` (freelancer). Pass `--paypal-email`, `--repo`, `--site`, `--commit-1`, `--commit-2` to use the real sandbox account and the real sample site.

### Using PayPal sandbox, Gemini and Cloudinary

Put keys in `backend/.env` (see [.env.example](.env.example)). `backend/scripts/sandbox_check.py` proves the PayPal assumptions the design rests on against the real sandbox (authorize then capture, authorize then void, partial capture releases the rest, a payout). Nothing is sent without keys, and the app starts in a fail-safe mode where no PayPal call can succeed.

## Tools we used

| Tool | For |
|---|---|
| **PayPal** Orders v2 (`AUTHORIZE`), Payments v2 (capture, void, refund, reads), Payouts, Webhooks, Transaction Search | The pledge holds, captures, refunds, the freelancer payout and the confirmation of each |
| **APIMatic**-generated `paypal-server-sdk` | Orders, Payments and balance reads (Payouts and webhook verification use `httpx`, as the SDK does not cover them) |
| **Gemini** (Flash model, set by `AI_MODEL`) | BA scoring and questions, BRD drafting, the verification questions and the vision review of evidence, the Guardian risk review. Not yet run against the real model |
| **FastAPI, SQLAlchemy 2, Alembic, Pydantic 2** | The service |
| **AG Grid Community** | Planned for the ledger, audit trail, pledge board, BRD requirements, verification matrix and plan steps |
| **Render, Aiven PostgreSQL, Cloudinary** (free plans) | Planned hosting, database and screenshot storage |

### How we used APIMatic

| Our use | PayPal API | Via |
|---|---|---|
| Create pledge orders (`AUTHORIZE`), authorize the order | Orders v2 | SDK |
| Capture, void, refund; read an authorization, a capture, a refund | Payments v2 | SDK |
| Guardian rules that check PayPal's own records (G-06) and balances (G-08) | Payments get, Transaction Search | SDK |
| Payout batches and their status | Payouts v1 | `httpx` |
| Verify a webhook signature | Notifications v1 | `httpx` |

## What we measured

* **1,376 automated tests** pass with no network and no keys. After each feature the rules were attacked on purpose: a small tool breaks the code (flips a comparison, removes a check, changes a number) and the tests must fail. Several hundred such deliberate breakages were run; every one is caught or documented as harmless in [docs/GAPS_AND_FIXES.md](docs/GAPS_AND_FIXES.md). That log also lists the real bugs this found in our own code.
* A property test shows that making any single verdict worse, or adding a hidden-instruction attempt, can never improve the verification outcome.
* A reconciliation test shows all eight money invariants hold on the seeded data.
* The AI evaluation table (BA, Verifier, Guardian, Strategist against a small labelled set) is **not produced yet**; it needs the Gemini key.

## Production boundaries (what this is not)

Real money, KYC, tax, legal enforceability of the contract, dispute arbitration, production authentication (login is email only and exists for the demo), money-transmission compliance and native apps are out of scope. Pledge holds are only guaranteed by PayPal for about three days. Colluding sponsors and a freelancer could still fake an approval: shill pledging and self-funding are flagged (soft flags S-01 and S-02), not prevented; mitigations are the automatic checks against the live site, the snippet-in-repository check, the Guardian and the public ledger.

## Documents

* [docs/SPEC.md](docs/SPEC.md): the full specification and API contract
* [docs/STATUS.md](docs/STATUS.md): task board and handoff log
* [docs/PROGRESS_SUMMARY.md](docs/PROGRESS_SUMMARY.md): plain-English summary after each increment
* [docs/DECISIONS.md](docs/DECISIONS.md): every decision that fills a gap in the spec (D-001 onward)
* [docs/GAPS_AND_FIXES.md](docs/GAPS_AND_FIXES.md): blockers, known gaps and every defect found and fixed

## Licence

MIT. See [LICENSE](LICENSE). All businesses and people in the demo are fictional.
