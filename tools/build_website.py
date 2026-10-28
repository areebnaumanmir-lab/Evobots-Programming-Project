"""Build the static website (GitHub Pages) that runs evobots in the visitor's browser.

Usage:
    python tools/build_website.py [--output site_build]

The site needs no server. It has the page, rendered once from the app's own template; a Web
Worker running Pyodide (Python compiled to WebAssembly) with numpy and Jinja2; and evobots'
Python source as a zip. All of it is served from the site itself, with no CDN at run time
(CLAUDE.md §14.4).

Pyodide 0.27.7 (MPL-2.0) and its three wheels are downloaded once into data/cache/
(git-ignored), checked against the SHA-256 values below, and copied into the site. That
download is the only step that needs internet. The site carries no MISO data (MISO's terms;
docs/data_sources.md §3): it starts on synthetic prices, and a visitor can load their own hub
table, which never leaves their browser.

Writes <output>/: index.html, static/, vendor/pyodide/, evobots_package.zip, evobots.zip,
VENDORED.md, .nojekyll.
"""

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
import jinja2  # noqa: E402

from evobots.service import Service, app_zip_bytes  # noqa: E402

PYODIDE_VERSION = "0.27.7"
PYODIDE_BASE_URL = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
CACHE_DIRECTORY = REPOSITORY_ROOT / "data" / "cache" / f"pyodide-{PYODIDE_VERSION}"
# SHA-256 of each file, recorded when first downloaded (round 30); the wheels' values are
# also in pyodide-lock.json.
SHA256_BY_FILE = {
    "pyodide.js": "b4cb23a53aba19c221659b9fb40a2f18281d685691dc06647fb0afd0681baf98",
    "pyodide.asm.js": "6b4c90de5b7172873f04f21884d0e9d2274e305fe32116558fe3e4fbe3618d51",
    "pyodide.asm.wasm": "a50dd1843f805a0b7c45b61037ee0d7b26dfe85efe0e18ef95a34ad24e401f5f",
    "python_stdlib.zip": "16611534726e5d8ac2bd8f926410b2dcb8d6f49aa24913463533b457a2115c16",
    "pyodide-lock.json": "9c45b916001a750f4102fc287494f3eab215909c7535c626a20db80fd6333e2c",
    "numpy-2.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl": (
        "ebb61241d962b98b21597d7ce43b67668a6d5bab3acec4fbe958657320d7cd08"
    ),
    "Jinja2-3.1.3-py3-none-any.whl": (
        "2c74f33712082b6807f96c6ad4466fe57307d79659887078952f1fa6572580b7"
    ),
    "markupsafe-2.1.5-cp312-cp312-pyodide_2024_0_wasm32.whl": (
        "cceab881a7705a8e219f480ed089c4f5b87aad34d704e49360a53173e83f2681"
    ),
}
APP_DIRECTORY = REPOSITORY_ROOT / "src" / "evobots" / "app"
SITE_STATIC_FILES = ("theme.css", "site.js", "worker.js")


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vendored_pyodide_files():
    """Paths of the verified Pyodide files in the cache, downloading any that are missing."""
    CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, expected in SHA256_BY_FILE.items():
        path = CACHE_DIRECTORY / name
        if not path.exists():
            print(f"downloading {name} (needs internet, once)")
            partial = path.with_name(name + ".part")
            with urllib.request.urlopen(PYODIDE_BASE_URL + name, timeout=120) as response:
                partial.write_bytes(response.read())
            partial.replace(path)
        if sha256_of(path) != expected:
            sys.exit(f"{name}: SHA-256 differs from the pinned value; delete it and rebuild")
        paths.append(path)
    return paths


def package_zip_bytes(path):
    """evobots' Python source and templates, as the zip the worker unpacks."""
    source_root = REPOSITORY_ROOT / "src"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted((source_root / "evobots").rglob("*")):
            if "__pycache__" in file_path.parts or not file_path.is_file():
                continue
            if file_path.suffix in (".py", ".html"):
                archive.write(file_path, file_path.relative_to(source_root).as_posix())


def render_page(service):
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(APP_DIRECTORY / "templates"), autoescape=True
    )
    return environment.get_template("index.html").render(
        is_website=True,
        sliders=service.slider_definitions(),
        data_status="Loading …",
        status={"message": "Loading Python in your browser …"},
        results=None,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=REPOSITORY_ROOT / "site_build")
    arguments = parser.parse_args()
    output = arguments.output
    if output.exists():
        shutil.rmtree(output)
    (output / "static").mkdir(parents=True)
    (output / "vendor" / "pyodide").mkdir(parents=True)
    service = Service(is_synthetic=True)
    (output / "index.html").write_text(render_page(service), encoding="utf-8")
    for name in SITE_STATIC_FILES:
        shutil.copy(APP_DIRECTORY / "static" / name, output / "static" / name)
    for path in vendored_pyodide_files():
        shutil.copy(path, output / "vendor" / "pyodide" / path.name)
    package_zip_bytes(output / "evobots_package.zip")
    (output / "evobots.zip").write_bytes(app_zip_bytes())
    (output / ".nojekyll").write_text("", encoding="utf-8")
    lines = [
        "# Vendored files",
        "",
        f"Pyodide {PYODIDE_VERSION} (MPL-2.0, https://pyodide.org) with numpy (BSD-3-Clause),",
        "Jinja2 and MarkupSafe (BSD-3-Clause), from the Pyodide distribution.",
        "",
        "| File | SHA-256 |",
        "|---|---|",
        *[f"| {name} | {digest} |" for name, digest in SHA256_BY_FILE.items()],
        "",
    ]
    (output / "VENDORED.md").write_text("\n".join(lines), encoding="utf-8")
    size = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    print(f"built {output} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
