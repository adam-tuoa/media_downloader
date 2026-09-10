import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def bbb_info() -> dict:
    """Real yt-dlp -J output for 'Big Buck Bunny 60fps 4K' with URLs/fragments stripped."""
    return json.loads((FIXTURES / "probe_bigbuckbunny.json").read_text(encoding="utf-8"))


@pytest.fixture
def multilang_info() -> dict:
    """Trimmed yt-dlp -J output for a video with dubbed tracks (en-US original, es, fr, id)."""
    return json.loads((FIXTURES / "probe_multilang.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _own_downloads_folder(monkeypatch, tmp_path):
    """Keep every test away from the real Downloads folder: the default download folder, and the
    pre-rename one the app adopts when it exists, are both looked up there."""
    from app import paths

    monkeypatch.setattr(paths, "user_downloads_dir", lambda: str(tmp_path / "Downloads"))
