"""Small OS integrations: open a folder, or reveal a file, in the user's file manager."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def reveal(path: Path) -> None:
    """Open a directory; for a file, open its folder with the file selected."""
    path = Path(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if path.is_file() else ["open", str(path)])
    elif os.name == "nt":
        if path.is_file():
            subprocess.Popen(["explorer", f"/select,{path}"])
        else:
            os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])
