"""Tests for the static website (tools/build_website.py, src/evobots/web.py).

The browser test serves a built site from localhost with every other request blocked; it
needs the pinned Pyodide files in data/cache (downloaded once by the build) and is skipped
without them.
"""

import functools
import http.server
import importlib.util
import threading
import zipfile
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPOSITORY_ROOT / "tools" / "build_website.py"


def load_build_module():
    spec = importlib.util.spec_from_file_location("build_website", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_page_renders_in_website_mode():
    build = load_build_module()
    from evobots.service import Service

    page = build.render_page(Service(is_synthetic=True))
    assert 'src="static/site.js"' in page and "/api/run" not in page
    assert 'id="table-file"' in page and 'href="evobots.zip"' in page
    assert "http://" not in page and "https://" not in page


def test_package_zip_holds_the_python_and_templates(tmp_path):
    build = load_build_module()
    path = tmp_path / "package.zip"
    build.package_zip_bytes(path)
    names = set(zipfile.ZipFile(path).namelist())
    assert {"evobots/web.py", "evobots/service.py", "evobots/app/templates/results.html"} <= names
    assert not any("__pycache__" in name for name in names)


def test_site_runs_in_a_browser_with_the_internet_blocked(tmp_path, chromium_browser):
    build = load_build_module()
    if not all((build.CACHE_DIRECTORY / name).exists() for name in build.SHA256_BY_FILE):
        pytest.skip("Pyodide files not cached; run tools/build_website.py once (needs internet)")
    import subprocess
    import sys

    output = tmp_path / "site"
    subprocess.run([sys.executable, str(BUILD_SCRIPT), "--output", str(output)], check=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(output))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    address = f"http://127.0.0.1:{server.server_address[1]}/"
    blocked, errors = [], []
    context = chromium_browser.new_context()
    context.route(
        "**/*",
        lambda route: (
            route.continue_()
            if route.request.url.startswith(address)
            else (blocked.append(route.request.url), route.abort())
        ),
    )
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(address)
    page.wait_for_function(
        "document.querySelector('#status').textContent.startsWith('Ready')", timeout=120000
    )
    page.fill("#evaluations", "100")
    page.fill("#training_years", "2")
    page.click("#run")
    page.wait_for_function("!document.querySelector('#run').disabled", timeout=300000)
    assert "Scored 100 traders" in page.inner_text("#status")
    assert page.inner_text("#results h2").startswith(("Best bot", "Do nothing"))
    assert blocked == [] and errors == []
    context.close()
    server.shutdown()
