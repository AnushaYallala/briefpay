import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.agents.ba_agent import BAAgent, BAQuestionsAgent
from app.models import BAAnswer, BAQuestion, BAScore, Job, ProjectMember, User
from app.schemas.ba import BAQuestion as QuestionSchema
from app.services import ba_rounds as rounds
from app.services import ba_service as svc
from tests.ba_factory import R0, R1, R2, conflict, question, questions, requirement
from tests.factories import scripted_adapter
from tests.test_ba_service import Setup


@pytest.fixture()
def s(db):
    return Setup(db)


def agents(s, *outputs):
    """BAAgent and BAQuestionsAgent sharing one scripted model: outputs are consumed in call order."""
    adapter, backend = scripted_adapter(s.db, *outputs)
    return BAAgent(adapter), BAQuestionsAgent(adapter), backend


def open_qs(s):
    return list(s.db.scalars(select(BAQuestion).where(BAQuestion.status == "OPEN").order_by(BAQuestion.id)))


def jobs_of(s, type_="BA_RUN"):
    return list(s.db.scalars(select(Job).where(Job.type == type_)))


# ---------------- the question schema ----------------

def test_a_question_must_be_short_plain_and_have_sane_options():
    ok = question()
    assert QuestionSchema.model_validate(ok).suggested_options == ["Enquiry form only", "Online booking"]
    assert QuestionSchema.model_validate({**ok, "suggested_options": []}).suggested_options is None
    assert QuestionSchema.model_validate({**ok, "suggested_options": None}).suggested_options is None
    for bad in ({"question": " ".join(["word"] * 31)}, {"question": "no"}, {"suggested_options": ["only one"]},
                {"suggested_options": ["a", "b", "c", "d", "e"]}, {"suggested_options": ["x" * 81, "y"]},
                {"dimension": "D11"}, {"addressed_to": ["EVERYONE"]}):
        with pytest.raises(ValidationError):
            QuestionSchema.model_validate({**ok, **bad})
    assert QuestionSchema.model_validate({**ok, "question": " ".join(["word"] * 30)})                # exactly 30 is fine


# ---------------- filtering the AI's questions ----------------

def proposed(*qs):
    return [QuestionSchema.model_validate(q) for q in qs]


def test_unknown_people_collapse_to_everyone_and_real_ones_are_kept():
    out = rounds.filter_questions(proposed(question(to=(1, 2, 99)), question("D6", "A second question about testing?", to=(99,)),
                                           question("D7", "Who supplies the photos?", to=("ALL", 1))),
                                  gap_dims={"D5", "D6", "D7"}, sponsor_ids={1, 2, 3}, already_asked=[])
    assert [q["addressed_to"] for q in out] == [[1, 2], ["ALL"], ["ALL"]]


def test_only_dimensions_that_still_have_a_gap_get_questions():
    out = rounds.filter_questions(proposed(question("D5"), question("D8", "What colours do you like?")),
                                  gap_dims={"D5"}, sponsor_ids={1}, already_asked=[])
    assert [q["dimension"] for q in out] == ["D5"]


def test_a_question_is_never_asked_twice_even_with_different_punctuation_or_case():
    text = "Should visitors be able to book online, or only send an enquiry?"
    out = rounds.filter_questions(proposed(question(text=text.upper().replace("?", " ?!")), question("D6", "A new one about tests?")),
                                  gap_dims={"D5", "D6"}, sponsor_ids={1}, already_asked=[text])
    assert [q["question"] for q in out] == ["A new one about tests?"]
    twice = rounds.filter_questions(proposed(question(), question()), gap_dims={"D5"}, sponsor_ids={1}, already_asked=[])
    assert len(twice) == 1                                                                           # repeats within one batch too


def test_at_most_five_questions_in_the_ais_order():
    qs = proposed(*[question(f"D{i}", f"Distinct question number {i} about the website?") for i in range(1, 9)])
    out = rounds.filter_questions(qs, gap_dims={f"D{i}" for i in range(1, 9)}, sponsor_ids={1}, already_asked=[])
    assert [q["dimension"] for q in out] == ["D1", "D2", "D3", "D4", "D5"]


# ---------------- running a round ----------------

def test_round_zero_scores_then_asks_the_ranked_questions(s):
    a, qa, backend = agents(s, s.out(R0, conflicts=[conflict()], out_of_scope=[]),
                            questions(question(to=s.member_ids[:2]), question("D6", "What should a visitor see when the enquiry form works?")))
    info = rounds.run_round(s.db, s.project, a, qa)
    assert info == {"score": 58, "round": 0, "state": "ACTIVE", "questions": 2}
    qs = rounds.session_questions(s.db, svc.get_session(s.db, s.project.id).id)
    assert [(q.round, q.status, q.dimension) for q in qs] == [(0, "OPEN", "D5"), (0, "OPEN", "D6")]
    assert qs[0].addressed_to_json == list(s.member_ids[:2]) and qs[0].suggested_options_json == ["Enquiry form only", "Online booking"]
    # what the question writer was told: ranked gaps (largest first), the red gates, and no emails
    ask = backend.calls[1]
    trusted = ask["parts"][0].text
    assert '"gaps_most_important_first"' in trusted and '"red_gates"' in trusted and "@" not in trusted + ask["system"]
    gaps_json = trusted[trusted.index('"gaps_most_important_first"'):]
    assert gaps_json.index('"D5"') < gaps_json.index('"D8"')
    assert any('"questions-already-asked"' in p.text or "questions-already-asked" in p.text for p in ask["parts"])


def test_running_the_same_round_again_neither_rescoring_nor_reasking(s):
    a, qa, backend = agents(s, s.out(R0, conflicts=[conflict()]), questions(question()))
    rounds.run_round(s.db, s.project, a, qa)
    calls = len(backend.calls)
    again = rounds.run_round(s.db, s.project, a, qa)
    assert len(backend.calls) == calls and again["questions"] == 1
    assert len(s.db.scalars(select(BAScore)).all()) == 1 and len(s.db.scalars(select(BAQuestion)).all()) == 1


def test_if_writing_questions_fails_the_score_is_kept_and_a_retry_resumes(s):
    a, qa, backend = agents(s, s.out(R0, conflicts=[conflict()]), RuntimeError("quota"), questions(question()))
    with pytest.raises(svc.BAError) as e:
        rounds.run_round(s.db, s.project, a, qa)
    assert e.value.code == "AI_UNAVAILABLE" and len(s.db.scalars(select(BAScore)).all()) == 1
    assert s.db.scalars(select(BAQuestion)).first() is None
    scored_calls = [c for c in backend.calls if c["agent"] == "BA_SCORE"]
    info = rounds.run_round(s.db, s.project, a, qa)
    assert info["questions"] == 1 and len([c for c in backend.calls if c["agent"] == "BA_SCORE"]) == len(scored_calls), "no second scoring"


def test_a_ready_score_asks_nothing(s):
    a, qa, backend = agents(s, s.out(R2, conflicts=[conflict(True, "Enquiry form only")]))
    info = rounds.run_round(s.db, s.project, a, qa)
    assert info["state"] == "READY" and info["questions"] == 0 and len(backend.calls) == 1


def test_a_changed_transcript_is_rescored_in_the_same_round_without_asking_again(s):
    from app.services import project_ops as ops
    a, qa, backend = agents(s, s.out(R0, conflicts=[conflict()]), questions(question()),
                            s.out(R1, conflicts=[conflict()], refs=("L1-L2",)))     # the new transcript has only 2 lines
    rounds.run_round(s.db, s.project, a, qa)
    ops.add_transcript(s.db, s.project, s.db.get(User, s.project.lead_user_id), source_name="v2.txt", raw="Brand new\nmeeting text")
    info = rounds.run_round(s.db, s.project, a, qa)
    scores = list(s.db.scalars(select(BAScore).order_by(BAScore.id)))
    assert [(r.round, r.total) for r in scores] == [(0, 58), (0, 79)], "the old score was for a transcript that no longer exists"
    assert info["questions"] == 1 and len(s.db.scalars(select(BAQuestion)).all()) == 1


def test_a_fallback_question_is_used_when_the_ai_only_repeats_itself(s):
    first = question()
    a, qa, _ = agents(s, s.out(R0, conflicts=[conflict()]), questions(first))
    rounds.run_round(s.db, s.project, a, qa)
    for q in open_qs(s):
        q.status = "SKIPPED"
    sess = svc.get_session(s.db, s.project.id)
    sess.round = 1
    a2, qa2, _ = agents(s, s.out(R0, conflicts=[conflict()]), questions(first))                                      # same question again
    info = rounds.run_round(s.db, s.project, a2, qa2)
    assert info["questions"] == 1
    new = [q for q in open_qs(s) if q.round == 1][0]
    assert new.question in rounds.FALLBACK_QUESTIONS.values() and new.addressed_to_json == ["ALL"]


def test_reaching_the_round_limit_without_a_ready_score_stops_asking(s):
    sess = svc.get_or_create_session(s.db, s.project)
    sess.round = 5
    a, qa, backend = agents(s, s.out(R1, conflicts=[conflict()]))
    info = rounds.run_round(s.db, s.project, a, qa)
    assert info["state"] == "MAX_ROUNDS" and info["questions"] == 0 and len(backend.calls) == 1
    assert s.db.scalars(select(BAQuestion)).first() is None


# ---------------- answering ----------------

def asked(s, *qs, round_=0):
    a, qa, backend = agents(s, s.out(R0, conflicts=[conflict()]), questions(*qs))
    rounds.run_round(s.db, s.project, a, qa)
    return open_qs(s), backend


def test_a_named_question_needs_every_named_person_an_all_question_needs_one(s):
    ravi, meena = s.sponsors
    [named, everyone], _ = asked(s, question(to=(ravi.id, meena.id)), question("D6", "What should a visitor see when it works?"))
    out = rounds.answer_question(s.db, named, ravi, "Enquiry form only", "Enquiry form only")
    assert out == {"question_status": "OPEN", "round_complete": False}
    out = rounds.answer_question(s.db, named, meena, "Agreed, no payments", None)
    assert out["question_status"] == "ANSWERED" and out["round_complete"] is False                      # the other question is open
    out = rounds.answer_question(s.db, everyone, s.lead, "A success message with a reference number", None)
    assert out == {"question_status": "ANSWERED", "round_complete": True}


def test_completing_a_round_advances_it_and_queues_the_next_scoring(s):
    [q1, q2], _ = asked(s, question(), question("D6", "What should a visitor see when it works?"))
    sess = svc.get_session(s.db, s.project.id)
    assert (sess.round, len(jobs_of(s))) == (0, 0)
    rounds.answer_question(s.db, q1, s.lead, "Enquiry only", None)
    assert (sess.round, len(jobs_of(s))) == (0, 0), "not complete yet"
    rounds.skip_question(s.db, q2)
    assert sess.round == 1 and len(jobs_of(s)) == 1 and jobs_of(s)[0].payload_json == {"project_id": s.project.id}


def test_who_may_answer(s):
    [q], _ = asked(s, question(to=(s.sponsors[0].id,)))
    freelancer = s.db.scalars(select(ProjectMember).where(ProjectMember.role == "FREELANCER")).first()
    for who, code in ((s.sponsors[1], "NOT_ADDRESSED"), (s.lead, "NOT_ADDRESSED"), (freelancer, "NOT_ADDRESSED")):
        with pytest.raises(svc.BAError) as e:
            rounds.answer_question(s.db, q, who, "I will answer anyway", None)
        assert e.value.code == code and e.value.status == 403
    rounds.answer_question(s.db, q, s.sponsors[0], "My answer", None)


def test_answer_validation(s):
    [q], _ = asked(s, question(to=("ALL",)))
    for text, opt, code in (("", None, "EMPTY_ANSWER"), ("   ", None, "EMPTY_ANSWER"), ("yes", "Carrier pigeon", "BAD_OPTION")):
        with pytest.raises(svc.BAError) as e:
            rounds.answer_question(s.db, q, s.lead, text, opt)
        assert e.value.code == code and e.value.status == 422
    rounds.answer_question(s.db, q, s.lead, "something else entirely", "Other")                      # "Other" is always allowed


def test_nobody_answers_twice_and_closed_questions_stay_closed(s):
    [q1, q2], _ = asked(s, question(to=("ALL",)), question("D6", "What should a visitor see when it works?", to=("ALL",)))
    rounds.answer_question(s.db, q1, s.lead, "first", None)
    with pytest.raises(svc.BAError) as e:
        rounds.answer_question(s.db, q1, s.lead, "second", None)
    assert e.value.code == "QUESTION_CLOSED"                                                          # q1 is already ANSWERED
    q3_names = rounds.answer_question(s.db, q2, s.lead, "x", None)
    assert q3_names["round_complete"]
    with pytest.raises(svc.BAError) as e:
        rounds.answer_question(s.db, q2, s.sponsors[0], "too late", None)                             # the round has moved on
    assert e.value.code == "QUESTION_CLOSED"
    with pytest.raises(svc.BAError):
        rounds.skip_question(s.db, q2)


def test_defence_in_depth_a_stale_round_or_a_closed_session_never_takes_answers(s):
    [q], _ = asked(s, question(to=("ALL",)))
    sess = svc.get_session(s.db, s.project.id)
    sess.round = 1                                                  # inconsistent on purpose: an OPEN question from round 0
    with pytest.raises(svc.BAError) as e:
        rounds.answer_question(s.db, q, s.lead, "late", None)
    assert e.value.code == "QUESTION_CLOSED"
    with pytest.raises(svc.BAError):
        rounds.skip_question(s.db, q)
    sess.round = 0
    for closed in ("MAX_ROUNDS", "FINALIZED", "BRD_GENERATED"):
        sess.state = closed
        with pytest.raises(svc.BAError) as e:
            rounds.answer_question(s.db, q, s.lead, "too late", None)
        assert e.value.code == "QUESTION_CLOSED"
    sess.state = "ACTIVE"
    assert rounds.answer_question(s.db, q, s.lead, "on time", None)["question_status"] == "ANSWERED"


def test_the_same_person_cannot_double_answer_a_shared_question(s):
    ravi, meena = s.sponsors
    [q], _ = asked(s, question(to=(ravi.id, meena.id)))
    rounds.answer_question(s.db, q, ravi, "mine", None)
    with pytest.raises(svc.BAError) as e:
        rounds.answer_question(s.db, q, ravi, "mine again", None)
    assert e.value.code == "ALREADY_ANSWERED"
    assert len(s.db.scalars(select(BAAnswer)).all()) == 1


# ---------------- the whole conversation: 58 -> 79 -> 93 ----------------

def test_three_rounds_take_the_demo_scene_from_58_to_93_and_ready(s):
    ravi, meena = s.sponsors
    outs = [s.out(R0, conflicts=[conflict()], requirements=[requirement("R1", by=s.member_ids, criteria=())], out_of_scope=[]),
            questions(question(to=(s.lead.id, meena.id)), question("D6", "What should a visitor see when the enquiry form works?"),
                      question("D7", "Who will supply the photos and text, and by when?")),
            s.out(R1, conflicts=[conflict()]),
            questions(question("D3", "Which of your own needs is still missing from the list?", options=None)),
            s.out(R2, conflicts=[conflict(True, "Enquiry form only, no payments on the site")])]
    a, qa, backend = agents(s, *outs)
    assert rounds.run_round(s.db, s.project, a, qa)["score"] == 58
    sess = svc.get_session(s.db, s.project.id)
    for q in open_qs(s):
        who = s.lead if "ALL" in q.addressed_to_json else next(m for m in (s.lead, ravi, meena) if m.id in q.addressed_to_json)
        for member in ([s.lead, meena] if q.addressed_to_json == [s.lead.id, meena.id] else [who]):
            rounds.answer_question(s.db, q, member, f"answer from {member.id}", None)
    assert sess.round == 1 and len(jobs_of(s)) == 1

    assert rounds.run_round(s.db, s.project, a, qa) == {"score": 79, "round": 1, "state": "ACTIVE", "questions": 1}
    [q2] = open_qs(s)
    assert q2.round == 1
    rounds.answer_question(s.db, q2, s.lead, "I need the boat tours listed", None)
    assert sess.round == 2

    final = rounds.run_round(s.db, s.project, a, qa)
    assert final == {"score": 93, "round": 2, "state": "READY", "questions": 0}
    assert [r.total for r in s.db.scalars(select(BAScore).order_by(BAScore.id))] == [58, 79, 93]
    assert [r.round for r in s.db.scalars(select(BAScore).order_by(BAScore.id))] == [0, 1, 2]
    # round 1 scoring saw round 0's answers and its own previous extraction
    texts = " ".join(p.text for p in backend.calls[2]["parts"])
    assert "answer from" in texts and "previous-extraction" in texts


# ---------------- manual runs, rate limit, finalize ----------------

def test_a_manual_run_queues_a_job_and_is_refused_when_it_cannot_help(s):
    assert isinstance(rounds.request_run(s.db, s.project), int) and len(jobs_of(s)) == 1
    a, qa, _ = agents(s, s.out(R0, conflicts=[conflict()]), questions(question()))
    rounds.run_round(s.db, s.project, a, qa)
    with pytest.raises(svc.BAError) as e:
        rounds.request_run(s.db, s.project)
    assert e.value.code == "QUESTIONS_OPEN"
    s.project.state = "BRD_REVIEW"
    with pytest.raises(svc.BAError) as e:
        rounds.request_run(s.db, s.project)
    assert e.value.code == "PROJECT_STATE"


@pytest.mark.parametrize("state", ["MAX_ROUNDS", "FINALIZED", "BRD_GENERATED"])
def test_no_runs_once_the_analysis_is_over(s, state):
    svc.get_or_create_session(s.db, s.project).state = state
    with pytest.raises(svc.BAError) as e:
        rounds.request_run(s.db, s.project)
    assert e.value.code == "BA_DONE"


def test_eight_runs_per_hour_per_project(s):
    for _ in range(8):
        rounds.enqueue_run(s.db, s.project.id)
    with pytest.raises(svc.BAError) as e:
        rounds.request_run(s.db, s.project)
    assert e.value.code == "RATE_LIMITED" and e.value.status == 429
    rounds.enqueue_run(s.db, s.project.id + 1)                                                        # other projects don't count
    assert rounds.recent_runs(s.db, s.project.id) == 8


def test_finalize_only_after_the_round_limit_and_it_closes_the_analysis(s):
    with pytest.raises(svc.BAError) as e:
        rounds.finalize(s.db, s.project)
    assert e.value.code == "NOT_FINALIZABLE"
    a, qa, _ = agents(s, s.out(R0, conflicts=[conflict()]), questions(question()))
    rounds.run_round(s.db, s.project, a, qa)
    with pytest.raises(svc.BAError):
        rounds.finalize(s.db, s.project)                                                              # ACTIVE, not MAX_ROUNDS
    sess = svc.get_session(s.db, s.project.id)
    sess.state = "MAX_ROUNDS"
    done = rounds.finalize(s.db, s.project)
    assert done.state == "FINALIZED" and all(q.status == "SKIPPED" for q in s.db.scalars(select(BAQuestion)))
    with pytest.raises(svc.BAError) as e:
        svc.score_round(s.db, s.project, a)
    assert e.value.code == "BA_DONE"
