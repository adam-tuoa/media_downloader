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
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app import __version__, desktop, formats, links, updates, ytdlp
from app.paths import data_dir
from app.store import ACTIVE, DONE, RUNNING, NewItem, Store
from app.worker import MAX_CONCURRENCY, Manager, current_settings, move_into, safe_name


async def _desktop_startup(app: FastAPI, manager: Manager) -> None:
    """Desktop mode: refresh yt-dlp before the queue starts, then look for an app update."""
    app.state.ytdlp_update = {"state": "running", "message": "Checking for a downloader update…"}
    try:
        report = await ytdlp.update()
        message = report.splitlines()[-1] if report else "Up to date"
        app.state.ytdlp_update = {"state": "done", "message": message}
    except Exception as exc:  # noqa: BLE001 - offline etc.; never block the app on this
        app.state.ytdlp_update = {"state": "failed", "message": str(exc)}
    await manager.start()
    app.state.app_update = await asyncio.to_thread(updates.check_latest, __version__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = Store(data_dir() / "jobs.sqlite3")
    manager = Manager(store)
    app.state.store, app.state.manager = store, manager
    app.state.token = os.environ.get("MD_TOKEN") or None
    app.state.desktop = os.environ.get("MD_DESKTOP") == "1"
    app.state.ytdlp_update = {"state": "idle", "message": ""}
    app.state.app_update = None
    app.state.quit_requested = False
    if not hasattr(app.state, "on_quit"):
        app.state.on_quit = None
    ytdlp.options.cookies_browser = store.get_setting("cookies_browser") or None
    startup: asyncio.Task | None = None
    if app.state.desktop:
        startup = asyncio.create_task(_desktop_startup(app, manager))
    else:
        await manager.start()
    try:
        yield
    finally:
        if startup and not startup.done():
            startup.cancel()
        await manager.stop()
        store.close()


app = FastAPI(title="Media Downloader", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def require_launch_token(request: Request, call_next):
    """In desktop mode every /api call must carry this launch's secret (cookie or header)."""
    token = getattr(request.app.state, "token", None)
    path = request.url.path
    if token and path.startswith("/api/") and path != "/api/health":
        supplied = request.cookies.get("md_token") or request.headers.get("x-md-token")
        if supplied != token:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "This tab isn't connected to the app"
                    " - open Media Downloader from its icon."
                },
            )
    return await call_next(request)


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
    audio_format: Literal["mp3", "m4a", "best", "wav", "aiff"] = "mp3"
    audio_bitrate: Literal[128, 192, 320] = 320


class LinksRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=100)


Browser = Literal["chrome", "firefox", "edge", "safari", "brave", "chromium", "opera", "vivaldi"]


class SettingsUpdate(BaseModel):
    output_dir: str | None = None
    concurrency: int | None = Field(default=None, ge=1, le=MAX_CONCURRENCY)
    cookies_browser: Browser | Literal[""] | None = None  # "" clears it
    audio_language: str | None = Field(
        default=None, pattern=r"^([A-Za-z]{2,3}(-[A-Za-z]{2,4})?)?$", description='"" = original'
    )
    # What the form starts with. The values are the UI's own choice keys; stored, not interpreted.
    default_kind: Literal["video", "audio"] | None = None
    default_video: str | None = Field(default=None, pattern=r"^(best|\d{3,4})$")
    default_audio: str | None = Field(
        default=None, pattern=r"^(mp3-(128|192|320)|m4a|best|wav|aiff)$"
    )


class RevealRequest(BaseModel):
    item_id: str | None = None
    group: str | None = Field(default=None, max_length=120)  # a playlist's folder


class LibrarySelection(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=500)


class MoveRequest(LibrarySelection):
    group: str = Field(default="", max_length=120, description='folder name; "" = the main folder')


@app.exception_handler(ytdlp.YtdlpError)
async def _ytdlp_error(_: Request, exc: ytdlp.YtdlpError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


def _store(request: Request) -> Store:
    return request.app.state.store


def _manager(request: Request) -> Manager:
    return request.app.state.manager


# --- info ---


@app.get("/launch")
async def launch(token: str, request: Request) -> RedirectResponse:
    """Where the launcher points the browser: remember the launch secret, then show the app."""
    if not request.app.state.token or token != request.app.state.token:
        raise HTTPException(403, "Wrong launch token")
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        "md_token", token, httponly=True, samesite="strict", max_age=365 * 24 * 3600
    )
    return response


@app.get("/api/health")
async def health(request: Request) -> dict:
    state = request.app.state
    try:
        version: str | None = await ytdlp.version()
    except (ytdlp.YtdlpError, TimeoutError):
        version = None
    return {
        "status": "ok" if version else "degraded",
        "ytdlp": version,
        "version": __version__,
        "desktop": bool(getattr(state, "desktop", False)),
        "ytdlp_update": getattr(state, "ytdlp_update", {"state": "idle", "message": ""}),
        "app_update": getattr(state, "app_update", None),
        "quit_requested": bool(getattr(state, "quit_requested", False)),
        "cookies_warning": ytdlp.cookie_warning(),
    }


@app.post("/api/update-ytdlp")
async def update_ytdlp(request: Request) -> dict:
    """Run yt-dlp's self-updater on demand (not while something is downloading)."""
    state = request.app.state
    if _store(request).count_with_status(RUNNING):
        raise HTTPException(409, "Wait for the current downloads to finish first")
    if state.ytdlp_update.get("state") == "running":
        raise HTTPException(409, "An update is already running")
    state.ytdlp_update = {"state": "running", "message": "Updating…"}
    try:
        report = await ytdlp.update()
    except (ytdlp.YtdlpError, TimeoutError) as exc:
        state.ytdlp_update = {"state": "failed", "message": str(exc)}
        raise HTTPException(502, str(exc)) from exc
    message = report.splitlines()[-1] if report else "Up to date"
    state.ytdlp_update = {"state": "done", "message": message}
    return {"ok": True, "message": message}


@app.post("/api/quit")
async def quit_app(request: Request) -> dict:
    """Desktop mode: stop the server (the launcher process then exits)."""
    state = request.app.state
    if not state.desktop:
        raise HTTPException(400, "Not running as the desktop app")
    state.quit_requested = True
    _manager(request).notify()
    if state.on_quit:
        state.on_quit()
    return {"ok": True}


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
async def remove_job(job_id: str, request: Request) -> dict:
    """Take a job off the board. Finished downloads stay in the library; files stay on disk."""
    store = _store(request)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    if any(item.status in ACTIVE for item in job.items):
        _manager(request).cancel_job(job_id)
    store.archive_job(job_id)
    return {"ok": True}


@app.post("/api/jobs/clear-finished")
async def clear_finished(request: Request) -> dict:
    return {"ok": True, "archived": _store(request).archive_finished()}


# --- library ---


def _with_file_status(rows: list[dict]) -> list[dict]:
    for row in rows:
        row["exists"] = bool(row["file_path"]) and Path(row["file_path"]).exists()
    return rows


@app.get("/api/library")
async def library(
    request: Request, q: str = "", limit: int = 100, offset: int = 0, group: str | None = None
) -> dict:
    """Everything ever downloaded, newest first, noting whether each file is still there.
    ``group`` narrows it to one playlist (collection), in playlist order."""
    store = _store(request)
    query = q.strip() or None
    limit = max(1, min(limit, 500))
    page = store.library(query, limit, offset, collection=group)
    rows = await asyncio.to_thread(_with_file_status, page)
    return {
        "items": rows,
        "total": store.library_count(query, collection=group),
        "offset": offset,
        "groups": store.collections(),
    }


@app.post("/api/library/remove")
async def forget_downloads(req: LibrarySelection, request: Request) -> dict:
    """Take several downloads out of the history at once; files are never touched."""
    store = _store(request)
    removed = 0
    for item_id in req.item_ids:
        if store.get_item(item_id) is not None:
            store.delete_item(item_id)
            removed += 1
    return {"ok": True, "removed": removed}


def _move_items(store: Store, item_ids: list[str], group: str) -> dict:
    """Move finished files into ``<output>/<group>/`` (or back to ``<output>``) and make that the
    items' collection, so "Download again" lands there too. Nothing is ever overwritten; items
    whose file has gone are skipped and reported."""
    name = safe_name(group) if group.strip() else None
    root = current_settings(store).output_dir
    dest_dir = root / name if name else root
    moved, skipped = 0, []
    for item_id in item_ids:
        item = store.get_item(item_id)
        if item is None or item.status != DONE or not item.file_path:
            skipped.append({"id": item_id, "title": None, "reason": "not a finished download"})
            continue
        title = item.title or item.url
        path = Path(item.file_path)
        if not path.exists():
            skipped.append({"id": item_id, "title": title, "reason": "file missing"})
            continue
        if path.parent.resolve() != dest_dir.resolve():
            try:
                path = move_into(path, dest_dir)
            except OSError as exc:
                reason = f"couldn't move it: {exc.strerror or exc}"
                skipped.append({"id": item_id, "title": title, "reason": reason})
                continue
        store.update_item(item_id, file_path=str(path), collection=name, collection_index=None)
        moved += 1
    return {"ok": True, "moved": moved, "skipped": skipped, "group": name}


@app.post("/api/library/move")
async def move_downloads(req: MoveRequest, request: Request) -> dict:
    return await asyncio.to_thread(_move_items, _store(request), req.item_ids, req.group)


@app.post("/api/library/{item_id}/redownload", status_code=201)
async def redownload(item_id: str, request: Request) -> dict:
    """Queue the same link again with the options it was downloaded with."""
    store = _store(request)
    item = store.get_item(item_id)
    job = store.get_job(item.job_id) if item else None
    if item is None or job is None:
        raise HTTPException(404, "No such download")
    new_job = store.create_job(
        job.kind,
        job.options,
        [
            NewItem(
                url=item.url,
                title=item.title,
                thumbnail=item.thumbnail,
                collection=item.collection,
                collection_index=item.collection_index,
            )
        ],
    )
    _manager(request).notify()
    return new_job.to_dict()


@app.delete("/api/library/{item_id}")
async def forget_download(item_id: str, request: Request) -> dict:
    store = _store(request)
    if store.get_item(item_id) is None:
        raise HTTPException(404, "No such download")
    store.delete_item(item_id)  # the file itself is never touched
    return {"ok": True}


@app.post("/api/items/{item_id}/open")
async def open_item(item_id: str, request: Request) -> dict:
    """Open a finished item's file in whatever the OS plays it with."""
    item = _store(request).get_item(item_id)
    if item is None or not item.file_path:
        raise HTTPException(404, "No such download")
    path = Path(item.file_path)
    if not await asyncio.to_thread(path.exists):
        raise HTTPException(404, "The file isn't where it was saved any more")
    await asyncio.to_thread(desktop.open_file, path)
    return {"ok": True, "path": str(path)}


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
        "audio_language": s.audio_language,
        "default_kind": store.get_setting("default_kind") or "video",
        "default_video": store.get_setting("default_video") or "best",
        "default_audio": store.get_setting("default_audio") or "mp3-320",
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
        ytdlp.options.unreadable_browser = None  # give the new (or fixed) setting a fresh go
    if req.audio_language is not None:
        store.set_setting("audio_language", req.audio_language.lower())
    for key in ("default_kind", "default_video", "default_audio"):
        value = getattr(req, key)
        if value is not None:
            store.set_setting(key, value)
    return _settings_dict(store)


def _reveal_target(store: Store, item_id: str | None, group: str | None = None) -> Path:
    if item_id:
        item = store.get_item(item_id)
        if item and item.file_path and Path(item.file_path).exists():
            return Path(item.file_path)
    folder = current_settings(store).output_dir
    if group and group.strip():
        playlist = folder / safe_name(group)
        if playlist.is_dir():
            return playlist
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@app.post("/api/reveal")
async def reveal(req: RevealRequest, request: Request) -> dict:
    """Open the output folder, a playlist's folder, or one item's folder with the file selected."""
    target = await asyncio.to_thread(_reveal_target, _store(request), req.item_id, req.group)
    await asyncio.to_thread(desktop.reveal, target)
    return {"ok": True, "path": str(target)}


# The desktop app serves the built UI from here (PLAN.md Phase 4).
# In dev the directory is absent and Vite serves the UI instead.
_static = Path(__file__).parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="ui")
