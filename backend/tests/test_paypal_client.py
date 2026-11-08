"""PayPalClient against fake SDK objects built from the REAL SDK model classes (so a wrong field name here would fail)."""
import json
from types import SimpleNamespace

import httpx
import pytest
from paypalserversdk.exceptions.api_exception import ApiException
from paypalserversdk.models.authorization import Authorization
from paypalserversdk.models.balance_information import BalanceInformation
from paypalserversdk.models.balances_response import BalancesResponse
from paypalserversdk.models.capture_request import CaptureRequest
from paypalserversdk.models.captured_payment import CapturedPayment
from paypalserversdk.models.money import Money
from paypalserversdk.models.order import Order
from paypalserversdk.models.payer import Payer
from paypalserversdk.models.payment_authorization import PaymentAuthorization
from paypalserversdk.models.payment_collection import PaymentCollection
from paypalserversdk.models.purchase_unit import PurchaseUnit
from paypalserversdk.models.refund import Refund
from paypalserversdk.models.refund_request import RefundRequest

from app.services import paypal_client as pc
from app.services import paypal_io
from app.services.guardian_rules import PayPalUnavailable
from app.services.paypal_io import PayPalWriteError


def usd(value):
    return Money(currency_code="USD", value=value)


def resp(body):
    return SimpleNamespace(body=body, status_code=200)


def api_error(status, body=None):
    text = json.dumps(body if body is not None else {"name": "ERR", "message": "boom", "debug_id": "dbg123"})
    return ApiException(f"HTTP {status}", SimpleNamespace(status_code=status, text=text))


class Group:
    """One SDK controller: records every call; `queue[name]` holds results (or exceptions) to return in turn."""

    def __init__(self, names, log):
        self.log, self.queue = log, {}
        for n in names:
            setattr(self, n, self._make(n))

    def _make(self, name):
        def call(options):
            self.log.append((name, options))
            q = self.queue.get(name, [])
            out = q.pop(0) if q else None
            if isinstance(out, Exception):
                raise out
            return out
        return call


class FakeSDK:
    def __init__(self):
        self.log = []
        self.payments = Group(["get_authorized_payment", "get_captured_payment", "capture_authorized_payment", "void_payment", "refund_captured_payment"], self.log)
        self.orders = Group(["create_order", "authorize_order", "get_order"], self.log)
        self.transaction_search = Group(["search_balances"], self.log)

    def calls(self, name):
        return [o for n, o in self.log if n == name]


class Http:
    """httpx.Client over a MockTransport; `routes` maps 'METHOD path' to a function(request) -> httpx.Response."""

    def __init__(self, routes):
        self.requests = []
        self.routes = routes
        self.client = httpx.Client(base_url=pc.SANDBOX_API, transport=httpx.MockTransport(self.handle))

    def handle(self, request):
        self.requests.append(request)
        key = f"{request.method} {request.url.path}"
        if key == "POST /v1/oauth2/token" and key not in self.routes:
            return httpx.Response(200, json={"access_token": "TOKEN", "expires_in": 3600})
        return self.routes[key](request)

    def to(self, path, method="POST"):
        return [r for r in self.requests if r.url.path == path and r.method == method]


def _no_network(request):
    pytest.fail(f"unexpected real HTTP call: {request.method} {request.url}")


NO_NETWORK = httpx.Client(base_url=pc.SANDBOX_API, transport=httpx.MockTransport(_no_network))   # shared: building a client loads an SSL context


def client(sdk=None, http=None, clock=None):
    return pc.PayPalClient("client-id", "client-secret", sdk=sdk or FakeSDK(), http=(http.client if http else NO_NETWORK),
                           clock=clock or (lambda: 0.0))


# ---------------- construction, secrets, money ----------------

def test_only_the_sandbox_and_real_credentials_are_accepted():
    with pytest.raises(pc.PayPalConfigError):
        pc.PayPalClient("id", "secret", environment="live", sdk=object())
    for cid, sec in (("", "s"), ("i", ""), ("", "")):
        with pytest.raises(pc.PayPalConfigError):
            pc.PayPalClient(cid, sec, sdk=object())


def test_the_credentials_never_appear_in_repr_or_errors():
    c = client()
    assert "client-secret" not in repr(c) and "client-id" not in repr(c) and repr(c) == "PayPalClient(sandbox)"


@pytest.mark.parametrize("cents,text", [(0, "0.00"), (5, "0.05"), (100, "1.00"), (40000, "400.00"), (40001, "400.01"), (999999, "9999.99")])
def test_cents_become_exact_strings_and_back(cents, text):
    assert pc.cents_to_value(cents) == text and pc.value_to_cents(text) == cents


@pytest.mark.parametrize("bad", [-1, 1.5, True, "5", None])
def test_cents_to_value_refuses_anything_but_non_negative_integers(bad):
    with pytest.raises(ValueError):
        pc.cents_to_value(bad)


@pytest.mark.parametrize("bad", ["1.234", "-1", "1e2", "abc", None, "", " 1", "1 ", "400.00\n", "1,000.00", ".5", "+1"])
def test_value_to_cents_accepts_only_plain_two_decimal_amounts(bad):
    with pytest.raises(ValueError):
        pc.value_to_cents(bad)
    assert pc.value_to_cents("150") == 15000 and pc.value_to_cents("1234.5") == 123450


# ---------------- reader ----------------

def test_get_authorization_uses_real_model_fields():
    sdk = FakeSDK()
    sdk.payments.queue["get_authorized_payment"] = [resp(PaymentAuthorization(status="CREATED", id="AUTH1", amount=usd("150.00")))]
    got = client(sdk).get_authorization("AUTH1")
    assert (got.status, got.amount_cents, got.currency) == ("CREATED", 15000, "USD")
    assert sdk.calls("get_authorized_payment") == [{"authorization_id": "AUTH1"}]


def test_get_capture_uses_real_model_fields():
    sdk = FakeSDK()
    sdk.payments.queue["get_captured_payment"] = [resp(CapturedPayment(status="COMPLETED", id="CAP1", amount=usd("100.00")))]
    got = client(sdk).get_capture("CAP1")
    assert (got.status, got.amount_cents) == ("COMPLETED", 10000)


def test_a_missing_object_is_none_but_any_other_failure_is_unavailable():
    for method, name in (("get_authorization", "get_authorized_payment"), ("get_capture", "get_captured_payment")):
        sdk = FakeSDK()
        sdk.payments.queue[name] = [api_error(404)]
        assert getattr(client(sdk), method)("X") is None
        for status in (400, 401, 403, 429, 500, 503):
            sdk.payments.queue[name] = [api_error(status)]
            with pytest.raises(PayPalUnavailable):
                getattr(client(sdk), method)("X")
        sdk.payments.queue[name] = [httpx.ConnectError("down")]
        with pytest.raises(PayPalUnavailable):
            getattr(client(sdk), method)("X")


def test_platform_balance_picks_the_primary_usd_balance():
    sdk = FakeSDK()
    sdk.transaction_search.queue["search_balances"] = [resp(BalancesResponse(balances=[
        BalanceInformation(currency="USD", total_balance=usd("11.00"), primary=False),
        BalanceInformation(currency="USD", total_balance=usd("1234.56"), primary=True)]))]
    assert client(sdk).platform_balance_cents() == 123456
    assert sdk.calls("search_balances") == [{"currency_code": "USD"}]


def test_balance_is_none_when_search_is_unavailable_to_the_app_and_unavailable_when_paypal_is_down():
    sdk = FakeSDK()
    sdk.transaction_search.queue["search_balances"] = [resp(BalancesResponse(balances=[BalanceInformation(currency="EUR", total_balance=usd("5.00"))])),
                                                       resp(BalancesResponse(balances=[])), resp(BalancesResponse())]
    assert [client(sdk).platform_balance_cents() for _ in range(3)] == [None, None, None]
    for status in (400, 401, 403, 404):
        sdk.transaction_search.queue["search_balances"] = [api_error(status)]
        assert client(sdk).platform_balance_cents() is None
    for boom in (api_error(500), api_error(429), httpx.ReadTimeout("slow")):
        sdk.transaction_search.queue["search_balances"] = [boom]
        with pytest.raises(PayPalUnavailable):
            client(sdk).platform_balance_cents()


# ---------------- writer: SDK calls ----------------

def test_capture_sends_the_step_key_exact_amount_and_final_capture():
    sdk = FakeSDK()
    sdk.payments.queue["capture_authorized_payment"] = [resp(CapturedPayment(status="COMPLETED", id="CAP9", amount=usd("142.86")))]
    out = client(sdk).capture_authorization("AUTH1", 14286, "USD", True, "abc123-1")
    assert out == {"id": "CAP9", "status": "COMPLETED", "amount_cents": 14286}
    [opts] = sdk.calls("capture_authorized_payment")
    assert opts["authorization_id"] == "AUTH1" and opts["paypal_request_id"] == "abc123-1"
    body = opts["body"]
    assert isinstance(body, CaptureRequest) and body.final_capture is True
    assert (body.amount.currency_code, body.amount.value) == ("USD", "142.86")


def test_capture_can_be_a_non_final_capture():
    sdk = FakeSDK()
    sdk.payments.queue["capture_authorized_payment"] = [resp(CapturedPayment(status="PENDING", id="C", amount=usd("1.00")))]
    client(sdk).capture_authorization("A", 100, "USD", False, "k")
    assert sdk.calls("capture_authorized_payment")[0]["body"].final_capture is False


def test_void_and_refund_send_their_keys_and_amounts():
    sdk = FakeSDK()
    sdk.payments.queue["void_payment"] = [None]
    sdk.payments.queue["refund_captured_payment"] = [resp(Refund(status="COMPLETED", id="REF1", amount=usd("50.00")))]
    c = client(sdk)
    assert c.void_authorization("AUTH2", "key-void") == {"id": "AUTH2", "status": "VOIDED"}
    assert sdk.calls("void_payment") == [{"authorization_id": "AUTH2", "paypal_request_id": "key-void"}]
    assert c.refund_capture("CAP1", 5000, "USD", "key-refund") == {"id": "REF1", "status": "COMPLETED", "amount_cents": 5000}
    [r] = sdk.calls("refund_captured_payment")
    assert r["capture_id"] == "CAP1" and r["paypal_request_id"] == "key-refund"
    assert isinstance(r["body"], RefundRequest) and (r["body"].amount.value, r["body"].amount.currency_code) == ("50.00", "USD")


@pytest.mark.parametrize("call", [
    lambda c: c.capture_authorization("A", 100, "USD", True, "k"), lambda c: c.void_authorization("A", "k"),
    lambda c: c.refund_capture("C", 100, "USD", "k")])
def test_write_errors_are_classified_transient_or_rejected_with_the_debug_id(call):
    names = {0: "capture_authorized_payment", 1: "void_payment", 2: "refund_captured_payment"}
    for status, transient in ((429, True), (500, True), (503, True), (400, False), (401, False), (403, False), (404, False), (422, False)):
        sdk = FakeSDK()
        for n in names.values():
            sdk.payments.queue[n] = [api_error(status, {"name": "UNPROCESSABLE", "message": "nope", "debug_id": "dbg-77",
                                                         "details": [{"issue": "INSTRUMENT_DECLINED"}]})]
        with pytest.raises(PayPalWriteError) as e:
            call(client(sdk))
        assert e.value.transient is transient and e.value.debug_id == "dbg-77" and f"PayPal {status}" in str(e.value)
        assert "INSTRUMENT_DECLINED" in str(e.value)
    for boom in (httpx.ConnectError("down"), httpx.ReadTimeout("slow"), TimeoutError("t"), ConnectionError("c")):
        sdk = FakeSDK()
        for n in names.values():
            sdk.payments.queue[n] = [boom]
        with pytest.raises(PayPalWriteError) as e:
            call(client(sdk))
        assert e.value.transient is True and e.value.debug_id is None


def test_a_non_json_error_body_still_gives_a_clean_error():
    sdk = FakeSDK()
    sdk.payments.queue["void_payment"] = [ApiException("Bad Gateway", SimpleNamespace(status_code=502, text="<html>oops</html>"))]
    with pytest.raises(PayPalWriteError) as e:
        client(sdk).void_authorization("A", "k")
    assert e.value.transient is True and e.value.debug_id is None and "502" in str(e.value)


@pytest.mark.parametrize("cents,currency", [(-1, "USD"), (10, "EUR"), (10.5, "USD")])
def test_an_invalid_amount_or_currency_is_refused_before_anything_is_sent(cents, currency):
    sdk = FakeSDK()
    with pytest.raises(PayPalWriteError) as e:
        client(sdk).capture_authorization("A", cents, currency, True, "k")
    assert e.value.transient is False and sdk.log == []


# ---------------- Payouts and webhooks over httpx ----------------

def payout_ok(request):
    return httpx.Response(201, json={"batch_header": {"payout_batch_id": "BATCH1", "batch_status": "PENDING"}})


def test_a_payout_batch_is_built_exactly_and_sent_with_the_request_id():
    http = Http({"POST /v1/payments/payouts": payout_ok})
    out = client(http=http).create_payout_batch(
        "briefpay-1-2-1", [{"receiver": "arjun@sandbox.example.com", "amount_cents": 40000, "sender_item_id": "17", "note": "BriefPay: Velugu"}],
        "USD", "BriefPay payout: Velugu Cove", "plankey-1")
    assert out == {"id": "BATCH1", "status": "PENDING"}
    [req] = http.to("/v1/payments/payouts")
    assert req.headers["authorization"] == "Bearer TOKEN" and req.headers["paypal-request-id"] == "plankey-1"
    body = json.loads(req.content)
    assert body["sender_batch_header"]["sender_batch_id"] == "briefpay-1-2-1"
    assert body["items"] == [{"recipient_type": "EMAIL", "receiver": "arjun@sandbox.example.com", "amount": {"value": "400.00", "currency": "USD"},
                              "note": "BriefPay: Velugu", "sender_item_id": "17"}]


def test_the_token_is_requested_once_cached_and_refreshed_after_it_expires():
    now = [0.0]
    http = Http({"POST /v1/payments/payouts": payout_ok})
    c = client(http=http, clock=lambda: now[0])
    item = [{"receiver": "a@b.co", "amount_cents": 100, "sender_item_id": "1"}]
    c.create_payout_batch("b1", item, "USD", "s", "k1")
    c.create_payout_batch("b2", item, "USD", "s", "k2")
    assert len(http.to("/v1/oauth2/token")) == 1
    token_req = http.to("/v1/oauth2/token")[0]
    assert token_req.headers["authorization"].startswith("Basic ") and b"grant_type=client_credentials" in token_req.content
    now[0] = 3600.0                                                      # past expires_in minus the 60 s margin
    c.create_payout_batch("b3", item, "USD", "s", "k3")
    assert len(http.to("/v1/oauth2/token")) == 2


def test_payout_errors_are_classified_and_credential_failures_are_not_retried():
    def fail(status, body=None):
        return lambda r: httpx.Response(status, json=body or {"name": "X", "message": "no", "debug_id": "d9"})
    item = [{"receiver": "a@b.co", "amount_cents": 100, "sender_item_id": "1"}]
    for status, transient in ((400, False), (403, False), (422, False), (429, True), (500, True), (503, True)):
        http = Http({"POST /v1/payments/payouts": fail(status)})
        with pytest.raises(PayPalWriteError) as e:
            client(http=http).create_payout_batch("b", item, "USD", "s", "k")
        assert e.value.transient is transient and e.value.debug_id == "d9"
    bad_token = Http({"POST /v1/oauth2/token": lambda r: httpx.Response(401, json={"error": "invalid_client"}), "POST /v1/payments/payouts": payout_ok})
    with pytest.raises(PayPalWriteError) as e:
        client(http=bad_token).create_payout_batch("b", item, "USD", "s", "k")
    assert e.value.transient is False and "credentials" in str(e.value) and not bad_token.to("/v1/payments/payouts")

    def refuse(request):
        raise httpx.ConnectError("down")
    with pytest.raises(PayPalWriteError) as e:
        client(http=Http({"POST /v1/payments/payouts": refuse})).create_payout_batch("b", item, "USD", "s", "k")
    assert e.value.transient is True


def test_only_usd_payouts_are_sent():
    http = Http({"POST /v1/payments/payouts": payout_ok})
    with pytest.raises(PayPalWriteError):
        client(http=http).create_payout_batch("b", [{"receiver": "a@b.co", "amount_cents": 1, "sender_item_id": "1"}], "EUR", "s", "k")
    assert http.to("/v1/payments/payouts") == []


def test_payout_batch_status_is_parsed_for_the_poll_fallback():
    data = {"batch_header": {"batch_status": "SUCCESS"}, "items": [
        {"payout_item_id": "PI1", "transaction_status": "SUCCESS", "payout_item": {"sender_item_id": "17", "receiver": "arjun@x.co", "amount": {"value": "400.00"}}}]}
    http = Http({"GET /v1/payments/payouts/BATCH1": lambda r: httpx.Response(200, json=data)})
    assert client(http=http).get_payout_batch("BATCH1") == {"batch_status": "SUCCESS", "items": [
        {"payout_item_id": "PI1", "transaction_status": "SUCCESS", "sender_item_id": "17", "receiver": "arjun@x.co", "amount_cents": 40000}]}
    for status in (404, 500):
        down = Http({"GET /v1/payments/payouts/B": lambda r, s=status: httpx.Response(s, json={"message": "x"})})
        with pytest.raises(PayPalUnavailable):
            client(http=down).get_payout_batch("B")


WEBHOOK_HEADERS = {"PayPal-Transmission-Id": "tid", "PayPal-Transmission-Time": "2026-11-10T12:00:00Z", "PayPal-Cert-Url": "https://api.paypal.com/cert",
                   "PayPal-Auth-Algo": "SHA256withRSA", "PayPal-Transmission-Sig": "sig"}
EVENT = json.dumps({"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": "CAP1"}})


def verify_route(status):
    return {"POST /v1/notifications/verify-webhook-signature": lambda r: httpx.Response(200, json={"verification_status": status})}


def test_webhook_verification_true_only_when_paypal_says_success_and_sends_the_event():
    http = Http(verify_route("SUCCESS"))
    assert client(http=http).verify_webhook_signature(WEBHOOK_HEADERS, EVENT, "WEBHOOK-ID") is True
    sent = json.loads(http.to("/v1/notifications/verify-webhook-signature")[0].content)
    assert sent["webhook_id"] == "WEBHOOK-ID" and sent["transmission_id"] == "tid" and sent["transmission_sig"] == "sig"
    assert sent["webhook_event"] == json.loads(EVENT) and sent["cert_url"] == "https://api.paypal.com/cert"
    assert client(http=Http(verify_route("FAILURE"))).verify_webhook_signature(WEBHOOK_HEADERS, EVENT, "W") is False


def test_webhook_verification_header_names_are_case_insensitive():
    http = Http(verify_route("SUCCESS"))
    lower = {k.lower(): v for k, v in WEBHOOK_HEADERS.items()}
    assert client(http=http).verify_webhook_signature(lower, EVENT, "W") is True


def test_malformed_webhooks_are_rejected_without_calling_paypal():
    http = Http(verify_route("SUCCESS"))
    c = client(http=http)
    assert c.verify_webhook_signature({}, EVENT, "W") is False
    assert c.verify_webhook_signature({k: v for k, v in WEBHOOK_HEADERS.items() if k != "PayPal-Transmission-Sig"}, EVENT, "W") is False
    assert c.verify_webhook_signature(WEBHOOK_HEADERS, "not json", "W") is False
    assert c.verify_webhook_signature(WEBHOOK_HEADERS, EVENT, "") is False
    assert http.requests == []


def test_an_unreachable_paypal_during_verification_is_unavailable_not_false():
    """False would make us drop a real event; unavailable lets the handler answer 5xx so PayPal retries."""
    for status in (500, 503, 429):
        http = Http({"POST /v1/notifications/verify-webhook-signature": lambda r, s=status: httpx.Response(s, json={"message": "x"})})
        with pytest.raises(PayPalUnavailable):
            client(http=http).verify_webhook_signature(WEBHOOK_HEADERS, EVENT, "W")
    assert client(http=Http({"POST /v1/notifications/verify-webhook-signature": lambda r: httpx.Response(400, json={"message": "bad"})})) \
        .verify_webhook_signature(WEBHOOK_HEADERS, EVENT, "W") is False


# ---------------- buyer-side orders ----------------

def test_creating_a_pledge_order_asks_for_authorize_not_capture():
    sdk = FakeSDK()
    sdk.orders.queue["create_order"] = [resp(Order(id="ORDER1", status="CREATED"))]
    out = client(sdk).create_authorize_order(15000, "USD", "camp:1:pledge:7", "Pledge to Velugu Cove", "order-7-abc")
    assert out == {"id": "ORDER1", "status": "CREATED"}
    [opts] = sdk.calls("create_order")
    body = opts["body"]
    assert opts["paypal_request_id"] == "order-7-abc" and body.intent == "AUTHORIZE"
    [unit] = body.purchase_units
    assert (unit.amount.currency_code, unit.amount.value, unit.custom_id, unit.description) == ("USD", "150.00", "camp:1:pledge:7", "Pledge to Velugu Cove")


def authorized_order(auth_status="CREATED", value="150.00", with_auth=True, payer=True):
    auth = Authorization(status=auth_status, id="AUTH77", amount=usd(value), expiration_time="2026-12-09T12:00:00Z")
    unit = PurchaseUnit(payments=PaymentCollection(authorizations=[auth] if with_auth else []))
    return Order(id="ORDER1", status="COMPLETED", purchase_units=[unit], payer=Payer(email_address="supporter@sandbox.example.com", payer_id="PAYERID") if payer else None)


def test_authorizing_an_order_returns_the_hold_and_the_payer_from_paypals_response():
    sdk = FakeSDK()
    sdk.orders.queue["authorize_order"] = [resp(authorized_order())]
    out = client(sdk).authorize_order("ORDER1", "authz-7-abc")
    assert out == {"order_id": "ORDER1", "status": "COMPLETED", "payer_email": "supporter@sandbox.example.com", "payer_id": "PAYERID",
                   "authorization": {"id": "AUTH77", "status": "CREATED", "amount_cents": 15000, "currency": "USD", "expiration_time": "2026-12-09T12:00:00Z"}}
    assert sdk.calls("authorize_order") == [{"id": "ORDER1", "paypal_request_id": "authz-7-abc"}]


def test_a_declined_authorization_and_a_missing_payer_do_not_crash():
    sdk = FakeSDK()
    sdk.orders.queue["authorize_order"] = [resp(authorized_order(with_auth=False, payer=False)), resp(authorized_order(auth_status="DENIED"))]
    first = client(sdk).authorize_order("O", "k")
    assert first["authorization"] is None and first["payer_email"] is None
    assert client(sdk).authorize_order("O", "k")["authorization"]["status"] == "DENIED"


def test_order_errors_use_the_same_classification():
    sdk = FakeSDK()
    sdk.orders.queue["authorize_order"] = [api_error(422, {"name": "UNPROCESSABLE_ENTITY", "message": "x", "debug_id": "d1",
                                                           "details": [{"issue": "ORDER_NOT_APPROVED"}]}), api_error(503)]
    with pytest.raises(PayPalWriteError) as e:
        client(sdk).authorize_order("O", "k")
    assert e.value.transient is False and "ORDER_NOT_APPROVED" in str(e.value) and e.value.debug_id == "d1"
    with pytest.raises(PayPalWriteError) as e:
        client(sdk).authorize_order("O", "k")
    assert e.value.transient is True


# ---------------- startup wiring ----------------

def test_without_credentials_nothing_is_configured_and_money_stays_fail_safe():
    before = (paypal_io.get_reader(), paypal_io.get_writer())
    assert pc.configure_from_settings(SimpleNamespace(paypal_client_id="", paypal_client_secret="", paypal_env="sandbox")) is None
    assert (paypal_io.get_reader(), paypal_io.get_writer()) == before
    assert isinstance(paypal_io.get_writer(), paypal_io.UnconfiguredWriter)


def test_with_credentials_the_same_client_becomes_reader_and_writer():
    try:
        c = pc.configure_from_settings(SimpleNamespace(paypal_client_id="id", paypal_client_secret="secret", paypal_env="sandbox"))
        assert isinstance(c, pc.PayPalClient) and paypal_io.get_reader() is c and paypal_io.get_writer() is c
        assert paypal_io.get_orders() is c, "the client is also the buyer-side order gateway"
    finally:
        paypal_io.reset_to_placeholders()


def test_a_live_environment_in_settings_is_refused_at_startup():
    with pytest.raises(pc.PayPalConfigError):
        pc.configure_from_settings(SimpleNamespace(paypal_client_id="id", paypal_client_secret="secret", paypal_env="live"))


# ---------------- fields the SDK leaves UNSET (the attribute does not exist) ----------------

def test_fields_paypal_omits_do_not_crash_the_client():
    """Found by testing against the real model classes: optional fields are absent, not None."""
    sdk = FakeSDK()
    bare_auth = Authorization(id="A1", amount=usd("1.00"))                       # no status, no expiration_time
    sdk.orders.queue["authorize_order"] = [
        resp(Order(id="O1")),                                                   # no status, no purchase_units, no payer
        resp(Order(id="O2", purchase_units=[PurchaseUnit()])),                  # a unit with no payments
        resp(Order(id="O3", purchase_units=[PurchaseUnit(payments=PaymentCollection(authorizations=[bare_auth]))]))]
    c = client(sdk)
    first, second, third = (c.authorize_order(f"O{i}", "k") for i in (1, 2, 3))
    assert first == {"order_id": "O1", "status": "UNKNOWN", "authorization": None, "payer_email": None, "payer_id": None}
    assert second["authorization"] is None
    assert third["authorization"] == {"id": "A1", "status": "UNKNOWN", "amount_cents": 100, "currency": "USD", "expiration_time": None}
    assert third["payer_email"] is None


def test_a_missing_status_reads_as_unknown_so_the_guardian_will_not_trust_it():
    sdk = FakeSDK()
    sdk.payments.queue["get_authorized_payment"] = [resp(PaymentAuthorization(id="A", amount=usd("5.00")))]
    sdk.payments.queue["get_captured_payment"] = [resp(CapturedPayment(id="C", amount=usd("5.00")))]
    sdk.payments.queue["capture_authorized_payment"] = [resp(CapturedPayment(id="C2", amount=usd("5.00")))]
    sdk.orders.queue["create_order"] = [resp(Order(id="O"))]
    c = client(sdk)
    assert c.get_authorization("A").status == "UNKNOWN" and c.get_capture("C").status == "UNKNOWN"
    assert c.capture_authorization("A", 500, "USD", True, "k")["status"] == "UNKNOWN"
    assert c.create_authorize_order(500, "USD", "x", "y", "k")["status"] == "UNKNOWN"


def test_a_balance_without_the_primary_flag_still_works():
    sdk = FakeSDK()
    sdk.transaction_search.queue["search_balances"] = [resp(BalancesResponse(balances=[BalanceInformation(currency="USD", total_balance=usd("7.50"))]))]
    assert client(sdk).platform_balance_cents() == 750
    sdk.transaction_search.queue["search_balances"] = [resp(BalancesResponse(balances=[BalanceInformation(currency="USD")]))]
    assert client(sdk).platform_balance_cents() is None
