#!/usr/bin/env python3
"""Copy backend/bin (yt-dlp, ffmpeg, deno) into the PyInstaller output, untouched.

PyInstaller re-signs and rewrites executables it collects as data; yt-dlp's executable (itself a
PyInstaller app) does not survive that. So the bundle is built without bin/, and this script
drops the pristine directory into the place ytdlp.BIN_DIR expects (sys._MEIPASS / "bin").

Run after `pyinstaller packaging/MediaDownloader.spec`:  python scripts/bundle_binaries.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "backend" / "bin"
DIST = ROOT / "dist"


def targets() -> list[Path]:
    """Every _MEIPASS directory PyInstaller produced under dist/."""
    found = []
    if (DIST / "MediaDownloader" / "_internal").is_dir():
        found.append(DIST / "MediaDownloader" / "_internal")
    mac_app = DIST / "Media Downloader.app" / "Contents" / "Frameworks"
    if mac_app.is_dir():
        found.append(mac_app)
    return found


def main() -> int:
    if not SOURCE.is_dir():
        print(f"{SOURCE} missing - run scripts/fetch_binaries.py first", file=sys.stderr)
        return 1
    places = targets()
    if not places:
        print(f"nothing built under {DIST} - run PyInstaller first", file=sys.stderr)
        return 1
    for place in places:
        dest = place / "bin"
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(SOURCE, dest, symlinks=True)  # copy2 keeps the executable bits
        size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / 1e6
        print(f"copied bin/ -> {dest.relative_to(ROOT)} ({size:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
