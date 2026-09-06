import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def bbb_info() -> dict:
    """Real yt-dlp -J output for 'Big Buck Bunny 60fps 4K' with URLs/fragments stripped."""
    return json.loads((FIXTURES / "probe_bigbuckbunny.json").read_text())
