from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import LedgerEntry, Project, ProjectMember, Transcript, User

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "velugu_cove_meeting_transcript.txt"


def login(client, email, name):
    r = client.post("/api/auth/login", json={"email": email, "display_name": name}).json()
    return {"Authorization": f"Bearer {r['token']}"}, r["user"]["id"]


@pytest.fixture()
def lakshmi(client):
    return login(client, "lakshmi@example.com", "Lakshmi")[0]


NEW = {"title": "Velugu Cove tourism website", "summary": "One website for the cove.", "location_label": "Velugu Cove",
       "budget_cents": 40000, "delivery_days": 5, "lead_business_name": "Sea Breeze Homestay",
       "lead_business_type": "Homestay", "lead_expected_pledge_cents": 15000}

TEAM = [
    {"email": "ravi@example.com", "display_name": "Ravi", "role": "SPONSOR", "business_name": "Ravi's Fish Kitchen",
     "business_type": "Restaurant", "expected_pledge_cents": 15000},
    {"email": "meena@example.com", "display_name": "Meena", "role": "SPONSOR", "business_name": "Cove Boat Tours",
     "expected_pledge_cents": 10000},
    {"email": "arjun@example.com", "display_name": "Arjun", "role": "FREELANCER"},
]


def make_project(client, h, **over):
    r = client.post("/api/projects", json={**NEW, **over}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- create ----------------

def test_creating_a_project_makes_the_creator_its_lead(client, lakshmi, db):
    p = make_project(client, lakshmi)
    assert p["state"] == "DRAFT" and p["currency"] == "USD" and p["budget_cents"] == 40000
    assert p["viewer"]["role"] == "LEAD" and p["payout_release_policy"] == "HUMAN"
    [lead] = p["members"]
    assert (lead["role"], lead["business_name"], lead["email"], lead["expected_pledge_cents"]) == (
        "LEAD", "Sea Breeze Homestay", "lakshmi@example.com", 15000)
    assert db.get(Project, p["id"]).lead_user_id == db.scalars(select(User)).first().id


def test_create_can_invite_the_whole_team_at_once(client, lakshmi, db):
    p = make_project(client, lakshmi, members=TEAM)
    roles = sorted((m["role"], m["display_name"]) for m in p["members"])
    assert roles == [("FREELANCER", "Arjun"), ("LEAD", "Lakshmi"), ("SPONSOR", "Meena"), ("SPONSOR", "Ravi")]
    assert {m["invite_status"] for m in p["members"] if m["role"] != "LEAD"} == {"INVITED"}
    assert db.scalars(select(User).where(User.email == "ravi@example.com")).one().display_name == "Ravi"


@pytest.mark.parametrize("over,status,code", [
    ({"title": "ab"}, 422, None), ({"budget_cents": -1}, 422, None), ({"delivery_days": 0}, 422, None),
    ({"payout_release_policy": "ANYTHING"}, 422, None), ({"budget_cents": 100001}, 422, "BUDGET_TOO_HIGH"),
])
def test_bad_project_input_is_refused(client, lakshmi, over, status, code):
    r = client.post("/api/projects", json={**NEW, **over}, headers=lakshmi)
    assert r.status_code == status
    if code:
        assert r.json()["error"]["code"] == code


def test_a_failed_invite_does_not_leave_a_half_created_project(client, lakshmi, db):
    bad = TEAM + [{"email": "ravi@example.com", "role": "SPONSOR"}]                      # duplicate email
    r = client.post("/api/projects", json={**NEW, "members": bad}, headers=lakshmi)
    assert r.status_code == 422 and r.json()["error"]["code"] == "DUPLICATE_INVITEE"
    assert db.scalars(select(Project)).first() is None


def test_creating_needs_a_login(client):
    assert client.post("/api/projects", json=NEW).status_code == 401


# ---------------- reading: public vs member ----------------

def test_the_public_list_shows_cards_without_private_data(client, lakshmi):
    make_project(client, lakshmi, members=TEAM)
    cards = client.get("/api/projects").json()["projects"]
    assert len(cards) == 1 and cards[0]["title"] == "Velugu Cove tourism website" and cards[0]["campaign"] is None
    assert "@" not in str(cards) and "members" not in cards[0]


def test_mine_lists_only_my_projects_and_needs_a_login(client, lakshmi):
    make_project(client, lakshmi)
    ravi = login(client, "ravi@example.com", "Ravi")[0]
    make_project(client, ravi, title="Ravi's other project")
    assert [p["title"] for p in client.get("/api/projects?mine=true", headers=ravi).json()["projects"]] == ["Ravi's other project"]
    assert len(client.get("/api/projects").json()["projects"]) == 2
    assert client.get("/api/projects?mine=true").status_code == 401


def test_public_detail_hides_emails_and_pledge_plans(client, lakshmi):
    pid = make_project(client, lakshmi, members=TEAM)["id"]
    body = client.get(f"/api/projects/{pid}").json()
    assert body["viewer"] is None and "transcript" not in body
    assert "@" not in str(body["members"]) and all("expected_pledge_cents" not in m for m in body["members"])
    assert {m["display_name"] for m in body["members"]} == {"Lakshmi", "Ravi", "Meena", "Arjun"}


def test_lead_sees_everything_a_sponsor_sees_contacts_but_not_pledge_plans(client, lakshmi):
    pid = make_project(client, lakshmi, members=TEAM)["id"]
    lead_view = client.get(f"/api/projects/{pid}", headers=lakshmi).json()
    assert any(m.get("expected_pledge_cents") == 15000 for m in lead_view["members"])
    ravi = login(client, "ravi@example.com", "Ravi")[0]
    sponsor_view = client.get(f"/api/projects/{pid}", headers=ravi).json()
    assert sponsor_view["viewer"]["role"] == "SPONSOR"
    assert any(m.get("email") == "lakshmi@example.com" for m in sponsor_view["members"])
    assert all("expected_pledge_cents" not in m for m in sponsor_view["members"])


def test_a_signed_in_stranger_gets_the_public_view(client, lakshmi):
    pid = make_project(client, lakshmi)["id"]
    stranger = login(client, "stranger@example.com", "Stranger")[0]
    body = client.get(f"/api/projects/{pid}", headers=stranger).json()
    assert body["viewer"] is None and "@" not in str(body["members"])


def test_a_bad_token_is_an_error_not_a_public_view(client, lakshmi):
    pid = make_project(client, lakshmi)["id"]
    assert client.get(f"/api/projects/{pid}", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert client.get("/api/projects/9999").status_code == 404


def test_an_invitee_opening_the_project_is_recorded_as_viewed(client, lakshmi, db):
    pid = make_project(client, lakshmi, members=TEAM)["id"]
    ravi = login(client, "ravi@example.com", "Ravi")[0]
    m = db.scalars(select(ProjectMember).join(User).where(User.email == "ravi@example.com")).one()
    assert (m.invite_status, m.joined_at, m.last_seen_at) == ("INVITED", None, None)
    client.get(f"/api/projects/{pid}", headers=ravi)
    db.refresh(m)
    assert m.invite_status == "VIEWED" and m.joined_at is not None and m.last_seen_at is not None
    assert next(x for x in client.get(f"/api/projects/{pid}", headers=lakshmi).json()["members"]
                if x["display_name"] == "Ravi")["invite_status"] == "VIEWED"


# ---------------- members ----------------

def put_members(client, h, pid, members):
    return client.put(f"/api/projects/{pid}/members", json={"members": members}, headers=h)


def test_lead_can_invite_and_re_invite_without_duplicates(client, lakshmi, db):
    pid = make_project(client, lakshmi)["id"]
    r = put_members(client, lakshmi, pid, TEAM)
    assert r.status_code == 200 and len(r.json()["members"]) == 4
    r = put_members(client, lakshmi, pid, [{"email": "RAVI@example.com", "role": "SPONSOR", "expected_pledge_cents": 20000}])
    ravi = next(m for m in r.json()["members"] if m["display_name"] == "Ravi")
    assert len(r.json()["members"]) == 4 and ravi["expected_pledge_cents"] == 20000
    assert ravi["business_name"] == "Ravi's Fish Kitchen"                                  # untouched fields survive
    assert len(db.scalars(select(User).where(User.email == "ravi@example.com")).all()) == 1


@pytest.mark.parametrize("members,code", [
    ([{"email": "x@example.com", "role": "SPONSOR"}, {"email": "X@example.com", "role": "SPONSOR"}], "DUPLICATE_INVITEE"),
    ([{"email": "lakshmi@example.com", "role": "SPONSOR"}], "ROLE_LOCKED"),            # the lead cannot be re-invited
    ([{"email": "arjun@example.com", "role": "SPONSOR"}], "ROLE_LOCKED"),              # a freelancer is never a sponsor
    ([{"email": "ravi@example.com", "role": "FREELANCER"}], "ROLE_LOCKED"),
    ([{"email": "other@example.com", "role": "FREELANCER"}], "FREELANCER_EXISTS"),
    ([{"email": "z@example.com", "role": "FREELANCER", "expected_pledge_cents": 500}], "BAD_INVITEE"),
])
def test_invalid_invitations_are_refused_and_change_nothing(client, lakshmi, db, members, code):
    pid = make_project(client, lakshmi, members=TEAM)["id"]
    before = db.scalars(select(ProjectMember)).all()
    r = put_members(client, lakshmi, pid, members)
    assert r.status_code in (409, 422) and r.json()["error"]["code"] == code
    assert len(db.scalars(select(ProjectMember)).all()) == len(before)


def test_only_the_lead_can_invite(client, lakshmi):
    pid = make_project(client, lakshmi, members=TEAM)["id"]
    ravi = login(client, "ravi@example.com", "Ravi")[0]
    r = put_members(client, ravi, pid, [{"email": "friend@example.com", "role": "SPONSOR"}])
    assert r.status_code == 403
    assert put_members(client, {}, pid, TEAM).status_code == 401


def test_roles_and_input_are_validated(client, lakshmi):
    pid = make_project(client, lakshmi)["id"]
    for bad in ([{"email": "x@example.com", "role": "LEAD"}], [{"email": "not-an-email", "role": "SPONSOR"}],
                [{"email": "x@example.com", "role": "SPONSOR", "expected_pledge_cents": -5}], []):
        assert put_members(client, lakshmi, pid, bad).status_code == 422


@pytest.mark.parametrize("state,sponsor_ok,freelancer_ok", [
    ("DRAFT", True, True), ("REQUIREMENTS", True, True), ("BRD_REVIEW", False, True), ("CONTRACTING", False, True),
    ("CAMPAIGN_SETUP", False, False), ("PLEDGING", False, False),
])
def test_who_can_be_invited_depends_on_the_stage(client, lakshmi, db, state, sponsor_ok, freelancer_ok):
    pid = make_project(client, lakshmi)["id"]
    db.get(Project, pid).state = state
    db.commit()
    s = put_members(client, lakshmi, pid, [{"email": "s@example.com", "role": "SPONSOR"}])
    f = put_members(client, lakshmi, pid, [{"email": "f@example.com", "role": "FREELANCER"}])
    assert (s.status_code == 200) == sponsor_ok and (f.status_code == 200) == freelancer_ok
    for r, ok in ((s, sponsor_ok), (f, freelancer_ok)):
        if not ok:
            assert r.json()["error"]["code"] == "PROJECT_STATE"


# ---------------- transcripts ----------------

def upload_text(client, h, pid, text="Lakshmi: hello\nRavi: hi", name="meeting.txt"):
    return client.post(f"/api/projects/{pid}/transcripts", json={"text": text, "source_name": name}, headers=h)


def test_the_first_transcript_moves_the_project_to_requirements_and_is_logged(client, lakshmi, db):
    pid = make_project(client, lakshmi)["id"]
    r = upload_text(client, lakshmi, pid)
    assert r.status_code == 201
    body = r.json()
    assert body["project_state"] == "REQUIREMENTS" and body["line_count"] == 2 and body["replaced_earlier"] is False
    assert len(body["sha256"]) == 64 and body["source_name"] == "meeting.txt"
    memo = db.scalars(select(LedgerEntry).where(LedgerEntry.type == "STATE_CHANGE")).one()
    assert memo.meta_json["from"] == "DRAFT" and memo.meta_json["to"] == "REQUIREMENTS" and memo.actor.startswith("user:")


def test_pasted_text_needs_no_filename(client, lakshmi):
    pid = make_project(client, lakshmi)["id"]
    r = client.post(f"/api/projects/{pid}/transcripts", json={"text": "Lakshmi: hello"}, headers=lakshmi)
    assert r.status_code == 201 and r.json()["source_name"] == "pasted-text.txt"


def test_uploading_the_sample_file_gives_numbered_lines(client, lakshmi):
    pid = make_project(client, lakshmi)["id"]
    r = client.post(f"/api/projects/{pid}/transcripts", files={"file": ("velugu.txt", SAMPLE.read_bytes(), "text/plain")},
                    headers=lakshmi)
    assert r.status_code == 201
    got = client.get(f"/api/projects/{pid}/transcript", headers=lakshmi).json()
    expected = SAMPLE.read_text(encoding="utf-8").strip("\n").split("\n")
    assert got["line_count"] == len(expected) == len(got["lines"])
    assert got["lines"][0] == {"n": 1, "text": expected[0]} and got["lines"][3]["n"] == 4
    assert got["lines"][3]["text"].startswith("Lakshmi: Thanks for coming") and got["source_name"] == "velugu.txt"


def test_a_vtt_file_is_cleaned_on_upload(client, lakshmi):
    pid = make_project(client, lakshmi)["id"]
    vtt = b"WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n<v Meena>No payments on the site.</v>\n"
    assert client.post(f"/api/projects/{pid}/transcripts", files={"file": ("m.vtt", vtt, "text/vtt")}, headers=lakshmi).status_code == 201
    assert client.get(f"/api/projects/{pid}/transcript", headers=lakshmi).json()["lines"] == [
        {"n": 1, "text": "Meena: No payments on the site."}]


def test_a_second_upload_replaces_the_first_without_another_state_change(client, lakshmi, db):
    pid = make_project(client, lakshmi)["id"]
    upload_text(client, lakshmi, pid, "old one")
    r = upload_text(client, lakshmi, pid, "new one\nwith two lines", "v2.txt")
    assert r.status_code == 201 and r.json()["replaced_earlier"] is True and r.json()["project_state"] == "REQUIREMENTS"
    latest = client.get(f"/api/projects/{pid}/transcript", headers=lakshmi).json()
    assert latest["source_name"] == "v2.txt" and latest["line_count"] == 2
    assert len(db.scalars(select(Transcript)).all()) == 2, "history is kept"
    assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.type == "STATE_CHANGE")).all()) == 1


@pytest.mark.parametrize("kwargs,status,code", [
    ({"json": {"text": "   "}}, 422, "TRANSCRIPT_EMPTY"),
    ({"json": {"text": "hello", "source_name": "minutes.pdf"}}, 422, "TRANSCRIPT_BAD_TYPE"),
    ({"json": {"text": "x" * 300_001}}, 413, "TRANSCRIPT_TOO_LARGE"),
    ({"json": {"nope": 1}}, 422, "TRANSCRIPT_NO_TEXT"),
    ({"json": ["text"]}, 422, "TRANSCRIPT_NO_TEXT"),
    ({"content": b"{not json", "headers_extra": {"content-type": "application/json"}}, 422, "BAD_JSON"),
    ({"files": {"other": ("a.txt", b"hi", "text/plain")}}, 422, "TRANSCRIPT_NO_FILE"),
    ({"files": {"file": ("a.txt", b"caf\xe9", "text/plain")}}, 422, "TRANSCRIPT_NOT_UTF8"),
    ({"files": {"file": ("a.mp3", b"ID3", "audio/mpeg")}}, 422, "TRANSCRIPT_BAD_TYPE"),
])
def test_bad_transcripts_are_refused_with_a_clear_code_and_nothing_is_stored(client, lakshmi, db, kwargs, status, code):
    pid = make_project(client, lakshmi)["id"]
    extra = kwargs.pop("headers_extra", {})
    r = client.post(f"/api/projects/{pid}/transcripts", headers={**lakshmi, **extra}, **kwargs)
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert db.scalars(select(Transcript)).first() is None and db.get(Project, pid).state == "DRAFT"


def test_only_the_lead_can_upload(client, lakshmi):
    pid = make_project(client, lakshmi, members=TEAM)["id"]
    ravi = login(client, "ravi@example.com", "Ravi")[0]
    assert upload_text(client, ravi, pid).status_code == 403
    stranger = login(client, "stranger@example.com", "S")[0]
    assert upload_text(client, stranger, pid).status_code == 403
    assert client.post(f"/api/projects/{pid}/transcripts", json={"text": "x"}).status_code == 401


@pytest.mark.parametrize("state", ["BRD_REVIEW", "CONTRACTING", "PLEDGING", "IN_PROGRESS"])
def test_the_transcript_is_locked_once_the_brd_is_being_reviewed(client, lakshmi, db, state):
    pid = make_project(client, lakshmi)["id"]
    upload_text(client, lakshmi, pid)
    db.get(Project, pid).state = state
    db.commit()
    r = upload_text(client, lakshmi, pid, "sneaky rewrite")
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROJECT_STATE"


def test_transcript_is_for_members_only_and_not_in_the_public_detail(client, lakshmi):
    pid = make_project(client, lakshmi, members=TEAM)["id"]
    assert client.get(f"/api/projects/{pid}/transcript", headers=lakshmi).status_code == 404
    upload_text(client, lakshmi, pid, "Lakshmi: private business plans")
    assert client.get(f"/api/projects/{pid}/transcript").status_code == 401
    assert client.get(f"/api/projects/{pid}/transcript", headers=login(client, "stranger@example.com", "S")[0]).status_code == 403
    ravi = login(client, "ravi@example.com", "Ravi")[0]
    assert client.get(f"/api/projects/{pid}/transcript", headers=ravi).json()["lines"][0]["text"].startswith("Lakshmi")
    public = client.get(f"/api/projects/{pid}").json()
    assert "private business plans" not in str(public) and "transcript" not in public
    member_view = client.get(f"/api/projects/{pid}", headers=ravi).json()
    assert member_view["transcript"]["line_count"] == 1 and "lines" not in member_view["transcript"]
    assert member_view["state"] == "REQUIREMENTS"


def test_lead_can_remove_invitee_before_lock_and_participation(client, lakshmi, db):
    """GAP-14: Lead can delete an invitee typo before sponsor lock/participation."""
    from app.models import ProjectMember

    created = make_project(client, lakshmi, members=TEAM)
    pid = created["id"]
    ravi_row = next(m for m in created["members"] if m["role"] == "SPONSOR")
    lead_row = next(m for m in created["members"] if m["role"] == "LEAD")
    arjun_row = next(m for m in created["members"] if m["role"] == "FREELANCER")
    ravi_hdr = login(client, "ravi@example.com", "Ravi")[0]

    assert client.delete(f"/api/projects/{pid}/members/{ravi_row['id']}", headers=ravi_hdr).status_code == 403
    assert client.delete(f"/api/projects/{pid}/members/{lead_row['id']}", headers=lakshmi).status_code == 409

    removed = client.delete(f"/api/projects/{pid}/members/{ravi_row['id']}", headers=lakshmi)
    assert removed.status_code == 200
    assert all(m["id"] != ravi_row["id"] for m in removed.json()["members"])
    assert db.get(ProjectMember, ravi_row["id"]) is None

    db.get(Project, pid).state = "CONTRACTING"
    db.commit()
    assert client.delete(f"/api/projects/{pid}/members/{arjun_row['id']}", headers=lakshmi).status_code == 200
