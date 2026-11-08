"""Settlement engine: pure functions, integer cents only (SPEC 8.3). No DB, no PayPal, no floats."""
import hashlib
import json

from app.schemas.plans import MoneyPlanSpec


class SettlementError(Exception):
    pass


def split_pro_rata(total: int, weights: list[tuple[int, int]]) -> dict[int, int]:
    """Largest-remainder split of `total` cents by integer weights; sums exactly to total.

    Ties on the remainder go to the smallest key, so the result is deterministic.
    """
    if total < 0 or not weights or any(w < 0 for _, w in weights):
        raise SettlementError("invalid split input")
    tw = sum(w for _, w in weights)
    if tw == 0:
        return {k: 0 for k, _ in weights}
    raw = [(k, total * w) for k, w in weights]
    out = {k: v // tw for k, v in raw}
    leftover = total - sum(out.values())
    for k, _ in sorted(raw, key=lambda x: (x[1] % tw, -x[0]), reverse=True)[:leftover]:
        out[k] += 1
    return out


def plan_captures(goal: int, pledges: list[tuple[int, int]]) -> dict[int, int]:
    """pledges = [(pledge_id, authorized_cents)] of live-valid holds.

    Each capture <= its authorization and the captures sum to exactly `goal`.
    """
    total = sum(a for _, a in pledges)
    if total < goal:
        raise SettlementError("Authorized total is below goal")
    caps = split_pro_rata(goal, pledges)
    if sum(caps.values()) != goal or any(caps[i] > a for i, a in pledges):
        raise SettlementError("capture split violated an invariant")
    return caps


def plan_refunds(captures: list[tuple[int, int, int]]) -> dict[int, int]:
    """captures = [(pledge_id, captured_cents, refunded_cents)] -> refundable remaining per pledge."""
    return {i: c - r for i, c, r in captures if c - r > 0}


def plan_freelancer_payout(contract_amount: int, pool_balance: int, fee_reserve: int) -> int:
    if contract_amount + fee_reserve > pool_balance:
        raise SettlementError("Pool does not cover contract + fees")
    return contract_amount


def canonical_json(obj) -> str:
    """Stable serialisation: sorted keys, no whitespace. Same data -> same string -> same hash."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def plan_hash(spec: MoneyPlanSpec) -> str:
    """sha256 over the canonical plan. Any changed recipient, amount or step changes the hash.

    Step idempotency keys are derived FROM this hash (SPEC 7.5.1), so they are excluded from it (D-021).
    """
    data = spec.model_dump(mode="json")
    for step in data["steps"]:
        step.pop("idempotency_key", None)
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def idempotency_key(plan_hash_hex: str, seq: int) -> str:
    return f"{plan_hash_hex[:16]}-{seq}"
