# Tutorial: from nothing to a judged, exported trader

Each step names the command, what it does and what you should see. Steps 1–6 work on synthetic demo data with no downloads, so you can try everything first. Steps 7–10 use real MISO data you download yourself.

Commands are shown with `uv run` (the project's environment). With the single-file engine (step 11), replace `uv run evobots` by `python evobots-0.1.0-<os>.pyz`.

## 1. Install
```
git clone <this repository> && cd evobots
uv sync
uv run pytest -q -m "not slow"      # the fast suite, offline
```
The tests block the network, so a pass means nothing needed the internet.

## 2. Look at the capital settings
```
uv run evobots capital
```
It prints what $1.5 million of starting capital implies:
- the full-size capital (about $1.39 million);
- the collateral at full size;
- the daily MWh limit the pledged credit supports.

Change a setting with flags, for example `--starting-capital 500000`. Every number comes from [capital_sizing.md](capital_sizing.md).

## 3. Open the app on demo data
```
uv run evobots serve --demo
```
Your browser opens at `http://127.0.0.1:8765/`, and the left navigation groups the pages:
- **Start:** Home, Quick run.
- **Evolve:** Evolution, Traders, Career, Life.
- **Market:** Data, Simulator, Capital.
- **ORFE:** the leaderboard and each module.
- **Reference:** Docs, Settings.

Every page says in one line what it shows.

## 4. Run a search
On the Evolution page, choose **Traders to evaluate** (try 2,000), **Worker processes** and **Locations** (A, the trading hubs), then **Start a run**. Or use the command line:
```
uv run evobots run --demo --evaluations 2000 --workers 2
```
- **Progress:** each batch prints a line with the traders scored, the current window, the archive size and the best fitness.
- **Pausing:** **Stop** (or `Ctrl+C`) checkpoints, and `uv run evobots resume runs/R1` continues byte-identically.
- **The decision:** the run ends with `trade` (a bot passed the quick gates) or `do nothing`.

## 5. Inspect traders and the report card
- **Traders page:** search a run's lineage by id, name, origin or operator, 100 at a time.
- **One trader:** click it to see:
  - its rules in plain English and its generated Python file;
  - its life (equity, drawdown);
  - what it saw on a chosen day;
  - its family tree.
- **The report card:**
  ```
  uv run evobots report runs/R1 --demo
  ```
  It writes `runs/R1/report_<trader>.json` and `.html`, with the eight gates G1–G8, rolling years, shock periods and the inference tests. The Report page shows the same.

## 6. Export a trader as one file
```
uv run evobots export-bot runs/R1 --demo                # the deployable bot
uv run evobots export-bot runs/R1 --trader R1-57 --demo # or any trader
python bot_R1-57.py --inputs day.csv
```
- **The file uses only the standard library.** It lists its rules and the inputs it needs at the top.
- **It is checked before it is written:** on 200 random days the file must bid exactly what the engine bids.
- **The inputs:** one CSV row per location-hour: `location, hour, cap_mw`, then the features the file lists. The Trader page's "What did it see?" table shows a day's values; `evobots.bots.source.rows_to_csv(input_rows(...))` writes them in this format.

## 7. Build the real data (MISO)
MISO's terms allow non-commercial use with credit. They forbid redistribution and automated downloads, so:
1. Download the day-ahead and final real-time LMP reports through misoenergy.org's Market Reports pages.
2. Save them, named as MISO publishes them, in `data/raw/miso/`. [data_coverage.md](data_coverage.md) lists the names by era.
3. Build and check the stores:
   ```
   uv run evobots data build --stage A   # the trading hubs, checked against recorded statistics
   uv run evobots data build --stage D   # every location (Stage C, ≈ 4 GB) and the yearly groups (Stage D)
   ```
   Stage C took about 7 minutes with 4 workers here and needs about 4 GB of disk.

The other inputs come from `uv run python tools/fetch_series.py`: gas, policy uncertainty and the risk-free rate. It needs internet, and your email in `config/local.toml` for the User-Agent.

The sealed year 2025-09-22 → 2026-09-21 goes to `data/holdout/`, and nothing but the final test reads it.

## 8. Run on real data
```
uv run evobots run --evaluations 20000 --workers 3
uv run evobots run --stage D --first-day 2013-01-01 --evaluations 2000 --workers 2
```
Stage D trades the yearly cluster representatives (about 290 locations over the whole period). It needs about 11 GB of memory from 2005; from 2013 the main process used about 4 GB here, with workers sharing most of it. Each trader costs about 40 times more than at Stage A.

## 9. The sealed test (once per run)
```
uv run evobots final-test runs/R7 --yes
```
- **It opens the sealed year once** for the run's chosen trader, logs who opened it and when, and writes `runs/R7/final_test.json`.
- **The Home page** then says "Opened on <date> for <trader> in <run>".
- **Refining** a trader whose sealed test was opened labels the new run "hold-out already used".

## 10. Paper trading on forward data
Drop MISO's daily files for 2026-09-22 onward (`YYYYMMDD_da_expost_lmp.csv`, `YYYYMMDD_rt_lmp_final.csv`) into `data/inbox/miso/`, then:
```
uv run evobots paper runs/R7                       # the run's deployable bot
uv run evobots paper runs/R7 --trader R7-1234      # or a named trader
uv run evobots paper --fetch                       # save today's EPU, GPR and Henry Hub files (internet)
```
- **The ledger:** each forward day with final RT is settled, and later days are "waiting for RT".
- **The next day's bids:** listed in `runs/paper/<id>/bids_<day>.csv` and on the Paper trading page.
- **What it costs to keep the seal:** features that look back into the sealed year are missing, never read. Until a few weeks of forward data exist, a trader trades only on the inputs it has.

## 11. One file for the whole engine (optional)
```
uv run --with shiv python tools/build_single_file.py
python dist/evobots-0.1.0-linux.pyz serve
```
- **Contents:** the code and its dependencies for this operating system and Python version (3.13). There is no data in it; each user builds their own store.
- **Where to build it:** on each operating system it is for.
