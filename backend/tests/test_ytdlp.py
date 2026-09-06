from pathlib import Path

from app import ytdlp


def test_parse_progress_line_with_na_values():
    line = (
        'PROGRESS {"status":"downloading","downloaded":3072,"total":223779,'
        '"estimate":NA,"speed":1225382.96,"eta":0}'
    )
    p = ytdlp.parse_line(line)
    assert isinstance(p, ytdlp.Progress)
    assert p.stage == "download" and p.status == "downloading"
    assert p.downloaded == 3072 and p.total == 223779 and p.eta == 0
    assert p.speed == 1225382.96
    assert round(p.fraction, 4) == round(3072 / 223779, 4)


def test_parse_progress_falls_back_to_estimate():
    line = (
        'PROGRESS {"status":"downloading","downloaded":10,"total":NA,'
        '"estimate":100,"speed":NA,"eta":NA}'
    )
    p = ytdlp.parse_line(line)
    assert p.total == 100 and p.speed is None and p.eta is None


def test_parse_postprocess_and_filepath_lines():
    pp = ytdlp.parse_line('PP {"status":"started","postprocessor":"Merger"}')
    assert pp.stage == "postprocess" and pp.postprocessor == "Merger" and pp.fraction is None
    path = ytdlp.parse_line("FILEPATH /tmp/x/Me at the zoo [jNQXAC9IVRw].mp4")
    assert path == Path("/tmp/x/Me at the zoo [jNQXAC9IVRw].mp4")
    assert ytdlp.parse_line("[download] Destination: something") is None


def test_extract_error_strips_boilerplate():
    stderr = (
        "WARNING: something minor\n"
        "ERROR: [youtube] abc: Video unavailable; please report this issue on "
        "https://github.com/yt-dlp/yt-dlp/issues?q= , filling out the appropriate issue template.\n"
    )
    assert ytdlp.extract_error(stderr) == "[youtube] abc: Video unavailable"
    assert ytdlp.extract_error("") == "yt-dlp failed"
    assert ytdlp.extract_error("Traceback...\nValueError: boom\n") == "ValueError: boom"
