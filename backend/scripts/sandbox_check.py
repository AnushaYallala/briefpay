"""Sandbox verification: proves the PayPal assumptions the whole design rests on, against the REAL sandbox.

    cd backend
    .venv/Scripts/python scripts/sandbox_check.py --payout-to <freelancer-sandbox-email>

Needs PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET in backend/.env (or the environment). Uses ONLY sandbox money.
A hold must be approved by a buyer in a browser, so the script pauses twice and prints a link: open it, log in as a
sandbox *personal* account (country US), approve, come back and press Enter. It sends a few dollars at most.

It checks, and prints PASS / FAIL / NOTE for each:
  A-1  Payouts works for this app and a sandbox personal account can receive a payout        (A-9)
  A-2  the SDK calls our client makes actually work (orders, payments, balances)
  A-8  capturing LESS than the hold with final_capture=true releases the remainder; void works on a hold
       and a fully/finally captured hold cannot be voided
Paste the summary into docs/STATUS.md section 3 ("Verified facts") and tell the assistant any FAIL.
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.guardian_rules import PayPalUnavailable  # noqa: E402
from app.services.paypal_client import PayPalClient, PayPalConfigError  # noqa: E402
from app.services.paypal_io import PayPalWriteError  # noqa: E402

HOLD_CENTS, CAPTURE_CENTS, VOID_CENTS, REFUND_CENTS, PAYOUT_CENTS = 1000, 700, 500, 100, 100
APPROVE_URL = "https://www.sandbox.paypal.com/checkoutnow?token={order_id}"


class Report:
    def __init__(self, out):
        self.out, self.rows = out, []

    def add(self, tag, ok, what, detail=""):
        self.rows.append((tag, "PASS" if ok else "FAIL", what, detail))
        self.out(f"  [{'PASS' if ok else 'FAIL'}] {tag}: {what}" + (f"  ({detail})" if detail else ""))

    def note(self, tag, what):
        self.rows.append((tag, "NOTE", what, ""))
        self.out(f"  [NOTE] {tag}: {what}")

    @property
    def failed(self):
        return any(r[1] == "FAIL" for r in self.rows)


def attempt(report, tag, what, fn):
    """Run one PayPal call; a PayPal error becomes a FAIL line with its debug id instead of a crash."""
    try:
        return fn()
    except (PayPalWriteError, PayPalUnavailable) as e:
        report.add(tag, False, what, f"{e} debug_id={getattr(e, 'debug_id', None)}")
        return None


def approved_hold(c, report, input_fn, out, cents, label):
    """Create an AUTHORIZE order, have a human approve it, authorize it. Returns the authorization dict or None."""
    order = attempt(report, "A-2", f"create an AUTHORIZE order for the {label} hold", lambda: c.create_authorize_order(
        cents, "USD", f"sandbox-check:{label}", f"BriefPay sandbox check ({label})", f"sbx-order-{label}-{uuid.uuid4().hex[:8]}"))
    if not order:
        return None
    report.add("A-2", order["status"] in ("CREATED", "PAYER_ACTION_REQUIRED"), f"order {order['id']} is waiting for the buyer", order["status"])
    out(f"\n  Open this link, log in as a sandbox PERSONAL buyer (US), approve, then come back:\n    {APPROVE_URL.format(order_id=order['id'])}")
    input_fn("  Press Enter once you approved... ")
    res = attempt(report, "A-2", f"authorize the approved {label} order", lambda: c.authorize_order(order["id"], f"sbx-authz-{label}-{uuid.uuid4().hex[:8]}"))
    if not res or not res["authorization"]:
        report.add("A-2", False, f"the {label} order produced a hold", "no authorization in the response (was it approved?)")
        return None
    a = res["authorization"]
    report.add("A-2", a["status"] == "CREATED" and a["amount_cents"] == cents, f"hold {a['id']} is CREATED for ${cents / 100:.2f}",
               f"status={a['status']} amount_cents={a['amount_cents']} expires={a['expiration_time']} payer={res['payer_email']}")
    return a


def check_partial_capture(c, report, input_fn, out):
    out("\nA-8: capture LESS than the hold with final_capture=true")
    a = approved_hold(c, report, input_fn, out, HOLD_CENTS, "capture")
    if not a:
        return
    cap = attempt(report, "A-8", f"capture ${CAPTURE_CENTS / 100:.2f} of the ${HOLD_CENTS / 100:.2f} hold with final_capture", lambda: c.capture_authorization(
        a["id"], CAPTURE_CENTS, "USD", True, f"sbx-cap-{uuid.uuid4().hex[:8]}"))
    if not cap:
        return
    report.add("A-8", cap["status"] in ("COMPLETED", "PENDING"), "the partial capture was accepted", f"id={cap['id']} status={cap['status']}")
    after = attempt(report, "A-8", "read the hold back", lambda: c.get_authorization(a["id"]))
    if after:
        report.add("A-8", after.status == "CAPTURED", "after a FINAL partial capture the hold is closed (remainder released)", f"hold status={after.status}")
    try:  # PayPal must refuse to void a hold that has been (finally) captured
        c.void_authorization(a["id"], f"sbx-void2-{uuid.uuid4().hex[:8]}")
        report.add("A-8", False, "voiding a captured hold must be refused", "PayPal accepted it")
    except PayPalWriteError as e:
        report.add("A-8", not e.transient, "voiding a captured hold is refused by PayPal", str(e))
    got = attempt(report, "A-2", "read the capture back", lambda: c.get_capture(cap["id"]))
    if got:
        report.add("A-2", got.amount_cents == CAPTURE_CENTS, f"capture {cap['id']} reads back as ${got.amount_cents / 100:.2f}", got.status)
    ref = attempt(report, "A-2", f"refund ${REFUND_CENTS / 100:.2f} of that capture", lambda: c.refund_capture(cap["id"], REFUND_CENTS, "USD", f"sbx-ref-{uuid.uuid4().hex[:8]}"))
    if ref:
        report.add("A-2", ref["status"] in ("COMPLETED", "PENDING"), "the refund was accepted", f"id={ref['id']} status={ref['status']}")


def check_void(c, report, input_fn, out):
    out("\nA-8: void a hold")
    a = approved_hold(c, report, input_fn, out, VOID_CENTS, "void")
    if not a:
        return
    v = attempt(report, "A-8", "void the hold", lambda: c.void_authorization(a["id"], f"sbx-void-{uuid.uuid4().hex[:8]}"))
    if v:
        after = attempt(report, "A-8", "read the hold back", lambda: c.get_authorization(a["id"]))
        if after:
            report.add("A-8", after.status == "VOIDED", "a voided hold reads back as VOIDED", f"status={after.status}")


def check_payout(c, report, email, out, sleep=time.sleep, tries=12):
    out("\nA-1 / A-9: Payouts to a sandbox personal account")
    batch = f"sbx-check-{uuid.uuid4().hex[:10]}"
    res = attempt(report, "A-1", f"send a ${PAYOUT_CENTS / 100:.2f} payout to {email}", lambda: c.create_payout_batch(
        batch, [{"receiver": email, "amount_cents": PAYOUT_CENTS, "sender_item_id": "1", "note": "BriefPay sandbox check"}],
        "USD", "BriefPay sandbox check", f"sbx-pay-{uuid.uuid4().hex[:8]}"))
    if not res:
        report.note("A-1", "If this is a permissions error, enable Payouts on the app (Developer Dashboard -> app -> Features).")
        return
    report.add("A-1", bool(res["id"]), "PayPal accepted the payout batch", f"batch={res['id']} status={res['status']}")
    for _ in range(tries):
        data = attempt(report, "A-1", "poll the batch", lambda: c.get_payout_batch(res["id"]))
        if data and data["items"] and data["items"][0]["transaction_status"] not in ("PENDING", "ONHOLD", None):
            st = data["items"][0]["transaction_status"]
            report.add("A-9", st == "SUCCESS", "the recipient item reached a final status", f"item status={st} batch={data['batch_status']}")
            return
        sleep(5)
    report.note("A-9", "the item was still PENDING after about a minute; check the recipient in the sandbox and rerun the poll later")


def main(argv=None, *, client=None, input_fn=input, out=print, sleep=time.sleep) -> int:
    ap = argparse.ArgumentParser(description="Verify the PayPal sandbox assumptions (uses sandbox money only).")
    ap.add_argument("--payout-to", help="sandbox email of the freelancer account (Arjun) to receive a $1.00 payout")
    ap.add_argument("--skip-holds", action="store_true", help="skip the two interactive hold checks")
    ap.add_argument("--skip-payout", action="store_true")
    args = ap.parse_args(argv)

    if client is None:
        from app.config import get_settings
        s = get_settings()
        if not (s.paypal_client_id and s.paypal_client_secret):
            out("PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are not set. Put them in backend/.env (see .env.example).")
            return 2
        try:
            client = PayPalClient(s.paypal_client_id, s.paypal_client_secret, environment=s.paypal_env)
        except PayPalConfigError as e:
            out(f"Configuration problem: {e}")
            return 2

    report = Report(out)
    out("PayPal sandbox check (sandbox money only)\n\nCredentials and balance")
    try:
        bal = client.platform_balance_cents()
        if bal is None:
            report.note("A-2", "balances are unavailable: enable Transaction search on the app (Features) so Guardian G-08 can run")
        else:
            report.add("A-2", True, "the platform balance can be read (Transaction search is enabled)", f"${bal / 100:,.2f}")
    except PayPalUnavailable as e:
        report.add("A-2", False, "read the platform balance", str(e))
    if not args.skip_holds:
        check_partial_capture(client, report, input_fn, out)
        check_void(client, report, input_fn, out)
    if args.payout_to and not args.skip_payout:
        check_payout(client, report, args.payout_to, out, sleep)
    elif not args.skip_payout:
        report.note("A-1", "payout not tested: rerun with --payout-to <freelancer sandbox email>")

    out("\nSummary (paste into docs/STATUS.md section 3):")
    for tag, verdict, what, detail in report.rows:
        out(f"  {tag:<4} {verdict:<4} {what}" + (f" [{detail}]" if detail else ""))
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
