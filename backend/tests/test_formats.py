import pytest
from app import formats


def test_video_options_one_per_height_best_first(bbb_info):
    options = formats.video_options(bbb_info)
    heights = [o.height for o in options]
    assert heights == sorted(set(heights), reverse=True)
    assert heights[0] == 2160
    assert 1080 in heights and 360 in heights


def test_1080p_prefers_h264_mp4_and_pairs_with_m4a(bbb_info):
    opt = next(o for o in formats.video_options(bbb_info) if o.height == 1080)
    assert opt.vcodec.startswith("avc1")
    assert opt.ext == "mp4"
    assert opt.fps == 60
    assert opt.audio_format_id == "140"  # AAC m4a partner for a clean mp4 mux
    assert opt.filesize and opt.filesize > 0
    assert opt.label.startswith("1080p60 · ")


def test_2160p_exists_even_without_h264(bbb_info):
    opt = formats.video_options(bbb_info)[0]
    assert opt.height == 2160
    assert not opt.vcodec.startswith("avc1")


def test_best_audio_skips_drc_twins(bbb_info):
    audio = formats.best_audio(bbb_info)
    assert audio is not None
    assert not audio.format_id.endswith("-drc")
    assert audio.abr == 129
    assert formats.best_audio(bbb_info, ext="m4a").format_id == "140"


def test_pick_height():
    options = formats.video_options
    info = {
        "formats": [
            {"format_id": str(h), "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4", "height": h}
            for h in (360, 720, 1080)
        ]
    }
    opts = options(info)
    assert formats.pick_height(opts, None).height == 1080
    assert formats.pick_height(opts, 720).height == 720
    assert formats.pick_height(opts, 900).height == 720
    assert formats.pick_height(opts, 200).height == 360  # smallest when nothing fits
    with pytest.raises(ValueError):
        formats.pick_height([], None)


def test_download_args(bbb_info):
    opt = next(o for o in formats.video_options(bbb_info) if o.height == 1080)
    args = formats.video_download_args(opt)
    assert args[:2] == ["-f", f"{opt.format_id}+140/{opt.format_id}+bestaudio/best[height<=1080]"]
    assert "--merge-output-format" in args

    muxed = formats.VideoOption(360, 30, "avc1", "mp4", "18", None, None, "360p")
    assert formats.video_download_args(muxed)[1] == "18/best[height<=360]"

    assert formats.audio_download_args("mp3", 192) == [
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "192K",
    ]


def test_summary_shape(bbb_info):
    s = formats.summary(bbb_info)
    assert s["title"].startswith("Big Buck Bunny")
    assert s["duration"] and s["thumbnail"] and s["webpage_url"]
    assert s["extractor"] == "Youtube"
    assert s["video"][0]["height"] == 2160
    assert s["audio"]["format_id"] in ("251", "140")


@pytest.mark.parametrize(
    ("size", "text"),
    [
        (None, ""),
        (0, ""),
        (999, "999 B"),
        (5 * 1024, "5.0 KB"),
        (250 * 1024**2, "250 MB"),
        (3 * 1024**3, "3.0 GB"),
    ],
)
def test_human_size(size, text):
    assert formats.human_size(size) == text


def test_prefers_direct_https_over_hls_at_same_height(bbb_info):
    opt = next(o for o in formats.video_options(bbb_info) if o.height == 1080)
    assert opt.format_id == "299"  # not the higher-bitrate but sizeless HLS twin, 312


def test_size_estimated_from_bitrate_when_missing():
    info = {
        "duration": 100,
        "formats": [
            {
                "format_id": "v",
                "vcodec": "avc1",
                "acodec": "none",
                "ext": "mp4",
                "height": 720,
                "tbr": 800,
            },
            {
                "format_id": "a",
                "vcodec": "none",
                "acodec": "mp4a",
                "ext": "m4a",
                "abr": 128,
                "tbr": 128,
            },
        ],
    }
    (opt,) = formats.video_options(info)
    assert opt.audio_format_id == "a"
    assert opt.filesize == int(800 * 1000 / 8 * 100) + int(128 * 1000 / 8 * 100)
    assert opt.label == "720p · 11 MB"  # 11,600,000 bytes
