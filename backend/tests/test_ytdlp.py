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


def test_template_root():
    assert ytdlp.template_root("/tmp/x/%(title)s [%(id)s].%(ext)s") == Path("/tmp/x")
    assert ytdlp.template_root("/tmp/x/%(artist)s/%(title)s.%(ext)s") == Path("/tmp/x")
    assert ytdlp.template_root("%(title)s.%(ext)s") == Path()


def test_resolve_output_prefers_reported_then_largest_complete_file(tmp_path):
    real = tmp_path / "Café [abc].mp4"
    real.write_bytes(b"x" * 100)
    (tmp_path / "Café [abc].mp4.part").write_bytes(b"x" * 1000)
    (tmp_path / "leftover.ytdl").write_bytes(b"x")
    assert ytdlp.resolve_output(real, tmp_path) == real
    assert ytdlp.resolve_output(tmp_path / "Caf? [abc].mp4", tmp_path) == real  # mangled report
    assert ytdlp.resolve_output(None, tmp_path) == real
    assert ytdlp.resolve_output(None, tmp_path / "missing") is None
    assert ytdlp.resolve_output(None, tmp_path / "missing") is None


def test_parse_progress_identifies_stream():
    def line(v: str, a: str) -> str:
        return (
            'PROGRESS {"status":"downloading","downloaded":1,"total":2,"estimate":NA,'
            f'"speed":NA,"eta":NA,"v":{v},"a":{a}}}'
        )

    cases = [
        (line('"av01.0.00M.08"', '"none"'), "video"),
        (line('"none"', '"opus"'), "audio"),
        (line('"avc1"', '"mp4a"'), "both"),
        (line("NA", "NA"), None),
    ]
    assert [ytdlp.parse_line(text).stream for text, _ in cases] == [s for _, s in cases]


def test_base_args_apply_cookies_and_allowlist(monkeypatch):
    monkeypatch.setattr(ytdlp.options, "cookies_browser", None)
    monkeypatch.delenv("MD_ALLOW_ANY_SITE", raising=False)
    args = ytdlp.base_args()
    assert "--use-extractors" in args and "--cookies-from-browser" not in args
    monkeypatch.setattr(ytdlp.options, "cookies_browser", "firefox")
    monkeypatch.setenv("MD_ALLOW_ANY_SITE", "1")
    args = ytdlp.base_args()
    assert args[args.index("--cookies-from-browser") + 1] == "firefox"
    assert "--use-extractors" not in args


def test_js_runtime_prefers_bundled_quickjs_over_deno(monkeypatch, tmp_path):
    monkeypatch.setattr(ytdlp, "BIN_DIR", tmp_path)
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)
    assert ytdlp.js_runtime_args() == []
    deno = tmp_path / f"deno{ytdlp._EXE_SUFFIX}"
    deno.write_bytes(b"")
    assert ytdlp.js_runtime_args() == ["--js-runtimes", f"deno:{deno}"]
    qjs = tmp_path / f"qjs{ytdlp._EXE_SUFFIX}"
    qjs.write_bytes(b"")
    assert ytdlp.js_runtime_args() == ["--no-js-runtimes", "--js-runtimes", f"quickjs:{qjs}"]
    assert "--no-js-runtimes" in ytdlp.base_args()


def test_complete_chapters_closes_the_ffprobe_path():
    chapters = [{"start_time": 0, "end_time": 5, "title": "a"}, {"start_time": 5, "title": "b"}]
    fixed = ytdlp.complete_chapters({"duration": 12, "chapters": chapters})
    assert fixed["chapters"][-1] == {"start_time": 5, "title": "b", "end_time": 12}
    assert chapters[-1] == {"start_time": 5, "title": "b"}  # caller's dict untouched
    assert ytdlp.complete_chapters({"chapters": chapters})["chapters"] is None
    complete = {"duration": 12, "chapters": [{"start_time": 0, "end_time": 12}]}
    assert ytdlp.complete_chapters(complete) is complete
    assert ytdlp.complete_chapters({"duration": 12}) == {"duration": 12}


def test_frozen_parent_environment_is_scrubbed_for_children():
    env = {
        "PATH": "/usr/bin",
        "_PYI_ARCHIVE_FILE": "/app/MediaDownloader",
        "_PYI_APPLICATION_HOME_DIR": "/app/_internal",
        "_MEIPASS2": "/app/_internal",
        "LD_LIBRARY_PATH": "/app/_internal",
        "LD_LIBRARY_PATH_ORIG": "/usr/lib",
    }
    cleaned = ytdlp.clean_frozen_env(env)
    assert not any(k.startswith("_PYI_") or k == "_MEIPASS2" for k in cleaned)
    assert cleaned["LD_LIBRARY_PATH"] == "/usr/lib" and "LD_LIBRARY_PATH_ORIG" not in cleaned
    assert cleaned["PATH"] == "/usr/bin"
    # An empty original means PyInstaller added the variable itself: drop it entirely.
    assert "LD_LIBRARY_PATH" not in ytdlp.clean_frozen_env(
        {"LD_LIBRARY_PATH": "/app/_internal", "LD_LIBRARY_PATH_ORIG": ""}
    )
    assert "_PYI_ARCHIVE_FILE" not in ytdlp._env()


def test_bundle_bin_dir_candidates(tmp_path, monkeypatch):
    frameworks = tmp_path / "Contents" / "Frameworks"
    resources_bin = tmp_path / "Contents" / "Resources" / "bin"
    frameworks.mkdir(parents=True)
    resources_bin.mkdir(parents=True)
    monkeypatch.setattr(ytdlp.sys, "_MEIPASS", str(frameworks), raising=False)
    assert ytdlp._default_bin_dir() == resources_bin  # macOS .app layout
    (frameworks / "bin").mkdir()
    assert ytdlp._default_bin_dir() == frameworks / "bin"  # plain onedir layout wins when present
    monkeypatch.delattr(ytdlp.sys, "_MEIPASS", raising=False)
    assert ytdlp._default_bin_dir().name == "bin"  # dev layout: next to the package
