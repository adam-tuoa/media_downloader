"""Thin async wrapper around the yt-dlp executable.

We drive the official binary rather than importing ``yt_dlp``: the binary self-updates
(``yt-dlp -U``) independently of app releases, which matters because YouTube changes constantly.
Helper binaries (ffmpeg, deno) live in ``backend/bin`` and are put on PATH for every call.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


def _default_bin_dir() -> Path:
    # A PyInstaller bundle (Phase 4) unpacks its data under sys._MEIPASS; dev runs use backend/bin.
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "bin"
    return Path(__file__).resolve().parent.parent / "bin"


BIN_DIR = Path(os.environ.get("MD_BIN_DIR") or _default_bin_dir())
_EXE_SUFFIX = ".exe" if os.name == "nt" else ""

PROGRESS_PREFIX = "PROGRESS "
POSTPROCESS_PREFIX = "PP "
FILEPATH_PREFIX = "FILEPATH "

# yt-dlp prints "NA" for missing fields even with the %(...)j (JSON) conversion.
_NA = re.compile(r"(?<=[:,\[])NA(?=[,}\]])")

_PROGRESS_TEMPLATE = (
    "download:"
    + PROGRESS_PREFIX
    + '{"status":%(progress.status)j,"downloaded":%(progress.downloaded_bytes)j,'
    '"total":%(progress.total_bytes)j,"estimate":%(progress.total_bytes_estimate)j,'
    '"speed":%(progress.speed)j,"eta":%(progress.eta)j}'
)
_POSTPROCESS_TEMPLATE = (
    "postprocess:"
    + POSTPROCESS_PREFIX
    + '{"status":%(progress.status)j,"postprocessor":%(progress.postprocessor)j}'
)

PROBE_TIMEOUT = 120  # seconds; metadata extraction should never take this long


class YtdlpError(RuntimeError):
    """yt-dlp failed; ``str(exc)`` is the user-facing message extracted from stderr."""


@dataclass(frozen=True)
class Progress:
    stage: str  # "download" | "postprocess"
    status: (
        str  # download: "downloading" | "finished" | "error"; postprocess: "started" | "finished"
    )
    downloaded: int | None = None
    total: int | None = None
    speed: float | None = None
    eta: int | None = None
    postprocessor: str | None = None

    @property
    def fraction(self) -> float | None:
        if self.downloaded is None or not self.total:
            return None
        return min(self.downloaded / self.total, 1.0)


def executable(name: str) -> str | None:
    """Path to a bundled binary, falling back to whatever is on PATH."""
    bundled = BIN_DIR / f"{name}{_EXE_SUFFIX}"
    if bundled.is_file():
        return str(bundled)
    return shutil.which(name)


def _ytdlp() -> str:
    """The bundled onedir build (backend/bin/yt-dlp/yt-dlp_macos | yt-dlp_linux | yt-dlp.exe)."""
    onedir = BIN_DIR / "yt-dlp"
    if onedir.is_dir():
        for candidate in sorted(onedir.iterdir()):
            if candidate.is_file() and candidate.name.startswith("yt-dlp"):
                return str(candidate)
    # Deliberately no PATH fallback: a stale system yt-dlp would fail in confusing ways.
    raise YtdlpError(
        f"Bundled yt-dlp not found in {onedir} - run `python scripts/fetch_binaries.py` first"
    )


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = str(BIN_DIR) + os.pathsep + env.get("PATH", "")
    # Windows consoles default to a legacy code page; make yt-dlp's output UTF-8 everywhere.
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


_PARTIAL_SUFFIXES = (".part", ".ytdl", ".temp", ".tmp")


def template_root(output_template: str) -> Path:
    """The fixed directory part of an -o template, i.e. everything before the first %(field)s."""
    fixed: list[str] = []
    for part in Path(output_template).parts:
        if "%(" in part:
            break
        fixed.append(part)
    return Path(*fixed) if fixed else Path()


def resolve_output(reported: Path | None, out_dir: Path) -> Path | None:
    """The finished file: the path yt-dlp reported if it exists, else the largest complete file
    under out_dir (covers a console mangling non-ASCII characters in the reported path)."""
    if reported and reported.exists():
        return reported
    if not out_dir.is_dir():
        return None
    candidates = [
        f for f in out_dir.rglob("*") if f.is_file() and not f.name.endswith(_PARTIAL_SUFFIXES)
    ]
    return max(candidates, key=lambda f: f.stat().st_size, default=None)


def base_args() -> list[str]:
    """Flags applied to every invocation: ignore user config, locate bundled ffmpeg/deno."""
    args = ["--ignore-config", "--no-warnings", "--color", "no_color"]
    ffmpeg = executable("ffmpeg")
    if ffmpeg:
        args += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
    deno = executable("deno")
    if deno:
        args += ["--js-runtimes", f"deno:{deno}"]
    return args


def extract_error(stderr: str) -> str:
    """Pick the message worth showing a person out of yt-dlp's stderr."""
    errors = [
        line[len("ERROR:") :].strip() for line in stderr.splitlines() if line.startswith("ERROR:")
    ]
    if errors:
        message = errors[-1]
    else:
        lines = [line for line in stderr.strip().splitlines() if line.strip()]
        message = lines[-1] if lines else "yt-dlp failed"
    # Bug-report boilerplate after ';' is noise to an end user.
    return message.split("; please report", 1)[0].strip()


def _int(value: object) -> int | None:
    return None if value is None else int(value)  # type: ignore[call-overload]


def parse_line(line: str) -> Progress | Path | None:
    """Classify one stdout line from a download run; None for lines we don't care about."""
    if line.startswith(FILEPATH_PREFIX):
        return Path(line[len(FILEPATH_PREFIX) :].strip())
    if line.startswith(PROGRESS_PREFIX):
        data = json.loads(_NA.sub("null", line[len(PROGRESS_PREFIX) :]))
        return Progress(
            stage="download",
            status=data.get("status") or "downloading",
            downloaded=_int(data.get("downloaded")),
            total=_int(data.get("total") or data.get("estimate")),
            speed=data.get("speed"),
            eta=_int(data.get("eta")),
        )
    if line.startswith(POSTPROCESS_PREFIX):
        data = json.loads(_NA.sub("null", line[len(POSTPROCESS_PREFIX) :]))
        return Progress(
            stage="postprocess",
            status=data.get("status") or "started",
            postprocessor=data.get("postprocessor"),
        )
    return None


async def _spawn(args: Sequence[str]) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        _ytdlp(),
        *base_args(),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_env(),
        limit=16 * 1024 * 1024,  # -J output is a single very long line
    )


async def _communicate(args: Sequence[str]) -> tuple[int, str, str]:
    """Run to completion; if the awaiting task is cancelled (asyncio.timeout etc.), kill yt-dlp."""
    proc = await _spawn(args)
    try:
        out, err = await proc.communicate()
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


async def _stream(args: Sequence[str], on_line: Callable[[str], None]) -> tuple[int, str]:
    proc = await _spawn(args)
    assert proc.stdout is not None and proc.stderr is not None

    async def pump() -> None:
        async for raw in proc.stdout:  # type: ignore[union-attr]
            on_line(raw.decode("utf-8", "replace").rstrip("\r\n"))

    _, stderr = await asyncio.gather(pump(), proc.stderr.read())
    rc = await proc.wait()
    return rc, stderr.decode("utf-8", "replace")


async def version() -> str:
    async with asyncio.timeout(30):
        rc, out, err = await _communicate(["--version"])
    if rc != 0:
        raise YtdlpError(extract_error(err))
    return out.strip().splitlines()[-1]


async def update() -> str:
    """Run yt-dlp's self-updater; returns its report text."""
    async with asyncio.timeout(300):
        rc, out, err = await _communicate(["-U"])
    if rc != 0:
        raise YtdlpError(extract_error(err))
    return out.strip()


async def probe(url: str) -> dict:
    """Metadata for a single item (playlists are resolved to the video, if the URL has both)."""
    try:
        async with asyncio.timeout(PROBE_TIMEOUT):
            rc, out, err = await _communicate(["-J", "--no-playlist", url])
    except TimeoutError:
        raise YtdlpError("Timed out while fetching video information") from None
    if rc != 0:
        raise YtdlpError(extract_error(err))
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise YtdlpError("yt-dlp returned unreadable metadata") from exc


async def download(
    url: str,
    format_args: Sequence[str],
    output_template: str,
    on_progress: Callable[[Progress], None] | None = None,
) -> Path:
    """Download one item; returns the final file path reported by yt-dlp after post-processing."""
    args = [
        "--no-playlist",
        "--newline",
        "--progress",
        "--progress-template",
        _PROGRESS_TEMPLATE,
        "--progress-template",
        _POSTPROCESS_TEMPLATE,
        "--print",
        "after_move:" + FILEPATH_PREFIX + "%(filepath)s",
        "-o",
        output_template,
        *format_args,
        url,
    ]
    result: Path | None = None

    def handle(line: str) -> None:
        nonlocal result
        parsed = parse_line(line)
        if isinstance(parsed, Path):
            result = parsed
        elif parsed is not None and on_progress:
            on_progress(parsed)

    rc, stderr = await _stream(args, handle)
    if rc != 0:
        raise YtdlpError(extract_error(stderr))
    path = await asyncio.to_thread(resolve_output, result, template_root(output_template))
    if path is None:
        raise YtdlpError("yt-dlp finished but did not produce an output file")
    return path
