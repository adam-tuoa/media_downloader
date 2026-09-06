"""Is there a newer release of the app on GitHub? (Best effort; never raises.)"""

from __future__ import annotations

import json
import logging
import re
import ssl
import urllib.request

import certifi

log = logging.getLogger(__name__)

RELEASES_REPO = "adam-tuoa/youtube_downloader_app"
LATEST_URL = f"https://api.github.com/repos/{RELEASES_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{RELEASES_REPO}/releases/latest"


def version_tuple(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", text.lstrip("vV").split("-")[0])
    return tuple(int(n) for n in numbers) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return version_tuple(latest) > version_tuple(current)


def check_latest(current: str, timeout: float = 5.0) -> dict | None:
    """{"latest": "0.5.0", "url": ...} when a newer release exists, else None."""
    try:
        request = urllib.request.Request(
            LATEST_URL, headers={"User-Agent": f"media-downloader/{current}"}
        )
        # Frozen builds have no system CA bundle on the Python side; certifi ships one.
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            data = json.load(response)
    except Exception as exc:  # noqa: BLE001 - offline, rate limited, no releases yet: all fine
        log.info("update check skipped: %s", exc)
        return None
    latest = str(data.get("tag_name") or "").lstrip("vV")
    if latest and is_newer(latest, current):
        return {"latest": latest, "url": data.get("html_url") or RELEASES_PAGE}
    return None
