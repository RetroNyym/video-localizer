import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from videoloc.srt import Cue  # noqa: E402
from videoloc.tts import build_track, clean_for_tts  # noqa: E402


def _write_tone(path: str, duration_ms: int, freq: float = 440.0, rate: int = 22050) -> None:
    n = int(rate * duration_ms / 1000)
    frames = bytearray()
    for i in range(n):
        import math

        value = int(12000 * math.sin(2 * math.pi * freq * i / rate))
        frames += struct.pack("<h", value)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))


def test_clean_for_tts_strips_tags():
    assert clean_for_tts("{\\an8}Merhaba\n<i>dünya</i>") == "Merhaba dünya"


def test_build_track_places_audio_at_cue_times(tmp_path):
    cues = [
        Cue(index=1, start=1000, end=1500, text="bir"),
        Cue(index=2, start=3000, end=4000, text="iki"),
    ]
    part1 = str(tmp_path / "a.wav")
    part2 = str(tmp_path / "b.wav")
    _write_tone(part1, 400)
    _write_tone(part2, 1200)
    out = str(tmp_path / "track.wav")
    build_track(cues, [part1, part2], out, padding_ms=200)

    with wave.open(out, "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        rate = wf.getframerate()
        total_ms = wf.getnframes() * 1000 / rate
        frames = wf.readframes(wf.getnframes())
    assert abs(total_ms - 4200) < 20

    def rms_at(start_ms: int, window_ms: int) -> float:
        start = int(rate * start_ms / 1000)
        count = int(rate * window_ms / 1000)
        chunk = frames[start * 2 : (start + count) * 2]
        samples = struct.unpack(f"<{len(chunk) // 2}h", chunk)
        if not samples:
            return 0.0
        return sum(abs(s) for s in samples) / len(samples)

    assert rms_at(1100, 300) > 200
    assert rms_at(2200, 300) < 50
    assert rms_at(3100, 300) > 200


def test_build_track_truncates_overlapping_audio(tmp_path):
    cues = [
        Cue(index=1, start=0, end=500, text="bir"),
        Cue(index=2, start=500, end=1500, text="iki"),
    ]
    part1 = str(tmp_path / "long.wav")
    part2 = str(tmp_path / "empty.wav")
    _write_tone(part1, 5000)
    with wave.open(part2, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"")
    out = str(tmp_path / "track.wav")
    build_track(cues, [part1, part2], out, padding_ms=0)
    with wave.open(out, "rb") as wf:
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    def avg_at(start_ms: int, window_ms: int) -> float:
        start = int(rate * start_ms / 1000)
        count = int(rate * window_ms / 1000)
        chunk = frames[start * 2 : (start + count) * 2]
        samples = struct.unpack(f"<{len(chunk) // 2}h", chunk)
        if not samples:
            return 0.0
        return sum(abs(s) for s in samples) / len(samples)

    assert avg_at(200, 200) > 200
    assert avg_at(600, 300) < 50
