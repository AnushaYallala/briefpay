"""The sandbox script's logic, run end to end against fakes (so the real run is not the first time it executes)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from paypalserversdk.models.balance_information import BalanceInformation
from paypalserversdk.models.balances_response import BalancesResponse
from paypalserversdk.models.captured_payment import CapturedPayment
from paypalserversdk.models.order import Order
from paypalserversdk.models.payment_authorization import PaymentAuthorization
from paypalserversdk.models.refund import Refund

from app.config import get_settings
from tests.test_paypal_client import FakeSDK, Http, api_error, authorized_order, client, resp, usd

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "sandbox_check.py"
spec = importlib.util.spec_from_file_location("sandbox_check", SCRIPT)
sandbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandbox)


class Run:
    """Collects the script's output and the prompts it showed; answers every prompt with Enter."""

    def __init__(self):
        self.lines, self.prompts = [], []

    def out(self, text=""):
        self.lines.append(str(text))

    def input(self, prompt=""):
        self.prompts.append(prompt)
        return ""

    @property
    def text(self):
        return "\n".join(self.lines)


def happy_sdk(*, hold_after_capture="CAPTURED", void_of_captured=None):
    sdk = FakeSDK()
    sdk.transaction_search.queue["search_balances"] = [resp(BalancesResponse(balances=[BalanceInformation(currency="USD", total_balance=usd("5000.00"), primary=True)]))]
    sdk.orders.queue["create_order"] = [resp(Order(id="ORD-CAP", status="CREATED")), resp(Order(id="ORD-VOID", status="CREATED"))]
    sdk.orders.queue["authorize_order"] = [resp(authorized_order(value="10.00")), resp(authorized_order(value="5.00"))]
    sdk.payments.queue["capture_authorized_payment"] = [resp(CapturedPayment(status="COMPLETED", id="CAP1", amount=usd("7.00")))]
    sdk.payments.queue["get_authorized_payment"] = [resp(PaymentAuthorization(status=hold_after_capture, id="AUTH77", amount=usd("10.00"))),
                                                    resp(PaymentAuthorization(status="VOIDED", id="AUTH77", amount=usd("5.00")))]
    sdk.payments.queue["void_payment"] = [void_of_captured if void_of_captured is not None else api_error(422, {"name": "X", "message": "AUTHORIZATION_ALREADY_CAPTURED", "debug_id": "d"}), None]
    sdk.payments.queue["get_captured_payment"] = [resp(CapturedPayment(status="COMPLETED", id="CAP1", amount=usd("7.00")))]
    sdk.payments.queue["refund_captured_payment"] = [resp(Refund(status="COMPLETED", id="REF1", amount=usd("1.00")))]
    return sdk


def payout_http(item_status="SUCCESS", create=None):
    batch = {"batch_header": {"batch_status": "SUCCESS"}, "items": [
        {"payout_item_id": "PI1", "transaction_status": item_status, "payout_item": {"sender_item_id": "1", "receiver": "arjun@sandbox.example.com", "amount": {"value": "1.00"}}}]}
    return Http({"POST /v1/payments/payouts": create or (lambda r: httpx.Response(201, json={"batch_header": {"payout_batch_id": "B1", "batch_status": "PENDING"}})),
                 "GET /v1/payments/payouts/B1": lambda r: httpx.Response(200, json=batch)})


def run(sdk=None, http=None, argv=("--payout-to", "arjun@sandbox.example.com")):
    r = Run()
    code = sandbox.main(list(argv), client=client(sdk or happy_sdk(), http or payout_http()), input_fn=r.input, out=r.out, sleep=lambda s: None)
    return code, r


# ---------------- starting up ----------------

def test_without_credentials_it_explains_what_to_do_and_exits_with_2(monkeypatch):
    monkeypatch.setattr(get_settings(), "paypal_client_id", "")
    monkeypatch.setattr(get_settings(), "paypal_client_secret", "")
    r = Run()
    assert sandbox.main([], out=r.out, input_fn=r.input) == 2
    assert "PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are not set" in r.text and r.prompts == []


def test_a_live_environment_is_refused(monkeypatch):
    monkeypatch.setattr(get_settings(), "paypal_client_id", "id")
    monkeypatch.setattr(get_settings(), "paypal_client_secret", "secret")
    monkeypatch.setattr(get_settings(), "paypal_env", "live")
    r = Run()
    assert sandbox.main([], out=r.out, input_fn=r.input) == 2 and "sandbox" in r.text


def test_the_script_runs_standalone_from_the_command_line():
    help_run = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, cwd=BACKEND)
    assert help_run.returncode == 0 and "--payout-to" in help_run.stdout
    env = {"PATH": "", "PAYPAL_CLIENT_ID": "", "PAYPAL_CLIENT_SECRET": "", "SYSTEMROOT": "C:\\Windows"}
    bare = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=BACKEND, env=env)
    assert bare.returncode == 2 and "PAYPAL_CLIENT_ID" in bare.stdout


# ---------------- a good run ----------------

def test_a_good_run_passes_every_check_and_asks_the_human_to_approve_twice():
    code, r = run()
    assert code == 0, r.text
    assert len(r.prompts) == 2
    assert "https://www.sandbox.paypal.com/checkoutnow?token=ORD-CAP" in r.text and "token=ORD-VOID" in r.text
    summary = r.text.split("Summary")[1]
    for must in ("the platform balance can be read", "after a FINAL partial capture the hold is closed", "voiding a captured hold is refused by PayPal",
                 "a voided hold reads back as VOIDED", "PayPal accepted the payout batch", "the recipient item reached a final status"):
        assert any(must in line and "PASS" in line for line in summary.splitlines()), f"missing PASS for: {must}\n{summary}"
    assert "FAIL" not in summary and "$5,000.00" in summary


def test_the_script_sends_the_amounts_it_promises():
    sdk = happy_sdk()
    code, _ = run(sdk)
    assert code == 0
    assert [o["body"].purchase_units[0].amount.value for o in sdk.calls("create_order")] == ["10.00", "5.00"]
    [cap] = sdk.calls("capture_authorized_payment")
    assert cap["body"].amount.value == "7.00" and cap["body"].final_capture is True
    assert sdk.calls("refund_captured_payment")[0]["body"].amount.value == "1.00"


def test_no_secret_is_ever_printed():
    _, r = run()
    assert "client-secret" not in r.text and "client-id" not in r.text


# ---------------- what a failing assumption looks like ----------------

def test_if_the_remainder_is_not_released_the_run_fails_loudly():
    """The key assumption A-8: a final partial capture must close the hold. If PayPal disagrees we must know."""
    code, r = run(happy_sdk(hold_after_capture="PARTIALLY_CAPTURED"))
    assert code == 1
    assert any("FAIL" in ln and "remainder released" in ln and "PARTIALLY_CAPTURED" in ln for ln in r.lines)


def test_if_paypal_lets_a_captured_hold_be_voided_the_run_fails():
    code, r = run(_sdk_allowing_void_of_captured())
    assert code == 1 and any("voiding a captured hold must be refused" in ln and "FAIL" in ln for ln in r.lines)


def _sdk_allowing_void_of_captured():
    sdk = happy_sdk()
    sdk.payments.queue["void_payment"] = [None, None]                      # PayPal accepts both voids
    return sdk


def test_an_order_that_was_never_approved_is_a_clear_failure_and_the_rest_continues():
    sdk = happy_sdk()
    from paypalserversdk.models.payment_collection import PaymentCollection
    from paypalserversdk.models.purchase_unit import PurchaseUnit
    sdk.orders.queue["authorize_order"] = [resp(Order(id="ORD-CAP", status="PAYER_ACTION_REQUIRED", purchase_units=[PurchaseUnit(payments=PaymentCollection())])),
                                           resp(authorized_order(value="5.00"))]
    sdk.payments.queue["get_authorized_payment"] = [resp(PaymentAuthorization(status="VOIDED", id="AUTH77", amount=usd("5.00")))]   # only the void check reads
    sdk.payments.queue["void_payment"] = [None]                                                                                       # ... and voids
    code, r = run(sdk)
    assert code == 1 and any("produced a hold" in ln and "FAIL" in ln and "was it approved" in ln for ln in r.lines)
    assert sdk.calls("capture_authorized_payment") == [], "no capture is attempted without a hold"
    assert any("a voided hold reads back as VOIDED" in ln and "PASS" in ln for ln in r.lines), "the void check still ran"


def test_a_payout_permission_error_tells_the_human_what_to_enable():
    http = payout_http(create=lambda r: httpx.Response(403, json={"name": "NOT_AUTHORIZED", "message": "Authorization failed", "debug_id": "dbg-pay"}))
    code, r = run(http=http)
    assert code == 1 and any("send a $1.00 payout" in ln and "FAIL" in ln and "dbg-pay" in ln for ln in r.lines)
    assert any("enable Payouts" in ln and "NOTE" in ln for ln in r.lines)


def test_a_pending_payout_is_a_note_not_a_failure():
    code, r = run(http=payout_http(item_status="PENDING"))
    assert code == 0 and any("still PENDING" in ln and "NOTE" in ln for ln in r.lines)


def test_balances_unavailable_is_a_note_that_says_how_to_enable_transaction_search():
    sdk = happy_sdk()
    sdk.transaction_search.queue["search_balances"] = [api_error(403)]
    code, r = run(sdk)
    assert code == 0 and any("Transaction search" in ln and "NOTE" in ln for ln in r.lines)


# ---------------- flags ----------------

def test_flags_skip_parts_and_the_payout_needs_an_address():
    sdk = FakeSDK()
    sdk.transaction_search.queue["search_balances"] = [resp(BalancesResponse(balances=[BalanceInformation(currency="USD", total_balance=usd("1.00"), primary=True)]))]
    code, r = run(sdk, argv=("--skip-holds",))
    assert code == 0 and r.prompts == [] and any("rerun with --payout-to" in ln for ln in r.lines)
    assert sdk.calls("create_order") == []
    code, r = run(happy_sdk(), argv=("--skip-payout",))
    assert code == 0 and not any("payout" in ln.lower() and "PASS" in ln for ln in r.lines)
