from app.store import CANCELLED, DONE, ERROR, QUEUED, RUNNING, Store


def test_create_list_and_delete_jobs(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    job = store.create_job("video", {"height": 720}, ["https://a", "https://b"])
    assert job.kind == "video" and job.options == {"height": 720}
    assert [i.url for i in job.items] == ["https://a", "https://b"]
    assert [i.status for i in job.items] == [QUEUED, QUEUED]

    later = store.create_job("audio", {"audio_format": "mp3", "audio_bitrate": 192}, ["https://c"])
    assert [j.id for j in store.list_jobs()] == [later.id, job.id]  # newest first

    store.delete_job(job.id)
    assert store.get_job(job.id) is None
    assert store.get_item(job.items[0].id) is None  # cascaded


def test_claim_updates_and_recovery(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    job = store.create_job("video", {}, ["https://a", "https://b"])
    first = store.claim_next_queued()
    assert first is not None and first.url == "https://a" and first.status == RUNNING
    assert first.started_at and first.stage == "Starting"

    store.update_item(first.id, downloaded=50, total=100, speed=10.0, eta=5, stage="Downloading")
    item = store.get_item(first.id)
    assert (item.downloaded, item.total, item.stage) == (50, 100, "Downloading")

    assert store.count_with_status(RUNNING) == 1
    assert store.recover_interrupted() == 1
    recovered = store.get_item(first.id)
    assert (
        recovered.status == QUEUED and recovered.downloaded is None and recovered.started_at is None
    )

    assert [i.status for i in store.items_with_status(QUEUED)] == [QUEUED, QUEUED]
    assert store.get_job(job.id).items[0].status == QUEUED


def test_update_rejects_unknown_columns(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    job = store.create_job("video", {}, ["https://a"])
    try:
        store.update_item(job.items[0].id, bogus=1)
    except ValueError as exc:
        assert "bogus" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_settings_roundtrip(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    assert store.get_setting("output_dir") is None
    store.set_setting("output_dir", "/tmp/x")
    store.set_setting("output_dir", "/tmp/y")
    assert store.get_setting("output_dir") == "/tmp/y"


def test_status_constants():
    assert {QUEUED, RUNNING, DONE, ERROR, CANCELLED} == {
        "queued",
        "running",
        "done",
        "error",
        "cancelled",
    }
