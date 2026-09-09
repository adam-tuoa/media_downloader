#!/usr/bin/env python3
"""Assemble the Windows app folder WITHOUT PyInstaller (whose exes Windows Defender quarantines).

Layout produced under build/windows/:
    python/                 python.org "embeddable" runtime (pythonw.exe is signed by the PSF)
    Lib/site-packages/      our `app` package (incl. the built UI) and its dependencies
    Lib/site-packages/bin/  yt-dlp, ffmpeg, qjs (verbatim; the app finds them next to the package)
    MediaDownloader.cmd     fallback launcher; the installer's shortcut runs pythonw.exe directly

Must run on Windows with the same Python minor version we ship (wheels are platform-specific).
packaging/windows.iss then wraps the folder into an Inno Setup installer.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "windows"
EMBED_URL = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"


def main() -> int:
    if sys.platform != "win32":
        print("this script assembles a Windows layout; run it on Windows", file=sys.stderr)
        return 1
    version = "{}.{}.{}".format(*sys.version_info[:3])
    tag = f"python{sys.version_info.major}{sys.version_info.minor}"
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)

    print(f"downloading embeddable Python {version}")
    with urllib.request.urlopen(EMBED_URL.format(v=version), timeout=300) as response:
        zipfile.ZipFile(io.BytesIO(response.read())).extractall(OUT / "python")
    # The ._pth file *is* sys.path for the embeddable runtime (relative to python/).
    (OUT / "python" / f"{tag}._pth").write_text(
        f"{tag}.zip\n.\n..\\Lib\\site-packages\n", encoding="utf-8"
    )

    site = OUT / "Lib" / "site-packages"
    print("installing the app and its dependencies")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-compile",
            "--target",
            str(site),
            str(ROOT / "backend"),
        ],
        check=True,
    )
    assert (site / "app" / "static" / "index.html").exists(), "built UI missing - run npm run build"

    print("adding yt-dlp, ffmpeg and qjs")
    # pip --target drops console-script wrappers (uvicorn.exe, media-downloader.exe) into
    # <target>/bin; they can't work in this layout and the real binaries go there instead.
    shutil.rmtree(site / "bin", ignore_errors=True)
    shutil.copytree(ROOT / "backend" / "bin", site / "bin")
    assert (site / "bin" / "yt-dlp" / "yt-dlp.exe").exists(), "run scripts/fetch_binaries.py first"

    (OUT / "MediaDownloader.cmd").write_text(
        '@start "" "%~dp0python\\pythonw.exe" -m app.launcher\r\n', encoding="utf-8"
    )
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"assembled {OUT.relative_to(ROOT)} ({size:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
