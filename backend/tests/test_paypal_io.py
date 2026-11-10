import pytest

from app.services import paypal_io
from app.services.paypal_io import PayPalWriteError


@pytest.fixture(autouse=True)
def restore():
    yield
    paypal_io.reset_to_placeholders()


class Recorder:
    def __init__(self):
        self.calls = []

    def create_authorize_order(self, *a):
        self.calls.append(("create", a))
        return {"id": "O1", "status": "CREATED"}

    def authorize_order(self, *a):
        self.calls.append(("authorize", a))
        return {"order_id": "O1"}


def test_by_default_no_pledge_can_be_taken_and_the_reason_is_clear():
    orders = paypal_io.get_orders()
    assert isinstance(orders, paypal_io.UnconfiguredOrders)
    for call in (lambda: orders.create_authorize_order(500, "USD", "x", "y", "k"), lambda: orders.authorize_order("O1", "k")):
        with pytest.raises(PayPalWriteError) as e:
            call()
        assert e.value.transient is False and "not configured" in str(e.value)


def test_configuring_orders_does_not_change_the_other_two_roles():
    reader, writer = paypal_io.get_reader(), paypal_io.get_writer()
    rec = Recorder()
    paypal_io.configure(orders=rec)
    assert paypal_io.get_orders() is rec and paypal_io.get_reader() is reader and paypal_io.get_writer() is writer


def test_configuring_only_reader_and_writer_leaves_orders_alone():
    before = paypal_io.get_orders()
    paypal_io.configure(reader=object(), writer=object())
    assert paypal_io.get_orders() is before


def test_the_three_roles_are_separate_objects_by_default():
    assert len({id(paypal_io.get_reader()), id(paypal_io.get_writer()), id(paypal_io.get_orders())}) == 3


def test_the_unconfigured_reader_refuses_refund_lookups_too():
    import pytest
    from app.services.guardian_rules import PayPalUnavailable
    with pytest.raises(PayPalUnavailable):
        paypal_io.UnconfiguredReader().get_refund("R1")
