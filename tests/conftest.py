"""Shared fixtures."""

import glob
import os

import pytest

# Where to look for a Chromium when Playwright's own download is absent (CLAUDE.md §14.4:
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
