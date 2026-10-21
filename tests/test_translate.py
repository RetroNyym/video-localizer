import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from videoloc.srt import Cue  # noqa: E402
from videoloc.translate import (  # noqa: E402
    Backend,
    TranslationError,
    protect,
    rewrap,
    translate_cues,
    unprotect,
)


class FakeBackend(Backend):
    name = "fake"
    label = "Sahte"

    def __init__(self, upper: bool = True):
        self.upper = upper
        self.calls = 0

    def available(self) -> bool:
        return True

    def supports(self, src: str, tgt: str) -> bool:
        return tgt != "auto"

    def translate_many(self, texts, src, tgt):
        self.calls += 1
        out = []
        for text in texts:
            words = text.split()
            joined = " ".join(reversed(words))
            out.append(joined.upper() if self.upper else joined)
        return out


def test_protect_and_unprotect_brace_tags():
    plain, tags = protect("{\\an8}Merhaba <i>dünya</i>")
    assert "{\\an8}" in tags
    assert "<i>" in tags
    assert "Merhaba" in plain
    assert "<i>" not in plain
    restored = unprotect(plain, tags)
    assert restored.startswith("{\\an8}")
    assert restored.endswith("</i>")
    assert "Merhaba" in restored


def test_rewrap_balances_lines():
    template = "kısa satır\nikinci satır"
    long_text = "bu çeviri metni orijinalden oldukça daha uzun bir içerikle gelir ve satırlara dağıtılmalıdır"
    wrapped = rewrap(long_text, template)
    lines = wrapped.split("\n")
    assert len(lines) >= 2
    assert " ".join(lines) == long_text


def test_rewrap_short_text_keeps_line_count():
    template = "tek uzun orijinal satır burada"
    wrapped = rewrap("kısa çeviri", template)
    assert "\n" not in wrapped


def test_translate_cues_preserves_timing_and_uses_cache():
    cues = [
        Cue(index=1, start=1000, end=2500, text="Hello world"),
        Cue(index=2, start=3000, end=4500, text="Second line\nwith wrap"),
    ]
    backend = FakeBackend()
    cache = {}
    out = translate_cues(cues, "en", "tr", backend=backend, cache=cache)
    assert [(c.start, c.end) for c in out] == [(1000, 2500), (3000, 4500)]
    assert out[0].text == "WORLD HELLO"
    assert out[1].text.count("\n") == 1
    assert len(cache) == 2

    out2 = translate_cues(cues, "en", "tr", backend=backend, cache=cache)
    assert backend.calls == 1
    assert [c.text for c in out2] == [c.text for c in out]


def test_translate_cues_rejects_auto_target():
    backend = FakeBackend()
    try:
        translate_cues([Cue(1, 0, 1, "x")], "en", "auto", backend=backend)
    except TranslationError:
        pass
    else:
        raise AssertionError("auto hedef reddedilmeli")


def test_translate_cues_unsupported_pair_message():
    class NoPair(FakeBackend):
        def supports(self, src, tgt) -> bool:
            return False

    try:
        translate_cues([Cue(1, 0, 1, "x")], "en", "tr", backend=NoPair())
    except TranslationError as exc:
        assert "desteklemiyor" in str(exc)
    else:
        raise AssertionError("desteklenmeyen çift reddedilmeli")
