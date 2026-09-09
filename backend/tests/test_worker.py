import asyncio

import pytest

from app import worker
from app.store import CANCELLED, DONE, ERROR, QUEUED, RUNNING, NewItem, Store
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
    assert fake.calls[0][:7] == [
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "192K",
    ]
    assert "--embed-thumbnail" in fake.calls[0] and "--embed-metadata" in fake.calls[0]
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


async def test_collection_items_get_a_folder_and_numbers(store, fake, tmp_path):
    manager = worker.Manager(store)
    await manager.start()
    try:
        job = store.create_job(
            "audio",
            {"audio_format": "best"},
            [
                NewItem("https://x/v1", collection="Live: At The Zoo?", collection_index=1),
                NewItem("https://x/v2", collection="Live: At The Zoo?", collection_index=12),
            ],
        )
        manager.notify()
        await wait_until(lambda: all(store.get_item(i.id).status == DONE for i in job.items))
    finally:
        await manager.stop()
    folder = tmp_path / "out" / "Live_ At The Zoo_"
    assert sorted(p.name for p in folder.iterdir()) == [
        "01 - Fake video [v1].mp3",
        "12 - Fake video [v2].mp3",
    ]
    assert fake.calls[0][:5] == ["-f", "bestaudio/best", "-x", "--audio-format", "best"]


def test_destination_and_safe_name(tmp_path):
    from app.store import Item

    plain = Item("i", "j", 0, "u", QUEUED)
    assert worker.destination(tmp_path, plain) == (tmp_path, "%(title)s.%(ext)s")
    numbered = Item("i", "j", 0, "u", QUEUED, collection="A/B", collection_index=3)
    assert worker.destination(tmp_path, numbered) == (
        tmp_path / "A_B",
        "03 - %(track,title)s.%(ext)s",
    )
    unnumbered = Item("i", "j", 0, "u", QUEUED, collection="Mix")
    assert worker.destination(tmp_path, unnumbered) == (
        tmp_path / "Mix",
        "%(track,title)s.%(ext)s",
    )

    assert worker.safe_name('  AC/DC: "Live" <2024>?  ') == "AC_DC_ _Live_ _2024_"
    assert worker.safe_name("trailing dots...") == "trailing dots"
    assert worker.safe_name("") == "Untitled" and worker.safe_name(None, "X") == "X"
    assert len(worker.safe_name("x" * 500)) == 120


def test_build_args_include_tags_and_subtitles(bbb_info):
    from app.store import Job

    video = Job("j", 0, "video", {"height": 720, "subtitles": True})
    args = worker.build_download_args(video, bbb_info)
    assert "--embed-thumbnail" in args and "--embed-subs" in args
    quiet = Job("j", 0, "video", {"height": 720})
    assert "--embed-subs" not in worker.build_download_args(quiet, bbb_info)
    audio = Job("j", 0, "audio", {"audio_format": "m4a"})
    args = worker.build_download_args(audio, bbb_info)
    assert "bestaudio[ext=m4a]" in args[1] and "--embed-metadata" in args
    wav = worker.build_download_args(Job("j", 0, "audio", {"audio_format": "wav"}), bbb_info)
    assert "--embed-metadata" in wav and "--embed-thumbnail" not in wav  # no cover art in WAV


def test_subtitles_follow_the_language_setting(bbb_info):
    from app.store import Job

    video = Job("j", 0, "video", {"height": 720, "subtitles": True})
    args = worker.build_download_args(video, bbb_info, "es")
    assert args[args.index("--sub-langs") + 1] == "es.*,es"
    original = worker.build_download_args(video, {**bbb_info, "language": "de"}, "")
    assert original[original.index("--sub-langs") + 1] == "de.*,de"


def test_build_args_follow_the_audio_language(multilang_info):
    from app.store import Job

    audio = Job("j", 0, "audio", {"audio_format": "m4a"})
    assert worker.build_download_args(audio, multilang_info, "es")[1].startswith("140-9/")
    assert worker.build_download_args(audio, multilang_info, "")[1].startswith("140-23/")
    video = Job("j", 0, "video", {"height": 720})
    assert "+140-12/" in worker.build_download_args(video, multilang_info, "fr")[1]
    assert "+140-23/" in worker.build_download_args(video, multilang_info, None)[1]


def test_audio_language_setting_defaults_to_english(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    assert worker.current_settings(store).audio_language == "en"
    store.set_setting("audio_language", "")
    assert worker.current_settings(store).audio_language == ""
