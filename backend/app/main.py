"""Media Downloader API: a download queue with progress, writing files to a folder.

Phase 1. Jobs are submitted with one or more URLs and shared options; a background worker
(see worker.py) processes the items. The UI polls /api/jobs.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app import desktop, formats, links, ytdlp
from app.paths import data_dir
from app.store import ACTIVE, NewItem, Store
from app.worker import MAX_CONCURRENCY, Manager, current_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = Store(data_dir() / "jobs.sqlite3")
    manager = Manager(store)
    app.state.store, app.state.manager = store, manager
    ytdlp.options.cookies_browser = store.get_setting("cookies_browser") or None
    await manager.start()
    try:
        yield
    finally:
        await manager.stop()
        store.close()


app = FastAPI(title="Media Downloader", version="0.2.0", lifespan=lifespan)

_origins = os.environ.get("MD_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _clean_url(value: str) -> str:
    value = value.strip()
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError(f"Not a link: {value[:60]!r} - links start with http:// or https://")
    return value


class UrlRequest(BaseModel):
    url: str = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def _must_be_a_link(cls, value: str) -> str:
        return _clean_url(value)


class LinkIn(BaseModel):
    url: str = Field(min_length=1)
    title: str | None = None
    thumbnail: str | None = None
    collection: str | None = Field(default=None, max_length=300)
    collection_index: int | None = Field(default=None, ge=1)


class JobCreate(BaseModel):
    links: list[LinkIn] = Field(min_length=1, max_length=500)
    kind: Literal["video", "audio"] = "video"
    height: int | None = Field(default=None, ge=144, description="video: largest height allowed")
    subtitles: bool = False
    audio_format: Literal["mp3", "m4a", "best"] = "mp3"
    audio_bitrate: Literal[128, 192, 320] = 320


class LinksRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=100)


Browser = Literal["chrome", "firefox", "edge", "safari", "brave", "chromium", "opera", "vivaldi"]


class SettingsUpdate(BaseModel):
    output_dir: str | None = None
    concurrency: int | None = Field(default=None, ge=1, le=MAX_CONCURRENCY)
    cookies_browser: Browser | Literal[""] | None = None  # "" clears it


class RevealRequest(BaseModel):
    item_id: str | None = None


@app.exception_handler(ytdlp.YtdlpError)
async def _ytdlp_error(_: Request, exc: ytdlp.YtdlpError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


def _store(request: Request) -> Store:
    return request.app.state.store


def _manager(request: Request) -> Manager:
    return request.app.state.manager


# --- info ---


@app.get("/api/health")
async def health() -> dict:
    try:
        version: str | None = await ytdlp.version()
    except (ytdlp.YtdlpError, TimeoutError):
        version = None
    return {"status": "ok" if version else "degraded", "ytdlp": version}


@app.post("/api/probe")
async def probe(req: UrlRequest) -> dict:
    return formats.summary(await ytdlp.probe(req.url))


# --- links ---


def _entry_thumbnail(entry: dict) -> str | None:
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = entry.get("thumbnails") or []
    return thumbs[-1].get("url") if thumbs else None


async def _describe_link(raw: str, link: links.Link, limit: asyncio.Semaphore) -> dict:
    """What one pasted line turns out to be; playlists get their entries listed."""
    base = {"input": raw, "url": link.url, "site": link.site}
    if link.kind == "video":
        return {**base, "kind": "video"}
    async with limit:
        try:
            info = await ytdlp.inspect(link.url)
        except ytdlp.YtdlpError as exc:
            return {"input": raw, "message": links.friendly_error(str(exc))}
    if info.get("_type") != "playlist":
        return {
            **base,
            "kind": "video",
            "url": info.get("webpage_url") or link.url,
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
        }
    entries = [
        {
            "url": e.get("url") or e.get("webpage_url"),
            "title": e.get("title"),
            "duration": e.get("duration"),
            "thumbnail": _entry_thumbnail(e),
        }
        for e in info.get("entries") or []
        if e and (e.get("url") or e.get("webpage_url"))
    ]
    count = info.get("playlist_count") or len(entries)
    return {
        **base,
        "kind": "playlist",
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "count": count,
        "truncated": count > len(entries),
        "entries": entries,
    }


@app.post("/api/links")
async def inspect_links(req: LinksRequest) -> dict:
    """Step one of adding downloads: say what each pasted line is (video, playlist + entries, or
    a problem) so the UI can let the user choose before anything is queued."""
    parsed: list[tuple[str, links.Link]] = []
    errors: list[dict] = []
    seen: set[str] = set()
    for raw in req.urls:
        if not raw.strip():
            continue
        try:
            link = links.parse(raw)
        except links.LinkError as exc:
            errors.append({"input": raw, "message": str(exc)})
            continue
        if link.url not in seen:
            seen.add(link.url)
            parsed.append((raw, link))
    limit = asyncio.Semaphore(3)
    described = await asyncio.gather(*(_describe_link(raw, link, limit) for raw, link in parsed))
    results = [d for d in described if "kind" in d]
    errors += [d for d in described if "kind" not in d]
    return {"links": results, "errors": errors}


# --- jobs ---


@app.get("/api/jobs")
async def list_jobs(request: Request) -> list[dict]:
    return [job.to_dict() for job in _store(request).list_jobs()]


@app.post("/api/jobs", status_code=201)
async def create_job(req: JobCreate, request: Request) -> dict:
    options = (
        {"height": req.height, "subtitles": req.subtitles}
        if req.kind == "video"
        else {"audio_format": req.audio_format, "audio_bitrate": req.audio_bitrate}
    )
    items: list[NewItem] = []
    seen: set[str] = set()
    for entry in req.links:
        try:
            link = links.parse(entry.url)
        except links.LinkError as exc:
            raise HTTPException(422, str(exc)) from exc
        if link.kind == "playlist":
            raise HTTPException(422, "Playlist links need to be expanded first (POST /api/links)")
        if link.url not in seen:
            seen.add(link.url)
            items.append(
                NewItem(
                    url=link.url,
                    title=entry.title,
                    thumbnail=entry.thumbnail,
                    collection=entry.collection,
                    collection_index=entry.collection_index,
                )
            )
    job = _store(request).create_job(req.kind, options, items)
    _manager(request).notify()
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    job = _store(request).get_job(job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> dict:
    if _store(request).get_job(job_id) is None:
        raise HTTPException(404, "No such job")
    _manager(request).cancel_job(job_id)
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, request: Request) -> dict:
    store = _store(request)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    if any(item.status in ACTIVE for item in job.items):
        _manager(request).cancel_job(job_id)
    store.delete_job(job_id)  # files stay where they are
    return {"ok": True}


@app.post("/api/items/{item_id}/cancel")
async def cancel_item(item_id: str, request: Request) -> dict:
    if _store(request).get_item(item_id) is None:
        raise HTTPException(404, "No such item")
    _manager(request).cancel_item(item_id)
    return {"ok": True}


@app.post("/api/items/{item_id}/retry")
async def retry_item(item_id: str, request: Request) -> dict:
    if not _manager(request).retry_item(item_id):
        raise HTTPException(409, "Only failed or cancelled items can be retried")
    return {"ok": True}


# --- settings & desktop ---


def _settings_dict(store: Store) -> dict:
    s = current_settings(store)
    return {
        "output_dir": str(s.output_dir),
        "concurrency": s.concurrency,
        "cookies_browser": store.get_setting("cookies_browser") or None,
    }


@app.get("/api/settings")
async def get_settings(request: Request) -> dict:
    return _settings_dict(_store(request))


def _prepare_folder(raw: str) -> tuple[Path | None, str | None]:
    """Resolve, create and check a folder the user typed; returns (path, error)."""
    path = Path(raw).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"Can't use that folder: {exc.strerror or exc}"
    if not os.access(path, os.W_OK):
        return None, "Can't write to that folder"
    return path.resolve(), None


@app.put("/api/settings")
async def update_settings(req: SettingsUpdate, request: Request) -> dict:
    store = _store(request)
    if req.output_dir is not None:
        path, error = await asyncio.to_thread(_prepare_folder, req.output_dir)
        if error or path is None:
            raise HTTPException(422, error or "Can't use that folder")
        store.set_setting("output_dir", str(path))
    if req.concurrency is not None:
        store.set_setting("concurrency", str(req.concurrency))
        _manager(request).notify()
    if req.cookies_browser is not None:
        store.set_setting("cookies_browser", req.cookies_browser)
        ytdlp.options.cookies_browser = req.cookies_browser or None
    return _settings_dict(store)


def _reveal_target(store: Store, item_id: str | None) -> Path:
    if item_id:
        item = store.get_item(item_id)
        if item and item.file_path and Path(item.file_path).exists():
            return Path(item.file_path)
    folder = current_settings(store).output_dir
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@app.post("/api/reveal")
async def reveal(req: RevealRequest, request: Request) -> dict:
    """Open the output folder, or the folder of one finished item with the file selected."""
    target = await asyncio.to_thread(_reveal_target, _store(request), req.item_id)
    await asyncio.to_thread(desktop.reveal, target)
    return {"ok": True, "path": str(target)}


# The desktop app serves the built UI from here (PLAN.md Phase 4).
# In dev the directory is absent and Vite serves the UI instead.
_static = Path(__file__).parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="ui")
