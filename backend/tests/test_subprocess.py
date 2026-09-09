"""Drive the wrapper with a fake yt-dlp (a Python script) to test the process plumbing itself:
threads, streaming, error capture, timeouts and cancellation - on every OS CI runs on."""

import asyncio
import os
import pathlib
import sys
import tempfile
import threading
import time

import pytest

from app import ytdlp

FAKE_YTDLP = r"""
import json, pathlib, sys, time
args = sys.argv[1:]
if "--hang" in args:
    time.sleep(60)
if "--spawn-child" in args:
    import subprocess
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    print("CHILD " + str(child.pid), flush=True)
    child.wait()
if "--version" in args:
    print("2099.01.01"); sys.exit(0)
if "-J" in args:
    if "bad" in args[-1]:
        print("ERROR: [youtube] bad: Video unavailable; please report this issue on github",
              file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"id": "id", "title": "Fake", "formats": []})); sys.exit(0)
out_dir = pathlib.Path(args[args.index("-o") + 1]).parent
out_dir.mkdir(parents=True, exist_ok=True)
if "--fail" in args:
    print("ERROR: [youtube] id: boom; please report this issue", file=sys.stderr); sys.exit(1)
out = out_dir / "Fake [id].mp4"
if "--load-info-json" in args:
    out.write_bytes(pathlib.Path(args[args.index("--load-info-json") + 1]).read_bytes())
else:
    out.write_bytes(b"data")
print('PROGRESS {"status":"downloading","downloaded":2,"total":4,"estimate":NA,"speed":NA,"eta":1}',
      flush=True)
print('PROGRESS {"status":"finished","downloaded":4,"total":4,"estimate":NA,"speed":NA,"eta":NA}',
      flush=True)
# The real yt-dlp writes postprocess progress to stderr (checked 2026.08.19); mirror that.
print('PP {"status":"started","postprocessor":"Merger"}', file=sys.stderr, flush=True)
print("WARNING: something harmless", file=sys.stderr, flush=True)
print("FILEPATH " + str(out), flush=True)
"""


@pytest.fixture
def fake_ytdlp(monkeypatch, tmp_path):
    script = tmp_path / "fake_ytdlp.py"
    script.write_text(FAKE_YTDLP, encoding="utf-8")
    monkeypatch.setattr(ytdlp, "_ytdlp", lambda: sys.executable)
    monkeypatch.setattr(ytdlp, "base_args", lambda: [str(script)])
    return tmp_path


async def test_version_and_probe(fake_ytdlp):
    assert await ytdlp.version() == "2099.01.01"
    assert (await ytdlp.probe("https://ok"))["title"] == "Fake"


async def test_probe_error_is_cleaned_up(fake_ytdlp):
    with pytest.raises(ytdlp.YtdlpError, match=r"\[youtube\] bad: Video unavailable$"):
        await ytdlp.probe("https://bad")


async def test_download_streams_progress_on_the_loop_thread(fake_ytdlp):
    events: list[ytdlp.Progress] = []
    threads: set[int] = set()

    def on_progress(p: ytdlp.Progress) -> None:
        events.append(p)
        threads.add(threading.get_ident())

    template = str(fake_ytdlp / "out" / "%(title)s.%(ext)s")
    path = await ytdlp.download("https://ok", [], template, on_progress)
    await asyncio.sleep(0)  # let any queued callbacks run

    assert path.name == "Fake [id].mp4" and path.read_bytes() == b"data"
    assert [(e.stage, e.status) for e in events] == [
        ("download", "downloading"),
        ("download", "finished"),
        ("postprocess", "started"),
    ]
    assert events[0].fraction == 0.5 and events[0].eta == 1
    assert threads == {threading.get_ident()}, "callbacks must run on the event-loop thread"


async def test_download_failure_reports_ytdlp_message(fake_ytdlp):
    with pytest.raises(ytdlp.YtdlpError, match=r"^\[youtube\] id: boom$"):
        await ytdlp.download("https://ok", ["--fail"], str(fake_ytdlp / "%(title)s.%(ext)s"))


async def test_cancel_kills_a_stuck_download(fake_ytdlp):
    cancel = threading.Event()
    asyncio.get_running_loop().call_later(0.3, cancel.set)
    started = time.monotonic()
    with pytest.raises(ytdlp.YtdlpError, match="Cancelled"):
        await ytdlp.download(
            "https://ok", ["--hang"], str(fake_ytdlp / "%(title)s.%(ext)s"), cancel=cancel
        )
    assert time.monotonic() - started < 10


def test_timeout_kills_the_process(fake_ytdlp):
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        ytdlp._run_sync(["--hang"], timeout=1)
    assert time.monotonic() - started < 10


async def test_download_can_reuse_probe_info(fake_ytdlp):
    template = str(fake_ytdlp / "out" / "%(title)s.%(ext)s")
    path = await ytdlp.download("https://ok", [], template, info={"title": "T"})
    content = await asyncio.to_thread(path.read_bytes)
    assert content == b'{"title": "T"}'  # the fake copied the info file we handed it
    leftovers = await asyncio.to_thread(
        lambda: list(pathlib.Path(tempfile.gettempdir()).glob("md-*.info.json"))
    )
    assert not leftovers  # temp info file cleaned up


@pytest.mark.skipif(
    os.name == "nt", reason="process-group semantics are POSIX; Windows uses taskkill /T"
)
def test_cancel_kills_children_too(fake_ytdlp):
    cancel = threading.Event()
    lines: list[str] = []

    def on_line(line: str) -> None:
        lines.append(line)
        if line.startswith("CHILD "):
            threading.Timer(0.2, cancel.set).start()

    rc, _ = ytdlp._stream_sync(["--spawn-child"], on_line, cancel)
    assert rc != 0 and cancel.is_set()
    child_pid = int(next(line for line in lines if line.startswith("CHILD ")).split()[1])
    time.sleep(0.5)
    with pytest.raises(OSError):
        os.kill(child_pid, 0)  # gone, not orphaned
