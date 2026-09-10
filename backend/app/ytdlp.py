"""Thin wrapper around the yt-dlp executable.

We drive the official binary rather than importing ``yt_dlp``: the binary self-updates
(``yt-dlp -U``) independently of app releases, which matters because YouTube changes constantly.
Helper binaries (ffmpeg, qjs) live in ``backend/bin`` and are put on PATH for every call.

Processes run through plain ``subprocess`` in worker threads, not asyncio's subprocess support:
on Windows, uvicorn's ``--reload`` mode uses a SelectorEventLoop, which cannot spawn processes
at all. Threads behave the same on every event loop and platform.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app import links

log = logging.getLogger(__name__)


def _default_bin_dir() -> Path:
    """Where the helper binaries live: next to the package in dev/Windows layouts, or inside a
    PyInstaller bundle - ``_MEIPASS/bin``, except in a macOS .app where bundle_binaries.py puts
    them in ``Contents/Resources/bin`` (codesign rejects dotted directory names in Frameworks)."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        root = Path(bundle_root)
        for candidate in (root / "bin", root.parent / "Resources" / "bin"):
            if candidate.is_dir():
                return candidate
        return root / "bin"
    return Path(__file__).resolve().parent.parent / "bin"


BIN_DIR = Path(os.environ.get("USEFULMEDIA_BIN_DIR") or _default_bin_dir())
_EXE_SUFFIX = ".exe" if os.name == "nt" else ""
# Stops console windows flashing up when the packaged (windowed) app spawns tools. Windows only.
_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

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
    '"speed":%(progress.speed)j,"eta":%(progress.eta)j,'
    '"v":%(info.vcodec)j,"a":%(info.acodec)j}'
)
_POSTPROCESS_TEMPLATE = (
    "postprocess:"
    + POSTPROCESS_PREFIX
    + '{"status":%(progress.status)j,"postprocessor":%(progress.postprocessor)j}'
)

PROBE_TIMEOUT = 120  # seconds; metadata extraction should never take this long
PLAYLIST_LIMIT = 200  # entries listed per playlist; beyond this we report "truncated"


@dataclass
class Options:
    """Runtime options applied to every yt-dlp call; set from Settings at startup and on change."""

    cookies_browser: str | None = None  # chrome | firefox | edge | safari | brave | ...
    # The browser whose cookies could not be read this session (permissions, missing profile).
    # Calls skip cookies while it matches cookies_browser; Settings resets it when saved.
    unreadable_browser: str | None = None
    unreadable_reason: str = ""


options = Options()
_COOKIE_FAILURE = re.compile(
    r"binarycookies|cookies? database|could not (?:find|copy|read|decrypt) [^\n]*cookie", re.I
)


def cookie_failure(stderr: str) -> bool:
    """yt-dlp died reading the browser's cookies - nothing to do with the site."""
    return bool(_COOKIE_FAILURE.search(stderr))


def cookie_warning() -> str | None:
    """What to tell the user when their cookie setting is being skipped."""
    browser = options.cookies_browser
    if not browser or options.unreadable_browser != browser:
        return None
    return (
        f"Couldn't read {browser.capitalize()}'s cookies ({options.unreadable_reason}), so"
        " downloads are running without them. Videos that need a sign-in will fail until"
        " that's fixed - see Settings."
    )


def _cookies_usable() -> bool:
    return bool(options.cookies_browser) and options.unreadable_browser != options.cookies_browser


def _note_cookie_failure(stderr: str) -> None:
    options.unreadable_browser = options.cookies_browser
    options.unreadable_reason = extract_error(stderr)
    log.warning(
        "can't read %s cookies (%s) - continuing without them",
        options.cookies_browser,
        options.unreadable_reason,
    )


_PARTIAL_SUFFIXES = (".part", ".ytdl", ".temp", ".tmp")


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
    stream: str | None = None  # "video" | "audio" | "both" - which stream a download line is for

    @property
    def fraction(self) -> float | None:
        if self.downloaded is None or not self.total:
            return None
        return min(self.downloaded / self.total, 1.0)


# --- locating things ---------------------------------------------------------------------------


def _ensure_executable(path: Path) -> str:
    """PyInstaller data copies can lose the exec bit; put it back (POSIX only)."""
    if os.name != "nt" and not os.access(path, os.X_OK):
        try:
            path.chmod(path.stat().st_mode | 0o755)
        except OSError:
            pass
    return str(path)


def executable(name: str) -> str | None:
    """Path to a bundled helper binary (ffmpeg, qjs), falling back to whatever is on PATH."""
    import shutil

    bundled = BIN_DIR / f"{name}{_EXE_SUFFIX}"
    if bundled.is_file():
        return _ensure_executable(bundled)
    return shutil.which(name)


def _ytdlp() -> str:
    """The bundled onedir build (backend/bin/yt-dlp/yt-dlp_macos | yt-dlp_linux | yt-dlp.exe)."""
    onedir = BIN_DIR / "yt-dlp"
    if onedir.is_dir():
        for candidate in sorted(onedir.iterdir()):
            if candidate.is_file() and candidate.name.startswith("yt-dlp"):
                return _ensure_executable(candidate)
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
    return clean_frozen_env(env)


def clean_frozen_env(env: dict[str, str]) -> dict[str, str]:
    """Undo what a PyInstaller-frozen parent leaks into child processes.

    yt-dlp's executable is itself a PyInstaller app: with our bootloader's ``_PYI_*`` variables
    in its environment it tries to read *our* archive and dies ("Could not load PyInstaller's
    embedded PKG archive"). PyInstaller also points ``LD_LIBRARY_PATH`` at our bundled libraries,
    which qjs/ffmpeg must not load."""
    cleaned = {k: v for k, v in env.items() if not k.startswith("_PYI_") and k != "_MEIPASS2"}
    if "LD_LIBRARY_PATH_ORIG" in cleaned:
        original = cleaned.pop("LD_LIBRARY_PATH_ORIG")
        if original:
            cleaned["LD_LIBRARY_PATH"] = original
        else:
            cleaned.pop("LD_LIBRARY_PATH", None)
    return cleaned


def js_runtime_args() -> list[str]:
    """YouTube's challenges need a JavaScript runtime. We bundle QuickJS-ng (``qjs``, 2 MB) instead
    of yt-dlp's default Deno (93 MB): measured 2026-09-09 on an Intel Mac, a YouTube probe takes
    ~4 s longer, once per link (downloads reuse the probe). A checkout that still has only deno
    keeps working. yt-dlp would rank deno above quickjs, hence ``--no-js-runtimes`` first."""
    qjs = executable("qjs")
    if qjs:
        return ["--no-js-runtimes", "--js-runtimes", f"quickjs:{qjs}"]
    deno = executable("deno")
    if deno:
        return ["--js-runtimes", f"deno:{deno}"]
    return []


def base_args(cookies: bool = True) -> list[str]:
    """Flags applied to every invocation: ignore user config, locate bundled ffmpeg and qjs.
    ``cookies=False`` leaves the browser cookies out (retries after they proved unreadable).

    No ffprobe is bundled (it was a second 77 MB copy of ffmpeg's libraries). yt-dlp falls back to
    ``ffmpeg -i`` for codec checks and only *requires* ffprobe for things this app never does:
    concatenation, HLS fixups, embedding info-json, thumbnails in MKV (we always merge to MP4)
    and, for M4A, only after mutagen - which yt-dlp's build includes - has failed."""
    args = ["--ignore-config", "--no-warnings", "--color", "no_color"]
    ffmpeg = executable("ffmpeg")
    if ffmpeg:
        args += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
    args += js_runtime_args()
    if cookies and _cookies_usable():
        args += ["--cookies-from-browser", options.cookies_browser or ""]
    if not links.allow_any_site():
        args += ["--use-extractors", links.EXTRACTOR_ALLOWLIST]
    return args


# --- parsing -------------------------------------------------------------------------------------


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


def _stream(vcodec: object, acodec: object) -> str | None:
    has_video = vcodec not in (None, "none")
    has_audio = acodec not in (None, "none")
    if has_video and has_audio:
        return "both"
    if has_video:
        return "video"
    if has_audio:
        return "audio"
    return None


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
            stream=_stream(data.get("v"), data.get("a")),
        )
    if line.startswith(POSTPROCESS_PREFIX):
        data = json.loads(_NA.sub("null", line[len(POSTPROCESS_PREFIX) :]))
        return Progress(
            stage="postprocess",
            status=data.get("status") or "started",
            postprocessor=data.get("postprocessor"),
        )
    return None


def complete_chapters(info: dict) -> dict:
    """A copy of ``info`` whose last chapter has an end time. Without one, yt-dlp's metadata step
    asks ffprobe for the file's duration - and we ship no ffprobe (see base_args)."""
    chapters = info.get("chapters")
    if not chapters or not isinstance(chapters[-1], dict) or chapters[-1].get("end_time"):
        return info
    if not info.get("duration"):
        return {**info, "chapters": None}
    last = {**chapters[-1], "end_time": info["duration"]}
    return {**info, "chapters": [*chapters[:-1], last]}


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


# --- running (blocking helpers; always called through asyncio.to_thread) -------------------------


def _popen(args: Sequence[str], cookies: bool = True) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [_ytdlp(), *base_args(cookies), *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(),
        creationflags=_CREATION_FLAGS,
        start_new_session=os.name != "nt",  # own process group, so we can kill ffmpeg too
    )


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    """Kill yt-dlp and anything it spawned (ffmpeg during a merge or conversion)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            creationflags=_CREATION_FLAGS,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass


def _run_sync(args: Sequence[str], timeout: float, cookies: bool = True) -> tuple[int, str, str]:
    """Run to completion; kills yt-dlp and raises TimeoutError if it takes too long."""
    proc = _popen(args, cookies)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        proc.communicate()
        raise TimeoutError(f"yt-dlp did not finish within {timeout:.0f}s") from None
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _run_tolerating_cookies(args: Sequence[str], timeout: float) -> tuple[int, str, str]:
    """Run; if the browser's cookies can't be read, run again without them. A broken cookie
    setting must not sink downloads from sites that never needed a login."""
    rc, out, err = _run_sync(args, timeout)
    if rc != 0 and _cookies_usable() and cookie_failure(err):
        _note_cookie_failure(err)
        rc, out, err = _run_sync(args, timeout, cookies=False)
        if rc != 0:
            err += f"\nERROR: {extract_error(err)}; also {options.unreadable_reason}"
    return rc, out, err


def _stream_sync(
    args: Sequence[str],
    on_line: Callable[[str], None],
    cancel: threading.Event | None = None,
    cookies: bool = True,
) -> tuple[int, str]:
    """Run, handing each stdout line to ``on_line`` as it arrives; ``cancel`` kills the process."""
    proc = _popen(args, cookies)
    assert proc.stdout is not None and proc.stderr is not None
    stderr_chunks: list[bytes] = []

    def drain_stderr() -> None:
        # yt-dlp prints the *postprocess* progress template to stderr (the download one goes to
        # stdout); pass those lines on so "Converting audio" etc. show, keep the rest for errors.
        for raw in proc.stderr:  # type: ignore[union-attr]
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith(POSTPROCESS_PREFIX):
                on_line(line)
            else:
                stderr_chunks.append(raw)

    def watch_cancel() -> None:
        while proc.poll() is None:
            if cancel is not None and cancel.wait(0.25):
                _kill_tree(proc)
                return

    threads = [threading.Thread(target=drain_stderr, daemon=True)]
    if cancel is not None:
        threads.append(threading.Thread(target=watch_cancel, daemon=True))
    for thread in threads:
        thread.start()
    try:
        for raw in proc.stdout:
            on_line(raw.decode("utf-8", "replace").rstrip("\r\n"))
    finally:
        rc = proc.wait()
        for thread in threads:
            thread.join()
    return rc, b"".join(stderr_chunks).decode("utf-8", "replace")


# --- public API ----------------------------------------------------------------------------------


async def version() -> str:
    rc, out, err = await asyncio.to_thread(_run_sync, ["--version"], 30, False)
    if rc != 0:
        raise YtdlpError(extract_error(err))
    return out.strip().splitlines()[-1]


async def update() -> str:
    """Run yt-dlp's self-updater; returns its report text."""
    rc, out, err = await asyncio.to_thread(_run_sync, ["-U"], 300, False)
    if rc != 0:
        raise YtdlpError(extract_error(err))
    return out.strip()


async def probe(url: str) -> dict:
    """Metadata for a single item (playlists are resolved to the video, if the URL has both)."""
    try:
        rc, out, err = await asyncio.to_thread(
            _run_tolerating_cookies, ["-J", "--no-playlist", url], PROBE_TIMEOUT
        )
    except TimeoutError:
        raise YtdlpError("Timed out while fetching video information") from None
    if rc != 0:
        raise YtdlpError(extract_error(err))
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise YtdlpError("yt-dlp returned unreadable metadata") from exc


async def inspect(url: str) -> dict:
    """Metadata for a possible playlist; entries are listed (flat, capped), not extracted."""
    try:
        rc, out, err = await asyncio.to_thread(
            _run_tolerating_cookies,
            ["-J", "--flat-playlist", "--playlist-end", str(PLAYLIST_LIMIT), url],
            PROBE_TIMEOUT,
        )
    except TimeoutError:
        raise YtdlpError("Timed out while reading the playlist") from None
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
    cancel: threading.Event | None = None,
    info: dict | None = None,
) -> Path:
    """Download one item; returns the final file path after post-processing.

    ``on_progress`` is always invoked on the event-loop thread, so callers can touch loop-bound
    state (the job table) without locks. Setting ``cancel`` kills yt-dlp promptly. Passing the
    dict from a recent ``probe()`` as ``info`` skips a second metadata extraction.
    """
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
    info_file: Path | None = None
    if info is not None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".info.json", prefix="md-", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(complete_chapters(info), fh)
            info_file = Path(fh.name)
        args += ["--load-info-json", str(info_file)]
    loop = asyncio.get_running_loop()
    reported: Path | None = None

    def handle(line: str) -> None:  # runs on the worker thread
        nonlocal reported
        parsed = parse_line(line)
        if isinstance(parsed, Path):
            reported = parsed
        elif parsed is not None and on_progress is not None:
            loop.call_soon_threadsafe(on_progress, parsed)

    try:
        rc, stderr = await asyncio.to_thread(_stream_sync, args, handle, cancel)
        if rc != 0 and not (cancel and cancel.is_set()) and _cookies_usable():
            if cookie_failure(stderr):
                _note_cookie_failure(stderr)
                rc, stderr = await asyncio.to_thread(_stream_sync, args, handle, cancel, False)
                if rc != 0:
                    stderr += f"\nERROR: {extract_error(stderr)}; also {options.unreadable_reason}"
    finally:
        if info_file is not None:
            info_file.unlink(missing_ok=True)
    if cancel is not None and cancel.is_set():
        raise YtdlpError("Cancelled")
    if rc != 0:
        raise YtdlpError(extract_error(stderr))
    path = await asyncio.to_thread(resolve_output, reported, template_root(output_template))
    if path is None:
        raise YtdlpError("yt-dlp finished but did not produce an output file")
    return path
