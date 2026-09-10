"""Understand the links people paste: normalise them, classify video vs playlist, enforce the
site allowlist. Pure functions - no network. yt-dlp is consulted only for shapes we can't tell
apart by looking (see ``main.inspect_links``)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit

SITE_NAMES = {"youtube": "YouTube", "vimeo": "Vimeo", "bandcamp": "Bandcamp"}

# yt-dlp extractor names we permit (case-insensitive regexes), passed as --use-extractors so the
# generic extractor can never be used to fetch arbitrary pages even if a URL slips past parse().
EXTRACTOR_ALLOWLIST = (
    "youtube,youtube:tab,youtube:playlist,youtube:clip,youtubeytbe,"
    "vimeo,vimeo:.*,bandcamp,bandcamp:.*"
)

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_PATH_ID = re.compile(r"^/(?:shorts|live|embed|v|e)/([A-Za-z0-9_-]{11})")
_YT_CHANNEL = re.compile(r"^/(?:@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)")
_TRACKING = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "si",
    "feature",
    "share",
    "ref",
}


class LinkError(ValueError):
    """The text isn't a link we can do anything with; ``str(exc)`` is fit to show a person."""


@dataclass(frozen=True)
class Link:
    url: str  # normalised, de-duplication key
    site: str  # youtube | vimeo | bandcamp | other
    kind: str  # video | playlist | unknown (ask yt-dlp)


def allow_any_site() -> bool:
    """Escape hatch for Adam's own use: USEFULMEDIA_ALLOW_ANY_SITE=1 lets yt-dlp try any site."""
    return os.environ.get("USEFULMEDIA_ALLOW_ANY_SITE") == "1"


def supported_sites() -> str:
    return ", ".join(SITE_NAMES.values())


def parse(raw: str) -> Link:
    text = raw.strip()
    if not text:
        raise LinkError("Empty line")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host or "." not in host:
        raise LinkError(f"Not a link: {raw.strip()[:60]}")
    host = host.removeprefix("www.").removeprefix("m.")

    if host in ("youtube.com", "youtu.be", "music.youtube.com", "youtube-nocookie.com"):
        return _youtube(host, parts.path, parse_qs(parts.query))
    if host == "vimeo.com" or host.endswith(".vimeo.com"):
        return _vimeo(parts.path, parse_qs(parts.query))
    if host.endswith(".bandcamp.com"):
        return _bandcamp(host, parts.path)
    if allow_any_site():
        query = {k: v for k, v in parse_qs(parts.query).items() if k not in _TRACKING}
        url = f"https://{host}{parts.path}" + (f"?{urlencode(query, doseq=True)}" if query else "")
        return Link(url=url, site="other", kind="unknown")
    raise LinkError(f"{host} isn't supported - only {supported_sites()} links work here")


def _youtube(host: str, path: str, query: dict[str, list[str]]) -> Link:
    video_id: str | None = None
    if host == "youtu.be":
        video_id = path.strip("/").split("/")[0] or None
    elif path == "/watch":
        video_id = (query.get("v") or [None])[0]
    else:
        match = _YT_PATH_ID.match(path)
        if match:
            video_id = match.group(1)

    if video_id is not None:
        if not _YT_ID.match(video_id):
            raise LinkError("That YouTube link looks incomplete - check it and try again")
        # A video inside a playlist (&list=...) means that video; the playlist link gives the list.
        return Link(url=f"https://www.youtube.com/watch?v={video_id}", site="youtube", kind="video")

    playlist_id = (query.get("list") or [None])[0]
    if path == "/playlist" and playlist_id:
        return Link(
            url=f"https://www.youtube.com/playlist?list={playlist_id}",
            site="youtube",
            kind="playlist",
        )
    if _YT_CHANNEL.match(path):
        raise LinkError("Channel links aren't supported yet - paste a video or playlist link")
    raise LinkError("That YouTube link isn't a video or a playlist")


def _vimeo(path: str, query: dict[str, list[str]]) -> Link:
    segments = [s for s in path.split("/") if s]
    if not segments:
        raise LinkError("That Vimeo link isn't a video or a showcase")
    if segments[0] == "video" and len(segments) == 2 and segments[1].isdigit():  # player.vimeo.com
        segments = [segments[1]]
    url = "https://vimeo.com/" + "/".join(segments)
    unlisted_hash = (query.get("h") or [None])[0]
    if unlisted_hash:
        url += f"?h={unlisted_hash}"

    first = segments[0]
    if first in ("showcase", "album", "groups", "channels") or re.fullmatch(r"user\d+", first):
        # /channels/staffpicks/123 is a video inside a channel; /channels/staffpicks is the channel
        kind = "video" if len(segments) >= 3 and segments[-1].isdigit() else "playlist"
    elif segments[-1].isdigit() or (
        len(segments) == 2 and segments[0].isdigit() and re.fullmatch(r"[0-9a-f]{6,}", segments[1])
    ):
        kind = "video"
    else:
        kind = "unknown"
    return Link(url=url, site="vimeo", kind=kind)


def _bandcamp(host: str, path: str) -> Link:
    path = path.rstrip("/")
    url = f"https://{host}{path}"
    if path.startswith("/track/"):
        return Link(url=url, site="bandcamp", kind="video")
    if path.startswith("/album/"):
        return Link(url=url, site="bandcamp", kind="playlist")
    if path in ("", "/music"):
        return Link(url=f"https://{host}/music", site="bandcamp", kind="playlist")  # discography
    raise LinkError("That Bandcamp link isn't a track or an album")


def dedupe(links: list[Link]) -> list[Link]:
    seen: set[str] = set()
    unique = []
    for link in links:
        if link.url not in seen:
            seen.add(link.url)
            unique.append(link)
    return unique


# Hints for yt-dlp messages that a person can act on. The original message is kept after the hint.
_HINTS = (
    (
        "cookies.binarycookies",  # macOS privacy (TCC) blocking Safari's cookie file
        "macOS is blocking Safari's cookies. In System Settings → Privacy & Security → Full Disk"
        " Access, switch on UsefulMedia (or Terminal, when running from source), then try"
        " again. Firefox and Chrome don't need this.",
    ),
    # Specific messages first: several of them also mention "cookies".
    (
        "sign in to confirm",
        "The site wants a sign-in check - set “Use cookies from” in Settings, or try later.",
    ),
    (
        "private video",
        "This video is private - you'd need to be signed in to an account that can see it.",
    ),
    ("members-only", "This is for channel members only - set “Use cookies from” in Settings."),
    ("cookies", "Needs a signed-in browser - set “Use cookies from” in Settings."),
    ("video unavailable", "This video isn't available any more."),
)


def friendly_error(message: str) -> str:
    lowered = message.lower()
    for needle, hint in _HINTS:
        if needle in lowered:
            return f"{hint} ({message})"
    return message
