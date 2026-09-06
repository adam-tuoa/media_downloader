from pathlib import Path
from urllib.parse import unquote

import pytest
from app import main, ytdlp
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    return TestClient(main.app)


def test_probe_returns_summary(client, bbb_info, monkeypatch):
    async def fake_probe(url):
        assert url == "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
        return bbb_info

    monkeypatch.setattr(ytdlp, "probe", fake_probe)
    r = client.post("/api/probe", json={"url": " https://www.youtube.com/watch?v=aqz-KE-bpKQ "})
    assert r.status_code == 200
    body = r.json()
    assert body["title"].startswith("Big Buck Bunny")
    assert body["video"][0]["height"] == 2160
    assert body["audio"]["abr"] == 129


def test_probe_rejects_non_links(client):
    r = client.post("/api/probe", json={"url": "big buck bunny"})
    assert r.status_code == 422
    assert "http" in r.text


def test_ytdlp_errors_become_502_with_message(client, monkeypatch):
    async def failing_probe(url):
        raise ytdlp.YtdlpError("[youtube] abc: Video unavailable")

    monkeypatch.setattr(ytdlp, "probe", failing_probe)
    r = client.post("/api/probe", json={"url": "https://youtu.be/abc"})
    assert r.status_code == 502
    assert r.json() == {"detail": "[youtube] abc: Video unavailable"}


def test_download_streams_file_and_cleans_up(client, bbb_info, monkeypatch):
    seen = {}

    async def fake_probe(url):
        return bbb_info

    async def fake_download(url, format_args, output_template, on_progress=None):
        seen["args"] = format_args
        out_dir = Path(output_template).parent
        seen["dir"] = out_dir
        path = out_dir / "Big Buck Bunny [aqz-KE-bpKQ].mp4"
        path.write_bytes(b"not really an mp4")
        return path

    monkeypatch.setattr(ytdlp, "probe", fake_probe)
    monkeypatch.setattr(ytdlp, "download", fake_download)

    r = client.post("/api/download", json={"url": "https://youtu.be/aqz-KE-bpKQ", "height": 720})
    assert r.status_code == 200
    assert r.content == b"not really an mp4"
    assert r.headers["content-type"] == "video/mp4"
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "Big Buck Bunny [aqz-KE-bpKQ].mp4" in unquote(disposition)
    assert seen["args"][1].endswith("/best[height<=720]")
    assert not seen["dir"].exists()  # temp dir removed by the background task


def test_audio_download_uses_extract_args(client, monkeypatch):
    seen = {}

    async def fake_download(url, format_args, output_template, on_progress=None):
        seen["args"] = format_args
        path = Path(output_template).parent / "song.mp3"
        path.write_bytes(b"mp3")
        return path

    monkeypatch.setattr(ytdlp, "download", fake_download)
    r = client.post(
        "/api/download",
        json={"url": "https://youtu.be/abc", "kind": "audio", "audio_bitrate": 192},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert seen["args"] == [
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "192K",
    ]


def test_download_failure_cleans_temp_dir(client, monkeypatch):
    dirs = {}

    async def failing_download(url, format_args, output_template, on_progress=None):
        dirs["dir"] = Path(output_template).parent
        raise ytdlp.YtdlpError("boom")

    monkeypatch.setattr(ytdlp, "download", failing_download)
    r = client.post("/api/download", json={"url": "https://youtu.be/abc", "kind": "audio"})
    assert r.status_code == 502
    assert not dirs["dir"].exists()
