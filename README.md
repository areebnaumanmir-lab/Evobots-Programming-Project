# evobots

Evolves small, readable trading bots for virtual bidding at MISO's eight electricity trading hubs, judges each one like a real trading career (it dies when it runs out of money), tests it on a year the search never saw, and hands you the best one as a standalone Python file.

**Preview.** The bots use a simplified rule genome (conditions, a score formula, side thresholds, a limit-price offset and a size). Fees and uplift are labelled estimates. This is a research tool, not investment advice; real trading needs MISO registration and collateral.

## Open it as a website

Once the repository owner has switched on GitHub Pages (below), anyone can open evobots at `https://<owner>.github.io/<repository>/`. Nothing to install:
- the same page and sliders run evobots' Python inside the browser (Pyodide); the first visit downloads about 17 MB;
- the website uses synthetic demo prices, because MISO's terms forbid publishing MISO data;
- if you built the MISO hub table with the downloadable app, load it on the page. It is read in your browser and never uploaded anywhere.

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

Without MISO data on your machine, the app runs in **demo mode** on synthetic prices.

## Use real MISO data

MISO's terms forbid redistributing its data, so no copy of evobots includes MISO prices; each user builds their own. MISO's terms also forbid automated access to its website. Read them, and download the market reports through MISO's site:
- the day-ahead (ex-post, and `da_lmp` before March 2015) and final real-time LMP reports, from the Market Reports pages on misoenergy.org;
- save the files into `data/raw/miso/`, named as MISO publishes them (`docs/data_coverage.md` lists the names by era).

Then run:

```
uv run evobots data build --stage A
```

This writes `data/store/hub_prices.csv.gz` and checks it. Restart the app and it uses the real data. The sealed hold-out year (2025-09-22 → 2026-09-21) is never read by the app.

## Command line

```
uv run evobots serve             # the app (add --demo for synthetic data, --port to change the port)
uv run evobots data build        # build the hub price store from files on disk
uv run evobots capital           # what the capital settings imply
uv run pytest                    # the test suite (offline)
```

## Where to read more

- `docs/design_rationale.md`: why each decision was made.
- `docs/market_rules.md`: MISO's virtual-trading rules.
- `docs/maths.md`: every formula with a worked example.
- `docs/data_sources.md`: every source and its terms.

## Acknowledgments

Price data: MISO (built locally, not redistributed). Weather forecasts are derived from National Weather Service forecasts archived by the Iowa Environmental Mesonet, Iowa State University. Other sources:
- U.S. Energy Information Administration (gas, oil, generator inventory);
- Baker, Bloom & Davis, Economic Policy Uncertainty (CC BY 4.0);
- Caldara & Iacoviello (2022), *American Economic Review* 112(4), Geopolitical Risk (CC BY);
- Board of Governors of the Federal Reserve System, 3-Month Treasury Bill rate (DTB3), retrieved from FRED.
