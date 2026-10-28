# Round 29: a deployable preview app on a deadline

Date: 2026-10-28. Areeb: "I'm on a tight deadline, I need a user-friendly deployment of this where with one click of a button users can go ahead and open a page with a bunch of sliders so they can run simulations and then download the code of the best bot, or they could rerun the evolution on a bunch of variations of the best bot and they can download this whole application to their laptop too. Just finish this quickly."

## 1. What was built
| Piece | File | What it does |
|---|---|---|
| One-click start | `Start evobots (Windows).bat`, `start_evobots.command` | installs uv the first time (internet once), then `uv run evobots serve`, which opens the browser at `http://127.0.0.1:8765/` |
| The page | `src/evobots/app/` (FastAPI + Jinja2, option A) | eight sliders, each explained and badged "Your choice"; the actions are words: Run simulation, Refine the best bot, Stop, Download best bot code, Download best bot genome, Download the whole app; a status line; the results (rules, career table, equity chart, the MAP-Elites map, top elites) |
| The bridge | `src/evobots/service.py` | validates the sliders, runs searches in a background thread, renders every number, chart (inline SVG) and paragraph in Python, and saves each run under `runs/` |
| Market data | `src/evobots/simulate/market.py` | the Stage A hub store as arrays, or synthetic demo data when MISO data isn't built on the machine; eight price features, point-in-time (DA to D−1, RT spreads to D−6) |
| Settlement | `src/evobots/simulate/engine.py` | the rules of §6.1 and §10: clearing by limit price, P&L, estimated costs, sizing on the trader's own trailing 1-in-100-day loss, out-of-money death, fitness |
| Traders | `src/evobots/bots/genome.py`, `codegen.py` | a simplified genome (conditions, score formula, side thresholds, price offset, size), five founders, mutation and crossover, exact JSON round trip, and the generated standalone standard-library Python file |
| Search | `src/evobots/qd/map_elites.py` | MAP-Elites on net direction × selectivity with rank-weighted parents (pressure 0.5), a walk-forward test year, quick gates, "best bot" or "do nothing"; Refine seeds a run with the best bot and 30 mutants |
| Downloadable app | `/download/evobots.zip` | every tracked and untracked-but-not-ignored file, without data, secrets, run outputs or MISO-derived tables |

**Measured on real MISO data:**
- One search of 600 traders takes 17 s; one 5-year career takes 35 ms.
- A run through the page (300 traders, 2019-09-23 → 2024-09-21 training) found R1-266. In the unseen test year 2024-09-22 → 2025-09-21 it turned $1.5M into $1,645,275, and $1,599,303 with doubled costs. Its rules are mostly INC in hours 1–17.
- Refine found R2-264 ($1,659,102).
- In a headless browser, the page made no request outside localhost and logged no console error after the favicon fix.

## 2. Simplifications, stated
- **Genome:** fixed slots (≤ 3 conditions, ≤ 3 score terms), not the typed-GP trees of §9.3. Those replace it at M4.
- **Features:** 8 of the 25 (the price and calendar features). Weather, gas, policy and capacity inputs arrive with the feature layer (M2).
- **Costs:** labelled estimates ($0.09 admin + $0.11 RSG per cleared MWh) until the Rates Factors file arrives.
- **Gates:** quick only (survival in both windows, positive test-year fitness at estimated and doubled costs). The full report card (G1–G8: bootstrap, deflated Sharpe, PBO …) is M7. A bot passing these gates is **not** shown to be deployable.
- **Sizing floor:** a trader with no visible losses is sized as if its 1-in-100-day loss were $1,000 (assumption, so sizing stays finite).
- **Test year:** 2024-09-22 → 2025-09-21, the last year before the sealed hold-out. Every run reuses it, so choosing among runs by it is itself selection; the sealed hold-out stays unopened.

## 3. MISO's terms and the downloadable app
- **Data:** the zip carries no MISO prices. Following round 25's switch (default off), it also leaves out the MISO-derived tables and pages:
  - `docs/data/*` benchmark and statistics tables;
  - the trailing-loss figure;
  - the design preview page;
  - the capital explorer page.
- **Tests:** the tests that reproduce `capital_sizing.md` from those tables are skipped in such a copy. A downloaded copy starts in demo mode on synthetic prices, and the README explains how a user builds MISO data from MISO's own pages.
- **Still in the zip:** the prose docs keep aggregate numbers (e.g. hub spread statistics quoted in `CLAUDE.md`). That is a judgment call for Areeb before sharing the zip publicly.

## 4. Not done
- **No public hosting.** This session's container is temporary, so the app runs on each user's machine; the launchers make that one double-click.
- **No `.pyz` single file** (§14.6, to be decided at M9).

## 5. Measured vs assumed
- **Measured:** the timings and run results above; the browser checks; `tests/test_preview_app.py` (generated code equals the engine on random inputs, deterministic search, app routes, zip contents).
- **Assumed:** the cost estimates; the $1,000 sizing floor; that price features alone are a fair preview of the feature set.
