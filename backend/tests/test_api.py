import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import desktop, main, ytdlp
from tests import fakes


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MD_DATA_DIR", str(tmp_path / "data"))
    with TestClient(main.app) as c:
        c.put("/api/settings", json={"output_dir": str(tmp_path / "out")})
        yield c


@pytest.fixture
def fake(monkeypatch):
    return fakes.install(monkeypatch)


def wait_for(client, job_id, status, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if all(i["status"] == status for i in job["items"]):
            return job
        time.sleep(0.02)
    raise AssertionError(f"job did not reach {status}: {job}")


def test_probe_returns_summary(client, bbb_info, monkeypatch):
    async def fake_probe(url):
        return bbb_info

    monkeypatch.setattr(ytdlp, "probe", fake_probe)
    r = client.post("/api/probe", json={"url": " https://www.youtube.com/watch?v=aqz-KE-bpKQ "})
    assert r.status_code == 200
    assert r.json()["video"][0]["height"] == 2160


def test_ytdlp_errors_become_502_with_message(client, monkeypatch):
    async def failing_probe(url):
        raise ytdlp.YtdlpError("[youtube] abc: Video unavailable")

    monkeypatch.setattr(ytdlp, "probe", failing_probe)
    r = client.post("/api/probe", json={"url": "https://youtu.be/abc"})
    assert r.status_code == 502
    assert r.json() == {"detail": "[youtube] abc: Video unavailable"}


def test_job_lifecycle(client, fake, tmp_path):
    r = client.post(
        "/api/jobs",
        json={
            "links": [
                {"url": "https://youtu.be/v1000000000", "title": "Prefilled"},
                {"url": " https://www.youtube.com/watch?v=v2000000000&t=3 "},
                {"url": "https://www.youtube.com/watch?v=v1000000000"},
            ],
            "kind": "video",
            "height": 720,
        },
    )
    assert r.status_code == 201, r.text
    job = r.json()
    assert [i["url"] for i in job["items"]] == [
        "https://www.youtube.com/watch?v=v1000000000",
        "https://www.youtube.com/watch?v=v2000000000",
    ]  # normalised, de-duplicated
    assert job["items"][0]["title"] == "Prefilled"
    assert job["options"] == {"height": 720, "subtitles": False}

    done = wait_for(client, job["id"], "done")
    assert done["items"][0]["title"] == "Fake video watch?v=v1000000000"
    assert done["items"][0]["file_path"].endswith("[v1000000000].mp4")

    listed = client.get("/api/jobs").json()
    assert [j["id"] for j in listed] == [job["id"]]

    assert client.delete(f"/api/jobs/{job['id']}").json() == {"ok": True}
    assert client.get("/api/jobs").json() == []  # off the board...
    assert client.get(f"/api/jobs/{job['id']}").json()["archived"] is True  # ...but not deleted
    assert list((tmp_path / "out").glob("*.mp4"))  # files are never deleted


def test_job_validation(client):
    r = client.post("/api/jobs", json={"links": [{"url": "not a link"}]})
    assert r.status_code == 422 and "Not a link" in r.json()["detail"]
    r = client.post("/api/jobs", json={"links": [{"url": "https://soundcloud.com/a/b"}]})
    assert r.status_code == 422 and "isn't supported" in r.json()["detail"]
    r = client.post(
        "/api/jobs", json={"links": [{"url": "https://www.youtube.com/playlist?list=PL1"}]}
    )
    assert r.status_code == 422 and "expanded first" in r.json()["detail"]
    r = client.post("/api/jobs", json={"links": []})
    assert r.status_code == 422


def test_inspect_links(client, fake):
    r = client.post(
        "/api/links",
        json={
            "urls": [
                "https://youtu.be/v1000000000?t=4",
                "https://www.youtube.com/playlist?list=PL1",
                "https://vimeo.com/ondemand/film",
                "https://soundcloud.com/x/y",
                "",
                "https://youtu.be/v1000000000",
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    kinds = [(link["kind"], link["url"]) for link in body["links"]]
    assert kinds == [
        ("video", "https://www.youtube.com/watch?v=v1000000000"),
        ("playlist", "https://www.youtube.com/playlist?list=PL1"),
        ("video", "https://vimeo.com/ondemand/film"),  # unknown shape resolved via yt-dlp
    ]
    playlist = body["links"][1]
    assert (
        playlist["title"] == "Fake playlist"
        and playlist["count"] == 3
        and not playlist["truncated"]
    )
    assert [e["title"] for e in playlist["entries"]] == ["Entry 1", "Entry 2", "Entry 3"]
    assert playlist["entries"][0]["thumbnail"] == "https://example.test/1.jpg"
    assert body["links"][2]["title"] == "Single via inspect"
    assert body["errors"] == [
        {
            "input": "https://soundcloud.com/x/y",
            "message": (
                "soundcloud.com isn't supported - only YouTube, Vimeo, Bandcamp links work here"
            ),
        }
    ]


def test_inspect_reports_playlist_failures_per_link(client, fake):
    fake.probe_error = "[youtube:tab] PL1: The playlist does not exist."
    r = client.post(
        "/api/links",
        json={
            "urls": ["https://www.youtube.com/playlist?list=PL1", "https://youtu.be/v1000000000"]
        },
    )
    body = r.json()
    assert [link["kind"] for link in body["links"]] == ["video"]
    assert body["errors"][0]["message"].startswith("[youtube:tab] PL1")


def test_cancel_and_retry(client, fake):
    fake.probe_error = "[youtube] v1: Private video"
    job = client.post(
        "/api/jobs", json={"links": [{"url": "https://youtu.be/v1000000000"}], "kind": "audio"}
    ).json()
    failed = wait_for(client, job["id"], "error")
    item_id = failed["items"][0]["id"]
    assert failed["items"][0]["error"].startswith("This video is private")

    fake.probe_error = None
    assert client.post(f"/api/items/{item_id}/retry").status_code == 200
    wait_for(client, job["id"], "done")
    assert client.post(f"/api/items/{item_id}/retry").status_code == 409

    fake.hold.set()
    job2 = client.post(
        "/api/jobs", json={"links": [{"url": "https://youtu.be/v9000000000"}]}
    ).json()
    wait_for(client, job2["id"], "running")
    assert client.post(f"/api/jobs/{job2['id']}/cancel").json() == {"ok": True}
    wait_for(client, job2["id"], "cancelled")
    assert client.post("/api/jobs/nope/cancel").status_code == 404


def test_settings(client, tmp_path):
    s = client.get("/api/settings").json()
    assert s["output_dir"] == str((tmp_path / "out").resolve()) and s["concurrency"] == 2
    assert s["cookies_browser"] is None

    assert (
        client.put("/api/settings", json={"cookies_browser": "firefox"}).json()["cookies_browser"]
        == "firefox"
    )
    assert ytdlp.options.cookies_browser == "firefox"
    assert (
        client.put("/api/settings", json={"cookies_browser": ""}).json()["cookies_browser"] is None
    )
    assert ytdlp.options.cookies_browser is None
    assert client.put("/api/settings", json={"cookies_browser": "netscape"}).status_code == 422

    assert s["audio_language"] == "en"
    assert (
        client.put("/api/settings", json={"audio_language": "ES"}).json()["audio_language"] == "es"
    )
    assert client.put("/api/settings", json={"audio_language": ""}).json()["audio_language"] == ""
    assert client.put("/api/settings", json={"audio_language": "english"}).status_code == 422

    r = client.put(
        "/api/settings", json={"concurrency": 3, "output_dir": str(tmp_path / "elsewhere")}
    )
    assert r.status_code == 200
    assert r.json()["concurrency"] == 3 and (tmp_path / "elsewhere").is_dir()

    assert client.put("/api/settings", json={"concurrency": 0}).status_code == 422
    (tmp_path / "afile").write_text("x")
    bad = client.put("/api/settings", json={"output_dir": str(tmp_path / "afile" / "sub")})
    assert bad.status_code == 422 and "folder" in bad.json()["detail"]


def test_reveal_opens_folder_or_file(client, fake, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(desktop, "reveal", lambda path: opened.append(str(path)))
    r = client.post("/api/reveal", json={})
    assert r.status_code == 200 and opened[-1] == str((tmp_path / "out").resolve())

    job = client.post("/api/jobs", json={"links": [{"url": "https://youtu.be/v1000000000"}]}).json()
    done = wait_for(client, job["id"], "done")
    client.post("/api/reveal", json={"item_id": done["items"][0]["id"]})
    assert opened[-1].endswith(".mp4")


def test_open_plays_a_finished_file(client, fake, monkeypatch):
    opened = []
    monkeypatch.setattr(desktop, "open_file", lambda path: opened.append(str(path)))
    job = client.post("/api/jobs", json={"links": [{"url": "https://youtu.be/v1000000000"}]}).json()
    done = wait_for(client, job["id"], "done")
    item_id = done["items"][0]["id"]
    assert client.post(f"/api/items/{item_id}/open").status_code == 200
    assert opened[-1].endswith(".mp4")
    Path(done["items"][0]["file_path"]).unlink()
    r = client.post(f"/api/items/{item_id}/open")
    assert r.status_code == 404 and "isn't where" in r.json()["detail"]
    assert client.post("/api/items/nope/open").status_code == 404


def test_job_options_and_collections(client, fake, tmp_path):
    r = client.post(
        "/api/jobs",
        json={
            "links": [
                {
                    "url": "https://youtu.be/v1000000000",
                    "collection": "Mixtape",
                    "collection_index": 1,
                },
                {
                    "url": "https://youtu.be/v2000000000",
                    "collection": "Mixtape",
                    "collection_index": 2,
                },
            ],
            "kind": "audio",
            "audio_format": "m4a",
        },
    )
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["options"] == {"audio_format": "m4a", "audio_bitrate": 320}
    assert job["items"][1]["collection"] == "Mixtape" and job["items"][1]["collection_index"] == 2
    done = wait_for(client, job["id"], "done")
    assert Path(done["items"][0]["file_path"]).parts[-2:] == (
        "Mixtape",
        "01 - Fake video [v1000000000].mp3",
    )
    assert (tmp_path / "out" / "Mixtape").is_dir()

    r = client.post(
        "/api/jobs",
        json={
            "links": [{"url": "https://youtu.be/v3000000000"}],
            "kind": "video",
            "subtitles": True,
        },
    )
    assert r.json()["options"] == {"height": None, "subtitles": True}
    bad = client.post(
        "/api/jobs",
        json={"links": [{"url": "https://youtu.be/v3000000000"}], "audio_format": "flac"},
    )
    assert bad.status_code == 422


def test_library_lists_redownloads_and_forgets(client, fake, tmp_path):
    job = client.post(
        "/api/jobs",
        json={
            "links": [
                {"url": "https://youtu.be/v1000000000", "title": "First"},
                {"url": "https://youtu.be/v2000000000"},
            ],
            "kind": "audio",
            "audio_format": "m4a",
        },
    ).json()
    done = wait_for(client, job["id"], "done")
    client.delete(f"/api/jobs/{job['id']}")  # archived, must still be in the library

    lib = client.get("/api/library").json()
    assert lib["total"] == 2 and [i["exists"] for i in lib["items"]] == [True, True]
    assert (
        lib["items"][0]["kind"] == "audio" and lib["items"][0]["options"]["audio_format"] == "m4a"
    )

    Path(done["items"][0]["file_path"]).unlink()  # the user moved/deleted it
    lib = client.get("/api/library", params={"q": "v1000000000"}).json()  # matches the URL
    assert lib["total"] == 1 and lib["items"][0]["exists"] is False

    r = client.post(f"/api/library/{done['items'][0]['id']}/redownload")
    assert r.status_code == 201
    again = r.json()
    assert again["kind"] == "audio" and again["options"] == {
        "audio_format": "m4a",
        "audio_bitrate": 320,
    }
    assert again["items"][0]["url"] == "https://www.youtube.com/watch?v=v1000000000"
    assert again["items"][0]["title"] == done["items"][0]["title"]  # carried over
    wait_for(client, again["id"], "done")
    assert client.get("/api/library").json()["total"] == 3

    assert client.delete(f"/api/library/{done['items'][0]['id']}").json() == {"ok": True}
    assert client.get("/api/library").json()["total"] == 2
    assert client.delete("/api/library/nope").status_code == 404
    assert client.post("/api/library/nope/redownload").status_code == 404

    assert client.post("/api/jobs/clear-finished").json()["archived"] == 1  # the redownload job
    assert client.get("/api/jobs").json() == []


def test_form_defaults_are_remembered(client):
    fresh = client.get("/api/settings").json()
    assert (fresh["default_kind"], fresh["default_video"], fresh["default_audio"]) == (
        "video",
        "best",
        "mp3-320",
    )
    r = client.put(
        "/api/settings",
        json={"default_kind": "audio", "default_video": "720", "default_audio": "m4a"},
    )
    assert r.status_code == 200 and r.json()["default_audio"] == "m4a"
    again = client.get("/api/settings").json()
    assert again["default_kind"] == "audio" and again["default_video"] == "720"
    assert client.put("/api/settings", json={"default_audio": "flac"}).status_code == 422
    assert client.put("/api/settings", json={"default_kind": "both"}).status_code == 422
