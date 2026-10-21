import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from videoloc.srt import (  # noqa: E402
    Cue,
    format_timestamp,
    merge_lines,
    parse,
    parse_timestamp,
    serialize,
    split_cue,
)


def test_timestamp_roundtrip():
    assert format_timestamp(0) == "00:00:00,000"
    assert format_timestamp(3_661_234) == "01:01:01,234"
    assert parse_timestamp("01:01:01,234") == 3_661_234
    assert parse_timestamp("00:01:02.5") == 62_500
    assert parse_timestamp("1:02:03:004") == 3_723_004
    assert parse_timestamp("00:05,000") == 5_000


def test_parse_basic_and_timing_preserved():
    text = (
        "\ufeff1\n"
        "00:00:01,000 --> 00:00:02,500\n"
        "Merhaba dünya\n"
        "\n"
        "2\n"
        "00:00:03,010 --> 00:00:04,999\n"
        "İki satır\n"
        "ikinci satır\n"
    )
    cues = parse(text)
    assert len(cues) == 2
    assert (cues[0].start, cues[0].end) == (1000, 2500)
    assert cues[0].text == "Merhaba dünya"
    assert cues[1].text == "İki satır\nikinci satır"
    out = serialize(cues)
    again = parse(out)
    assert [(c.start, c.end, c.text) for c in again] == [(c.start, c.end, c.text) for c in cues]


def test_parse_crlf_and_missing_index():
    text = "00:00:01,000 --> 00:00:02,000\r\nSelam\r\n\r\n00:00:03,000 --> 00:00:04,000\r\nİkinci\r\n"
    cues = parse(text)
    assert len(cues) == 2
    assert cues[0].text == "Selam"
    assert cues[1].start == 3000


def test_parse_with_positioning_coordinates():
    text = "1\n00:00:01,000 --> 00:00:02,000 X1:0 X2:100 Y1:0 Y2:50\nMetin\n"
    cues = parse(text)
    assert len(cues) == 1
    assert cues[0].end == 2000


def test_serialize_renumbers_but_keeps_times():
    cues = [
        Cue(index=7, start=10, end=20, text="a"),
        Cue(index=99, start=100, end=200, text="b"),
    ]
    out = serialize(cues)
    assert out.startswith("1\n00:00:00,010 --> 00:00:00,020")
    assert "\n2\n00:00:00,100 --> 00:00:00,200" in out


def test_merge_lines_wraps_to_width():
    text = "bu çok uzun bir cümle satır sınırını aşıyor olmalı"
    merged = merge_lines(text, max_chars=20, max_lines=3)
    assert "\n" in merged
    assert all(len(line) <= 25 for line in merged.split("\n"))
    assert " ".join(merged.split()) == text


def test_split_long_cue_keeps_total_duration():
    cue = Cue(index=1, start=1000, end=9000, text="kelime " * 40)
    parts = split_cue(cue, max_chars=30, max_lines=2)
    assert len(parts) > 1
    assert parts[0].start == 1000
    assert parts[-1].end == 9000
    for prev, nxt in zip(parts, parts[1:], strict=False):
        assert prev.end <= nxt.start
        assert nxt.start >= prev.start
