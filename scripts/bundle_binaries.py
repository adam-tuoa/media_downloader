#!/usr/bin/env python3
"""Copy backend/bin (yt-dlp, ffmpeg, qjs) into the PyInstaller output, untouched, then re-seal.

PyInstaller re-signs and rewrites executables it collects as data; yt-dlp's executable (itself a
PyInstaller app) does not survive that. So the bundle is built without bin/, and this script
drops the pristine directory into the place the app looks (see ytdlp._default_bin_dir):

  Linux/Windows onedir:  dist/UsefulMedia/_internal/bin
  macOS .app:            dist/UsefulMedia.app/Contents/Resources/bin

On macOS the copy must go under Resources, not Frameworks: codesign treats dotted directory
names (yt-dlp's *.dist-info) under Frameworks as broken nested bundles. Afterwards the unsigned
tools (ffmpeg, qjs) get an ad-hoc signature and the whole app is re-signed, otherwise a
quarantined download shows Gatekeeper's "damaged and can't be opened" instead of the usual
right-click -> Open path.

Run after `pyinstaller packaging/UsefulMedia.spec`:  python scripts/bundle_binaries.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "backend" / "bin"
DIST = ROOT / "dist"
MACHO_MAGIC = {
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
}


def targets() -> list[tuple[Path, Path | None]]:
    """(destination bin dir, .app bundle or None) for everything PyInstaller produced."""
    found: list[tuple[Path, Path | None]] = []
    if (DIST / "UsefulMedia" / "_internal").is_dir():
        found.append((DIST / "UsefulMedia" / "_internal" / "bin", None))
    app = DIST / "UsefulMedia.app"
    if app.is_dir():
        found.append((app / "Contents" / "Resources" / "bin", app))
    return found


def is_macho(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(4) in MACHO_MAGIC


def is_signed(path: Path) -> bool:
    return subprocess.run(["codesign", "-dv", str(path)], capture_output=True).returncode == 0


def seal_app(app: Path, bin_dir: Path) -> None:
    for file in bin_dir.rglob("*"):
        if file.is_file() and not file.is_symlink() and is_macho(file) and not is_signed(file):
            subprocess.run(["codesign", "--force", "--sign", "-", str(file)], check=True)
            print(f"  ad-hoc signed {file.relative_to(app)}")
    subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    print(f"  re-signed and verified {app.name}")


def main() -> int:
    if not SOURCE.is_dir():
        print(f"{SOURCE} missing - run scripts/fetch_binaries.py first", file=sys.stderr)
        return 1
    places = targets()
    if not places:
        print(f"nothing built under {DIST} - run PyInstaller first", file=sys.stderr)
        return 1
    for dest, app in places:
        if app is not None:  # an older layout put bin/ under Frameworks; never leave both
            shutil.rmtree(app / "Contents" / "Frameworks" / "bin", ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(SOURCE, dest, symlinks=True)  # copy2 keeps the executable bits
        size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / 1e6
        print(f"copied bin/ -> {dest.relative_to(ROOT)} ({size:.0f} MB)")
        if app is not None and sys.platform == "darwin":
            seal_app(app, dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
