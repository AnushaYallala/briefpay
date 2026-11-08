import pytest
from pydantic import ValidationError

from app.schemas.brd import AutoCheckHint, BRDContent, BRDDraft, SitemapEntry
from app.services import brd_service as svc
from app.services.brd_render import content_hash
from tests.brd_factory import criterion, draft, draft_requirement

PROJECT = {"title": "Velugu Cove website", "budget_cents": 40000, "currency": "USD", "delivery_days": 5}


def ctx(**over):
    base = dict(sponsor_ids={1, 2, 3}, sponsor_business={1: "Sea Breeze Homestay", 2: "Ravi's Fish Kitchen", 3: "Cove Boat Tours"},
                line_count=30, answer_ids={7}, analysis_ids=["R1", "R2"], out_of_scope=["No booking engine"],
                project=PROJECT, code_open_items=[])
    base.update(over)
    return svc.AssembleContext(**base)


def build(d=None, **kw):
    return svc.assemble(BRDDraft.model_validate(d or draft()), ctx(**kw))


# ---------------- the draft schema ----------------

@pytest.mark.parametrize("hint,ok", [
    ({"type": "PAGE_CONTAINS", "path": "/contact", "text": "Send enquiry"}, True),
    ({"type": "PAGE_CONTAINS", "path": "/contact"}, False), ({"type": "PAGE_CONTAINS", "path": "/contact", "text": "  "}, False),
    ({"type": "PAGE_CONTAINS", "path": "contact", "text": "x"}, False), ({"type": "PAGE_CONTAINS", "path": "/Contact Us", "text": "x"}, False),
    ({"type": "URL_REACHABLE", "path": "/stay"}, True), ({"type": "URL_REACHABLE"}, False),
    ({"type": "FILE_EXISTS", "path": "assets/room1.jpg"}, True), ({"type": "FILE_EXISTS"}, False),
    ({"type": "MOBILE_VIEWPORT"}, True), ({"type": "REPO_PUBLIC"}, False), ({"type": "COMMIT_EXISTS"}, False),
])
def test_auto_check_hints_must_be_complete_and_mechanical(hint, ok):
    if ok:
        assert AutoCheckHint.model_validate(hint)
    else:
        with pytest.raises(ValidationError):
            AutoCheckHint.model_validate(hint)


def test_the_draft_schema_rejects_malformed_pieces():
    for bad in ({"requirements": []}, {"business_goals": []}, {"sitemap": []}, {"executive_summary": "short"},
                {"sitemap": [{"path": "stay", "purpose": "The homestay"}]}, {"sitemap": [{"path": "/Stay Page", "purpose": "x" * 5}]}):
        with pytest.raises(ValidationError):
            BRDDraft.model_validate(draft(**bad))
    for bad_req in (draft_requirement(weight=0), draft_requirement(weight=6), draft_requirement(priority="NICE"),
                    draft_requirement(criteria=[criterion(evidence=())]), draft_requirement(criteria=[criterion(evidence=("VIDEO",))]),
                    draft_requirement(criteria=[criterion(given="")]), draft_requirement(criteria=[criterion()] * 9)):
        with pytest.raises(ValidationError):
            BRDDraft.model_validate(draft(requirements=[bad_req]))
    assert SitemapEntry(path="/", purpose="Welcome page") and SitemapEntry(path="/getting-there", purpose="Directions")


# ---------------- codes, order, criteria ----------------

def test_requirements_get_sequential_codes_must_first_in_drafted_order():
    d = draft(requirements=[
        draft_requirement("Gallery", "SHOULD", ids=("R2",)), draft_requirement("Map", "COULD", ids=("R3",)),
        draft_requirement("Enquiry form", "MUST", ids=("R1",)), draft_requirement("Rooms page", "MUST", ids=("R4",))])
    c = build(d, analysis_ids=["R1", "R2", "R3", "R4"])
    assert [(r.code, r.title, r.priority) for r in c.requirements] == [
        ("REQ-001", "Enquiry form", "MUST"), ("REQ-002", "Rooms page", "MUST"),
        ("REQ-003", "Gallery", "SHOULD"), ("REQ-004", "Map", "COULD")]


def test_criteria_ids_are_assigned_by_code_per_requirement():
    d = draft(requirements=[draft_requirement(criteria=[criterion(), criterion(then="the form is cleared"), criterion(then="an email is sent")],
                                              ids=("R1", "R2"))])
    c = build(d)
    assert [a.id for a in c.requirements[0].acceptance_criteria] == ["AC-1", "AC-2", "AC-3"]


def test_every_must_needs_a_criterion_but_should_and_could_may_go_without():
    assert build(draft(requirements=[draft_requirement(ids=("R1", "R2")), draft_requirement("Gallery", "SHOULD", criteria=[]),
                                     draft_requirement("Map", "COULD", criteria=[])]))
    with pytest.raises(svc.BRDError) as e:
        build(draft(requirements=[draft_requirement(criteria=[], ids=("R1", "R2"))]))
    assert e.value.code == "BRD_INVALID" and "Enquiry form" in e.value.message


def test_a_brd_without_any_must_is_refused():
    with pytest.raises(svc.BRDError) as e:
        build(draft(requirements=[draft_requirement("Gallery", "SHOULD", ids=("R1", "R2"))]))
    assert "no MUST" in e.value.message


def test_nothing_from_the_analysis_may_be_dropped():
    d = draft(requirements=[draft_requirement(ids=("R1",))])
    with pytest.raises(svc.BRDError) as e:
        build(d)
    assert e.value.code == "BRD_INVALID" and "R2" in e.value.message
    assert build(d, analysis_ids=["R1"])                                       # fine when R2 never existed
    merged = draft(requirements=[draft_requirement("Enquiry and gallery", ids=("R1", "R2"))])
    assert build(merged)                                                       # merging two analysis items is allowed


# ---------------- sanitising what the model said ----------------

def test_unknown_people_and_made_up_references_are_stripped():
    d = draft(requirements=[draft_requirement(ids=("R1", "R2"), by=(1, 99, 2, 2), refs=("L2", "L500", "answer:7", "answer:8", "junk"))])
    r = build(d).requirements[0]
    assert r.requested_by == [1, 2] and r.source_refs == ["L2", "answer:7"]


def test_every_sponsor_appears_as_a_stakeholder_and_unknown_ones_do_not():
    d = draft(stakeholders=[{"member_id": 1, "business_name": None, "needs": ["Show my rooms"]},
                            {"member_id": 99, "business_name": "Ghost Ltd", "needs": ["x"]}])
    c = build(d)
    assert [s.member_id for s in c.stakeholders] == [1, 2, 3]
    assert c.stakeholders[0].business_name == "Sea Breeze Homestay" and c.stakeholders[0].needs == ["Show my rooms"]
    assert c.stakeholders[1].needs == ["Enquiry form"], "a sponsor the model forgot is filled from what they asked for, not invented"
    assert c.stakeholders[2].business_name == "Cove Boat Tours"


def test_content_owners_must_be_real_sponsors():
    d = draft(content_responsibilities=[{"item": "Room photos", "owner_member_id": 1, "due": "Nov 20"},
                                        {"item": "Menu text", "owner_member_id": 42, "due": None}])
    assert [cr.owner_member_id for cr in build(d).content_responsibilities] == [1, None]


# ---------------- facts the model must not decide ----------------

def test_budget_deadline_and_currency_come_from_the_project_record():
    c = build(draft(hosting="Render static site", domain="velugucove.example"))
    assert (c.constraints.budget_cents, c.constraints.currency, c.constraints.delivery_days) == (40000, "USD", 5)
    assert (c.constraints.hosting, c.constraints.domain) == ("Render static site", "velugucove.example")
    c2 = svc.assemble(BRDDraft.model_validate(draft()), ctx(project={**PROJECT, "delivery_days": None}))
    assert c2.constraints.delivery_days is None


def test_the_title_falls_back_to_the_project_title():
    assert build(draft(title="")).title == "Velugu Cove website"
    assert build(draft(title="   ")).title == "Velugu Cove website"
    assert build().title == "Velugu Cove tourism website"


def test_scope_exclusions_from_the_analysis_always_survive_and_duplicates_collapse():
    c = build(draft(out_of_scope=["online payments on the site", "No booking engine.", "A blog"]), out_of_scope=["No booking engine", "Online payments on the site"])
    assert c.out_of_scope[:2] == ["No booking engine", "Online payments on the site"]
    assert len(c.out_of_scope) == 3 and c.out_of_scope[2] == "A blog"


def test_open_items_combine_the_real_gaps_with_the_models_and_are_capped():
    c = build(draft(open_items=["Which domain name?", "which domain name?"]), code_open_items=["Every sponsor has a need captured: no need captured yet for member(s) [3]"])
    assert c.open_items == ["Every sponsor has a need captured: no need captured yet for member(s) [3]", "Which domain name?"]
    many = build(draft(open_items=[f"Question {i}" for i in range(20)]), code_open_items=[f"Gap {i}" for i in range(15)])
    assert len(many.open_items) == 20 and many.open_items[0] == "Gap 0"


# ---------------- the hash ----------------

def test_the_same_inputs_give_the_same_hash_and_any_change_gives_a_different_one():
    a, b = build(), build()
    assert content_hash(a) == content_hash(b) and len(content_hash(a)) == 64
    base = content_hash(a)
    for change in ({"executive_summary": "A different summary that is also long enough."}, {"audience": "Other people entirely"},
                   {"out_of_scope": ["Something else"]}):
        assert content_hash(build(draft(**change))) != base
    other_budget = svc.assemble(BRDDraft.model_validate(draft()), ctx(project={**PROJECT, "budget_cents": 40001}))
    assert content_hash(other_budget) != base
    tampered = BRDContent.model_validate(a.model_dump())
    tampered.requirements[0].acceptance_criteria[0].then = "nothing happens"
    assert content_hash(tampered) != base


def test_the_hash_is_exactly_sha256_of_canonical_json_so_anyone_can_recompute_it():
    """The contract and the verifier bind to this hash and must be able to reproduce it without our code (SPEC 7.2)."""
    import hashlib
    import json
    c = build()
    canonical = json.dumps(c.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert content_hash(c) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    reordered = json.loads(json.dumps(c.model_dump(mode="json")))
    reordered = dict(reversed(list(reordered.items())))                                  # same data, opposite key order
    assert hashlib.sha256(json.dumps(reordered, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest() == content_hash(c)


# ---------------- open items from the score ----------------

class FakeScore:
    def __init__(self, total, gates, dims):
        self.total, self.gates_json, self.dimensions_json = total, gates, dims


def gates(**red):
    g = {f"GT-{i}": {"title": f"Gate {i}", "passed": f"GT-{i}" not in red, "detail": red.get(f"GT-{i}", "ok")} for i in range(1, 6)}
    g["observations"] = {}
    return g


def dims(**cov):
    return [{"name": f"Dimension {i}", "coverage_effective": cov.get(f"D{i}", 1.0)} for i in range(1, 11)]


def test_a_clean_ready_analysis_has_no_open_items():
    assert svc.open_items_from_score(FakeScore(93, gates(), dims(D8=0.5)), finalized=False, target=90) == []


def test_red_gates_are_always_listed_and_thin_dimensions_follow():
    items = svc.open_items_from_score(FakeScore(93, gates(**{"GT-3": "unresolved: booking"}), dims(D8=0.25, D2=0.75)), finalized=False, target=90)
    assert items == ["Gate 3: unresolved: booking", "Dimension 8 is only partly specified."]


def test_a_finalized_analysis_lists_what_is_still_thin_even_with_green_gates():
    items = svc.open_items_from_score(FakeScore(79, gates(), dims(D5=0.5, D7=0.0)), finalized=True, target=90)
    assert items == ["Dimension 5 is only partly specified.", "Dimension 7 is only partly specified."]
    assert svc.open_items_from_score(FakeScore(85, gates(), dims(D5=0.5)), finalized=False, target=90) == ["Dimension 5 is only partly specified."]
