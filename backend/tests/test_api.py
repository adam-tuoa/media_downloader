import time

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
            "urls": ["https://x/v1", " https://x/v2 ", "https://x/v1"],
            "kind": "video",
            "height": 720,
        },
    )
    assert r.status_code == 201, r.text
    job = r.json()
    assert [i["url"] for i in job["items"]] == [
        "https://x/v1",
        "https://x/v2",
    ]  # trimmed, de-duplicated
    assert job["options"] == {"height": 720}

    done = wait_for(client, job["id"], "done")
    assert done["items"][0]["title"] == "Fake video v1"
    assert done["items"][0]["file_path"].endswith("Fake video [v1].mp4")
    assert (tmp_path / "out" / "Fake video [v2].mp4").exists()

    listed = client.get("/api/jobs").json()
    assert [j["id"] for j in listed] == [job["id"]]

    assert client.delete(f"/api/jobs/{job['id']}").json() == {"ok": True}
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    assert (tmp_path / "out" / "Fake video [v1].mp4").exists()  # files are never deleted


def test_job_validation(client):
    r = client.post("/api/jobs", json={"urls": ["not a link"]})
    assert r.status_code == 422 and "http" in r.text
    r = client.post("/api/jobs", json={"urls": ["  "]})
    assert r.status_code == 422 and "at least one" in r.text
    r = client.post("/api/jobs", json={"urls": []})
    assert r.status_code == 422


def test_cancel_and_retry(client, fake):
    fake.probe_error = "[youtube] v1: Private video"
    job = client.post("/api/jobs", json={"urls": ["https://x/v1"], "kind": "audio"}).json()
    failed = wait_for(client, job["id"], "error")
    item_id = failed["items"][0]["id"]
    assert failed["items"][0]["error"] == "[youtube] v1: Private video"

    fake.probe_error = None
    assert client.post(f"/api/items/{item_id}/retry").status_code == 200
    wait_for(client, job["id"], "done")
    assert client.post(f"/api/items/{item_id}/retry").status_code == 409

    fake.hold.set()
    job2 = client.post("/api/jobs", json={"urls": ["https://x/v9"]}).json()
    wait_for(client, job2["id"], "running")
    assert client.post(f"/api/jobs/{job2['id']}/cancel").json() == {"ok": True}
    wait_for(client, job2["id"], "cancelled")
    assert client.post("/api/jobs/nope/cancel").status_code == 404


def test_settings(client, tmp_path):
    s = client.get("/api/settings").json()
    assert s["output_dir"] == str((tmp_path / "out").resolve()) and s["concurrency"] == 2

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

    job = client.post("/api/jobs", json={"urls": ["https://x/v1"]}).json()
    done = wait_for(client, job["id"], "done")
    client.post("/api/reveal", json={"item_id": done["items"][0]["id"]})
    assert opened[-1].endswith("Fake video [v1].mp4")
