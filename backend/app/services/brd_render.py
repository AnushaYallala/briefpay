"""BRD rendering and hashing (SPEC 7.2): Markdown comes from a template, never from the model; the hash is of the
canonical JSON. Pure functions, no DB.

Every user-derived string goes through an escaping filter: angle brackets become entities (so nothing can become HTML
in any Markdown viewer), newlines collapse in one-line positions, and pipes are escaped inside table cells.
"""
import hashlib
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas.brd import AutoCheckHint, BRDContent
from app.services.settlement import canonical_json

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_BLOCK_START = re.compile(r"^(?:[#*+\-=_~`|]|\d+[.)])")


def _guard(line: str) -> str:
    """A line must never BEGIN with something Markdown reads as structure (heading, list, rule, code fence, table,
    setext underline, numbered list). One backslash makes the first character literal. (`>` is already an entity.)"""
    return "\\" + line if _BLOCK_START.match(line) else line


def inline(text) -> str:
    return _guard(re.sub(r"\s+", " ", _escape(text or "")).strip())


def block(text) -> str:
    """Paragraphs: line breaks kept, but no line can pose as structure the author did not mean."""
    lines = [ln.strip() for ln in _escape(text or "").splitlines() if ln.strip()]
    return "\n\n".join(_guard(ln) for ln in lines)


def cell(text) -> str:
    return inline(text).replace("|", "\\|")


def money(cents: int, currency: str) -> str:
    return f"{currency} {cents // 100:,}.{cents % 100:02d}"


def describe_hint(h: dict) -> str:
    hint = AutoCheckHint.model_validate(h)
    return {"URL_REACHABLE": f"the page {hint.path} loads",
            "PAGE_CONTAINS": f"the page {hint.path} contains \"{inline(hint.text)}\"",
            "FILE_EXISTS": f"the file {hint.path} exists in the repository",
            "MOBILE_VIEWPORT": "the site declares a mobile viewport"}[hint.type]


def render_markdown(content: BRDContent, *, version: int, score: int, names: dict[int, str]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False, trim_blocks=True, lstrip_blocks=True,
                      keep_trailing_newline=True, undefined=StrictUndefined)

    def person(member_id) -> str:
        return inline(names.get(member_id, f"member #{member_id}"))

    env.filters.update(
        inline=inline, block=block, cell=cell, money=money, person=person, hint=describe_hint,
        people=lambda ids: ", ".join(person(i) for i in ids) or "not recorded",
        person_or_dash=lambda i: person(i) if i is not None else "to be agreed")
    text = env.get_template("brd.md.j2").render(c=content.model_dump(mode="json"), version=version, score=score)
    return re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"


def content_hash(content: BRDContent) -> str:
    """sha256 of the canonical JSON. Sponsors approve THIS hash; the contract binds to it."""
    return hashlib.sha256(canonical_json(content.model_dump(mode="json")).encode("utf-8")).hexdigest()
