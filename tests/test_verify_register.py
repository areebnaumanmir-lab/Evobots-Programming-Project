"""docs/verify_register.md lists the current [verify] markers (rerun the tool if this fails)."""

import importlib.util
import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPOSITORY_ROOT / "tools/list_verify_markers.py"


def test_register_is_current():
    specification = importlib.util.spec_from_file_location("list_verify_markers", TOOL_PATH)
    tool = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(tool)
    previous_directory = os.getcwd()
    os.chdir(REPOSITORY_ROOT)
    try:
        expected = tool.register_markdown(tool.marker_rows())
    finally:
        os.chdir(previous_directory)
    actual = (REPOSITORY_ROOT / "docs/verify_register.md").read_text(encoding="utf-8")
    assert actual == expected, "run: python tools/list_verify_markers.py"
