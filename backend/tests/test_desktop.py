from pathlib import Path

from app import desktop


def test_reveal_commands_per_platform():
    folder = Path("/Users/dad/Downloads/UsefulMedia")
    file = folder / "01 - Song.mp3"
    assert desktop.reveal_command(folder, "darwin", False) == ["open", str(folder)]
    assert desktop.reveal_command(file, "darwin", True) == ["open", "-R", str(file)]
    assert desktop.reveal_command(file, "linux", True) == ["xdg-open", str(folder)]
    assert desktop.reveal_command(folder, "linux", False) == ["xdg-open", str(folder)]


def test_open_commands_per_platform():
    file = Path("/Users/dad/Downloads/UsefulMedia/01 - Song.mp3")
    assert desktop.open_command(file, "darwin") == ["open", str(file)]
    assert desktop.open_command(file, "linux") == ["xdg-open", str(file)]


def test_windows_explorer_select_is_one_quoted_argument():
    # Paths with spaces are the case that used to open Documents instead of the file.
    file = Path(r"C:\Users\Dad\Downloads\UsefulMedia\01 - Song.mp3")
    assert desktop.reveal_command(file, "win32", True) == (
        r'explorer /select,"C:\Users\Dad\Downloads\UsefulMedia\01 - Song.mp3"'
    )
    folder = Path(r"C:\Users\Dad\Downloads\UsefulMedia")
    assert desktop.reveal_command(folder, "win32", False) == (
        r'explorer "C:\Users\Dad\Downloads\UsefulMedia"'
    )
