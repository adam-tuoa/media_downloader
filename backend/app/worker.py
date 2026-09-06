"""The download queue: picks queued items, runs yt-dlp for each, records progress.

Everything here runs on the event-loop thread except yt-dlp itself (see ytdlp.py), so the
store is touched without locks. Progress writes are throttled to a few per second per item.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app import formats, links, ytdlp
from app.paths import default_output_dir
from app.store import CANCELLED, DONE, ERROR, QUEUED, RUNNING, Item, Job, Store

log = logging.getLogger(__name__)

PROGRESS_WRITE_INTERVAL = 0.25  # seconds between progress rows for one item
MAX_CONCURRENCY = 4

STAGE_LABELS = {
    "Merger": "Merging video and audio",
    "ExtractAudio": "Converting audio",
    "FixupM4a": "Finishing audio",
    "ThumbnailsConvertor": "Preparing cover art",
    "MetadataParser": "Reading tags",
    "Metadata": "Adding tags",
    "EmbedThumbnail": "Adding cover art",
    "EmbedSubtitle": "Adding subtitles",
    "MoveFiles": "Finishing",
    "FFmpegVideoRemuxer": "Remuxing",
    "FFmpegVideoConvertor": "Converting video",
}

_ILLEGAL_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_name(text: str | None, fallback: str = "Untitled") -> str:
    """A folder/file name that is legal on Windows, macOS and Linux."""
    cleaned = _ILLEGAL_NAME_CHARS.sub("_", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:120] or fallback


DEFAULT_AUDIO_LANGUAGE = "en"  # "" means "the original track, whatever language it is"


@dataclass(frozen=True)
class Settings:
    output_dir: Path
    concurrency: int
    audio_language: str


def current_settings(store: Store) -> Settings:
    output_dir = store.get_setting("output_dir")
    concurrency = store.get_setting("concurrency")
    language = store.get_setting("audio_language")
    return Settings(
        output_dir=Path(output_dir) if output_dir else default_output_dir(),
        concurrency=max(1, min(MAX_CONCURRENCY, int(concurrency or 2))),
        audio_language=DEFAULT_AUDIO_LANGUAGE if language is None else language,
    )


def build_download_args(job: Job, info: dict, language: str | None = None) -> list[str]:
    """yt-dlp arguments for one item. ``language`` picks among dubbed audio tracks when a video
    has several; "" or None keeps the original."""
    language = language or None
    if job.kind == "audio":
        audio_format = job.options.get("audio_format", "mp3")
        track = formats.best_audio(
            info, ext="m4a" if audio_format == "m4a" else None, language=language
        ) or formats.best_audio(info, language=language)
        args = formats.audio_download_args(
            audio_format,
            int(job.options.get("audio_bitrate", 320)),
            preferred_id=track.format_id if track else None,
        )
        return args + formats.tag_args(info, "audio")
    options = formats.video_options(info, language=language)
    if not options:
        raise ytdlp.YtdlpError("No video streams found for this link - try Audio instead")
    args = formats.video_download_args(formats.pick_height(options, job.options.get("height")))
    args += formats.tag_args(info, "video")
    if job.options.get("subtitles"):
        args += formats.subtitle_args()
    return args


def destination(output_dir: Path, item: Item) -> tuple[Path, str]:
    """(folder the finished file goes in, yt-dlp filename template) for one item.

    Items from a playlist/album get the collection's own folder and a "01 - " prefix, using the
    track name when the site provides one (Bandcamp) and the title otherwise."""
    if item.collection:
        folder = output_dir / safe_name(item.collection)
        if item.collection_index:
            return folder, f"{item.collection_index:02d} - %(track,title)s.%(ext)s"
        return folder, "%(track,title)s.%(ext)s"
    return output_dir, "%(title)s.%(ext)s"


def move_into(path: Path, dest_dir: Path) -> Path:
    """Move a finished file into the output folder without overwriting anything."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / path.name
    n = 1
    while target.exists():
        target = dest_dir / f"{path.stem} ({n}){path.suffix}"
        n += 1
    shutil.move(str(path), str(target))
    return target


class Manager:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.wake = asyncio.Event()
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.cancels: dict[str, threading.Event] = {}
        self._runner: asyncio.Task[None] | None = None

    # --- lifecycle ---

    async def start(self) -> None:
        recovered = self.store.recover_interrupted()
        if recovered:
            log.info("re-queued %d interrupted item(s)", recovered)
        self._runner = asyncio.create_task(self._run(), name="download-queue")

    async def stop(self) -> None:
        if self._runner:
            self._runner.cancel()
            self._runner = None
        for cancel in self.cancels.values():
            cancel.set()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    def notify(self) -> None:
        self.wake.set()

    # --- scheduling ---

    async def _run(self) -> None:
        while True:
            self.wake.clear()
            self._launch_ready()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=2.0)
            except TimeoutError:
                pass

    def _launch_ready(self) -> None:
        limit = current_settings(self.store).concurrency
        while len(self.tasks) < limit:
            item = self.store.claim_next_queued()
            if item is None:
                return
            task = asyncio.create_task(self._process(item), name=f"item-{item.id}")
            self.tasks[item.id] = task
            task.add_done_callback(lambda _t, item_id=item.id: self._finished(item_id))

    def _finished(self, item_id: str) -> None:
        self.tasks.pop(item_id, None)
        self.cancels.pop(item_id, None)
        self.wake.set()

    # --- one item ---

    async def _process(self, item: Item) -> None:
        cancel = threading.Event()
        self.cancels[item.id] = cancel
        settings = current_settings(self.store)
        work_dir = settings.output_dir / ".incomplete" / item.id
        try:
            job = self.store.get_job(item.job_id)
            if job is None:  # deleted while queued
                return
            info = await ytdlp.probe(item.url)
            if info.get("_type") == "playlist":
                raise ytdlp.YtdlpError(
                    "This is a playlist link - add it on its own to choose which entries to get"
                )
            self.store.update_item(
                item.id,
                title=info.get("title"),
                uploader=info.get("uploader") or info.get("channel") or info.get("artist"),
                duration=info.get("duration"),
                thumbnail=info.get("thumbnail"),
                stage="Starting download",
            )
            if cancel.is_set():
                raise ytdlp.YtdlpError("Cancelled")
            args = build_download_args(job, info, settings.audio_language)
            work_dir.mkdir(parents=True, exist_ok=True)
            seen: dict[str, int | None] = {"total": None}
            final_dir, name_template = destination(settings.output_dir, item)
            path = await ytdlp.download(
                item.url,
                args,
                str(work_dir / name_template),
                on_progress=self._progress_writer(item.id, seen),
                cancel=cancel,
                info=info,
            )
            final = await asyncio.to_thread(move_into, path, final_dir)
            self.store.update_item(
                item.id,
                status=DONE,
                stage="Done",
                file_path=str(final),
                downloaded=seen["total"],
                total=seen["total"],
                speed=None,
                eta=None,
                finished_at=time.time(),
            )
        except ytdlp.YtdlpError as exc:
            if cancel.is_set():
                self.store.update_item(
                    item.id,
                    status=CANCELLED,
                    stage=None,
                    speed=None,
                    eta=None,
                    finished_at=time.time(),
                )
            else:
                self.store.update_item(
                    item.id,
                    status=ERROR,
                    stage=None,
                    error=links.friendly_error(str(exc)),
                    speed=None,
                    eta=None,
                    finished_at=time.time(),
                )
        except Exception as exc:  # noqa: BLE001 - never let one item take the queue down
            log.exception("item %s failed unexpectedly", item.id)
            self.store.update_item(
                item.id,
                status=ERROR,
                stage=None,
                error=f"Unexpected error: {exc}",
                finished_at=time.time(),
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _progress_writer(self, item_id: str, seen: dict[str, int | None]):
        """Callback that records progress rows, throttled, and remembers the last known total."""
        last_write = 0.0
        last_stage: str | None = None

        def on_progress(p: ytdlp.Progress) -> None:
            nonlocal last_write, last_stage
            if p.stage == "postprocess":
                stage = STAGE_LABELS.get(p.postprocessor or "", "Processing")
                values: dict = {"stage": stage, "speed": None, "eta": None}
                must_write = stage != last_stage
            else:
                stage = {"video": "Downloading video", "audio": "Downloading audio"}.get(
                    p.stream or "", "Downloading"
                )
                if p.total:
                    seen["total"] = p.total
                values = {
                    "stage": stage,
                    "downloaded": p.downloaded,
                    "total": p.total,
                    "speed": p.speed,
                    "eta": p.eta,
                }
                must_write = stage != last_stage or p.status != "downloading"  # finished/error
            now = time.monotonic()
            if must_write or now - last_write >= PROGRESS_WRITE_INTERVAL:
                self.store.update_item(item_id, **values)
                last_write, last_stage = now, stage

        return on_progress

    # --- user actions ---

    def cancel_item(self, item_id: str) -> None:
        item = self.store.get_item(item_id)
        if item is None:
            return
        if item.status == RUNNING and item_id in self.cancels:
            self.cancels[item_id].set()
        elif item.status == QUEUED:
            self.store.update_item(item_id, status=CANCELLED, finished_at=time.time())

    def cancel_job(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        if job:
            for item in job.items:
                self.cancel_item(item.id)

    def retry_item(self, item_id: str) -> bool:
        item = self.store.get_item(item_id)
        if item is None or item.status not in (ERROR, CANCELLED):
            return False
        self.store.update_item(
            item_id,
            status=QUEUED,
            stage=None,
            error=None,
            downloaded=None,
            total=None,
            speed=None,
            eta=None,
            file_path=None,
            started_at=None,
            finished_at=None,
        )
        self.notify()
        return True
