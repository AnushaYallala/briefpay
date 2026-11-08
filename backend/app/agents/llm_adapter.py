"""LLMAdapter: the only way any agent talks to a model (SPEC 7.0).

Responsibilities: input hashing, replay/record, schema validation with one retry,
and an `agent_runs` audit row for every call (powers the AI audit trail grid).
Backends only turn (system, parts, schema) into raw JSON; they never touch the DB.
"""
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.models import AgentRun


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
    """Gemini via google-genai with structured JSON output. Free tier only; never enable billing (D-012)."""

    provider = "gemini"

    def __init__(self, api_key: str, model: str, client=None):
        if not model:
            raise AgentError("AI_MODEL is not set (verify the current Gemini Flash model name; A-4)")
        self.model = model
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
        try:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system, temperature=temperature,
                    response_mime_type="application/json", response_schema=schema,
                ),
            )
            data = json.loads(resp.text)
        except json.JSONDecodeError as e:
            # Not valid JSON at all: surface as a dict the schema check will reject (and retry once)
            return RawResult(data={"__invalid_json__": str(e)})
        except Exception as e:  # network, quota, safety block, ...
            raise AgentError(f"gemini call failed: {type(e).__name__}: {e}") from e
        usage = getattr(resp, "usage_metadata", None)
        return RawResult(
            data=data, provider=self.provider, model=self.model,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )


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
            self._log(who, agent, project_id, prompt_version, in_hash, started, "SCHEMA_INVALID", None, str(e), in_tok, out_tok)
            raise
        except AgentError as e:
            self._log(who, agent, project_id, prompt_version, in_hash, started, "ERROR", None, str(e), in_tok, out_tok)
            raise
        except Exception as e:
            self._log(who, agent, project_id, prompt_version, in_hash, started, "ERROR", None, f"{type(e).__name__}: {e}", in_tok, out_tok)
            raise AgentError(str(e)) from e

        output = result.model_dump(mode="json")
        save = getattr(self.backend, "save_fixture", None)
        if not replayed and save is not None:
            save(agent, in_hash, output, prompt_version)
        self._log(who, agent, project_id, prompt_version, in_hash, started,
                  "REPLAYED" if replayed else "OK", output, None, in_tok, out_tok)
        return result

    def _log(self, who, agent, project_id, prompt_version, in_hash, started, status, output, error, in_tok, out_tok):
        """Own session + commit so the audit row survives a caller's rollback."""
        db = self.session_factory()
        try:
            db.add(AgentRun(
                project_id=project_id, agent=agent, provider=who[0], model=who[1],
                prompt_version=prompt_version, input_hash=in_hash,
                latency_ms=int((time.perf_counter() - started) * 1000),
                input_tokens=in_tok, output_tokens=out_tok, status=status,
                output_json=output, error=error,
            ))
            db.commit()
        finally:
            db.close()


def build_adapter(settings, session_factory: Callable[[], Session], fixtures_dir: Path | None = None) -> LLMAdapter:
    """AI_PROVIDER = gemini | replay | replay_or_real."""
    fixtures_dir = fixtures_dir or Path(__file__).resolve().parents[2] / "fixtures" / "replay"
    provider = settings.ai_provider
    real = None
    if provider in ("gemini", "replay_or_real") and settings.gemini_api_key:
        real = GeminiBackend(settings.gemini_api_key, settings.ai_model)
    if provider == "gemini":
        if real is None:
            raise AgentError("AI_PROVIDER=gemini needs GEMINI_API_KEY")
        return LLMAdapter(real, session_factory)
    if provider in ("replay", "replay_or_real"):
        return LLMAdapter(ReplayBackend(fixtures_dir, fallback=real), session_factory)
    raise AgentError(f"unknown AI_PROVIDER {provider}")
