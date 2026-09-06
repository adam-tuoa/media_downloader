#!/usr/bin/env python3
"""Download yt-dlp, ffmpeg/ffprobe and deno for this platform into backend/bin/.

Run once for local development; CI runs it on each build target before packaging.
Idempotent: existing files are kept unless --force is given.

yt-dlp is fetched as the *onedir* build (a directory, backend/bin/yt-dlp/), not the single-file
executable: the single-file build unpacks itself on every launch and macOS then security-scans
every unpacked library, which measured at ~23 s per invocation. The onedir build pays that once.
"""

from __future__ import annotations

import argparse
import io
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "backend" / "bin"

YTDLP = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/{asset}"
DENO = "https://github.com/denoland/deno/releases/latest/download/{asset}"
FFMPEG_BUILDS = "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/{asset}"
EVERMEET = "https://evermeet.cx/ffmpeg/getrelease/{tool}/zip"  # macOS x86_64 static builds


def detect() -> tuple[str, str]:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    return platform.system(), arch


def fetch(url: str) -> bytes:
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "media-downloader-fetch"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


def save(name: str, data: bytes) -> None:
    path = BIN_DIR / name
    path.write_bytes(data)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  saved {path.relative_to(ROOT)} ({len(data) / 1e6:.1f} MB)")


def member_from_zip(data: bytes, basename: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if Path(info.filename).name == basename and not info.is_dir():
                return zf.read(info)
    raise FileNotFoundError(f"{basename} not found in zip")


def member_from_tar(data: bytes, basename: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
        for info in tf.getmembers():
            if Path(info.name).name == basename and info.isfile():
                return tf.extractfile(info).read()  # type: ignore[union-attr]
    raise FileNotFoundError(f"{basename} not found in tar")


def extract_zip(data: bytes, dest: Path) -> None:
    """Extract, restoring the unix mode bits zipfile would otherwise drop."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            target = dest / info.filename
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
            mode = (info.external_attr >> 16) & 0o777
            if mode:
                target.chmod(mode)


def fetch_ytdlp(system: str, arch: str) -> None:
    asset = {
        ("Darwin", "x86_64"): "yt-dlp_macos.zip",
        ("Darwin", "arm64"): "yt-dlp_macos.zip",
        ("Linux", "x86_64"): "yt-dlp_linux.zip",
        ("Linux", "arm64"): "yt-dlp_linux_aarch64.zip",
        ("Windows", "x86_64"): "yt-dlp_win.zip",
        ("Windows", "arm64"): "yt-dlp_win_arm64.zip",
    }[(system, arch)]
    dest = BIN_DIR / "yt-dlp"
    if dest.is_file():  # an older single-file build
        dest.unlink()
    shutil.rmtree(dest, ignore_errors=True)
    extract_zip(fetch(YTDLP.format(asset=asset)), dest)
    exe = ytdlp_executable(dest)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"  extracted {dest.relative_to(ROOT)}/ ({size / 1e6:.0f} MB), executable {exe.name}")
    # First launch of freshly written binaries is slow on macOS (security scan); do it here, once.
    print("  warming up (first launch)...", end="", flush=True)
    started = time.time()
    version = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=300)
    print(f" yt-dlp {version.stdout.strip()} ({time.time() - started:.0f}s)")


def ytdlp_executable(directory: Path) -> Path:
    """The top-level executable of an onedir build: yt-dlp_macos, yt-dlp_linux or yt-dlp.exe."""
    for candidate in sorted(directory.iterdir()):
        if candidate.is_file() and candidate.name.startswith("yt-dlp"):
            return candidate
    raise FileNotFoundError(f"no yt-dlp executable in {directory}")


def fetch_deno(system: str, arch: str) -> None:
    triple = {
        ("Darwin", "x86_64"): "x86_64-apple-darwin",
        ("Darwin", "arm64"): "aarch64-apple-darwin",
        ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
        ("Linux", "arm64"): "aarch64-unknown-linux-gnu",
        ("Windows", "x86_64"): "x86_64-pc-windows-msvc",
        ("Windows", "arm64"): "aarch64-pc-windows-msvc",
    }[(system, arch)]
    exe = "deno.exe" if system == "Windows" else "deno"
    save(exe, member_from_zip(fetch(DENO.format(asset=f"deno-{triple}.zip")), exe))


def fetch_ffmpeg(system: str, arch: str) -> None:
    if system == "Windows":
        asset = (
            "ffmpeg-master-latest-winarm64-gpl.zip"
            if arch == "arm64"
            else "ffmpeg-master-latest-win64-gpl.zip"
        )
        data = fetch(FFMPEG_BUILDS.format(asset=asset))
        for tool in ("ffmpeg.exe", "ffprobe.exe"):
            save(tool, member_from_zip(data, tool))
    elif system == "Linux":
        asset = (
            "ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
            if arch == "arm64"
            else "ffmpeg-master-latest-linux64-gpl.tar.xz"
        )
        data = fetch(FFMPEG_BUILDS.format(asset=asset))
        for tool in ("ffmpeg", "ffprobe"):
            save(tool, member_from_tar(data, tool))
    else:  # macOS: evermeet ships x86_64 builds (run under Rosetta on Apple Silicon)
        try:
            for tool in ("ffmpeg", "ffprobe"):
                save(tool, member_from_zip(fetch(EVERMEET.format(tool=tool)), tool))
        except Exception as exc:  # noqa: BLE001 - any download failure falls back to the system copy
            system_ffmpeg = shutil.which("ffmpeg")
            if not system_ffmpeg:
                raise
            print(f"  ! could not download ffmpeg ({exc}); using system copy at {system_ffmpeg}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument(
        "--only", nargs="*", choices=["yt-dlp", "deno", "ffmpeg"], help="subset to fetch"
    )
    args = parser.parse_args()

    system, arch = detect()
    print(f"platform: {system} {arch} -> {BIN_DIR.relative_to(ROOT)}/")
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".exe" if system == "Windows" else ""

    steps = {
        "yt-dlp": ("yt-dlp", fetch_ytdlp),  # a directory (onedir build)
        "deno": (f"deno{ext}", fetch_deno),
        "ffmpeg": (f"ffmpeg{ext}", fetch_ffmpeg),
    }
    for name, (marker, fn) in steps.items():
        if args.only and name not in args.only:
            continue
        present = BIN_DIR / marker
        if (present.is_dir() if name == "yt-dlp" else present.is_file()) and not args.force:
            print(f"{name}: already present, skipping (use --force to refresh)")
            continue
        print(f"{name}:")
        fn(system, arch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
