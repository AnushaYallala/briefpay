"""Groq for the brief writer only (D-062): the backend, the router and the wiring. Everything runs on fake clients: no key, no network."""
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.agents import brd_generator
from app.agents import llm_adapter as la
from app.agents.llm_adapter import (
    BRD_AGENT, AgentError, GroqBackend, ImagePart, LLMAdapter, MissingBackend, RawResult, ReplayBackend, RoutedBackend, TextPart, build_adapter,
)
from app.config import Settings
from app.models import AgentRun


class Out(BaseModel):
    score: int
    note: str


class FakeGroq:
    """Stands in for the Groq SDK client: records every request and replays scripted replies."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def reply(content, prompt=11, completion=7):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion))


def backend(*replies, model="llama-test"):
    client = FakeGroq(*replies)
    return GroqBackend("key", model, client=client), client


def gen(b, parts=None, system="SYS", temperature=0.2, agent=BRD_AGENT):
    return b.generate(agent=agent, in_hash="h", system=system, parts=parts or [TextPart("hello")], schema=Out, temperature=temperature)


# ---------------- the backend ----------------

def test_it_asks_for_json_with_the_schema_in_the_instructions_and_returns_the_answer_with_its_cost():
    b, client = backend(reply('{"score": 3, "note": "ok"}'))
    r = gen(b, [TextPart("first part"), TextPart("second part")], temperature=0.1)
    assert (r.data, r.provider, r.model, r.input_tokens, r.output_tokens, r.replayed) == ({"score": 3, "note": "ok"}, "groq", "llama-test", 11, 7, False)
    [req] = client.requests
    assert req["model"] == "llama-test" and req["temperature"] == 0.1 and req["response_format"] == {"type": "json_object"}
    assert req["max_completion_tokens"] == GroqBackend.MAX_OUTPUT_TOKENS
    system, user = req["messages"]
    assert system["role"] == "system" and system["content"].startswith("SYS\n\nReply with ONE JSON object")
    assert "JSON" in system["content"] and '"score"' in system["content"] and '"note"' in system["content"]       # JSON mode needs the word, and the model needs the shape
    assert user == {"role": "user", "content": "first part\n\nsecond part"}


def test_the_schema_text_is_the_same_every_time_so_the_audit_hash_story_holds():
    b, client = backend(reply("{}"), reply("{}"))
    gen(b)
    gen(b)
    assert client.requests[0]["messages"][0] == client.requests[1]["messages"][0]


def test_a_missing_usage_block_is_fine():
    b, _ = backend(SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"score": 1, "note": "x"}'))]))
    r = gen(b)
    assert (r.input_tokens, r.output_tokens) == (None, None) and r.data["score"] == 1


def test_it_refuses_images_without_calling_groq():
    b, client = backend(reply("{}"))
    with pytest.raises(AgentError, match="text-only"):
        gen(b, [TextPart("x"), ImagePart(b"png", "image/png")], agent="VERIFY_JUDGE")
    assert client.requests == []


@pytest.mark.parametrize("content", ["not json at all", "", None, "{"])
def test_a_reply_that_is_not_json_becomes_a_marker_the_schema_check_rejects(content):
    b, _ = backend(reply(content))
    r = gen(b)
    assert "__invalid_json__" in r.data and (r.provider, r.model) == ("groq", "llama-test")


def test_a_reply_with_no_choices_is_treated_the_same_way():
    b, _ = backend(SimpleNamespace(choices=[], usage=None))
    assert "__invalid_json__" in gen(b).data


def test_a_failing_call_becomes_an_agent_error_that_names_the_cause():
    b, _ = backend(RuntimeError("rate limit reached"))
    with pytest.raises(AgentError, match="groq call failed: RuntimeError: rate limit reached"):
        gen(b)


def test_a_model_name_is_required():
    with pytest.raises(AgentError, match="GROQ_MODEL is not set"):
        GroqBackend("key", "", client=FakeGroq())


def test_the_sdk_is_only_loaded_when_a_real_call_is_set_up():
    real = GroqBackend("some-key", "llama-test")                                # builds the real client; no network until a call is made
    assert type(real._client).__module__.startswith("groq")


# ---------------- through the adapter: audit rows, retry, failure ----------------

@pytest.fixture()
def factory(db):
    return sessionmaker(bind=db.get_bind(), expire_on_commit=False)


def audit(factory):
    s = factory()
    try:
        return list(s.scalars(select(AgentRun).order_by(AgentRun.id)))
    finally:
        s.close()


def ask(adapter, agent=BRD_AGENT):
    return adapter.generate_json(system="sys", parts=[TextPart("hi")], schema=Out, agent=agent, project_id=1, prompt_version="v1")


def test_a_good_answer_is_logged_as_groq_with_its_model_and_tokens(factory):
    b, _ = backend(reply('{"score": 5, "note": "fine"}'))
    out = ask(LLMAdapter(b, factory))
    assert out == Out(score=5, note="fine")
    [row] = audit(factory)
    assert (row.agent, row.provider, row.model, row.status, row.input_tokens, row.output_tokens) == (BRD_AGENT, "groq", "llama-test", "OK", 11, 7)


def test_a_bad_first_answer_is_retried_once_with_the_complaint_and_then_accepted(factory):
    b, client = backend(reply('{"score": "many"}'), reply('{"score": 2, "note": "now fine"}'))
    assert ask(LLMAdapter(b, factory)).score == 2
    assert len(client.requests) == 2 and "failed validation" in client.requests[1]["messages"][0]["content"]
    assert [r.status for r in audit(factory)] == ["OK"]


def test_two_bad_answers_are_recorded_as_a_schema_failure(factory):
    b, _ = backend(reply("nonsense"), reply("still nonsense"))
    with pytest.raises(la.AgentSchemaInvalid):
        ask(LLMAdapter(b, factory))
    [row] = audit(factory)
    assert (row.status, row.provider) == ("SCHEMA_INVALID", "groq") and row.output_json is None


def test_a_failing_call_is_recorded_as_an_error_with_the_cause(factory):
    b, _ = backend(RuntimeError("503"))
    with pytest.raises(AgentError):
        ask(LLMAdapter(b, factory))
    [row] = audit(factory)
    assert row.status == "ERROR" and "groq call failed" in row.error and "503" in row.error


# ---------------- the router ----------------

class Named:
    def __init__(self, provider, model="m"):
        self.provider, self.model, self.calls = provider, model, []

    def generate(self, **kw):
        self.calls.append(kw["agent"])
        return RawResult(data={"score": 1, "note": self.provider}, provider=self.provider, model=self.model)


def route_call(router, agent):
    return router.generate(agent=agent, in_hash="h", system="s", parts=[TextPart("x")], schema=Out, temperature=0.2)


def test_the_brief_writer_goes_to_its_own_backend_and_everything_else_to_the_default():
    default, groq = Named("gemini"), Named("groq")
    router = RoutedBackend(default, {BRD_AGENT: groq})
    assert route_call(router, BRD_AGENT).data["note"] == "groq"
    for agent in ("BA_SCORE", "BA_QUESTIONS", "VERIFY_JUDGE", "VERIFY_QUESTIONS", "GUARDIAN_LLM", "STRATEGIST"):
        assert route_call(router, agent).data["note"] == "gemini", agent
    assert groq.calls == [BRD_AGENT] and len(default.calls) == 6
    assert (router.provider, router.model) == ("gemini", "m")


def test_without_a_default_only_the_routed_agent_works_and_the_others_say_why():
    router = RoutedBackend(None, {BRD_AGENT: Named("groq")})
    assert route_call(router, BRD_AGENT).data["note"] == "groq"
    with pytest.raises(AgentError, match="BA_SCORE: no AI provider is configured"):
        route_call(router, "BA_SCORE")
    assert router.provider == "groq"


def test_a_provider_without_a_key_fails_with_its_own_message():
    with pytest.raises(AgentError, match="needs GROQ_API_KEY"):
        MissingBackend("groq", "BRD_PROVIDER=groq needs GROQ_API_KEY").generate(agent="x")


# ---------------- the wiring ----------------

class SpyGemini(Named):
    def __init__(self, key, model):
        super().__init__("gemini", model)
        self.key = key


class SpyGroq(Named):
    def __init__(self, key, model):
        super().__init__("groq", model)
        self.key = key


@pytest.fixture()
def spies(monkeypatch):
    monkeypatch.setattr(la, "GeminiBackend", SpyGemini)
    monkeypatch.setattr(la, "GroqBackend", SpyGroq)


def settings(**kw):
    return Settings(_env_file=None, **kw)


def live(adapter):
    """The backend that is asked when a recorded answer is missing."""
    return adapter.backend.fallback


def test_by_default_nothing_changes_and_groq_is_not_involved(spies, factory):
    a = build_adapter(settings(ai_provider="replay_or_real", gemini_api_key="g", ai_model="gm", groq_api_key="q"), factory)
    assert isinstance(live(a), SpyGemini) and not isinstance(live(a), RoutedBackend)


def test_with_both_keys_the_brief_writer_uses_groq_and_the_rest_use_gemini(spies, factory):
    a = build_adapter(settings(ai_provider="replay_or_real", gemini_api_key="g", ai_model="gm", brd_provider="groq", groq_api_key="q", groq_model="llama-x"), factory)
    router = live(a)
    assert isinstance(router, RoutedBackend)
    assert route_call(router, BRD_AGENT).provider == "groq" and route_call(router, "BA_SCORE").provider == "gemini"
    assert (router.routes[BRD_AGENT].key, router.routes[BRD_AGENT].model) == ("q", "llama-x")
    assert (router.default.key, router.default.model) == ("g", "gm")


def test_the_choice_of_provider_is_not_case_sensitive(spies, factory):
    a = build_adapter(settings(ai_provider="replay_or_real", gemini_api_key="g", ai_model="gm", brd_provider=" Groq ", groq_api_key="q"), factory)
    assert isinstance(live(a), RoutedBackend)


def test_groq_alone_serves_the_brief_writer_and_every_other_agent_says_it_has_no_provider(spies, factory):
    a = build_adapter(settings(ai_provider="replay_or_real", brd_provider="groq", groq_api_key="q"), factory)
    router = live(a)
    assert route_call(router, BRD_AGENT).provider == "groq"
    with pytest.raises(AgentError, match="no AI provider is configured"):
        route_call(router, "STRATEGIST")


def test_asking_for_groq_without_a_key_fails_only_the_brief_writer_and_says_why(spies, factory):
    a = build_adapter(settings(ai_provider="replay_or_real", gemini_api_key="g", ai_model="gm", brd_provider="groq"), factory)
    router = live(a)
    with pytest.raises(AgentError, match="BRD_PROVIDER=groq needs GROQ_API_KEY"):
        route_call(router, BRD_AGENT)
    assert route_call(router, "BA_SCORE").provider == "gemini"


def test_an_unknown_brief_provider_is_refused_at_once(spies, factory):
    with pytest.raises(AgentError, match="unknown BRD_PROVIDER openai"):
        build_adapter(settings(ai_provider="replay_or_real", brd_provider="openai"), factory)


def test_replay_only_mode_never_goes_live_even_if_groq_is_asked_for(spies, factory, tmp_path):
    a = build_adapter(settings(ai_provider="replay", brd_provider="groq", groq_api_key="q"), factory, fixtures_dir=tmp_path)
    assert isinstance(a.backend, ReplayBackend) and a.backend.fallback is None


def test_strict_gemini_mode_still_routes_the_brief_writer(spies, factory):
    a = build_adapter(settings(ai_provider="gemini", gemini_api_key="g", ai_model="gm", brd_provider="groq", groq_api_key="q"), factory)
    assert isinstance(a.backend, RoutedBackend) and route_call(a.backend, BRD_AGENT).provider == "groq"


def test_strict_gemini_mode_without_a_gemini_key_is_refused_unless_groq_will_serve(spies, factory):
    with pytest.raises(AgentError, match="needs GEMINI_API_KEY"):
        build_adapter(settings(ai_provider="gemini"), factory)


def test_a_recorded_answer_wins_over_the_live_provider_and_a_new_one_is_recorded(spies, factory, tmp_path):
    a = build_adapter(settings(ai_provider="replay_or_real", gemini_api_key="g", ai_model="gm", brd_provider="groq", groq_api_key="q"), factory, fixtures_dir=tmp_path)
    first = ask(a)                                                                # no fixture yet: Groq answers and the answer is recorded
    assert (first.score, first.note) == (1, "groq")
    again = ask(a)                                                                # now it is replayed, nobody is asked
    assert again == first and live(a).routes[BRD_AGENT].calls == [BRD_AGENT]
    assert [r.status for r in audit(factory)] == ["OK", "REPLAYED"]


# ---------------- the settings and the agent name ----------------

def test_the_brief_writer_agent_name_is_the_one_the_router_uses():
    assert brd_generator.AGENT == BRD_AGENT == "BRD_GEN"


def test_the_settings_read_the_groq_values_and_default_to_no_routing():
    s = settings()
    assert (s.brd_provider, s.groq_api_key) == ("", "") and s.groq_model
    s = settings(brd_provider="groq", groq_api_key="k", groq_model="m")
    assert (s.brd_provider, s.groq_api_key, s.groq_model) == ("groq", "k", "m")


def test_the_example_env_file_documents_the_new_settings_without_a_key():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    assert "BRD_PROVIDER=" in text and "GROQ_MODEL=" in text and "GROQ_API_KEY=" in text
    for line in text.splitlines():
        if line.startswith("GROQ_API_KEY="):
            assert line.strip() == "GROQ_API_KEY="                                  # never a real key in a committed file
    assert any(l.startswith("groq") for l in (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8").lower().splitlines())


def test_oversized_transcript_on_413_retries_once_condensed():
    big_lines = "\n".join(f"L{i}: line content number {i} extra words" for i in range(1, 600))
    transcript_part = TextPart(f'<untrusted source="transcript">{big_lines}</untrusted>')
    b, client = backend(RuntimeError("Error code: 413 - rate_limit_exceeded"), reply('{"score": 4, "note": "ok"}'))
    r = gen(b, parts=[TextPart("TRUSTED"), transcript_part])
    assert r.data == {"score": 4, "note": "ok"}
    assert len(client.requests) == 2
    sent_first = client.requests[0]["messages"][1]["content"]
    sent_retry = client.requests[1]["messages"][1]["content"]
    assert len(sent_retry) < len(sent_first) // 2 and '<untrusted source="transcript">' in sent_retry and "L1:" in sent_retry


def test_short_text_on_413_fails_immediately_without_extra_retry():
    b, client = backend(RuntimeError("Error code: 413 - rate_limit_exceeded"))
    with pytest.raises(AgentError, match="413"):
        gen(b, parts=[TextPart("short prompt")])
    assert len(client.requests) == 1


def test_single_element_list_wrapping_object_is_unwrapped():
    b, _ = backend(reply('[{"score": 5, "note": "wrapped"}]'))
    r = gen(b)
    assert r.data == {"score": 5, "note": "wrapped"}
