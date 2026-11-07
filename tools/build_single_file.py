"""Build the engine as one file: dist/evobots-<version>-<os>.pyz (`docs/design_spec.md` §14.6).

Usage:
    uv run --with shiv python tools/build_single_file.py

The .pyz holds the evobots code and its dependencies (NumPy, SciPy, Numba, FastAPI, …) for
this operating system and Python version; shiv unpacks it to ~/.shiv on first run. It holds
no MISO data: MISO data is used non-commercially with credit and never redistributed
(round 25), so each user builds the store with `evobots data build` from their own download.

Run it with the same Python version (3.13):
    python dist/evobots-0.1.0-linux.pyz serve
    python dist/evobots-0.1.0-linux.pyz run --evaluations 2000

Whether this ships as the engine deliverable is Areeb's decision (§14.6, §17.1 question 3);
it is an option, not a requirement. Build it on each operating system it is for (Windows
first): a .pyz with compiled dependencies is specific to one OS and Python version.
"""

import platform
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    """Run shiv on the project; prints the file and its size."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    system = platform.system().lower()
    output = ROOT / "dist" / f"evobots-{version}-{system}.pyz"
    output.parent.mkdir(exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "shiv",
        "--console-script",
        "evobots",
        "--output-file",
        str(output),
        "--python",
        "/usr/bin/env python3",
        "--reproducible",
        str(ROOT),
    ]
    subprocess.run(command, check=True)
    print(f"Wrote {output} ({output.stat().st_size / 2**20:.0f} MB)")


if __name__ == "__main__":
    main()
