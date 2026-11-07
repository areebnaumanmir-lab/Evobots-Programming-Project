"""The one-click start scripts: cmd.exe and macOS shells must be able to read them.

A Windows batch file needs CRLF line endings, and a ")" inside an `if ( … )` block (even in an
echo) ends the block early: cmd then stops on a syntax error before `pause`, so the window
flashes and closes. The script therefore uses `goto` labels and no parentheses at all outside
`rem` comments.
"""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_SCRIPT = REPOSITORY_ROOT / "Start evobots (Windows).bat"
MACOS_SCRIPT = REPOSITORY_ROOT / "start_evobots.command"


def test_windows_script_has_crlf_line_endings():
    data = WINDOWS_SCRIPT.read_bytes()
    assert data.count(b"\n") == data.count(b"\r\n") > 0


def test_windows_script_has_no_parentheses_outside_comments():
    for number, line in enumerate(WINDOWS_SCRIPT.read_text().splitlines(), 1):
        if line.strip().lower().startswith("rem "):
            continue
        assert "(" not in line and ")" not in line, (number, line)


def test_windows_script_keeps_the_window_open_and_always_reaches_pause():
    lines = [line.strip() for line in WINDOWS_SCRIPT.read_text().splitlines()]
    assert lines[-1] == "pause" and ":end" in lines
    assert "uv run evobots serve" in lines


def test_macos_script_has_unix_line_endings():
    assert b"\r" not in MACOS_SCRIPT.read_bytes()
