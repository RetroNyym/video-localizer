from __future__ import annotations

import re
from dataclasses import dataclass

_TS_RE = re.compile(r"^(?:(\d{1,4})[:,])?(\d{1,3})[:,](\d{1,3})[.,:](\d{1,4})$")


@dataclass
class Cue:
    index: int
    start: int
    end: int
    text: str

    @property
    def duration_ms(self) -> int:
        return max(0, self.end - self.start)

    @property
    def lines(self) -> list[str]:
        return self.text.split("\n")

    def copy(self, **kwargs) -> Cue:
        data = {"index": self.index, "start": self.start, "end": self.end, "text": self.text}
        data.update(kwargs)
        return Cue(**data)


def parse_timestamp(value: str) -> int:
    value = value.strip()
    match = _TS_RE.match(value)
    if not match:
        raise ValueError(f"Geçersiz zaman damgası: {value!r}")
    hours, minutes, seconds, frac = match.groups()
    frac = (frac + "000")[:3]
    total = 0
    if hours:
        total += int(hours) * 3_600_000
    total += int(minutes) * 60_000
    total += int(seconds) * 1_000
    total += int(frac)
    return total


def format_timestamp(ms: int) -> str:
    if ms < 0:
        ms = 0
    hours, rem = divmod(int(ms), 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse(text: str) -> list[Cue]:
    text = text.lstrip("﻿")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n[ \t]*\n", text.strip("\n"))
    cues: list[Cue] = []
    order = 0
    for block in blocks:
        raw_lines = block.split("\n")
        timing_idx = None
        for i, line in enumerate(raw_lines):
            if "-->" in line:
                timing_idx = i
                break
        if timing_idx is None:
            continue
        index = order + 1
        head = raw_lines[timing_idx].strip()
        if timing_idx > 0:
            candidate = raw_lines[timing_idx - 1].strip()
            if candidate.isdigit():
                index = int(candidate)
        start_raw, _, end_raw = head.partition("-->")
        start = parse_timestamp(start_raw.split()[0])
        end = parse_timestamp(end_raw.split()[0]) if end_raw.split() else start
        body = raw_lines[timing_idx + 1 :]
        while body and not body[-1].strip():
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
        cues.append(Cue(index=index, start=start, end=end, text="\n".join(body)))
        order += 1
    return cues


def serialize(cues: list[Cue], renumber: bool = True) -> str:
    parts: list[str] = []
    for i, cue in enumerate(cues, start=1):
        index = i if renumber else cue.index
        parts.append(
            f"{index}\n{format_timestamp(cue.start)} --> {format_timestamp(cue.end)}\n{cue.text}"
        )
    return "\n\n".join(parts) + "\n"


def read_file(path: str) -> list[Cue]:
    for encoding in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
        try:
            with open(path, encoding=encoding, newline="") as fh:
                content = fh.read()
        except UnicodeDecodeError:
            continue
        cues = parse(content)
        if cues:
            return cues
    raise ValueError(f"Altyazı okunamadı: {path}")


def write_file(path: str, cues: list[Cue], encoding: str = "utf-8") -> None:
    with open(path, "w", encoding=encoding, newline="") as fh:
        fh.write(serialize(cues))


def merge_lines(text: str, max_chars: int, max_lines: int) -> str:
    words = text.split()
    if not words:
        return text
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
        if len(lines) == max_lines and current:
            joined = " ".join(lines + [current])
            if len(joined) > max_chars * max_lines:
                break
    if current:
        lines.append(current)
    return "\n".join(lines)


def split_cue(cue: Cue, max_chars: int, max_lines: int) -> list[Cue]:
    text = merge_lines(cue.text, max_chars, max_lines)
    lines = text.split("\n")
    if len(lines) <= max_lines and max(len(line) for line in lines) <= max_chars:
        return [cue.copy(text=text)]
    return _split_by_duration(cue, lines, max_lines)


def _split_by_duration(cue: Cue, lines: list[str], max_lines: int) -> list[Cue]:
    groups: list[list[str]] = []
    for i in range(0, len(lines), max_lines):
        groups.append(lines[i : i + max_lines])
    total_chars = sum(len(" ".join(g)) for g in groups) or 1
    out: list[Cue] = []
    offset = cue.start
    for group in groups:
        share = len(" ".join(group)) / total_chars
        span = int(cue.duration_ms * share)
        end = min(offset + span, cue.end) if group is not groups[-1] else cue.end
        out.append(cue.copy(start=offset, end=max(end, offset + 1), text="\n".join(group)))
        offset = out[-1].end
    if out:
        out[-1] = out[-1].copy(end=cue.end)
    return out
