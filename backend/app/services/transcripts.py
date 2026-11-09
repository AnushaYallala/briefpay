"""Transcript intake (SPEC 7.1, 10): bytes or text in, clean numbered text out. Pure, no DB.

Line numbers are what BA `source_refs` ("L12-L15") point at, so the stored text must be exactly what the
BA Agent and the transcript panel both number. Plain text and Markdown keep every line; WebVTT is reduced
to the spoken lines.
"""
import hashlib
import re

MAX_BYTES = 300_000
MAX_LINES = 5_000
ALLOWED_SUFFIXES = (".txt", ".vtt", ".md")


class TranscriptError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _decode(raw: bytes) -> str:
    if len(raw) > MAX_BYTES:
        raise TranscriptError("TRANSCRIPT_TOO_LARGE", f"Transcript is over {MAX_BYTES // 1000} KB")
    if b"\x00" in raw:
        raise TranscriptError("TRANSCRIPT_NOT_TEXT", "That looks like a binary file, not a text transcript")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise TranscriptError("TRANSCRIPT_NOT_UTF8", "Please save the transcript as UTF-8 text") from e


def _clean_vtt(text: str) -> list[str]:
    out: list[str] = []
    skipping_block = False
    for i, line in enumerate(text.split("\n")):
        stripped = line.strip()
        if i == 0 and stripped.startswith("WEBVTT"):
            continue
        if not stripped:
            skipping_block = False
            if out and out[-1] != "":
                out.append("")
            continue
        if skipping_block or stripped.startswith(("NOTE", "STYLE", "REGION")):
            skipping_block = True
            continue
        if "-->" in stripped or re.fullmatch(r"\d+", stripped):  # cue timing / cue number
            continue
        stripped = re.sub(r"<v\s+([^>]+)>", r"\1: ", stripped)  # <v Lakshmi>text -> "Lakshmi: text"
        stripped = re.sub(r"</?[^>]+>", "", stripped).strip()
        if stripped:
            out.append(stripped)
    return out


def normalize(raw: bytes | str, source_name: str) -> tuple[str, int, str]:
    """Return (text, line_count, sha256). Raises TranscriptError for anything unusable."""
    text = raw if isinstance(raw, str) else _decode(raw)
    if isinstance(raw, str) and len(raw.encode("utf-8")) > MAX_BYTES:
        raise TranscriptError("TRANSCRIPT_TOO_LARGE", f"Transcript is over {MAX_BYTES // 1000} KB")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text:
        raise TranscriptError("TRANSCRIPT_NOT_TEXT", "That looks like a binary file, not a text transcript")
    is_vtt = source_name.lower().endswith(".vtt") or text.lstrip().startswith("WEBVTT")
    lines = _clean_vtt(text) if is_vtt else [ln.rstrip() for ln in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not any(ln.strip() for ln in lines):
        raise TranscriptError("TRANSCRIPT_EMPTY", "The transcript has no text")
    if len(lines) > MAX_LINES:
        raise TranscriptError("TRANSCRIPT_TOO_LONG", f"Transcript is over {MAX_LINES} lines")
    clean = "\n".join(lines)
    return clean, len(lines), hashlib.sha256(clean.encode("utf-8")).hexdigest()


def check_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "pasted-text.txt"
    if not name.lower().endswith(ALLOWED_SUFFIXES):
        raise TranscriptError("TRANSCRIPT_BAD_TYPE", f"Upload a {', '.join(ALLOWED_SUFFIXES)} file or paste the text")
    return name[:255]


def numbered(text: str) -> list[dict]:
    """[{n: 1, text: "..."}]: the numbering the BA Agent and the UI both use."""
    return [{"n": i, "text": ln} for i, ln in enumerate(text.split("\n"), start=1)]
