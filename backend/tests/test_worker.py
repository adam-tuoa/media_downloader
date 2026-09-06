import asyncio

import pytest

from app import worker
from app.store import CANCELLED, DONE, ERROR, QUEUED, RUNNING, Store
from tests import fakes


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "db.sqlite3")
    s.set_setting("output_dir", str(tmp_path / "out"))
    s.set_setting("concurrency", "2")
    return s


@pytest.fixture
def fake(monkeypatch):
    return fakes.install(monkeypatch)


async def wait_until(predicate, max_wait=5.0):
    deadline = asyncio.get_running_loop().time() + max_wait
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


async def test_job_runs_to_done_and_moves_file(store, fake, tmp_path):
    manager = worker.Manager(store)
    await manager.start()
    try:
        job = store.create_job("video", {"height": 720}, ["https://x/v1"])
        manager.notify()
        await wait_until(lambda: store.get_item(job.items[0].id).status == DONE)
    finally:
        await manager.stop()

    item = store.get_item(job.items[0].id)
    assert item.title == "Fake video v1" and item.uploader == "Someone" and item.duration == 12
    assert item.stage == "Done" and item.error is None and item.finished_at
    assert item.file_path == str(tmp_path / "out" / "Fake video [v1].mp4")
    assert (tmp_path / "out" / "Fake video [v1].mp4").read_bytes() == b"media"
    assert not (tmp_path / "out" / ".incomplete" / item.id).exists()
    assert fake.calls[0][:2] == ["-f", "22/best[height<=720]"]  # 720p muxed stream chosen
    assert fake.infos[0]["title"] == "Fake video v1"  # probe result reused for the download
    assert item.downloaded == item.total == 300  # final counters reflect the finished download


async def test_audio_job_uses_extract_args_and_no_overwrite(store, fake, tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "Fake video [v1].mp3").write_bytes(b"old")
    manager = worker.Manager(store)
    await manager.start()
    try:
        job = store.create_job(
            "audio", {"audio_format": "mp3", "audio_bitrate": 192}, ["https://x/v1"]
        )
        manager.notify()
        await wait_until(lambda: store.get_item(job.items[0].id).status == DONE)
    finally:
        await manager.stop()
    assert fake.calls[0] == [
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "192K",
    ]
    item = store.get_item(job.items[0].id)
    assert item.file_path.endswith("Fake video [v1] (1).mp3")
    assert (tmp_path / "out" / "Fake video [v1].mp3").read_bytes() == b"old"


async def test_probe_failure_marks_error(store, fake):
    fake.probe_error = "[youtube] v1: Video unavailable"
    manager = worker.Manager(store)
    await manager.start()
    try:
        job = store.create_job("video", {}, ["https://x/v1"])
        manager.notify()
        await wait_until(lambda: store.get_item(job.items[0].id).status == ERROR)
    finally:
        await manager.stop()
    error = store.get_item(job.items[0].id).error
    assert error.startswith("This video isn't available") and "[youtube] v1" in error


async def test_concurrency_limit_and_cancel(store, fake):
    fake.hold.set()
    manager = worker.Manager(store)
    await manager.start()
    try:
        job = store.create_job("video", {}, ["https://x/v1", "https://x/v2", "https://x/v3"])
        manager.notify()
        await wait_until(lambda: store.count_with_status(RUNNING) == 2)
        await asyncio.sleep(0.1)
        assert store.count_with_status(RUNNING) == 2 and store.count_with_status(QUEUED) == 1

        manager.cancel_job(job.id)
        await wait_until(lambda: store.count_with_status(CANCELLED) == 3)
    finally:
        await manager.stop()
    statuses = [store.get_item(i.id).status for i in job.items]
    assert statuses == [CANCELLED, CANCELLED, CANCELLED]


async def test_retry_requeues_failed_item(store, fake):
    fake.probe_error = "boom"
    manager = worker.Manager(store)
    await manager.start()
    try:
        job = store.create_job("video", {}, ["https://x/v1"])
        manager.notify()
        item_id = job.items[0].id
        await wait_until(lambda: store.get_item(item_id).status == ERROR)

        fake.probe_error = None
        assert manager.retry_item(item_id) is True
        await wait_until(lambda: store.get_item(item_id).status == DONE)
        assert manager.retry_item(item_id) is False  # not retryable when done
    finally:
        await manager.stop()
    assert store.get_item(item_id).error is None


def test_move_into_never_overwrites(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "dest"
    for expected in ("a.mp4", "a (1).mp4", "a (2).mp4"):
        f = src / "a.mp4"
        f.write_bytes(b"x")
        assert worker.move_into(f, dest).name == expected
    assert sorted(p.name for p in dest.iterdir()) == ["a (1).mp4", "a (2).mp4", "a.mp4"]


def test_current_settings_defaults_and_clamping(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    s = worker.current_settings(store)
    assert s.concurrency == 2 and s.output_dir.name == "Media Downloader"
    store.set_setting("concurrency", "99")
    assert worker.current_settings(store).concurrency == worker.MAX_CONCURRENCY


async def test_playlist_link_is_refused_by_worker(store, fake, monkeypatch):
    async def playlist_probe(url):
        return {"_type": "playlist", "title": "PL", "entries": []}

    monkeypatch.setattr(worker.ytdlp, "probe", playlist_probe)
    manager = worker.Manager(store)
    await manager.start()
    try:
        job = store.create_job("video", {}, ["https://www.youtube.com/playlist?list=PL1"])
        manager.notify()
        await wait_until(lambda: store.get_item(job.items[0].id).status == ERROR)
    finally:
        await manager.stop()
    assert "playlist" in store.get_item(job.items[0].id).error


async def test_error_messages_get_friendly_hints(store, fake):
    fake.probe_error = "[vimeo] 1: The web client only works when logged-in. Use --cookies"
    manager = worker.Manager(store)
    await manager.start()
    try:
        job = store.create_job("video", {}, ["https://vimeo.com/1"])
        manager.notify()
        await wait_until(lambda: store.get_item(job.items[0].id).status == ERROR)
    finally:
        await manager.stop()
    assert store.get_item(job.items[0].id).error.startswith("Needs a signed-in browser")


def test_stage_labels_follow_the_stream(store):
    manager = worker.Manager(store)
    job = store.create_job("video", {}, ["https://x/v1"])
    item_id = job.items[0].id
    on_progress = manager._progress_writer(item_id, {"total": None})
    on_progress(worker.ytdlp.Progress("download", "downloading", 1, 10, stream="video"))
    assert store.get_item(item_id).stage == "Downloading video"
    on_progress(worker.ytdlp.Progress("download", "downloading", 1, 10, stream="audio"))
    assert store.get_item(item_id).stage == "Downloading audio"
    on_progress(worker.ytdlp.Progress("download", "downloading", 1, 10))
    assert store.get_item(item_id).stage == "Downloading"
