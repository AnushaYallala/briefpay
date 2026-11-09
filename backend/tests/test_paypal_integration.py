"""The real PayPalClient plugged into the real MoneyExecutor and Guardian rules, with only the SDK faked."""
import pytest
from paypalserversdk.models.balance_information import BalanceInformation
from paypalserversdk.models.balances_response import BalancesResponse
from paypalserversdk.models.captured_payment import CapturedPayment
from paypalserversdk.models.payment_authorization import PaymentAuthorization
from sqlalchemy import select

from app.models import MoneyPlanStep, Pledge
from app.services import guardian_rules as g
from app.services import plan_builder as pb
from app.services.money_executor import execute
from tests.factories import NOW, World
from tests.test_money_executor import approved_capture, approved_release, steps_of
from tests.test_paypal_client import FakeSDK, api_error, client, resp, usd


@pytest.fixture()
def w(db):
    return World(db)


def captured(cap_id, cents):
    return resp(CapturedPayment(status="COMPLETED", id=cap_id, amount=usd(pc_value(cents))))


def pc_value(cents):
    return f"{cents // 100}.{cents % 100:02d}"


# ---------------- executor + client ----------------

def test_the_executor_drives_the_real_client_with_the_step_keys_as_paypal_request_ids(w):
    plan = approved_capture(w)
    sdk = FakeSDK()
    sdk.payments.queue["capture_authorized_payment"] = [captured("CAP1", 15000), captured("CAP2", 15000), captured("CAP3", 10000)]
    execute(w.db, plan.id, client(sdk), now=NOW)
    sent = sdk.calls("capture_authorized_payment")
    pledges = list(w.db.scalars(select(Pledge).order_by(Pledge.id)))
    assert [o["authorization_id"] for o in sent] == [p.paypal_authorization_id for p in pledges]
    assert [o["paypal_request_id"] for o in sent] == [s.idempotency_key for s in steps_of(w, plan)]
    assert [(o["body"].amount.value, o["body"].amount.currency_code, o["body"].final_capture) for o in sent] == [
        ("150.00", "USD", True), ("150.00", "USD", True), ("100.00", "USD", True)]
    assert [s.paypal_ref for s in steps_of(w, plan)] == ["CAP1", "CAP2", "CAP3"] and {s.state for s in steps_of(w, plan)} == {"SENT"}


def test_a_transient_paypal_error_is_retried_with_the_very_same_request_id(w):
    plan = approved_capture(w)
    sdk = FakeSDK()
    sdk.payments.queue["capture_authorized_payment"] = [api_error(503), api_error(429), captured("CAP1", 15000), captured("CAP2", 15000), captured("CAP3", 10000)]
    execute(w.db, plan.id, client(sdk), now=NOW)
    keys = [o["paypal_request_id"] for o in sdk.calls("capture_authorized_payment")]
    assert len(keys) == 5 and len(set(keys[:3])) == 1, "the first step was tried three times under ONE idempotency key"
    assert {s.state for s in steps_of(w, plan)} == {"SENT"}


def test_a_declined_capture_fails_that_step_with_paypals_reason_and_debug_id(w):
    plan = approved_capture(w)
    sdk = FakeSDK()
    sdk.payments.queue["capture_authorized_payment"] = [
        api_error(422, {"name": "UNPROCESSABLE_ENTITY", "message": "x", "debug_id": "dbg-9", "details": [{"issue": "INSTRUMENT_DECLINED"}]}),
        captured("CAP2", 15000), captured("CAP3", 10000)]
    execute(w.db, plan.id, client(sdk), now=NOW)
    s1, s2, s3 = steps_of(w, plan)
    assert s1.state == "FAILED" and s1.error_json["debug_id"] == "dbg-9" and "INSTRUMENT_DECLINED" in s1.error_json["message"]
    assert s1.error_json["transient"] is False and s1.error_json["attempts"] == 1
    assert (s2.state, s3.state) == ("SENT", "SENT")


def test_a_release_plan_voids_every_hold_through_the_client(w):
    plan = approved_release(w)
    sdk = FakeSDK()
    sdk.payments.queue["void_payment"] = [None, None, None]
    execute(w.db, plan.id, client(sdk), now=NOW)
    sent = sdk.calls("void_payment")
    assert len(sent) == 3 and sdk.calls("capture_authorized_payment") == []
    assert [o["paypal_request_id"] for o in sent] == [s.idempotency_key for s in steps_of(w, plan)]


# ---------------- Guardian + client ----------------

def authorization(status, cents, aid):
    return resp(PaymentAuthorization(status=status, id=aid, amount=usd(pc_value(cents))))


def capture_plan_row(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    return pb.save_proposed(w.db, pb.build_capture_pledges(w.db, w.campaign.id, NOW), proposed_by="system")


def evaluate(w, plan, sdk, balance="1000.00"):
    if balance and not sdk.transaction_search.queue.get("search_balances"):          # G-08 asks PayPal for the platform balance
        sdk.transaction_search.queue["search_balances"] = [resp(BalancesResponse(balances=[BalanceInformation(currency="USD", total_balance=usd(balance), primary=True)]))]
    return g.evaluate(w.db, plan, now=NOW, reader=client(sdk))


def test_the_guardian_verifies_every_hold_against_paypals_records_through_the_client(w):
    plan = capture_plan_row(w)
    sdk = FakeSDK()
    # G-06 looks each hold up; G-09 looks them up again (cached per authorization id within one evaluation)
    sdk.payments.queue["get_authorized_payment"] = [authorization("CREATED", a, f"AUTH{i}") for i, a in enumerate((15000, 15000, 10000), start=1)]
    ev = evaluate(w, plan, sdk)
    assert ev.get("G-06").status == g.PASS and ev.get("G-06").paypal_verified and ev.get("G-09").status == g.PASS
    assert ev.get("G-08").status == g.PASS and ev.get("G-08").paypal_verified
    assert len(sdk.calls("get_authorized_payment")) == 3, "each authorization is fetched once per review"
    assert ev.decision == "ALLOW", [(r.id, r.detail) for r in ev.results if r.status != g.PASS]


@pytest.mark.parametrize("status", ["VOIDED", "CAPTURED", "PARTIALLY_CAPTURED", "DENIED", "PENDING", "UNKNOWN"])
def test_any_hold_status_other_than_created_blocks_the_capture(w, status):
    plan = capture_plan_row(w)
    sdk = FakeSDK()
    sdk.payments.queue["get_authorized_payment"] = [authorization(status, 15000, "AUTH1"), authorization("CREATED", 15000, "AUTH2"),
                                                    authorization("CREATED", 10000, "AUTH3")]
    ev = evaluate(w, plan, sdk)
    assert ev.get("G-06").status == g.FAIL and ev.decision == "BLOCK"


def test_a_hold_whose_amount_differs_at_paypal_blocks_the_capture(w):
    plan = capture_plan_row(w)
    sdk = FakeSDK()
    sdk.payments.queue["get_authorized_payment"] = [authorization("CREATED", 14999, "AUTH1"), authorization("CREATED", 15000, "AUTH2"),
                                                    authorization("CREATED", 10000, "AUTH3")]
    assert evaluate(w, plan, sdk).get("G-06").status == g.FAIL


@pytest.mark.parametrize("boom", [api_error(500), api_error(429), api_error(401)])
def test_when_paypal_cannot_answer_the_review_holds_instead_of_blocking_or_allowing(w, boom):
    plan = capture_plan_row(w)
    sdk = FakeSDK()
    sdk.payments.queue["get_authorized_payment"] = [boom]
    ev = evaluate(w, plan, sdk)
    assert ev.get("G-06").status == g.UNVERIFIED and [f["id"] for f in ev.soft_flags] == ["S-03"] and ev.decision == "HOLD"
