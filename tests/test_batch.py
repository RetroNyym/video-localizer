import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from videoloc.batch import Context, Job, expand_inputs, run_job  # noqa: E402
from videoloc.srt import read_file  # noqa: E402
from videoloc.translate import Backend  # noqa: E402


class FakeBackend(Backend):
    name = "fake"
    label = "Sahte"

    def available(self) -> bool:
        return True

    def supports(self, src, tgt) -> bool:
        return tgt != "auto"

    def translate_many(self, texts, src, tgt):
        return [f"[{tgt}] {t}" for t in texts]


def _write_srt(path: str) -> None:
    content = (
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n"
        "2\n00:01:03,250 --> 00:01:05,500\nWorld line\nsecond\n"
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)


def test_run_job_translates_srt_and_keeps_timing(tmp_path):
    src = str(tmp_path / "video.srt")
    out_dir = str(tmp_path / "out")
    _write_srt(src)
    logs = []
    ctx = Context(log=logs.append, progress=lambda v, t: None, backend=FakeBackend())
    job = Job(input_path=src, output_dir=out_dir, target_lang="tr", source_lang="en", transcribe=False)
    result = run_job(job, ctx)
    assert result.ok, result.message
    assert result.srt_path and os.path.exists(result.srt_path)
    cues = read_file(result.srt_path)
    original = read_file(src)
    assert [(c.start, c.end) for c in cues] == [(c.start, c.end) for c in original]
    assert cues[0].text == "[tr] Hello"
    assert cues[1].text.split("\n")[0].startswith("[tr] World")
    assert result.cues == 2


def test_run_job_writes_next_to_input_when_outdir_empty(tmp_path):
    src = str(tmp_path / "clip.srt")
    _write_srt(src)
    ctx = Context(log=lambda m: None, progress=lambda v, t: None, backend=FakeBackend())
    job = Job(input_path=src, output_dir="", target_lang="de", source_lang="en", transcribe=False)
    result = run_job(job, ctx)
    assert result.ok, result.message
    assert os.path.dirname(result.srt_path) == str(tmp_path)


def test_run_job_reports_error_without_srt_and_without_transcribe(tmp_path):
    fake_video = str(tmp_path / "video.mp4")
    with open(fake_video, "wb") as fh:
        fh.write(b"\x00" * 16)
    ctx = Context(log=lambda m: None, progress=lambda v, t: None, backend=FakeBackend())
    job = Job(input_path=fake_video, output_dir=str(tmp_path), transcribe=False)
    result = run_job(job, ctx)
    assert not result.ok
    assert "altyazı" in result.message.lower() or "alutyazı" in result.message.lower()


def test_translation_cache_is_persisted(tmp_path):
    src = str(tmp_path / "a.srt")
    cache_path = str(tmp_path / "cache.json")
    _write_srt(src)
    ctx = Context(log=lambda m: None, progress=lambda v, t: None, backend=FakeBackend(), cache_path=cache_path)
    job = Job(input_path=src, output_dir=str(tmp_path / "o1"), target_lang="tr", source_lang="en", transcribe=False)
    assert run_job(job, ctx).ok
    assert os.path.exists(cache_path)

    ctx2 = Context(log=lambda m: None, progress=lambda v, t: None, backend=FakeBackend(), cache_path=cache_path)
    job2 = Job(input_path=src, output_dir=str(tmp_path / "o2"), target_lang="tr", source_lang="en", transcribe=False)
    assert run_job(job2, ctx2).ok
    assert "en>tr:Hello" in ctx2.cache


def test_expand_inputs_finds_media_and_subs(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("atlanır", encoding="utf-8")
    found = expand_inputs([str(tmp_path)])
    names = sorted(os.path.basename(p) for p in found)
    assert names == ["a.mp4", "b.srt"]
