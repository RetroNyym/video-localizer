import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from videoloc import tts  # noqa: E402
from videoloc.srt import Cue  # noqa: E402

pytestmark = pytest.mark.skipif(not tts.available(), reason="pyttsx3 kurulu değil")


def test_synthesize_cues_batch(tmp_path):
    cues = [
        Cue(index=1, start=0, end=2000, text="Merhaba dünya"),
        Cue(index=2, start=2500, end=5000, text="{\\an8}Bu bir\ntest cümlesidir."),
    ]
    paths = tts.synthesize_cues(cues, str(tmp_path))
    assert len(paths) == 2
    for path in paths:
        assert os.path.exists(path) and os.path.getsize(path) > 1000
        with wave.open(path, "rb") as wf:
            assert wf.getnframes() > 1000


def test_synthesize_and_build_full_track(tmp_path):
    cues = [
        Cue(index=1, start=200, end=2500, text="Merhaba"),
        Cue(index=2, start=3000, end=5500, text="dünya"),
    ]
    parts = tts.synthesize_cues(cues, str(tmp_path))
    out = str(tmp_path / "full.wav")
    tts.build_track(cues, parts, out, padding_ms=100)
    with wave.open(out, "rb") as wf:
        total_ms = wf.getnframes() * 1000 / wf.getframerate()
    assert abs(total_ms - 5600) < 60


def test_synthesize_with_sapi_engine(tmp_path):
    cues = [Cue(index=1, start=0, end=2000, text="Merhaba dünya")]
    paths = tts.synthesize_cues(cues, str(tmp_path), engine="sapi", prefix="sapi")
    assert os.path.getsize(paths[0]) > 500


def test_synthesize_with_piper_engine(tmp_path):
    from videoloc import voices

    if voices.TR_VOICE_KEY not in voices.installed_piper_voices():
        pytest.skip("Piper TR sesi indirilmemiş")
    if not tts.piper_available():
        pytest.skip("piper-tts kurulu değil")
    cues = [Cue(index=1, start=0, end=3000, text="Merhaba, bu Piper Türkçe testidir.")]
    paths = tts.synthesize_cues(
        cues, str(tmp_path), engine="piper", voice=voices.TR_VOICE_KEY, prefix="piper"
    )
    with wave.open(paths[0], "rb") as wf:
        assert wf.getframerate() == 22050
        assert wf.getnframes() > 4000


def test_default_engine_prefers_piper_when_available():
    expected = "piper" if tts.piper_available() else "sapi"
    assert tts.default_engine() == expected
