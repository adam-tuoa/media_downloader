"""Media Downloader API.

Phase 0: probe one URL and download one item straight to the browser.
Phase 1 replaces the direct download with a job queue that writes to a folder.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.background import BackgroundTask

from app import formats, ytdlp

app = FastAPI(title="Media Downloader", version="0.1.0")

_origins = os.environ.get("MD_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".opus": "audio/ogg",
    ".ogg": "audio/ogg",
}


class UrlRequest(BaseModel):
    url: str = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def _must_be_a_link(cls, value: str) -> str:
        value = value.strip()
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("Enter a full link starting with http:// or https://")
        return value


class DownloadRequest(UrlRequest):
    kind: Literal["video", "audio"] = "video"
    height: int | None = Field(
        default=None, ge=144, description="video: cap on height; None = best"
    )
    audio_format: Literal["mp3"] = "mp3"
    audio_bitrate: Literal[128, 192, 320] = 320


@app.exception_handler(ytdlp.YtdlpError)
async def _ytdlp_error(_: Request, exc: ytdlp.YtdlpError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


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


@app.post("/api/download")
async def download(req: DownloadRequest) -> FileResponse:
    if req.kind == "video":
        options = formats.video_options(await ytdlp.probe(req.url))
        if not options:
            raise HTTPException(422, "No video streams found for this link - try Audio instead")
        args = formats.video_download_args(formats.pick_height(options, req.height))
    else:
        args = formats.audio_download_args(req.audio_format, req.audio_bitrate)

    tmp = Path(tempfile.mkdtemp(prefix="media-downloader-"))
    try:
        path = await ytdlp.download(req.url, args, str(tmp / "%(title)s [%(id)s].%(ext)s"))
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return FileResponse(
        path,
        filename=path.name,
        media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True),
    )


# The desktop app serves the built UI from here (PLAN.md Phase 4).
# In dev the directory is absent and Vite serves the UI instead.
_static = Path(__file__).parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="ui")
