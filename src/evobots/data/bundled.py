"""Install the data bundled with evobots, so a fresh download runs on real data (round 42).

`data/bundled/` holds the built MISO hub price table (reproduced with MISO's written
permission of 2026-11-06; conditions in `data/bundled/NOTICE.md`), the parsed weather
forecasts, and the newest gas, policy-uncertainty, risk-free and geopolitical-risk files.
Every `evobots` command except `capital` and `data` calls `install_bundled_data` first. It
copies each bundled file to where the readers look, unless a file is already there: a store
built on this machine, or an imported data pack, always wins.

- `data/bundled/store/<file>` → `data/store/<file>`
- `data/bundled/series/<source>/<file>` → `data/raw/series/<source>/<file>`

Example:
    >>> import tempfile
    >>> root = Path(tempfile.mkdtemp())
    >>> (root / "data/bundled/store").mkdir(parents=True)
    >>> _ = (root / "data/bundled/store/hub_prices.csv.gz").write_bytes(b"x")
    >>> install_bundled_data(root)
    ['Installed the bundled data: 1 file (MISO hub prices, weather, gas, EPU, rates).']
    >>> (root / "data/store/hub_prices.csv.gz").read_bytes(), install_bundled_data(root)
    (b'x', [])
"""

import shutil
from pathlib import Path

BUNDLED_DIRECTORY = Path("data/bundled")
TARGET_BY_FOLDER = {"store": Path("data/store"), "series": Path("data/raw/series")}


def bundled_files(root):
    """(bundled path, target path) for every bundled data file."""
    root = Path(root)
    pairs = []
    for folder, target in TARGET_BY_FOLDER.items():
        source = root / BUNDLED_DIRECTORY / folder
        if source.is_dir():
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    pairs.append((path, root / target / path.relative_to(source)))
    return pairs


def install_bundled_data(root=Path(".")):
    """Copy missing bundled files into place; returns a message when anything was copied."""
    copied = 0
    for source, target in bundled_files(root):
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        shutil.copyfile(source, partial)
        partial.replace(target)
        copied += 1
    if not copied:
        return []
    noun = "file" if copied == 1 else "files"
    return [
        f"Installed the bundled data: {copied} {noun} (MISO hub prices, weather, gas, EPU, rates)."
    ]
