"""Desktop-mode behaviour: launch token, quit, update endpoints, launcher helpers."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from app import launcher, main, updates, ytdlp
from tests import fakes


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    monkeypatch.setenv("MD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MD_TOKEN", "secret-token")
    monkeypatch.setenv("MD_DESKTOP", "1")

    async def fake_update():
        return "Latest version: stable@2099.01.01\nyt-dlp is up to date"

    monkeypatch.setattr(ytdlp, "update", fake_update)
    monkeypatch.setattr(
        updates, "check_latest", lambda current: {"latest": "9.9.9", "url": "https://x/rel"}
    )
    fakes.install(monkeypatch)
    quits = []
    main.app.state.on_quit = lambda: quits.append(True)
    with TestClient(main.app) as client:
        yield client, quits
    main.app.state.on_quit = None


def test_api_requires_the_launch_token(desktop):
    client, _ = desktop
    assert client.get("/api/jobs").status_code == 401
    assert "icon" in client.get("/api/jobs").json()["detail"]
    assert client.get("/api/health").status_code == 200  # public: instance detection needs it
    assert client.get("/api/jobs", headers={"x-md-token": "secret-token"}).status_code == 200


def test_launch_sets_cookie_then_everything_works(desktop):
    client, _ = desktop
    assert client.get("/launch?token=wrong", follow_redirects=False).status_code == 403
    r = client.get("/launch?token=secret-token", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "md_token=secret-token" in cookie
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/jobs").status_code == 200  # TestClient keeps the cookie


def test_desktop_startup_updates_ytdlp_and_checks_releases(desktop):
    client, _ = desktop
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        h = client.get("/api/health").json()
        if h["ytdlp_update"]["state"] == "done" and h["app_update"]:
            break
        time.sleep(0.02)
    assert h["desktop"] is True and h["version"] == main.__version__
    assert h["ytdlp_update"] == {"state": "done", "message": "yt-dlp is up to date"}
    assert h["app_update"] == {"latest": "9.9.9", "url": "https://x/rel"}


def test_update_and_quit_endpoints(desktop):
    client, quits = desktop
    client.get("/launch?token=secret-token", follow_redirects=False)
    time.sleep(0.1)
    r = client.post("/api/update-ytdlp")
    assert r.status_code == 200 and r.json()["message"] == "yt-dlp is up to date"
    assert client.post("/api/quit").json() == {"ok": True}
    assert quits == [True]
    assert client.get("/api/health").json()["quit_requested"] is True


def test_no_token_means_open_dev_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("MD_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MD_TOKEN", raising=False)
    monkeypatch.delenv("MD_DESKTOP", raising=False)
    with TestClient(main.app) as client:
        assert client.get("/api/jobs").status_code == 200
        assert client.post("/api/quit").status_code == 400
        h = client.get("/api/health").json()
        assert h["desktop"] is False and h["ytdlp_update"]["state"] == "idle"


def test_version_comparison():
    assert updates.is_newer("v0.5.0", "0.4.0")
    assert updates.is_newer("1.0", "0.9.9")
    assert not updates.is_newer("0.4.0", "0.4.0")
    assert not updates.is_newer("0.4.0-rc1", "0.4.0")
    assert updates.version_tuple("garbage") == (0,)


def test_check_latest_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(updates.urllib.request, "urlopen", boom)
    assert updates.check_latest("0.4.0") is None


def test_launcher_helpers(tmp_path):
    port = launcher.free_port()
    assert 1024 < port < 65536
    assert launcher.running_instance(tmp_path) is None  # no file
    path = launcher.write_instance(tmp_path, 8123, "tok")
    assert json.loads(path.read_text())["port"] == 8123
    assert launcher.running_instance(tmp_path) is None  # file, but nothing listening
    assert launcher.launch_url(8123, "tok") == "http://127.0.0.1:8123/launch?token=tok"
