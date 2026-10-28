#!/bin/sh
# One-click start for macOS (double-click) and Linux (run ./start_evobots.command):
# installs uv the first time (needs internet once), then opens evobots in your browser.
cd "$(dirname "$0")" || exit 1
if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv, the Python package manager evobots uses (first run only) ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
fi
uv run evobots serve
