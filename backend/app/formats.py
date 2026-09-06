"""Turn yt-dlp's format list into the few choices a non-technical user should see.

YouTube serves HD as separate video and audio streams, so a "quality" is really
(best video stream at that height) + (best compatible audio stream), merged by ffmpeg.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

Info = dict[str, Any]
Format = dict[str, Any]

MAX_H264_HEIGHT = 1080  # above this YouTube only offers VP9/AV1


@dataclass(frozen=True)
class VideoOption:
    height: int
    fps: int | None
    vcodec: str
    ext: str
    format_id: str
    audio_format_id: str | None  # None when the stream already carries audio
    filesize: int | None  # estimated total including audio, when known
    label: str


@dataclass(frozen=True)
class AudioOption:
    format_id: str
    abr: int | None
    acodec: str
    ext: str
    filesize: int | None


def human_size(size: int | None) -> str:
    if not size or size <= 0:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" or value >= 10 else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _size(fmt: Format, duration: float | None = None) -> int | None:
    """Known size, else an estimate from bitrate x duration (HLS streams report no size)."""
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if not size and fmt.get("tbr") and duration:
        size = int(fmt["tbr"] * 1000 / 8 * duration)
    return size or None


def _is_direct(fmt: Format) -> bool:
    """Plain HTTPS streams download faster and more reliably than HLS fragment lists."""
    return str(fmt.get("protocol") or "https").startswith("http")


def _has(fmt: Format, key: str) -> bool:
    return fmt.get(key) not in (None, "none")


def _is_video(fmt: Format) -> bool:
    return (
        _has(fmt, "vcodec")
        and bool(fmt.get("height"))
        and fmt.get("ext") != "mhtml"  # storyboards
        and not fmt.get("has_drm")
        and "premium" not in str(fmt.get("format_note", "")).lower()
    )


def _is_audio_only(fmt: Format) -> bool:
    return (
        not _has(fmt, "vcodec")
        and fmt.get("acodec") != "none"
        and bool(fmt.get("abr") or fmt.get("tbr"))
        and not str(fmt.get("format_id", "")).endswith("-drc")  # dynamic-range-compressed twins
        and not fmt.get("has_drm")
    )


def _video_rank(fmt: Format) -> tuple[bool, float, bool, float]:
    vcodec = str(fmt.get("vcodec") or "").lower()
    compatible = vcodec.startswith("avc1") and fmt.get("ext") == "mp4"  # plays everywhere
    return (compatible, fmt.get("fps") or 0, _is_direct(fmt), fmt.get("tbr") or 0)


def _audio_rank(fmt: Format) -> tuple[float, bool, bool]:
    return (
        fmt.get("abr") or fmt.get("tbr") or 0,
        _is_direct(fmt),
        str(fmt.get("acodec", "")).startswith("opus"),
    )


def best_audio(info: Info, ext: str | None = None) -> AudioOption | None:
    candidates = [f for f in info.get("formats", []) if _is_audio_only(f)]
    if ext:
        candidates = [f for f in candidates if f.get("ext") == ext]
    if not candidates:
        return None
    fmt = max(candidates, key=_audio_rank)
    return AudioOption(
        format_id=str(fmt["format_id"]),
        abr=round(fmt["abr"]) if fmt.get("abr") else None,
        acodec=str(fmt.get("acodec") or "?"),
        ext=str(fmt.get("ext") or "?"),
        filesize=_size(fmt, info.get("duration")),
    )


def video_options(info: Info) -> list[VideoOption]:
    """One option per available height, best first."""
    audio = best_audio(info, ext="m4a") or best_audio(info)  # AAC muxes cleanly into mp4
    by_height: dict[int, list[Format]] = {}
    for fmt in info.get("formats", []):
        if _is_video(fmt):
            by_height.setdefault(int(fmt["height"]), []).append(fmt)

    options: list[VideoOption] = []
    for height in sorted(by_height, reverse=True):
        fmt = max(by_height[height], key=_video_rank)
        partner = None if _has(fmt, "acodec") else audio
        size = _size(fmt, info.get("duration"))
        if size and partner and partner.filesize:
            size += partner.filesize
        fps = round(fmt["fps"]) if fmt.get("fps") else None
        label = f"{height}p{fps if fps and fps > 30 else ''}"
        if size:
            label += f" · {human_size(size)}"
        options.append(
            VideoOption(
                height=height,
                fps=fps,
                vcodec=str(fmt.get("vcodec") or "?"),
                ext=str(fmt.get("ext") or "?"),
                format_id=str(fmt["format_id"]),
                audio_format_id=partner.format_id if partner else None,
                filesize=size,
                label=label,
            )
        )
    return options


def pick_height(options: list[VideoOption], height: int | None) -> VideoOption:
    """Largest option not exceeding ``height`` (or the smallest available); best when None."""
    if not options:
        raise ValueError("no video options")
    if height is None:
        return options[0]
    fitting = [o for o in options if o.height <= height]
    return fitting[0] if fitting else options[-1]


def video_download_args(option: VideoOption) -> list[str]:
    if option.audio_format_id is None:
        spec = f"{option.format_id}/best[height<={option.height}]"
    else:
        spec = (
            f"{option.format_id}+{option.audio_format_id}"
            f"/{option.format_id}+bestaudio/best[height<={option.height}]"
        )
    return ["-f", spec, "--merge-output-format", "mp4"]


AUDIO_FORMATS = ("mp3", "m4a", "best")


def audio_download_args(audio_format: str = "mp3", bitrate: int = 320) -> list[str]:
    """How to get audio out.

    mp3  - transcode (compatibility); can't exceed the source's quality
    m4a  - YouTube's AAC stream copied as-is when available (no re-encode), else transcoded
    best - the site's best stream in its native codec, untouched
           (Opus from YouTube, MP3 from Bandcamp)
    """
    if audio_format == "m4a":
        return [
            "-f",
            "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio/best",
            "-x",
            "--audio-format",
            "m4a",
        ]
    if audio_format == "best":
        return ["-f", "bestaudio/best", "-x", "--audio-format", "best"]
    return [
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        f"{bitrate}K",
    ]


def tag_args(info: Info, kind: str) -> list[str]:
    """Embed title/artist/album/date tags and cover art. For audio from sites that give no artist
    (YouTube outside its music catalogue), split an "Artist - Title" name when there is one."""
    args = ["--embed-metadata", "--embed-thumbnail", "--convert-thumbnails", "jpg"]
    if kind == "audio" and not info.get("artist") and " - " in str(info.get("title") or ""):
        args += ["--parse-metadata", "title:%(artist)s - %(title)s"]
    return args


def subtitle_args(languages: str = "en.*,en") -> list[str]:
    """Embed real (not auto-generated) subtitles when the video has them; silent when it doesn't."""
    return ["--write-subs", "--sub-langs", languages, "--embed-subs"]


def summary(info: Info) -> dict[str, Any]:
    """What the UI needs from a probe."""
    audio = best_audio(info)
    return {
        "id": info.get("id"),
        "title": info.get("title") or "Untitled",
        "uploader": info.get("uploader") or info.get("channel") or info.get("artist"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "video": [asdict(o) for o in video_options(info)],
        "audio": asdict(audio) if audio else None,
    }
