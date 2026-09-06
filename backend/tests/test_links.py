import pytest

from app import links

YT = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw&list=PLx&index=3&t=5s&si=abc",
        "https://youtu.be/jNQXAC9IVRw?t=10",
        "https://youtu.be/jNQXAC9IVRw?list=PLbpi6ZahtOH6Blw3RGYpWkSByi_T7Rygb",
        "https://youtube.com/shorts/jNQXAC9IVRw",
        "https://www.youtube.com/live/jNQXAC9IVRw?feature=share",
        "https://www.youtube.com/embed/jNQXAC9IVRw",
        "https://music.youtube.com/watch?v=jNQXAC9IVRw&list=RDAMVMabc",
        "https://m.youtube.com/watch?v=jNQXAC9IVRw",
        "youtube.com/watch?v=jNQXAC9IVRw",
        "  https://www.youtube.com/watch?v=jNQXAC9IVRw  ",
    ],
)
def test_youtube_video_shapes_normalise_to_one_url(raw):
    link = links.parse(raw)
    assert link == links.Link(url=YT, site="youtube", kind="video")


def test_youtube_playlist_and_rejections():
    pl = links.parse(
        "https://www.youtube.com/playlist?list=PLbpi6ZahtOH6Blw3RGYpWkSByi_T7Rygb&si=x"
    )
    assert pl.kind == "playlist"
    assert pl.url == "https://www.youtube.com/playlist?list=PLbpi6ZahtOH6Blw3RGYpWkSByi_T7Rygb"
    with pytest.raises(links.LinkError, match="Channel links"):
        links.parse("https://www.youtube.com/@veritasium")
    with pytest.raises(links.LinkError, match="incomplete"):
        links.parse("https://www.youtube.com/watch?v=short")
    with pytest.raises(links.LinkError, match="isn't a video"):
        links.parse("https://www.youtube.com/feed/trending")


def test_vimeo_shapes():
    assert links.parse("https://vimeo.com/76979871") == links.Link(
        "https://vimeo.com/76979871", "vimeo", "video"
    )
    assert links.parse("https://player.vimeo.com/video/76979871?h=abc123&badge=0").url == (
        "https://vimeo.com/76979871?h=abc123"
    )
    unlisted = links.parse("https://vimeo.com/76979871/9f8e7d6c5b")
    assert unlisted.kind == "video" and unlisted.url == "https://vimeo.com/76979871/9f8e7d6c5b"
    assert links.parse("https://vimeo.com/channels/staffpicks/1221558167").kind == "video"
    assert links.parse("https://vimeo.com/channels/staffpicks").kind == "playlist"
    assert links.parse("https://vimeo.com/showcase/12345").kind == "playlist"
    assert links.parse("https://vimeo.com/ondemand/somefilm").kind == "unknown"


def test_bandcamp_shapes():
    track = links.parse("https://youtube-dl.bandcamp.com/track/youtube-dl-test-song?from=embed")
    assert track == links.Link(
        "https://youtube-dl.bandcamp.com/track/youtube-dl-test-song", "bandcamp", "video"
    )
    album = links.parse("https://nightbringer.bandcamp.com/album/hierophany-of-the-open-grave/")
    assert album.kind == "playlist"
    assert (
        links.parse("https://nightbringer.bandcamp.com").url
        == "https://nightbringer.bandcamp.com/music"
    )
    with pytest.raises(links.LinkError, match="track or an album"):
        links.parse("https://nightbringer.bandcamp.com/merch")


def test_unsupported_and_garbage(monkeypatch):
    with pytest.raises(links.LinkError, match="soundcloud.com isn't supported"):
        links.parse("https://soundcloud.com/forss/flickermood")
    with pytest.raises(links.LinkError, match="Not a link"):
        links.parse("hello world")
    with pytest.raises(links.LinkError, match="Empty"):
        links.parse("   ")
    monkeypatch.setenv("MD_ALLOW_ANY_SITE", "1")
    other = links.parse("https://soundcloud.com/forss/flickermood?utm_source=x&si=1")
    assert other == links.Link("https://soundcloud.com/forss/flickermood", "other", "unknown")


def test_dedupe_keeps_first():
    a = links.parse("https://youtu.be/jNQXAC9IVRw")
    b = links.parse("https://www.youtube.com/watch?v=jNQXAC9IVRw&t=1")
    c = links.parse("https://vimeo.com/1")
    assert links.dedupe([a, b, c, a]) == [a, c]


def test_friendly_error_hints():
    msg = (
        "[vimeo] 1: The web client only works when logged-in. Use --cookies, --cookies-from-browser"
    )
    out = links.friendly_error(msg)
    assert out.startswith("Needs a signed-in browser") and msg in out
    assert links.friendly_error("[youtube] x: Video unavailable").startswith(
        "This video isn't available"
    )
    assert links.friendly_error("something else") == "something else"
