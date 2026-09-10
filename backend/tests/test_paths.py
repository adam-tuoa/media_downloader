"""The app-data folder, and what the rename from Media Downloader carries across."""

from fastapi.testclient import TestClient

from app import main, paths


def _app_data_under(monkeypatch, root):
    monkeypatch.delenv("USEFULMEDIA_DATA_DIR", raising=False)
    monkeypatch.setattr(paths, "user_data_dir", lambda name, appauthor=False: str(root / name))
    monkeypatch.setattr(paths, "adopted_from", None)


def test_old_app_data_folder_is_moved_across_once(monkeypatch, tmp_path):
    _app_data_under(monkeypatch, tmp_path)
    old = tmp_path / paths.LEGACY_APP_NAME
    old.mkdir()
    (old / "jobs.sqlite3").write_bytes(b"db")
    (old / "app.log").write_text("log", encoding="utf-8")

    folder = paths.data_dir()

    assert folder == tmp_path / paths.APP_NAME
    assert (folder / "jobs.sqlite3").read_bytes() == b"db"
    assert (folder / "app.log").read_text(encoding="utf-8") == "log"
    assert not old.exists()
    assert paths.adopted_from == old
    assert paths.data_dir() == folder  # a second call is a plain lookup


def test_existing_new_folder_leaves_the_old_one_alone(monkeypatch, tmp_path):
    _app_data_under(monkeypatch, tmp_path)
    old = tmp_path / paths.LEGACY_APP_NAME
    old.mkdir()
    (old / "jobs.sqlite3").write_bytes(b"old")
    new = tmp_path / paths.APP_NAME
    new.mkdir()
    (new / "jobs.sqlite3").write_bytes(b"new")

    assert paths.data_dir() == new
    assert (new / "jobs.sqlite3").read_bytes() == b"new"
    assert (old / "jobs.sqlite3").read_bytes() == b"old"
    assert paths.adopted_from is None


def test_fresh_install_needs_no_old_folder(monkeypatch, tmp_path):
    _app_data_under(monkeypatch, tmp_path)
    assert paths.data_dir().is_dir()
    assert paths.adopted_from is None


def test_override_skips_the_move(monkeypatch, tmp_path):
    _app_data_under(monkeypatch, tmp_path)
    (tmp_path / paths.LEGACY_APP_NAME).mkdir()
    monkeypatch.setenv("USEFULMEDIA_DATA_DIR", str(tmp_path / "elsewhere"))
    assert paths.data_dir() == tmp_path / "elsewhere"
    assert (tmp_path / paths.LEGACY_APP_NAME).is_dir()


def test_default_download_folders():
    assert paths.default_output_dir().name == "UsefulMedia"
    assert paths.legacy_output_dir().name == "Media Downloader"


def test_downloads_stay_in_the_pre_rename_folder_when_it_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("USEFULMEDIA_DATA_DIR", str(tmp_path / "data"))
    legacy = paths.legacy_output_dir()
    legacy.mkdir(parents=True)
    with TestClient(main.app) as client:
        assert client.get("/api/settings").json()["output_dir"] == str(legacy)


def test_new_installs_download_to_the_new_default(monkeypatch, tmp_path):
    monkeypatch.setenv("USEFULMEDIA_DATA_DIR", str(tmp_path / "data"))
    with TestClient(main.app) as client:
        assert client.get("/api/settings").json()["output_dir"] == str(paths.default_output_dir())
