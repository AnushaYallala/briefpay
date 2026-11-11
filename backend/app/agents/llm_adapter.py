"""LLMAdapter: the only way any agent talks to a model (SPEC 7.0).

Responsibilities: input hashing, replay/record, schema validation with one retry,
and an `agent_runs` audit row for every call (powers the AI audit trail grid).
Backends only turn (system, parts, schema) into raw JSON; they never touch the DB.
"""
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.models import AgentRun

BRD_AGENT = "BRD_GEN"          # the brief writer (agents/brd_generator.py): the only agent that can be sent to Groq

log = logging.getLogger("briefpay.ai")


# ---------- parts ----------
@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    data: bytes
    mime: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


Part = TextPart | ImagePart


# ---------- errors ----------
class AgentError(Exception):
    """Model call failed (network, quota, ...). Callers fall back to a safe state."""


class AgentSchemaInvalid(AgentError):
    """Model output failed schema validation twice."""


class FixtureMissing(AgentError):
    """Replay mode has no recorded output for this input and no real model to record from."""


# ---------- hashing ----------
def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def input_hash(agent: str, prompt_version: str, system: str, parts: list[Part]) -> str:
    """sha256(agent + prompt_version + canonical inputs + image hashes). Prompt bump => new hash (D-005)."""
    texts = [p.text for p in parts if isinstance(p, TextPart)]
    images = [p.sha256 for p in parts if isinstance(p, ImagePart)]
    payload = canonical_json({"system": system, "texts": texts, "images": images})
    return hashlib.sha256(f"{agent}|{prompt_version}|{payload}".encode("utf-8")).hexdigest()


# ---------- backends ----------
@dataclass
class RawResult:
    data: dict
    replayed: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider: str | None = None  # who actually produced it (set by live backends)
    model: str | None = None


class Backend(Protocol):
    provider: str
    model: str

    def generate(
        self, *, agent: str, in_hash: str, system: str, parts: list[Part],
        schema: type[BaseModel], temperature: float,
    ) -> RawResult: ...


class ReplayBackend:
    """Serves recorded outputs from fixtures/replay/<agent>/<input_hash>.json.

    With a `fallback` backend (AI_PROVIDER=replay_or_real) a missing fixture is fetched live and,
    once the adapter has validated it, recorded for next time.
    """

    provider = "replay"

    def __init__(self, fixtures_dir: Path, fallback: Backend | None = None):
        self.dir = Path(fixtures_dir)
        self.fallback = fallback
        self.model = fallback.model if fallback else "replay"

    def _path(self, agent: str, in_hash: str) -> Path:
        return self.dir / agent / f"{in_hash}.json"

    def generate(self, *, agent, in_hash, system, parts, schema, temperature) -> RawResult:
        path = self._path(agent, in_hash)
        if path.exists():
            return RawResult(data=json.loads(path.read_text(encoding="utf-8"))["output"], replayed=True)
        if self.fallback is None:
            raise FixtureMissing(f"no replay fixture for {agent}/{in_hash[:12]}")
        return self.fallback.generate(
            agent=agent, in_hash=in_hash, system=system, parts=parts, schema=schema, temperature=temperature
        )

    def save_fixture(self, agent: str, in_hash: str, output: dict, prompt_version: str) -> None:
        path = self._path(agent, in_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"agent": agent, "prompt_version": prompt_version, "input_hash": in_hash,
                        "output": output}, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )


class GeminiBackend:
    """Gemini via google-genai with structured JSON output and model routing fallback. Free tier only; never enable billing (D-012)."""

    provider = "gemini"
    DEFAULT_FALLBACKS = (
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.8-flash",
    )

    def __init__(self, api_key: str, model: str, client=None, fallback_models: tuple[str, ...] | None = None):
        if not model:
            raise AgentError("AI_MODEL is not set (verify the current Gemini Flash model name; A-4)")
        self.model = model
        self.fallback_models = fallback_models if fallback_models is not None else tuple(
            m for m in self.DEFAULT_FALLBACKS if m != model
        )
        if client is not None:
            self._client = client
        else:
            from google import genai  # lazy: tests and replay mode don't need the SDK/network

            self._client = genai.Client(api_key=api_key)

    def generate(self, *, agent, in_hash, system, parts, schema, temperature) -> RawResult:
        from google.genai import types

        contents = [
            types.Part.from_text(text=p.text) if isinstance(p, TextPart)
            else types.Part.from_bytes(data=p.data, mime_type=p.mime)
            for p in parts
        ]

        models_to_try = [self.model] + [m for m in self.fallback_models if m != self.model]
        last_error = None

        log.info("[Gemini AI] Agent '%s' starting generation with primary model '%s' (pool: %s)",
                 agent, self.model, ", ".join(models_to_try[1:]))

        for idx, candidate_model in enumerate(models_to_try, 1):
            try:
                log.info("[Gemini AI] (%s/%s) Requesting '%s' for agent '%s'...",
                         idx, len(models_to_try), candidate_model, agent)
                resp = self._client.models.generate_content(
                    model=candidate_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system, temperature=temperature,
                        response_mime_type="application/json", response_schema=schema,
                    ),
                )
                data = json.loads(resp.text)
                usage = getattr(resp, "usage_metadata", None)
                in_tok = getattr(usage, "prompt_token_count", None)
                out_tok = getattr(usage, "candidates_token_count", None)
                log.info("[Gemini AI] SUCCESS with '%s' for '%s' (Tokens: %s in, %s out)",
                         candidate_model, agent, in_tok, out_tok)
                return RawResult(
                    data=data, provider=self.provider, model=candidate_model,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                )
            except json.JSONDecodeError as e:
                log.warning("[Gemini AI] '%s' returned invalid JSON: %s. Surfacing to schema validator.", candidate_model, e)
                return RawResult(data={"__invalid_json__": str(e)})
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "getaddrinfo" in err_str or "wsa_host_not_found" in err_str:
                    log.error("[Gemini AI] Network/DNS unreachable ([Errno 11001] getaddrinfo failed). Please verify your internet connection.")
                    break
                is_recoverable = any(
                    k in err_str
                    for k in (
                        "429", "quota", "resource_exhausted", "rate", "limit",
                        "not_found", "not found", "503", "unavailable", "500",
                        "demand", "overloaded", "timeout", "deadline", "connection",
                        "aborted", "reset"
                    )
                )
                if not is_recoverable and len(models_to_try) == 1:
                    log.error("[Gemini AI] Non-recoverable error with '%s': %s", candidate_model, e)
                    break
                log.warning("[Gemini AI] Model '%s' issue (%s/%s): %s (%s). Falling back to next candidate...",
                            candidate_model, idx, len(models_to_try), type(e).__name__, str(e)[:180])
                time.sleep(1.0)
                continue

        log.error("[Gemini AI] All candidate models exhausted for agent '%s'. Last error: %s: %s",
                  agent, type(last_error).__name__, last_error)
        raise AgentError(f"gemini call failed across models: {type(last_error).__name__}: {last_error}") from last_error


# ---------- adapter ----------
class LLMAdapter:
    """Calls the backend, validates against the Pydantic schema, logs every call."""

    def __init__(self, backend: Backend, session_factory: Callable[[], Session]):
        self.backend = backend
        self.session_factory = session_factory

    @property
    def provider(self) -> str:
        return self.backend.provider

    @property
    def model(self) -> str:
        return self.backend.model

    def generate_json(
        self, *, system: str, parts: list[Part], schema: type[BaseModel], agent: str,
        project_id: int | None, prompt_version: str, temperature: float = 0.2,
        run_ids: list[int] | None = None,
    ) -> BaseModel:
        in_hash = input_hash(agent, prompt_version, system, parts)
        started = time.perf_counter()
        in_tok = out_tok = None
        replayed = False
        who = (self.provider, self.model)
        try:
            raw = self.backend.generate(agent=agent, in_hash=in_hash, system=system, parts=parts,
                                        schema=schema, temperature=temperature)
            replayed = raw.replayed
            if raw.provider:
                who = (raw.provider, raw.model or self.model)
            in_tok, out_tok = raw.input_tokens, raw.output_tokens
            try:
                result = schema.model_validate(raw.data)
            except ValidationError as first:
                if raw.replayed:  # a recorded fixture won't change on retry
                    raise AgentSchemaInvalid(f"replayed fixture invalid: {first}") from first
                retry_system = f"{system}\n\nYour previous output failed validation:\n{first}\nReturn corrected JSON."
                raw = self.backend.generate(agent=agent, in_hash=in_hash, system=retry_system, parts=parts,
                                            schema=schema, temperature=temperature)
                in_tok, out_tok = raw.input_tokens, raw.output_tokens
                try:
                    result = schema.model_validate(raw.data)
                except ValidationError as second:
                    raise AgentSchemaInvalid(f"output failed validation twice: {second}") from second
        except AgentSchemaInvalid as e:
            self._note(run_ids, self._log(who, agent, project_id, prompt_version, in_hash, started, "SCHEMA_INVALID", None, str(e), in_tok, out_tok))
            raise
        except AgentError as e:
            self._note(run_ids, self._log(who, agent, project_id, prompt_version, in_hash, started, "ERROR", None, str(e), in_tok, out_tok))
            raise
        except Exception as e:
            self._note(run_ids, self._log(who, agent, project_id, prompt_version, in_hash, started, "ERROR", None, f"{type(e).__name__}: {e}", in_tok, out_tok))
            raise AgentError(str(e)) from e

        output = result.model_dump(mode="json")
        save = getattr(self.backend, "save_fixture", None)
        if not replayed and save is not None:
            save(agent, in_hash, output, prompt_version)
        self._note(run_ids, self._log(who, agent, project_id, prompt_version, in_hash, started,
                  "REPLAYED" if replayed else "OK", output, None, in_tok, out_tok))
        return result

    @staticmethod
    def _note(run_ids, run_id: int) -> None:
        if run_ids is not None:
            run_ids.append(run_id)

    def _log(self, who, agent, project_id, prompt_version, in_hash, started, status, output, error, in_tok, out_tok):
        """Own session + commit so the audit row survives a caller's rollback."""
        for attempt in range(3):
            db = self.session_factory()
            try:
                row = AgentRun(
                    project_id=project_id, agent=agent, provider=who[0], model=who[1],
                    prompt_version=prompt_version, input_hash=in_hash,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    input_tokens=in_tok, output_tokens=out_tok, status=status,
                    output_json=output, error=error,
                )
                db.add(row)
                db.commit()
                return row.id
            except Exception as e:
                db.rollback()
                if attempt == 2:
                    log.warning("Could not persist agent_run (%s): %s", agent, e)
                    return 0
                time.sleep(0.2 * (attempt + 1))
            finally:
                db.close()
        return 0


class GroqBackend:
    """Groq (OpenAI-style chat API) with JSON mode, for TEXT-ONLY agents. It cannot read images, so it is never used for the Verifier.

    JSON mode makes the reply valid JSON but does not enforce our schema, so the schema is written into the instructions and the
    adapter's own validation (with one retry) does the enforcing, exactly as for every other backend."""

    provider = "groq"
    MAX_OUTPUT_TOKENS = 16384            # a reasoning model spends part of this thinking; a full brief needs the rest

    def __init__(self, api_key: str, model: str, client=None):
        if not model:
            raise AgentError("GROQ_MODEL is not set")
        self.model = model
        if client is not None:
            self._client = client
        else:
            from groq import Groq  # lazy: tests and replay mode don't need the SDK/network

            self._client = Groq(api_key=api_key)

    @staticmethod
    def _condense_for_tpm(user_text: str, budget_chars: int = 8000) -> str | None:
        """Condense an oversized transcript block so a free-tier 8k-TPM Groq request can fit."""
        start_tag = '<untrusted source="transcript">'
        end_tag = "</untrusted>"
        start_idx = user_text.find(start_tag)
        if start_idx != -1:
            end_idx = user_text.find(end_tag, start_idx + len(start_tag))
            if end_idx != -1:
                inner = user_text[start_idx + len(start_tag):end_idx]
                if len(inner) > budget_chars:
                    head_budget, tail_budget = int(budget_chars * 0.65), int(budget_chars * 0.25)
                    head_lines, tail_lines = [], []
                    used = 0
                    for ln in inner.splitlines():
                        if used + len(ln) + 1 > head_budget and head_lines:
                            break
                        head_lines.append(ln)
                        used += len(ln) + 1
                    used = 0
                    for ln in reversed(inner.splitlines()):
                        if used + len(ln) + 1 > tail_budget and tail_lines:
                            break
                        tail_lines.append(ln)
                        used += len(ln) + 1
                    tail_lines.reverse()
                    marker = "\n[... middle lines condensed to fit Groq 8,000 TPM free-tier limit; rely on analysis facts and lines above/below ...]\n"
                    condensed_inner = "\n".join(head_lines) + marker + "\n".join(tail_lines)
                    return user_text[:start_idx + len(start_tag)] + condensed_inner + user_text[end_idx:]
        if len(user_text) > budget_chars * 2:
            head_c, tail_c = int(budget_chars * 0.65), int(budget_chars * 0.35)
            return user_text[:head_c] + "\n[... condensed to fit Groq TPM limit ...]\n" + user_text[-tail_c:]
        return None

    def generate(self, *, agent, in_hash, system, parts, schema, temperature) -> RawResult:
        if any(isinstance(p, ImagePart) for p in parts):
            raise AgentError(f"{agent}: Groq is text-only; this agent sends images, so it must use another provider")
        instructions = (f"{system}\n\nReply with ONE JSON object and nothing else (no markdown, no commentary) that matches this JSON Schema:\n"
                        f"{json.dumps(schema.model_json_schema(), sort_keys=True, separators=(',', ':'))}")
        user = "\n\n".join(p.text for p in parts if isinstance(p, TextPart))
        log.info("[Groq AI] Requesting '%s' for agent '%s'...", self.model, agent)
        try:
            resp = self._client.chat.completions.create(
                model=self.model, temperature=temperature, max_completion_tokens=self.MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": instructions}, {"role": "user", "content": user}],
            )
        except Exception as e:
            err_l = str(e).lower()
            is_too_large = any(k in err_l for k in ("413", "request too large", "tokens per minute", "rate_limit_exceeded"))
            condensed = self._condense_for_tpm(user) if is_too_large else None
            if condensed is not None:
                log.warning("[Groq AI] Request exceeded '%s' TPM cap on '%s'. Retrying once with condensed transcript...", self.model, agent)
                try:
                    resp = self._client.chat.completions.create(
                        model=self.model, temperature=temperature, max_completion_tokens=self.MAX_OUTPUT_TOKENS,
                        response_format={"type": "json_object"},
                        messages=[{"role": "system", "content": instructions}, {"role": "user", "content": condensed}],
                    )
                except Exception as retry_err:
                    log.error("[Groq AI] Condensed retry failed for '%s' on '%s': %s: %s", agent, self.model, type(retry_err).__name__, retry_err)
                    raise AgentError(f"groq call failed: {type(retry_err).__name__}: {retry_err}") from retry_err
            else:
                log.error("[Groq AI] Request failed for '%s' on '%s': %s: %s", agent, self.model, type(e).__name__, e)
                raise AgentError(f"groq call failed: {type(e).__name__}: {e}") from e
        try:
            data = json.loads(resp.choices[0].message.content or "")
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
                data = data[0]
        except (json.JSONDecodeError, IndexError, AttributeError) as e:
            log.warning("[Groq AI] '%s' returned invalid JSON: %s. Surfacing to schema validator.", self.model, e)
            return RawResult(data={"__invalid_json__": str(e)}, provider=self.provider, model=self.model)    # the schema check rejects it and retries once
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", None)
        out_tok = getattr(usage, "completion_tokens", None)
        log.info("[Groq AI] SUCCESS with '%s' for '%s' (Tokens: %s in, %s out)", self.model, agent, in_tok, out_tok)
        return RawResult(data=data, provider=self.provider, model=self.model,
                         input_tokens=in_tok, output_tokens=out_tok)


class MissingBackend:
    """Stands in for a provider that was asked for but has no key, so only the agents that need it fail, and say why."""

    def __init__(self, provider: str, message: str):
        self.provider, self.model, self.message = provider, "unavailable", message

    def generate(self, **_kw) -> RawResult:
        raise AgentError(self.message)


class RoutedBackend:
    """Sends chosen agents to their own backend and everything else to the default one."""

    def __init__(self, default: Backend | None, routes: dict[str, Backend]):
        self.default, self.routes = default, dict(routes)
        first = default or next(iter(self.routes.values()))
        self.provider, self.model = first.provider, first.model            # only used to label a call that fails before it is answered

    def generate(self, *, agent, in_hash, system, parts, schema, temperature) -> RawResult:
        backend = self.routes.get(agent, self.default)
        if backend is None:
            raise AgentError(f"{agent}: no AI provider is configured for this agent (set GEMINI_API_KEY)")
        return backend.generate(agent=agent, in_hash=in_hash, system=system, parts=parts, schema=schema, temperature=temperature)


def build_adapter(settings, session_factory: Callable[[], Session], fixtures_dir: Path | None = None) -> LLMAdapter:
    """AI_PROVIDER = gemini | replay | replay_or_real."""
    fixtures_dir = fixtures_dir or Path(__file__).resolve().parents[2] / "fixtures" / "replay"
    provider = settings.ai_provider
    real = None
    if provider in ("gemini", "replay_or_real") and settings.gemini_api_key:
        real = GeminiBackend(settings.gemini_api_key, settings.ai_model)
    brd = (settings.brd_provider or "").strip().lower()
    if brd not in ("", "groq"):
        raise AgentError(f"unknown BRD_PROVIDER {settings.brd_provider}")
    if brd == "groq" and provider != "replay":
        groq = (GroqBackend(settings.groq_api_key, settings.groq_model) if settings.groq_api_key
                else MissingBackend("groq", "BRD_PROVIDER=groq needs GROQ_API_KEY"))
        real = RoutedBackend(real, {BRD_AGENT: groq})                      # the brief writer goes to Groq; every other agent keeps its provider
    if provider == "gemini":
        if real is None:
            raise AgentError("AI_PROVIDER=gemini needs GEMINI_API_KEY")
        return LLMAdapter(real, session_factory)
    if provider in ("replay", "replay_or_real"):
        return LLMAdapter(ReplayBackend(fixtures_dir, fallback=real), session_factory)
    raise AgentError(f"unknown AI_PROVIDER {provider}")
