# Gaps and Fixes

A running list of everything that is **missing, risky, unverified, or was found and fixed** while building. It is separate from `STATUS.md` (which says what is done) so that nothing gets lost in handoff notes. Every increment adds to it.

- **Open gaps** are things still to do or to decide. Severity: **High** = blocks the demo or is a safety risk, **Medium** = should be fixed before submission, **Low** = nice to have or documented limit.
- **Fixes** are problems that were found and already resolved, kept so the reasoning is not lost.
- IDs are permanent. When a gap is closed, move it to Fixes (keep the ID) and say how.

_Last updated: 2026-11-08, end of T-15._

---

## 1. Open gaps

### Blocked on something only a human can provide
| ID | Sev | Gap | Needed / planned |
|---|---|---|---|
| GAP-01 | High | **No real PayPal connection exists.** Everything money-related (executor, Guardian PayPal checks, plan lifecycle) is tested only against fakes. Sandbox behaviour of `final_capture`, void, payouts and webhook payloads is unverified (assumptions A-1, A-2, A-3, A-8, A-9). | Human: T-02 (US sandbox accounts, app with Payouts and Transaction search, Client ID and Secret in `.env`). Then T-20 (real client + sandbox script), T-21 (webhooks), T-43. |
| GAP-02 | High | **No real Gemini call has ever been made.** Structured-output acceptance of our nested schemas (lists of objects, enums, float coverage) is unverified (A-4). Question and BRD quality is unjudged. | Human: Google AI Studio key (billing OFF) and the Flash model name in `.env`. First live run may require flattening a schema. |
| GAP-03 | Medium | **Replay fixtures do not exist yet.** Without a key or recorded answers, every Guardian review comes back HOLD (`GUARDIAN_LLM_UNAVAILABLE`) and the BA/BRD jobs retry and fail. Safe, but the demo cannot run without them. | T-52 (record fixtures with a key; do it before the demo). |
| GAP-04 | Medium | GitHub repo setup incomplete (T-01): licence visible in About, secret scanning enabled. | Human, in the GitHub UI. |
| GAP-05 | Medium | Aiven PostgreSQL not created (T-03), so the migration has only been run on SQLite. Type differences (BigInteger autoincrement, JSON, timezone-aware datetimes) are untested on Postgres. | Human: T-03. Then run `alembic upgrade head` and the suite against it once (T-61a). |
| GAP-06 | Medium | Teammate's freelancer sample site and its two commit SHAs (one rejected, one accepted) not available yet (T-60); needed for verification tests and the video. | Teammate. |

### Safety and correctness gaps in code that exists
| ID | Sev | Gap | Planned |
|---|---|---|---|
| GAP-07 | Medium | `GET /api/jobs/{id}` has **no authorization**. Job results can contain project ids and scores. | Restrict to members of the job's project once jobs carry a project id (add to payload convention). |
| GAP-08 | Medium | Ledger append-only is enforced only by ORM event guards. Raw SQL can still edit or delete rows. | Add a Postgres trigger (and SQLite trigger for tests) in a migration. |
| GAP-09 | Medium | **Partial capture has no repair path.** If some captures fail the plan ends PARTIAL, the campaign stays CAPTURING and the project stays PLEDGING (by design), but nothing lets the lead refund the captured part or rebuild. | T-44 / T-27: refund plan from CAPTURING state, UI. G-02 state rules would need to allow it. |
| GAP-10 | Medium | G-12 "all-sponsor override" (payout after a final verification failure) is **not implemented**: only a VERIFIED report can pass. | Decide with T-34/T-36 whether to build it; spec says shown in the ledger. |
| GAP-11 | Low | `REAUTH_PLEDGES` / `REAUTH_AUTH` (SHOULD) not built; builder and executor refuse it. | Cut-order item 2; only if time. |
| GAP-12 | Low | A pledge whose pro-rata capture rounds to 0 gets no capture step and would stay held. Unreachable with the 500-cent minimum but untested. | Add a test or void such holds in the capture plan. |
| GAP-13 | Low | Executor commits the session it is given (needed for crash safety). Callers cannot wrap it in a larger transaction. | Document; acceptable. |
| GAP-14 | Low | `PUT /projects/{id}/members` cannot remove or decline an invitee. Typos in an invite need a database edit. | Add a remove/decline action before sponsors are locked. |
| GAP-15 | Low | `GET /projects/{id}` writes (viewed-tracking). Fine functionally, unusual for a GET. | Leave; note for review. |
| GAP-16 | Low | BA manual-run rate limit counts jobs by loading recent `BA_RUN` rows and filtering in Python. Fine at demo scale. | Leave. |
| GAP-17 | Low | A replaced transcript re-scores the current round but leaves already-asked questions (which may now be stale). | Acceptable; lead can skip them. |
| GAP-18 | Low | No `/demo/persona` switcher or `/admin/reconcile` endpoint yet (spec section 10). | T-05 / T-48 / T-52. |

### Process and tooling
| ID | Sev | Gap | Planned |
|---|---|---|---|
| GAP-19 | Low | Windows line-ending warnings (`LF will be replaced by CRLF`) on every commit; no `.gitattributes`. | Add `* text=auto eol=lf` once, in a quiet moment (will touch many files). |
| GAP-20 | Low | `AI-Toolkit/` exists only locally (gitignored, per request). The APIMatic Context Plugin (T-08) is a separate item and is not yet configured. | Human + T-08. |
| GAP-21 | Low | No frontend exists. Every feature so far is API-only. | T-05 and the UI tasks. |
| GAP-22 | Medium | **The UI must render BRD Markdown without raw HTML.** The server escapes `<`, `>` and structure characters, but a viewer that enables raw HTML would reopen the hole. | Frontend (T-17): use a Markdown renderer with HTML disabled, or render from `content` JSON instead of the Markdown. |
| GAP-23 | Medium | **No way for a human to edit a BRD.** If the model keeps producing an invalid draft, or the sponsors want a wording change, the only route is regenerate or reject-and-reanswer. | Decide after the first real run; a lead-only edit that creates a new hash is straightforward. |
| GAP-24 | Low | `BRD_INVALID` (a dropped requirement, a MUST without a criterion) is detected after a successful model call, so each job retry makes another model call (up to 3) without telling the model what was wrong. | Feed the validation error back for one corrective retry, like the schema retry does. |
| GAP-25 | Low | The BRD schema is strict (sitemap paths lowercase `/a-b`, hints complete, 30 requirements max). A real model may break it often enough to fail the job. | Loosen after the first live Gemini run. Same family as GAP-02. |
| GAP-26 | Low | BRD Markdown is rendered with names from the database at generation time; renaming a user later changes nothing in the stored Markdown, and the hash covers only the JSON content. | Acceptable; note for the UI (prefer rendering names from ids). |
| GAP-27 | Low | No PDF export of the BRD (SHOULD). | Cut-order item 4. |
| GAP-28 | Medium | **One unresponsive sponsor blocks the whole project.** Approval must be unanimous, the voter set is frozen once the BRD is under review (D-026), and there is no way to remove or replace a sponsor. | Decide a policy before the demo scenario matters: lead can remove a non-responding sponsor (re-opening the vote), or a deadline-based quorum. Needs a SPEC decision. |
| GAP-29 | Low | A sponsor can reject repeatedly; each rejection forces a new BA round and a new BRD. There is no limit or cool-down. | Rate limit rejections per BRD version, or require the lead's confirmation after N rejections. |
| GAP-30 | Low | A rejection question uses `dimension = "BRD"`, which is not one of the ten rubric dimensions. The UI must show a null `dimension_name` as 'BRD feedback'; the scorer does not map it to a coverage gap. | Frontend note (T-16); acceptable. |
| GAP-31 | Low | No notification when a BRD is ready, approved or rejected; sponsors must open the app. | Email notifications are COULD (spec 4.3). |

---

## 2. Fixes (found and resolved)

| ID | When | What was wrong | Fix |
|---|---|---|---|
| FIX-01 | T-04 | `AI-Toolkit` was tracked as a git submodule-style link on the remote. | Untracked and added to `.gitignore`; remote `main` no longer has it. |
| FIX-02 | T-40 | SPEC 7.5.1 was circular: step idempotency keys derive from `plan_hash`, which covered the steps (including the keys). | `plan_hash` excludes keys, then keys are derived (D-021). |
| FIX-03 | T-26 | A retried plan with unchanged data would have the **same hash and the same unique idempotency keys** as the failed plan. My own test hid this behind a bare `Exception`. | `inputs.attempt` counter on retries (D-022); test now asserts the retry works. |
| FIX-04 | T-45 | A failed payout left its batch `PENDING`, which made Guardian G-12 ("a payout is already pending") block the retry. | Failed payout marks batch and item `FAILED`; G-02/G-12 accept `PAYOUT_FAILED` (D-024). |
| FIX-05 | T-42 | A failed AI call lost the link to its `agent_runs` row, so the audit trail could not show which call failed. | Errors carry `run_id`; the review stores it (D-025). |
| FIX-06 | T-42 | An always-true assertion (`... or True`) in a lifecycle test. | Replaced with a real check of the failed step's message and the project state. |
| FIX-07 | T-11 | A test-editing script written as Python-in-a-shell-heredoc corrupted a test file with a NUL byte; separately, oversized parametrized values blew past the Windows environment-variable limit via pytest test ids. | File deleted and rewritten with the Write tool; large params given short explicit ids. Rule recorded in AGENTS.md. |
| FIX-08 | T-13 | A brand-new project with no transcript was told "the BA Agent runs in REQUIREMENTS (it is DRAFT)", which does not say what to do. | The transcript check now comes first: "Upload the meeting transcript first". |
| FIX-09 | T-13 | The state-guard inside `answer_question` (old round / closed session) was untested; a mutation survived. | Added a defence-in-depth test. |
| FIX-10 | T-14 | `requirements.txt` pinned `pydantic==2.10.4` while `google-genai` had pulled the installed version to 2.14.3, so a fresh `pip install -r requirements.txt` (CI, a teammate) could fail to resolve. | Pin corrected to 2.14.3; verified by installing into a brand-new virtualenv and running all 437 tests. |
| FIX-11 | T-14 | `AGENTS.md` section 4 (Commands) was still the unfilled template, and the spec's GitHub Actions CI did not exist. | Commands filled with the verified ones; `.github/workflows/ci.yml` added (migrate + pytest). |
| FIX-12 | T-14 | **Security bug in my own BRD renderer, found by its tests:** the heading guard only escaped a single marker followed by a space, so an AI-drafted description containing `## Injected` (or `---`, a code fence, a table row, `2)` lists) would have become real structure in an approved document. | Any line that begins with a Markdown structure character now gets a leading backslash, in paragraphs and one-line fields; tests cover each marker and a full hostile draft. |
| FIX-13 | T-14 | The shared `World` test fixture pre-creates an approved BRD and a contract (for the money tests), which silently turned the first generated BRD into version 2. | BRD tests delete them in their fixture; STATUS notes the trap. |
| FIX-14 | T-14 | Mutation testing showed the hash tests only proved determinism, not that the hash is `sha256(canonical_json(content))` as the spec requires and other components must reproduce. | Added a test that recomputes the hash independently, including key-order independence. |
| FIX-15 | T-15 | Mutation testing found two approval rules enforced by only one layer in the tests: the 'decision counts only on the exact hash' filter and the service-level 'freelancers cannot vote' check (the router check masked it). | Added tests that force the situation (a stale-hash row; calling the service directly). |
| FIX-16 | T-15 | A vague assertion (`... == 409 or ... == 409`) in the full-loop test could not fail. | Pinned to `BRD_CLOSED`. My mutation script also crashed on a syntax-breaking mutant because it parsed pytest's last line; it now uses the process exit code. |

---

## 3. Mutation-test survivors that were judged harmless
These were deliberately-broken versions of the code that no test caught. Each was reviewed and is **not** a test gap.

| When | Mutant | Why harmless |
|---|---|---|
| T-12 | "Unknown member ids satisfy GT-5" (remove the `if m in known_member_ids` filter in the gate) | Extra unknown ids can never cover a missing sponsor, so the result is identical. The behaviour that matters (stripping unknown ids from stored requirements) is tested separately. |
