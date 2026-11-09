"""Demo-only "Simulate tampered plan" mutations (SPEC 7.5.6).

Each mutation returns a COPY of a plan spec, re-hashed with fresh idempotency keys (a careful attacker would
do that), so the Guardian must catch it on substance, not on a trivially stale key. Nothing here touches PayPal.
"""
from app.schemas.plans import MoneyPlanSpec, PlanStep
from app.services.settlement import idempotency_key, plan_hash

ATTACKER = "attacker@example.com"

# mutation -> (plan kind it applies to, rules that must go red)
MUTATIONS: dict[str, tuple[str, set[str]]] = {
    "SWAP_RECIPIENT": ("FREELANCER_PAYOUT", {"G-12", "G-03"}),
    "INFLATE_AMOUNT": ("FREELANCER_PAYOUT", {"G-12", "G-07"}),
    "EXTRA_RECIPIENT": ("FREELANCER_PAYOUT", {"G-12", "G-04"}),
    "DOUBLE_CAPTURE": ("CAPTURE_PLEDGES", {"G-10", "G-02"}),
    "CAPTURE_IN_RELEASE": ("RELEASE_HOLDS", {"G-11"}),
}


class TamperError(Exception):
    pass


def _rekey(spec: MoneyPlanSpec, steps: list[PlanStep]) -> MoneyPlanSpec:
    steps = [s.model_copy(update={"seq": i, "idempotency_key": ""}) for i, s in enumerate(steps, start=1)]
    draft = spec.model_copy(update={"steps": steps})
    h = plan_hash(draft)
    return draft.model_copy(update={"steps": [s.model_copy(update={"idempotency_key": idempotency_key(h, s.seq)})
                                              for s in steps]})


def apply_mutation(spec: MoneyPlanSpec, mutation: str) -> MoneyPlanSpec:
    if mutation not in MUTATIONS:
        raise TamperError(f"unknown mutation {mutation}")
    kind, _ = MUTATIONS[mutation]
    if spec.kind != kind:
        raise TamperError(f"{mutation} applies to {kind} plans, not {spec.kind}")
    steps = [s.model_copy() for s in spec.steps]
    if not steps and mutation != "CAPTURE_IN_RELEASE":
        raise TamperError("plan has no steps to tamper with")
    if mutation == "SWAP_RECIPIENT":
        steps[0].receiver_email = ATTACKER
    elif mutation == "INFLATE_AMOUNT":
        steps[0].amount_cents += 10000
    elif mutation == "EXTRA_RECIPIENT":
        steps.append(steps[0].model_copy(update={"receiver_email": ATTACKER, "amount_cents": 1000}))
    elif mutation == "DOUBLE_CAPTURE":
        steps.append(steps[0].model_copy())
    elif mutation == "CAPTURE_IN_RELEASE":
        victim = steps[0] if steps else None
        if victim is None:
            raise TamperError("release plan has no hold to capture")
        steps[0] = victim.model_copy(update={"op": "CAPTURE_AUTH", "bucket": "POOL"})
    return _rekey(spec, steps)
