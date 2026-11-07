# evobots

Evolves small, readable trading bots for virtual bidding in MISO's day-ahead electricity market (at its trading hubs, at yearly cluster representatives, or at every location), judges each one like a real trading career (it dies when it runs out of money), tests it on a year the search never saw, and hands you the best one as a standalone Python file. When no bot passes the deployment gates, it says "do nothing".

**Preview.** The bots use a simplified rule genome (conditions, a score formula, side thresholds, a limit-price offset and a size). Fees and uplift are labelled estimates. This is a research tool, not investment advice; real trading needs MISO registration and collateral.

## Open it as a website

Once the repository owner has switched on GitHub Pages (below), anyone can open evobots at `https://<owner>.github.io/<repository>/`. Nothing to install:
- the same page and sliders run evobots' Python inside the browser (Pyodide);
- it runs on MISO's real hub prices for 2005–2025, loaded into the browser at start-up. The first visit downloads about 35 MB: Python plus the 17 MB price table. The MISO data is reproduced with MISO's permission; the site's `data/NOTICE.md` gives the conditions;
- you can also load a hub table you built yourself. It is read in your browser and never uploaded anywhere.

**Switching it on (repository owner, once):**
1. GitHub Pages needs a public repository, or a paid GitHub plan for a private one.
2. In the repository: Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. Merge this work into `main`. The workflow `.github/workflows/pages.yml` builds the site with `tools/build_website.py` and publishes it on every push to `main`; you can also run it by hand under Actions → "Publish website".

To try the website locally: `uv run python tools/build_website.py`, then `python -m http.server --directory site_build`, and open `http://127.0.0.1:8000/`.

## Quick start (one click)

1. Download the app: in a running copy use **Download the whole app**, or get this repository as a zip, and unzip it.
2. Start it:
   - **Windows:** double-click `Start evobots (Windows).bat`.
   - **macOS:** double-click `start_evobots.command` (first time: right-click → Open).
   - **Linux:** run `./start_evobots.command`.

   The first start installs [uv](https://docs.astral.sh/uv/) and the Python packages, so it needs internet once. After that evobots runs offline.
3. Your browser opens at `http://127.0.0.1:8765/`. On that page:
   - **Sliders** set starting capital, daily risk budget, MW cap, training years, search budget, selection pressure, cost multiple and seed.
   - **Run simulation** evolves bots on the training years. It then scores the survivors on the unseen test year (2024-09-22 → 2025-09-21) at estimated and doubled costs, and picks the best bot. If none passes, it says "do nothing".
   - **Download best bot code** saves the bot as a standalone, standard-library Python file. Run it with `python trader_R1-266.py --inputs today.csv`.
   - **Refine the best bot** starts a new search from the best bot and variations of it.
   - **Download the whole app** saves this application as a zip.

The app runs on **real MISO data from the first start**: the hub prices (2005–2025), weather forecasts and the gas, policy-uncertainty and interest-rate series come with it in `data/bundled/` and are installed automatically. Nothing else to download. Start it with `--demo` for synthetic prices instead.

**Want someone's runs too** (searches, report cards, paper ledgers)? Put their `evobots-data-pack.zip` in the evobots folder or in your Downloads folder before starting, and the app imports it once by itself. They make one with `uv run evobots data pack`. Packs are git-ignored; share one only under the conditions in `data/bundled/NOTICE.md`.

## Use real MISO data

The app already includes MISO's hub prices (above). To rebuild them yourself, or to add the all-location store (Stage C/D), download MISO's market reports through MISO's site; its terms forbid automated access:
- the day-ahead (ex-post, and `da_lmp` before March 2015) and final real-time LMP reports, from the Market Reports pages on misoenergy.org;
- save the files into `data/raw/miso/`, named as MISO publishes them (`docs/data_coverage.md` lists the names by era).

Then run:

```
uv run evobots data build --stage A
```

This writes `data/store/hub_prices.csv.gz` and checks it. Restart the app and it uses the real data. The sealed hold-out year (2025-09-22 → 2026-09-21) is never read by the app.

`uv run evobots data build --stage D` also builds every location (Stage C: yearly memory-mapped arrays, about 4 GB) and the yearly cluster representatives (Stage D) that `evobots run --stage D` searches on.

## Command line

```
uv run evobots serve                          # the app (--demo for synthetic data, --port to change the port)
uv run evobots data build [--stage A|D|C]     # build the stores from files on disk
uv run evobots capital                        # what the capital settings imply
uv run evobots run [--stage D] [--evaluations N]   # a MAP-Elites search; resume with `evobots resume runs/R<n>`
uv run evobots report runs/R<n>               # the report card (gates G1–G8) as JSON and HTML
uv run evobots export-bot runs/R<n> [--trader ID]  # one standard-library .py file, equivalence-checked
uv run evobots paper runs/R<n> [--trader ID]  # paper trading on forward data (files in data/inbox/miso/)
uv run evobots final-test runs/R<n> --yes     # the sealed 12-month test, once per run (logged)
uv run pytest                                 # the test suite (offline)
```

A single-file engine (`dist/evobots-<version>-<os>.pyz`, code and dependencies, no data) is built with `uv run --with shiv python tools/build_single_file.py`.

## Where to read more

- `docs/tutorial.md`: every step, from install to paper trading.
- `docs/orfe_report/report.md` and `summary.md`: the write-up and its two-page summary.
- `docs/architecture.md`: how the code is organised.
- `docs/design_rationale.md`: why each decision was made.
- `docs/market_rules.md`: MISO's virtual-trading rules.
- `docs/maths.md`: every formula with a worked example.
- `docs/data_sources.md`: every source and its terms.

## Acknowledgments

Price data: Midcontinent Independent System Operator, Inc. (MISO), public market reports, misoenergy.org. They are reproduced in `data/bundled/` with MISO's written permission for this project (2026-11-06), on condition that the source is acknowledged and the conditions of reproduction are made clear: **if you reproduce or reuse the MISO files, read [data/bundled/NOTICE.md](data/bundled/NOTICE.md) first**. Weather forecasts are derived from National Weather Service forecasts archived by the Iowa Environmental Mesonet, Iowa State University. Other sources:
- U.S. Energy Information Administration (gas, oil, generator inventory);
- Baker, Bloom & Davis, Economic Policy Uncertainty (CC BY 4.0);
- Caldara & Iacoviello (2022), *American Economic Review* 112(4), Geopolitical Risk (CC BY);
- Board of Governors of the Federal Reserve System, 3-Month Treasury Bill rate (DTB3), retrieved from FRED.
