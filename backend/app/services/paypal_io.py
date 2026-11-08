"""PayPal I/O boundaries.

`PayPalWriter` is the set of PayPal WRITE calls. Only `money_executor.py` may receive one and call it
(SPEC 7.6, 12). `PayPalReader` (defined in guardian_rules) is read-only. The real SDK/httpx implementations
arrive with T-20/T-43; until PayPal credentials exist the `Unconfigured*` placeholders fail loudly and safely.
"""
from typing import Protocol

from app.services.guardian_rules import PayPalObject, PayPalReader, PayPalUnavailable


class PayPalWriteError(Exception):
    """A write failed. `transient` errors (timeouts, 5xx, rate limits) may be retried with the same request id."""

    def __init__(self, message: str, transient: bool = False, debug_id: str | None = None):
        super().__init__(message)
        self.transient, self.debug_id = transient, debug_id


class PayPalWriter(Protocol):
    """Every method takes the step's idempotency key as PayPal-Request-Id."""

    def capture_authorization(self, authorization_id: str, amount_cents: int, currency: str,
                              final_capture: bool, request_id: str) -> dict: ...
    def void_authorization(self, authorization_id: str, request_id: str) -> dict: ...
    def refund_capture(self, capture_id: str, amount_cents: int, currency: str, request_id: str) -> dict: ...
    def create_payout_batch(self, sender_batch_id: str, items: list[dict], currency: str,
                            email_subject: str, request_id: str) -> dict: ...


class UnconfiguredWriter:
    def _no(self, *_a, **_k):
        raise PayPalWriteError("PayPal is not configured (set PAYPAL_CLIENT_ID/SECRET); no money moved", transient=False)

    capture_authorization = void_authorization = refund_capture = create_payout_batch = _no


class UnconfiguredReader:
    def get_authorization(self, authorization_id: str) -> PayPalObject | None:
        raise PayPalUnavailable("PayPal is not configured")

    get_capture = get_authorization

    def platform_balance_cents(self) -> int | None:
        raise PayPalUnavailable("PayPal is not configured")


_reader: PayPalReader = UnconfiguredReader()
_writer: PayPalWriter = UnconfiguredWriter()


def get_reader() -> PayPalReader:
    return _reader


def get_writer() -> PayPalWriter:
    return _writer


class OrderGateway(Protocol):
    """The buyer-side PayPal calls behind the Pledge Gate: create an AUTHORIZE order, authorize it once approved.
    Only `pledge_service` calls these (enforced by tests/test_chokepoint.py). Separate from `PayPalWriter` on purpose:
    creating a hold moves no money, capturing or paying out does."""

    def create_authorize_order(self, amount_cents: int, currency: str, custom_id: str, description: str, request_id: str) -> dict: ...
    def authorize_order(self, order_id: str, request_id: str) -> dict: ...


class UnconfiguredOrders:
    def _no(self, *_a, **_k):
        raise PayPalWriteError("PayPal is not configured (set PAYPAL_CLIENT_ID/SECRET); no pledge can be taken", transient=False)

    create_authorize_order = authorize_order = _no


_orders: OrderGateway = UnconfiguredOrders()


def get_orders() -> OrderGateway:
    return _orders


def configure(reader: PayPalReader | None = None, writer: PayPalWriter | None = None, orders: OrderGateway | None = None) -> None:
    """Install real (or fake, in tests) clients. Called once at startup by the PayPal client module (T-20)."""
    global _reader, _writer, _orders
    if reader is not None:
        _reader = reader
    if writer is not None:
        _writer = writer
    if orders is not None:
        _orders = orders
