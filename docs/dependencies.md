# Dependencies

Every library evobots uses: purpose, licence and version (`CLAUDE.md` §14.2, §20.2). Versions are pinned in `uv.lock`. Licences are read from each installed package's metadata (obs., round 23: `importlib.metadata`, the `License-Expression` field). Add a row whenever `pyproject.toml` gains a dependency.

## Runtime

| Library | Version | Licence | Purpose |
|---|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause (bundled parts: 0BSD, MIT, Zlib, CC0-1.0) | arrays for prices, P&L and the trailing 1-in-100-day loss |

## Development and tests

| Library | Version | Licence | Purpose |
|---|---|---|---|
| pytest | 9.1.1 | MIT | test runner; doctests in `src/` |
| pytest-socket | 0.8.1 | MIT | blocks networking in tests, apart from localhost (§14.4) |
| ruff | 0.17.2 | MIT | lint (pycodestyle, pyflakes, pep8-naming, docstrings, import order) and format |
| playwright | 1.64.1 | Apache-2.0 | headless-browser tests of pages: no console errors, no network requests, values shown (§14.4) |
| pluggy, iniconfig, packaging, Pygments | 1.7.0, 2.3.1, 26.3, 2.21.0 | MIT, MIT, Apache-2.0 OR BSD-2-Clause, BSD-2-Clause | pulled in by pytest |
| pyee, greenlet, typing_extensions | 14.0.0, 3.5.6, 4.16.0 | MIT, MIT AND PSF-2.0, PSF-2.0 | pulled in by playwright |

**Browser for the page tests.**
- Playwright drives a Chromium that is not a Python package. On a new machine, run `uv run playwright install chromium` once (needs internet).
- `tests/conftest.py` also accepts `EVOBOTS_CHROMIUM_PATH`, or the cloud container's pre-installed browser.
- Without a browser, the page tests are skipped and say why.

## Build

| Tool | Licence | Purpose |
|---|---|---|
| hatchling | MIT [verify: not installed in the environment; build back end only] | builds the `evobots` package from `src/evobots` |

## Planned (added when first used)

| Library | Milestone | Licence | Purpose |
|---|---|---|---|
| scipy | O0 (M0) | BSD-3-Clause [verify on install] | linear programs (HiGHS) for the DC-OPF explanation, then O2 and O4 |
| numba | M3 | BSD-2-Clause [verify on install] | the fast simulator engine (§14.3) |
| pyarrow or polars | M1 | Apache-2.0 / MIT [verify on install] | CSV ingestion |
| openpyxl, xlrd | M1 | MIT, BSD [verify on install] | EIA spreadsheets |
| FastAPI, Jinja2, uvicorn | M1.5 | MIT, BSD-3-Clause, BSD-3-Clause [verify on install] | the local app (option A) |
| cvxpy, Clarabel | O2–O3 | Apache-2.0 [verify on install] | convex models (CVaR, log-growth) |
| statsmodels | O1, O6 | BSD-3-Clause [verify on install] | regime switching, quantile regression, Cox models |
