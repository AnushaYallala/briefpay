"""The Strategist's words (SPEC 7.4): facts from code -> wording from the model -> numbers CHECKED -> stored. Advisory only. Flushes only.

The forecast itself is deterministic (`strategist_math`). The model only phrases it. Every number or amount in anything it writes
must be one of the numbers in the facts; otherwise that text is replaced by a template built from the facts and a flag is recorded.
If the model is unavailable, over quota or invalid, the template wording is used for everything, so the lead always gets text.
"""
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm_adapter import AgentError
from app.agents.strategist import StrategistAgent
from app.config import get_settings
from app.models import Campaign, Project, StrategistReport
from app.services import campaign_ops

URL = re.compile(r"https?://\S+")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
LABEL = "estimate (heuristic)"
MAX_TARGETS = 5
ONE_DRAFT_PER_DAY = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def money(cents: int) -> str:
    return f"${cents // 100:,}" + (f".{cents % 100:02d}" if cents % 100 else "")


def numbers_in(text: str) -> set[Decimal]:
    """Every number in the text (links are ignored), as exact values: $100, 100 and 100.00 are the same number."""
    found = set()
    for token in NUMBER.findall(URL.sub(" ", text or "")):
        try:
            found.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            pass
    return found


def campaign_url(c: Campaign) -> str:
    return f"{get_settings().web_base_url.rstrip('/')}/campaign?id={c.id}"


# =============================== facts ===============================

def build_facts(db: Session, c: Campaign, computed: dict) -> dict:
    f, s = computed["forecast"], computed["suggestions"]
    totals = campaign_ops.pledge_totals(db, c)
    deadline = _aware(c.deadline_at)
    targets = []
    for t in s["nudge_targets"][:MAX_TARGETS]:
        cents = t.get("expected_pledge_cents")
        targets.append({"member_id": t["member_id"], "name": t["name"], "expected_formatted": money(cents) if cents else None,
                        "viewed": t["invite_status"] == "VIEWED"})
    return {"label": LABEL, "goal_formatted": money(f["goal_cents"]), "pledged_formatted": money(f["pledged_cents"]), "gap_formatted": money(f["gap_cents"]),
            "gap_cents": f["gap_cents"], "hours_left": int(round(f["hours_left"])), "pledged_count": totals["pledge_count"],
            "pledged_pct": f["pledged_cents"] * 100 // f["goal_cents"] if f["goal_cents"] else 0, "probability_pct": int(round(f["probability"] * 100)),
            "deadline_text": f"{deadline:%b} {deadline.day}, {deadline:%H:%M} UTC", "targets": targets}


def allowed_numbers(facts: dict) -> set[Decimal]:
    text = " ".join(str(facts[k]) for k in ("goal_formatted", "pledged_formatted", "gap_formatted", "hours_left", "pledged_count", "pledged_pct",
                                           "probability_pct", "deadline_text"))
    text += " " + " ".join(t["expected_formatted"] or "" for t in facts["targets"]) + " " + " ".join(t["name"] for t in facts["targets"])
    return numbers_in(text)


# =============================== template wording (also the fallback) ===============================

def template_nudge(name: str, facts: dict, url: str) -> str:
    return f"{name}, we're {facts['gap_formatted']} short with {facts['hours_left']} h left. The link: {url}"


def template_narrative(facts: dict) -> dict:
    n = facts["pledged_count"]
    risks = []
    if facts["probability_pct"] < 50:
        risks.append("The expected pledges are well below the goal")
    if any(not t["viewed"] for t in facts["targets"]):
        risks.append("Some invitees have not opened the campaign link yet")
    if facts["gap_cents"] and facts["hours_left"] < 24:
        risks.append("Little time is left")
    return {"headline": f"About a {facts['probability_pct']}% chance of reaching the goal ({LABEL})",
            "explanation": (f"{facts['pledged_formatted']} of {facts['goal_formatted']} is held in {n} pledge{'' if n == 1 else 's'} ({facts['pledged_pct']}%). "
                            f"{facts['gap_formatted']} is still needed with {facts['hours_left']} h left. This is a rough estimate, not a promise. "
                            "A pledge is only a hold: nobody is charged unless the goal is reached."),
            "risk_factors": risks}


# =============================== checking what the model wrote ===============================

def clean(text: str) -> str:
    return " ".join(URL.sub(" ", text or "").split())


def _fits(text: str, allowed: set[Decimal]) -> bool:
    return numbers_in(text) <= allowed


def check_narrative(out, facts: dict, allowed: set[Decimal]) -> tuple[dict, list[str]]:
    base, flags = template_narrative(facts), []
    headline, explanation = clean(out.headline), clean(out.explanation)
    if not headline or not _fits(headline, allowed):
        headline = base["headline"]
        flags.append("HEADLINE_NUMBER_MISMATCH")
    if not explanation or not _fits(explanation, allowed):
        explanation = base["explanation"]
        flags.append("EXPLANATION_NUMBER_MISMATCH")
    risks = []
    for r in out.risk_factors:
        r = clean(r)
        if r and _fits(r, allowed):
            risks.append(r)
        elif r:
            flags.append("RISK_NUMBER_MISMATCH")
    return {"headline": headline, "explanation": explanation, "risk_factors": risks}, flags


def check_nudges(out, facts: dict, allowed: set[Decimal], url: str) -> tuple[list[dict], list[str]]:
    targets = {t["member_id"]: t for t in facts["targets"]}
    nudges, flags, seen = [], [], set()
    for d in out.nudges:
        if d.member_id not in targets:
            flags.append("NUDGE_UNKNOWN_MEMBER")
            continue
        if d.member_id in seen:
            flags.append("NUDGE_DUPLICATE")
            continue
        seen.add(d.member_id)
        name, text, own = targets[d.member_id]["name"], clean(d.message), []
        if not text or not _fits(text, allowed):
            text, own, source = template_nudge(name, facts, url), ["NUDGE_NUMBER_MISMATCH"], "TEMPLATE"
            flags.append("NUDGE_NUMBER_MISMATCH")
        else:
            text, source = f"{text} {url}", "AI"
        nudges.append({"member_id": d.member_id, "name": name, "channel": d.channel, "message": text, "source": source, "flags": own, "reused": False})
    return nudges, flags


def template_nudges(facts: dict, url: str) -> list[dict]:
    return [{"member_id": t["member_id"], "name": t["name"], "channel": "WHATSAPP", "message": template_nudge(t["name"], facts, url),
             "source": "TEMPLATE", "flags": [], "reused": False} for t in facts["targets"]]


def reuse_todays_drafts(db: Session, c: Campaign, report: StrategistReport, nudges: list[dict], now: datetime) -> list[dict]:
    """One draft per invitee per day: someone drafted for in the last 24 hours keeps that draft instead of getting a new one."""
    earlier: dict[int, dict] = {}
    for r in db.scalars(select(StrategistReport).where(StrategistReport.campaign_id == c.id, StrategistReport.id < report.id).order_by(StrategistReport.id)):
        if now - _aware(r.created_at) <= ONE_DRAFT_PER_DAY:
            for n in r.nudges_json or []:
                earlier[n["member_id"]] = n
    return [{**earlier[n["member_id"]], "reused": True} if n["member_id"] in earlier else n for n in nudges]


# =============================== the entry point ===============================

def add_narrative(db: Session, report: StrategistReport, c: Campaign, project: Project, agent: StrategistAgent, computed: dict,
                  now: datetime | None = None) -> dict:
    now = now or _now()
    facts, url = build_facts(db, c, computed), campaign_url(c)
    allowed, flags, run_id = allowed_numbers(facts), [], None
    try:
        out, run_id = agent.words(facts, project.title, project.id)
        narrative, nflags = check_narrative(out, facts, allowed)
        nudges, uflags = check_nudges(out, facts, allowed, url)
        flags += nflags + uflags
        source = "AI"
    except AgentError as e:                                     # unavailable, over quota, or invalid twice: the code writes it all
        run_id = getattr(e, "run_id", None)
        narrative, nudges, source = template_narrative(facts), template_nudges(facts, url), "TEMPLATE"
        flags.append("AI_UNAVAILABLE")
    nudges = reuse_todays_drafts(db, c, report, nudges, now)
    report.narrative_json = {**narrative, "source": source, "label": LABEL, "flags": sorted(set(flags))}
    report.nudges_json = nudges
    report.agent_run_id = run_id
    db.flush()
    return {"source": source, "flags": sorted(set(flags)), "nudges": len(nudges), "agent_run_id": run_id}
