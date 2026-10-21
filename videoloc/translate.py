from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable

from .langs import AUTO_CODE
from .srt import Cue

Progress = Callable[[int, int, str], None]

_PROTECTED_RE = re.compile(r"(\{[^}]*\}|</?[A-Za-z][^<>]*>)")
_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


class TranslationError(RuntimeError):
    pass


class Backend:
    name = "base"
    label = "Temel"

    def available(self) -> bool:
        return False

    def supports(self, src: str, tgt: str) -> bool:
        return False

    def translate_many(self, texts: list[str], src: str, tgt: str) -> list[str]:
        raise NotImplementedError

    def translate(self, text: str, src: str, tgt: str) -> str:
        return self.translate_many([text], src, tgt)[0]


class ArgosBackend(Backend):
    name = "argos"
    label = "Çevrimdışı (Argos)"

    def __init__(self) -> None:
        self._pkg = None
        self._installed: set[tuple[str, str]] | None = None
        try:
            import argostranslate.package as pkg

            self._pkg = pkg
        except Exception:
            self._pkg = None

    def _pairs(self) -> set[tuple[str, str]]:
        if self._installed is None:
            pairs: set[tuple[str, str]] = set()
            if self._pkg is not None:
                try:
                    for item in self._pkg.get_installed_packages():
                        pairs.add((item.from_code, item.to_code))
                except Exception:
                    pairs = set()
            self._installed = pairs
        return self._installed

    def available(self) -> bool:
        if self._pkg is None:
            return False
        try:
            import argostranslate.translate  # noqa: F401
        except Exception:
            return False
        return True

    def installed_pairs(self) -> set[tuple[str, str]]:
        return self._pairs()

    def supports(self, src: str, tgt: str) -> bool:
        if src == AUTO_CODE or tgt == AUTO_CODE:
            return False
        return (src, tgt) in self._pairs()

    def translate_many(self, texts: list[str], src: str, tgt: str) -> list[str]:
        import argostranslate.translate as at

        return [at.translate(text, src, tgt) if text.strip() else text for text in texts]


class GtxBackend(Backend):
    name = "gtx"
    label = "Google (doğrudan)"

    ENDPOINT = "https://translate.googleapis.com/translate_a/single"

    def available(self) -> bool:
        return True

    def supports(self, src: str, tgt: str) -> bool:
        return tgt != AUTO_CODE

    def translate_many(self, texts: list[str], src: str, tgt: str) -> list[str]:
        import time

        out: list[str] = []
        for i, text in enumerate(texts):
            if not text.strip():
                out.append(text)
                continue
            out.append(self._one(text, src, tgt))
            if i < len(texts) - 1:
                time.sleep(0.22)
        return out

    def _one(self, text: str, src: str, tgt: str, attempts: int = 4) -> str:
        import json
        import time
        import urllib.error
        import urllib.parse
        import urllib.request

        params = urllib.parse.urlencode(
            {"client": "gtx", "sl": src, "tl": tgt, "dt": "t", "q": text}
        )
        url = f"{self.ENDPOINT}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                segments = payload[0] or []
                result = "".join(seg[0] for seg in segments if seg and seg[0])
                if result:
                    return result
                raise TranslationError("Boş çeviri yanıtı")
            except Exception as exc:
                last = exc
                if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503):
                    break
                time.sleep(1.5 * (attempt + 1))
        raise TranslationError(f"Çeviri başarısız oldu: {last}") from last


class GoogleBackend(Backend):
    name = "google"
    label = "Google Çeviri"

    def available(self) -> bool:
        try:
            from deep_translator import GoogleTranslator  # noqa: F401
        except Exception:
            return False
        return True

    def supports(self, src: str, tgt: str) -> bool:
        return tgt != AUTO_CODE

    def translate_many(self, texts: list[str], src: str, tgt: str) -> list[str]:
        import time


        out: list[str] = []
        for chunk in _chunk(texts, max_items=20):
            if not chunk:
                continue
            out.extend(self._translate_chunk(chunk, src, tgt))
            if len(chunk) >= 20:
                time.sleep(0.3)
        return out

    def _translate_chunk(self, chunk: list[str], src: str, tgt: str) -> list[str]:
        import time

        from deep_translator import GoogleTranslator

        last_error: Exception | None = None
        for attempt in range(4):
            try:
                translator = GoogleTranslator(source=src, target=tgt)
                result = translator.translate_batch(chunk)
                if isinstance(result, str):
                    result = [result]
                result = list(result)
                if len(result) != len(chunk):
                    raise TranslationError("Çeviri sonucu eksik döndü")
                return [item or "" for item in result]
            except Exception as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        single: list[str] = []
        translator = GoogleTranslator(source=src, target=tgt)
        for text in chunk:
            for attempt in range(3):
                try:
                    value = translator.translate(text)
                    single.append(value or "")
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(2.0 * (attempt + 1))
            else:
                raise TranslationError(f"Çeviri başarısız oldu: {last_error}") from last_error
            time.sleep(0.25)
        return single


def _chunk(texts: list[str], max_chars: int = 4000, max_items: int = 40) -> Iterable[list[str]]:
    batch: list[str] = []
    size = 0
    for text in texts:
        if batch and (size + len(text) > max_chars or len(batch) >= max_items):
            yield batch
            batch, size = [], 0
        batch.append(text)
        size += len(text) + 1
    if batch:
        yield batch


def backend_pool() -> list[Backend]:
    return [ArgosBackend(), GtxBackend(), GoogleBackend()]


def get_backend(
    prefer: str = "auto", src: str = AUTO_CODE, tgt: str = AUTO_CODE
) -> Backend:
    pool = backend_pool()
    if prefer and prefer != "auto":
        for backend in pool:
            if backend.name == prefer:
                if not backend.available():
                    hint = {
                        "argos": "argostranslate",
                        "gtx": "",
                        "google": "deep-translator",
                    }.get(backend.name, "")
                    raise TranslationError(
                        f"{backend.label} motoru kullanılamıyor."
                        + (f" Kurulum: pip install {hint}" if hint else "")
                    )
                return backend
        raise TranslationError(f"Bilinmeyen çeviri motoru: {prefer}")
    for backend in pool:
        if backend.available() and backend.supports(src, tgt):
            return backend
    for backend in pool:
        if backend.available():
            return backend
    raise TranslationError(
        "Çeviri motoru bulunamadı. Kurulum: pip install deep-translator "
        "(veya tamamen çevrimdışı için: pip install argostranslate)"
    )


def protect(text: str) -> tuple[str, list[str]]:
    tags = _PROTECTED_RE.findall(text)
    stripped = _PROTECTED_RE.sub(" ", text)
    stripped = re.sub(r"\s{2,}", " ", stripped).strip()
    return stripped, tags


def unprotect(text: str, tags: list[str]) -> str:
    brace = [tag for tag in tags if tag.startswith("{")]
    inline = [tag for tag in tags if not tag.startswith("{")]
    result = text
    opens = [t for t in inline if not t.startswith("</")]
    closes = [t for t in inline if t.startswith("</")]
    if opens and not re.search(rf"<{re.escape(_tag_name(opens[0]))}[ >]", result, re.I):
        result = f"{opens[0]} {result}"
    if closes and not re.search(r"</[A-Za-z][^<>]*>", result):
        result = f"{result} {closes[-1]}"
    if brace:
        result = " ".join(brace) + " " + result
    return re.sub(r"\s{2,}", " ", result).strip()


def _tag_name(tag: str) -> str:
    return tag.strip("</>").split()[0].split(">")[0]


def rewrap(translated: str, template: str) -> str:
    translated = " ".join(translated.split())
    if not translated:
        return translated
    tmpl_lines = template.split("\n")
    longest = max((len(line) for line in tmpl_lines), default=0)
    width = max(longest, 20)
    target_lines = max(1, len(tmpl_lines))
    total = len(translated)
    line_count = max(target_lines, math.ceil(total / max(width, 1)))
    per_line = math.ceil(total / line_count)
    words = translated.split()
    lines: list[str] = []
    buffer: list[str] = []
    for word in words:
        if not buffer:
            buffer = [word]
            continue
        candidate = " ".join(buffer) + " " + word
        if len(candidate) <= per_line or len(lines) >= line_count - 1:
            buffer.append(word)
        else:
            lines.append(" ".join(buffer))
            buffer = [word]
    if buffer:
        lines.append(" ".join(buffer))
    return "\n".join(lines)


def translate_text(
    text: str,
    src: str,
    tgt: str,
    backend: Backend | None = None,
) -> str:
    backend = backend or get_backend("auto", src, tgt)
    plain, tags = protect(text)
    if not plain:
        return text
    if not backend.supports(src, tgt):
        raise TranslationError(
            f"{backend.label} bu dil çiftini desteklemiyor ({src} -> {tgt}). "
            "Kaynak dili açık seçin veya başka bir motor deneyin."
        )
    result = backend.translate(plain, src, tgt)
    return unprotect(rewrap(result, text), tags)


def translate_cues(
    cues: list[Cue],
    src: str,
    tgt: str,
    backend: Backend | None = None,
    progress: Progress | None = None,
    cache: dict[str, str] | None = None,
) -> list[Cue]:
    if tgt == AUTO_CODE:
        raise TranslationError("Hedef dil seçilmelidir.")
    backend = backend or get_backend("auto", src, tgt)
    if not backend.supports(src, tgt):
        raise TranslationError(
            f"{backend.label} bu dil çiftini desteklemiyor ({src} -> {tgt}). "
            "Kaynak dili açık seçin veya başka bir motor deneyin."
        )
    cache = cache if cache is not None else {}
    prepared: list[tuple[int, str, list[str], str]] = []
    results: dict[int, str] = {}
    pending: list[str] = []

    for pos, cue in enumerate(cues):
        plain, tags = protect(cue.text)
        key = f"{src}>{tgt}:{plain}"
        if not plain:
            results[pos] = cue.text
            continue
        if key in cache:
            results[pos] = unprotect(rewrap(cache[key], cue.text), tags)
            if progress:
                progress(pos + 1, len(cues), "önbellek")
            continue
        prepared.append((pos, plain, tags, key))
        pending.append(plain)

    done_before = len(results)
    if pending:
        try:
            translated = backend.translate_many(pending, src, tgt)
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError(f"Çeviri başarısız oldu: {exc}") from exc
        for (pos, plain, tags, key), value in zip(prepared, translated, strict=False):
            value = value if value else plain
            cache[key] = value
            results[pos] = unprotect(rewrap(value, cues[pos].text), tags)
            if progress:
                done_before += 1
                progress(done_before, len(cues), "çevriliyor")

    return [cue.copy(text=results[pos]) for pos, cue in enumerate(cues)]
