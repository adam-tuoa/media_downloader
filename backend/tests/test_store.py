import sqlite3

from app.store import CANCELLED, DONE, ERROR, QUEUED, RUNNING, NewItem, Store


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


def test_items_carry_collection(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    job = store.create_job(
        "audio", {}, [NewItem("https://a", collection="An Album", collection_index=2), "https://b"]
    )
    assert (job.items[0].collection, job.items[0].collection_index) == ("An Album", 2)
    assert (job.items[1].collection, job.items[1].collection_index) == (None, None)


def test_old_database_gets_new_columns(tmp_path):
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE jobs (id TEXT PRIMARY KEY, created_at REAL NOT NULL, kind TEXT NOT NULL,
            options TEXT NOT NULL);
        CREATE TABLE items (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, position INTEGER NOT NULL,
            url TEXT NOT NULL, status TEXT NOT NULL, title TEXT, uploader TEXT, duration REAL,
            thumbnail TEXT, stage TEXT, downloaded INTEGER, total INTEGER, speed REAL, eta INTEGER,
            file_path TEXT, error TEXT, created_at REAL NOT NULL, started_at REAL,
            finished_at REAL);
        INSERT INTO jobs VALUES ('j', 1, 'video', '{}');
        INSERT INTO items (id, job_id, position, url, status, created_at)
            VALUES ('i', 'j', 0, 'https://a', 'done', 1);
        """
    )
    conn.commit()
    conn.close()
    store = Store(path)  # must not fail, and must add the columns
    item = store.get_item("i")
    assert item is not None and item.collection is None and item.collection_index is None
    store.update_item("i", collection="X", collection_index=1)
    assert store.get_item("i").collection == "X"
