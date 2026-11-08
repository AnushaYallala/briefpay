import re

from app.schemas.brd import BRDDraft
from app.services import brd_service as svc
from app.services.brd_render import block, cell, describe_hint, inline, money, render_markdown
from tests.brd_factory import criterion, draft, draft_requirement
from tests.test_brd_assemble import ctx

NAMES = {1: "Lakshmi (Sea Breeze Homestay)", 2: "Ravi (Ravi's Fish Kitchen)", 3: "Meena (Cove Boat Tours)"}


def build(d=None, **kw):
    return svc.assemble(BRDDraft.model_validate(d or draft()), ctx(**kw))


def render(content=None, **kw):
    return render_markdown(content or build(), version=kw.get("version", 1), score=kw.get("score", 93), names=kw.get("names", NAMES))


# ---------------- the filters ----------------

def test_angle_brackets_and_ampersands_can_never_become_html():
    assert inline("<script>alert(1)</script> & more") == "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more"
    assert "<" not in block("<img src=x onerror=alert(1)>") and "<" not in cell("<b>")


def test_inline_text_cannot_break_the_layout():
    assert inline("Line one\n\n# Heading   with\ttabs") == "Line one # Heading with tabs"
    assert cell("a | b") == "a \\| b"


def test_a_paragraph_line_cannot_pose_as_a_heading_list_or_quote():
    out = block("Normal text\n# Fake heading\n## Deeper heading\n- fake bullet\n> fake quote\n1. fake step\n2) another\n+ plus\n* star"
                "\n---\n===\n```\n~~~\n| a | b |\n____\n3 apples and 2024 remain plain")
    assert out.split("\n\n") == ["Normal text", "\\# Fake heading", "\\## Deeper heading", "\\- fake bullet", "&gt; fake quote",
                                 "\\1. fake step", "\\2) another", "\\+ plus", "\\* star", "\\---", "\\===", "\\```", "\\~~~",
                                 "\\| a | b |", "\\____", "3 apples and 2024 remain plain"]
    assert block("") == "" and block(None) == ""


def test_a_one_line_field_cannot_start_structure_either():
    assert inline("# shout") == "\\# shout" and inline("- item") == "\\- item" and inline("--- rule") == "\\--- rule"
    assert inline("1. first") == "\\1. first" and inline("Plain text - with a dash") == "Plain text - with a dash"
    assert inline("2024 launch") == "2024 launch" and inline("  ") == ""


def test_money_is_formatted_from_integer_cents():
    assert money(40000, "USD") == "USD 400.00" and money(5, "USD") == "USD 0.05" and money(123456789, "EUR") == "EUR 1,234,567.89"


def test_hints_are_described_in_plain_words():
    assert describe_hint({"type": "PAGE_CONTAINS", "path": "/contact", "text": "Send <b>enquiry"}) == 'the page /contact contains "Send &lt;b&gt;enquiry"'
    assert describe_hint({"type": "URL_REACHABLE", "path": "/stay", "text": None}) == "the page /stay loads"
    assert describe_hint({"type": "FILE_EXISTS", "path": "assets/a.jpg", "text": None}) == "the file assets/a.jpg exists in the repository"
    assert describe_hint({"type": "MOBILE_VIEWPORT", "path": None, "text": None}) == "the site declares a mobile viewport"


# ---------------- the document ----------------

def test_the_document_has_every_section_in_order_with_real_content():
    md = render()
    assert md.startswith("# Velugu Cove tourism website\n")
    assert "*Business Requirements Document · version 1 · analysis score 93/100*" in md
    headings = re.findall(r"^## (.+)$", md, re.M)
    assert headings == ["1. Executive summary", "2. Business goals and success measures", "3. Stakeholders", "4. Audience",
                        "5. Site structure", "6. Requirements", "7. Non-functional requirements", "8. Who provides the content",
                        "9. Constraints", "10. Out of scope", "11. Open items", "12. Glossary"]
    assert "| `/contact` | The enquiry form |" in md
    assert "**Lakshmi (Sea Breeze Homestay)** · Sea Breeze Homestay" in md
    assert "- **Budget:** USD 400.00" in md and "- **Delivery time:** 5 days" in md
    assert "| Room photos and prices | Lakshmi (Sea Breeze Homestay) | Nov 20 |" in md
    assert "- Online payments on the site" in md and "*None. The analysis found nothing left to settle.*" in md


def test_a_requirement_reads_as_given_when_then_with_evidence_and_the_automatic_check():
    md = render()
    assert "### REQ-001 · Enquiry form" in md and "### REQ-002 · Gallery of rooms" in md
    assert "**Priority:** MUST · **Weight:** 5/5 · **Requested by:** Lakshmi (Sea Breeze Homestay), Ravi (Ravi's Fish Kitchen), Meena (Cove Boat Tours)" in md
    assert ("- **AC-1** Given a visitor opens the contact page, when they fill in the enquiry form and send it, "
            "then a confirmation with a reference number is shown.") in md
    assert "  - Evidence: SCREENSHOT, CODE_SNIPPET" in md
    assert '  - Automatic check: the page /contact contains "Send enquiry"' in md
    assert "*Source: L3-L5*" in md
    assert "*No acceptance criteria (not required at this priority).*" in md                   # the SHOULD without criteria


def test_optional_sections_disappear_when_empty():
    md = render(build(draft(non_functional=[], content_responsibilities=[], glossary=[], success_measures=[])))
    assert "Non-functional" not in md and "Who provides the content" not in md and "Glossary" not in md and "How we will know" not in md
    assert "## 9. Constraints" in md


def test_open_items_and_scope_are_listed_when_present():
    md = render(build(draft(out_of_scope=[]), code_open_items=["Gate 3: unresolved: booking"], out_of_scope=[]))
    assert "- Gate 3: unresolved: booking" in md and "*Nothing has been listed as out of scope.*" in md


def test_hostile_text_anywhere_in_the_draft_is_neutralised():
    evil = "<script>alert('x')</script>"
    d = draft(title=f"Site {evil}", executive_summary="Summary line one.\n# Not a heading\nline three is fine here.",
              requirements=[draft_requirement(f"Form {evil}", ids=("R1", "R2"), description=f"Do it\n## Injected\n{evil}",
                                              criteria=[criterion(given=f"a user {evil}", then="a | pipe | row")])],
              sitemap=[{"path": "/", "purpose": f"Home | {evil}"}], glossary=[{"term": evil, "definition": "A scary term here"}])
    md = render(build(d))
    assert "<" not in md.replace("&lt;", "").replace("&gt;", "") and "<script>" not in md
    assert "&lt;script&gt;" in md and "\n## Injected" not in md and "\n# Not a heading" not in md
    assert "Home \\| &lt;script&gt;" in md
    assert re.findall(r"^## (.+)$", md, re.M)[:6] == ["1. Executive summary", "2. Business goals and success measures", "3. Stakeholders",
                                                        "4. Audience", "5. Site structure", "6. Requirements"]


def test_names_are_looked_up_and_unknown_people_are_shown_safely():
    md = render(names={1: "<b>Lakshmi</b>"})
    assert "&lt;b&gt;Lakshmi&lt;/b&gt;" in md and "member #2" in md
    assert "@" not in render(), "the document never contains an email"


def test_rendering_is_deterministic_and_no_blank_line_runs():
    a, b = render(), render()
    assert a == b and "\n\n\n" not in a and a.endswith("\n") and not a.endswith("\n\n")
