"""Where the app keeps its data and where downloads go by default."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from platformdirs import user_data_dir, user_downloads_dir

log = logging.getLogger(__name__)

APP_NAME = "UsefulMedia"
# Up to v0.6.1 the app was Media Downloader: its app-data folder and default download folder.
LEGACY_APP_NAME = "MediaDownloader"
LEGACY_DOWNLOADS_NAME = "Media Downloader"

adopted_from: Path | None = None  # set when this process moved the old app-data folder across


def data_dir() -> Path:
    """Per-user app data: the jobs database, app.log, instance.json. Override with
    USEFULMEDIA_DATA_DIR (tests, portable use). The first launch after the rename moves the old
    Media Downloader folder across, so settings and the Library carry over."""
    override = os.environ.get("USEFULMEDIA_DATA_DIR")
    path = Path(override or user_data_dir(APP_NAME, appauthor=False))
    if not override:
        adopt_legacy_data(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def adopt_legacy_data(path: Path) -> bool:
    """Rename the old app-data folder to ``path`` - once, and only while ``path`` doesn't exist."""
    global adopted_from
    old = Path(user_data_dir(LEGACY_APP_NAME, appauthor=False))
    if path.exists() or not old.is_dir():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        old.rename(path)
    except OSError as exc:  # e.g. the old app still running on Windows: start fresh instead
        log.warning("could not move %s to %s: %s", old, path, exc)
        return False
    adopted_from = old
    return True


def default_output_dir() -> Path:
    return Path(user_downloads_dir()) / APP_NAME


def legacy_output_dir() -> Path:
    """Where downloads went by default before the rename."""
    return Path(user_downloads_dir()) / LEGACY_DOWNLOADS_NAME
