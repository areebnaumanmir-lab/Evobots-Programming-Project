"""M1.5: the multi-page app (design spec §14.5, §15).

- every page answers, on whatever data and runs this copy has;
- the UI is separated from everything else: evobots.app imports only evobots.service, and no
  core module imports evobots.app (the CLI starts the server);
- nothing loads from the internet; in a real browser no page logs an error or asks for a
  non-local URL, and a screenshot of each page is saved under tests/screenshots/.
"""

import re
import socket
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evobots.app import server

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src" / "evobots"
SCREENSHOT_DIRECTORY = REPOSITORY_ROOT / "tests" / "screenshots"
PAGES = [
    "/",
    "/quick",
    "/capital",
    "/settings",
    "/evolution",
    "/traders",
    "/career",
    "/life",
    "/data",
    "/simulator",
    "/paper",
    "/docs",
    "/docs/maths.md",
    "/gallery",
    "/best",
] + [
    f"/orfe/{name}"
    for name in ("leaderboard", "scenarios", "risk", "portfolio", "battery", "impact", "search")
]


@pytest.fixture(scope="module")
def client():
    server.app_settings["is_demo"] = True
    yield TestClient(server.app)
    server.app_settings["is_demo"] = False


def test_every_page_answers(client):
    for path in PAGES:
        response = client.get(path)
        assert response.status_code == 200, (path, response.text[:300])
        assert "<nav" in response.text or path == "/quick"


def test_missing_things_are_404_and_bad_input_is_400(client):
    assert client.get("/docs/../pyproject.toml").status_code == 404
    assert client.get("/orfe/nothing").status_code == 404
    assert client.post("/api/search", json={"evaluations": 5}).status_code == 400
    assert client.post("/api/capital", json={"starting_capital_usd": 10}).status_code == 400
    assert client.post("/api/final-test/R0/R0-1", json={"confirmation": "no"}).status_code == 400


def test_the_app_imports_only_the_service_and_nothing_imports_the_app():
    pattern = re.compile(r"^\s*(?:from|import)\s+(evobots(?:\.[\w.]+)?)", re.MULTILINE)
    for path in (SOURCE_ROOT / "app").rglob("*.py"):
        for module in pattern.findall(path.read_text(encoding="utf-8")):
            assert module in ("evobots", "evobots.service") or module.startswith("evobots.app"), (
                path,
                module,
            )
    for path in SOURCE_ROOT.rglob("*.py"):
        if "app" in path.relative_to(SOURCE_ROOT).parts or path.name == "cli.py":
            continue
        imported = pattern.findall(path.read_text(encoding="utf-8"))
        assert not any(module.startswith("evobots.app") for module in imported), path


def test_templates_and_scripts_have_no_formulas_or_remote_urls():
    for path in (SOURCE_ROOT / "app").rglob("*"):
        if path.suffix in (".html", ".js", ".css", ".toml"):
            text = path.read_text(encoding="utf-8")
            assert "http://" not in text and "https://" not in text, path
    script = (SOURCE_ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"Math\.|\*\s*\d|/\s*\d", script), "app.js must not compute results"


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def running_server():
    import uvicorn

    server.app_settings["is_demo"] = True
    port = free_port()
    instance = uvicorn.Server(
        uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    for _ in range(100):
        if instance.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    instance.should_exit = True
    thread.join(timeout=10)
    server.app_settings["is_demo"] = False


def test_pages_in_a_browser_offline(running_server, chromium_browser):
    SCREENSHOT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    context = chromium_browser.new_context(viewport={"width": 1280, "height": 900})
    remote_requests = []
    context.route(
        "**/*",
        lambda route: (
            (remote_requests.append(route.request.url), route.abort())
            if not route.request.url.startswith(running_server)
            else route.continue_()
        ),
    )
    page = context.new_page()
    errors = []
    page.on(
        "console", lambda message: errors.append(message.text) if message.type == "error" else None
    )
    page.on("pageerror", lambda error: errors.append(str(error)))
    for path in PAGES:
        page.goto(running_server + path)
        page.wait_for_load_state("networkidle")
        name = path.strip("/").replace("/", "_") or "home"
        page.screenshot(path=str(SCREENSHOT_DIRECTORY / f"{name}.png"), full_page=False)
    context.close()
    assert remote_requests == []
    assert errors == []
