"""Shared fixtures."""

import glob
import os
from pathlib import Path

import pytest

# A downloaded copy of the app has no MISO-derived tables (MISO's terms; docs/data_sources.md
# §3), so the tests that reproduce capital_sizing.md from them are skipped there.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MISO_BENCHMARK_PATH = REPOSITORY_ROOT / "docs/data/benchmark_full_size_daily_pnl.csv"
collect_ignore = []
if not MISO_BENCHMARK_PATH.exists():
    collect_ignore = [
        "test_calibration_tables.py",
        "test_sizing.py",
        "test_storms.py",
        "test_capital_explorer_browser.py",
    ]

# Where to look for a Chromium when Playwright's own download is absent (docs/design_spec.md §14.4:
# browser tests run offline). EVOBOTS_CHROMIUM_PATH wins; then the cloud container's
# pre-installed browser; then Playwright's default (after `playwright install chromium`).
CHROMIUM_CANDIDATE_PATTERNS = ("/opt/pw-browsers/chromium-*/chrome-linux*/chrome",)


@pytest.fixture(scope="session")
def chromium_browser():
    """A headless Chromium, or a skip with the reason when none can be started."""
    sync_api = pytest.importorskip("playwright.sync_api")
    executable_paths = [os.environ.get("EVOBOTS_CHROMIUM_PATH")]
    for pattern in CHROMIUM_CANDIDATE_PATTERNS:
        executable_paths += sorted(glob.glob(pattern))
    executable_paths.append(None)
    with sync_api.sync_playwright() as playwright:
        errors = []
        for executable_path in executable_paths:
            if executable_path == "":
                continue
            try:
                browser = playwright.chromium.launch(executable_path=executable_path)
            except Exception as error:  # noqa: BLE001 - try the next candidate
                errors.append(f"{executable_path}: {str(error).splitlines()[0]}")
                continue
            yield browser
            browser.close()
            return
        pytest.skip("no Chromium could be started: " + "; ".join(errors))
