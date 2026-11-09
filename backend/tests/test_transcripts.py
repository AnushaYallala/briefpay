from pathlib import Path

import pytest

from app.services import transcripts as tx

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "velugu_cove_meeting_transcript.txt"


def norm(raw, name="t.txt"):
    return tx.normalize(raw, name)


def test_the_real_sample_transcript_keeps_every_line():
    raw = SAMPLE.read_bytes()
    text, n, digest = norm(raw, SAMPLE.name)
    expected = SAMPLE.read_text(encoding="utf-8").strip("\n").split("\n")
    lines = text.split("\n")
    assert n == len(expected) and lines[0].startswith("Velugu Cove Business Owners")
    assert lines[2] == "" and lines[3].startswith("Lakshmi: Thanks for coming") and len(digest) == 64


def test_newlines_are_normalised_and_edges_trimmed_but_inner_blank_lines_stay():
    text, n, _ = norm("\r\n\r\nRavi: hi   \r\n\r\nMeena: hello\rLakshmi: ok\n\n\n")
    assert text == "Ravi: hi\n\nMeena: hello\nLakshmi: ok" and n == 4


def test_a_utf8_bom_is_dropped_and_telugu_text_survives():
    raw = "﻿లక్ష్మి: నమస్కారం\nRavi: hi".encode("utf-8")
    text, n, _ = norm(raw)
    assert text.startswith("లక్ష్మి") and n == 2


def test_hash_is_stable_and_changes_with_content():
    a, b = norm("one\ntwo")[2], norm("one\r\ntwo\r\n")[2]
    assert a == b and a != norm("one\nthree")[2]


def test_webvtt_is_reduced_to_the_spoken_lines():
    vtt = ("WEBVTT\n\nNOTE this is a comment\nacross two lines\n\nSTYLE\n::cue {color: red}\n\n"
           "1\n00:00:01.000 --> 00:00:04.000\n<v Lakshmi>We need <i>one</i> website.</v>\n\n"
           "2\n00:00:05.000 --> 00:00:07.000\n<v Ravi>Menu and timings.</v>\nAnd directions.\n")
    text, n, _ = norm(vtt, "meeting.vtt")
    assert text == "Lakshmi: We need one website.\n\nRavi: Menu and timings.\nAnd directions." and n == 4
    assert "-->" not in text and "NOTE" not in text and "color" not in text


def test_webvtt_is_detected_from_content_even_without_the_extension():
    assert norm("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello", "notes.txt")[0] == "hello"


NUL = chr(0)


@pytest.mark.parametrize("raw,code", [
    pytest.param("", "TRANSCRIPT_EMPTY", id="empty"),
    pytest.param("  \n\t\n ", "TRANSCRIPT_EMPTY", id="blank"),
    pytest.param(("%s%sbinary" % (NUL, chr(1))).encode(), "TRANSCRIPT_NOT_TEXT", id="binary"),
    pytest.param(b"caf\xe9 au lait", "TRANSCRIPT_NOT_UTF8", id="latin1"),
    pytest.param(b"x" * (tx.MAX_BYTES + 1), "TRANSCRIPT_TOO_LARGE", id="too-large-bytes"),
    pytest.param("x" * (tx.MAX_BYTES + 1), "TRANSCRIPT_TOO_LARGE", id="too-large-text"),
    pytest.param("a\n" * (tx.MAX_LINES + 1), "TRANSCRIPT_TOO_LONG", id="too-many-lines"),
    pytest.param("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n", "TRANSCRIPT_EMPTY", id="vtt-with-no-speech"),
])
def test_unusable_transcripts_are_rejected_with_a_specific_code(raw, code):
    with pytest.raises(tx.TranscriptError) as e:
        norm(raw)
    assert e.value.code == code


def test_filenames():
    assert tx.check_filename("") == "pasted-text.txt" and tx.check_filename(None) == "pasted-text.txt"
    assert tx.check_filename("Meeting.TXT") == "Meeting.TXT" and tx.check_filename("a.vtt") == "a.vtt"
    assert len(tx.check_filename("n" * 300 + ".md")) == 255
    for bad in ("minutes.pdf", "audio.mp3", "x.exe", "notes"):
        with pytest.raises(tx.TranscriptError) as e:
            tx.check_filename(bad)
        assert e.value.code == "TRANSCRIPT_BAD_TYPE"


def test_numbering_starts_at_one_and_matches_the_stored_text():
    assert tx.numbered("a\n\nb") == [{"n": 1, "text": "a"}, {"n": 2, "text": ""}, {"n": 3, "text": "b"}]
