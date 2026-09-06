"""Drive the wrapper with a fake yt-dlp (a Python script) to test the process plumbing itself:
threads, streaming, error capture, timeouts and cancellation - on every OS CI runs on."""

import asyncio
import sys
import threading
import time

import pytest

from app import ytdlp

FAKE_YTDLP = r"""
import json, pathlib, sys, time
args = sys.argv[1:]
if "--hang" in args:
    time.sleep(60)
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
out.write_bytes(b"data")
print('PROGRESS {"status":"downloading","downloaded":2,"total":4,"estimate":NA,"speed":NA,"eta":1}',
      flush=True)
print('PROGRESS {"status":"finished","downloaded":4,"total":4,"estimate":NA,"speed":NA,"eta":NA}',
      flush=True)
print('PP {"status":"started","postprocessor":"Merger"}', flush=True)
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
