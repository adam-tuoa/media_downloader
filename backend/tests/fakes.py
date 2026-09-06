"""A controllable stand-in for the ytdlp module used by the worker and API tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app import ytdlp

INFO = {
    "id": "abc",
    "title": "Fake video",
    "uploader": "Someone",
    "duration": 12,
    "thumbnail": "https://example.test/t.jpg",
    "formats": [
        {"format_id": "18", "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4", "height": 360},
        {"format_id": "22", "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4", "height": 720},
    ],
}


class FakeYtdlp:
    """probe() returns INFO (or raises); download() writes a file and can be held open."""

    def __init__(self) -> None:
        self.probe_error: str | None = None
        self.download_error: str | None = None
        self.hold = asyncio.Event()  # when set, downloads wait here until release() is called
        self.release = asyncio.Event()
        self.calls: list[list[str]] = []
        self.infos: list[dict | None] = []
        self.progress_steps = 3

    async def probe(self, url: str) -> dict:
        if self.probe_error:
            raise ytdlp.YtdlpError(self.probe_error)
        return {**INFO, "title": f"Fake video {url.rsplit('/', 1)[-1]}"}

    async def download(
        self, url, format_args, output_template, on_progress=None, cancel=None, info=None
    ):
        self.calls.append(list(format_args))
        self.infos.append(info)
        if self.download_error:
            raise ytdlp.YtdlpError(self.download_error)
        out_dir = ytdlp.template_root(output_template)
        for i in range(1, self.progress_steps + 1):
            if on_progress:
                status = "finished" if i == self.progress_steps else "downloading"
                on_progress(ytdlp.Progress("download", status, i * 100, 300, 1000.0, 3 - i))
            await asyncio.sleep(0)
        if self.hold.is_set():
            while not self.release.is_set():
                if cancel is not None and cancel.is_set():
                    raise ytdlp.YtdlpError("Cancelled")
                await asyncio.sleep(0.02)
        if cancel is not None and cancel.is_set():
            raise ytdlp.YtdlpError("Cancelled")
        if on_progress:
            on_progress(ytdlp.Progress("postprocess", "started", postprocessor="Merger"))
        ext = "mp3" if "-x" in format_args else "mp4"
        path = Path(out_dir) / f"Fake video [{url.rsplit('/', 1)[-1]}].{ext}"
        path.write_bytes(b"media")
        return path


def install(monkeypatch) -> FakeYtdlp:
    fake = FakeYtdlp()
    monkeypatch.setattr(ytdlp, "probe", fake.probe)
    monkeypatch.setattr(ytdlp, "download", fake.download)
    return fake
