"""SPEC 12: "A unit test fails if any other module imports SDK/HTTP write methods."

Only money_executor.py may CALL PayPal write methods, and only it (via the job handler) may obtain a writer.
When the real PayPal client lands (T-20) it must be added to ALLOWED_DEFINERS and nowhere else.
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
WRITE_METHODS = ("capture_authorization", "void_authorization", "refund_capture", "create_payout_batch", "reauthorize")
ALLOWED_CALLERS = {"money_executor.py"}
ALLOWED_DEFINERS = {"paypal_io.py", "paypal_client.py"}       # Protocol / placeholders / the real client (T-20)
SDK_IMPORTERS = {"paypal_client.py"}                           # only this module may import the PayPal SDK


def sources():
    for path in APP.rglob("*.py"):
        yield path, path.read_text(encoding="utf-8")


def test_only_the_executor_calls_paypal_write_methods():
    offenders = []
    for path, text in sources():
        if path.name in ALLOWED_CALLERS | ALLOWED_DEFINERS:
            continue
        for m in WRITE_METHODS:
            if re.search(rf"\b{m}\b", text):
                offenders.append(f"{path.relative_to(APP)} mentions {m}")
    assert not offenders, "\n".join(offenders)


def test_the_executor_really_is_the_one_calling_them():
    text = (APP / "services" / "money_executor.py").read_text(encoding="utf-8")
    for m in ("capture_authorization", "void_authorization", "refund_capture", "create_payout_batch"):
        assert f"writer.{m}(" in text


def test_only_the_job_handler_obtains_a_writer():
    users = [str(p.relative_to(APP)) for p, t in sources() if "get_writer" in t and p.name != "paypal_io.py"]
    assert users == [str(Path("services") / "job_handlers.py")]


def test_no_api_router_can_reach_a_writer():
    for path, text in sources():
        if "routers" in path.parts:
            assert "PayPalWriter" not in text and "get_writer" not in text and "money_executor" not in text, path.name


def test_only_the_paypal_client_module_may_import_the_sdk_or_http_writes():
    for path, text in sources():
        if path.name in SDK_IMPORTERS:
            continue
        assert "paypal_server_sdk" not in text and "paypalserversdk" not in text, path.name
        assert not re.search(r"api-m\.(sandbox\.)?paypal\.com", text), f"{path.name} hardcodes a PayPal URL"


def test_agents_cannot_import_money_modules():
    """Agents never call PayPal, compute money or build plans (SPEC 7.6)."""
    for path, text in sources():
        if "agents" in path.parts:
            for banned in ("money_executor", "plan_builder", "paypal_io", "settlement", "ledger", "plan_lifecycle"):
                assert not re.search(rf"import .*\b{banned}\b|from app\.services import .*\b{banned}\b", text), \
                    f"{path.relative_to(APP)} imports {banned}"


ORDER_METHODS = ("create_authorize_order", "authorize_order")
ORDER_CALLERS = {"pledge_service.py"}      # the Pledge Gate (T-22); the client defines them


def test_buyer_side_order_calls_stay_behind_the_pledge_gate():
    """Creating and authorizing pledge orders is the only buyer-side PayPal write; only the Pledge Gate may call it."""
    offenders = []
    for path, text in sources():
        if path.name in ALLOWED_DEFINERS | ORDER_CALLERS:
            continue
        for m in ORDER_METHODS:
            if re.search(rf"\b{m}\b", text):
                offenders.append(f"{path.relative_to(APP)} mentions {m}")
    assert not offenders, "\n".join(offenders)


def test_nothing_but_the_paypal_client_imports_an_http_library():
    """Payouts and webhook verification use httpx, but only inside paypal_client.py; no other module may open a connection."""
    for path, text in sources():
        if path.name in SDK_IMPORTERS:
            continue
        assert not re.search(r"^\s*(import|from)\s+(httpx|requests|urllib3|aiohttp)", text, re.M), f"{path.relative_to(APP)} imports an HTTP library"
