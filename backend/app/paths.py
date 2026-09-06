"""Where the app keeps its data and where downloads go by default."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir, user_downloads_dir

APP_NAME = "MediaDownloader"


def data_dir() -> Path:
    """Per-user app data (the jobs database). Override with MD_DATA_DIR (tests, portable use)."""
    path = Path(os.environ.get("MD_DATA_DIR") or user_data_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_output_dir() -> Path:
    return Path(user_downloads_dir()) / "Media Downloader"
