# Round 39: M1.5, the multi-page app, and the ORFE results

Date: 2026-11-07. Part of "finish all of this" (round 32).

## What was built
- **The app shell (M1.5, `docs/design_spec.md` §14.5, §15).** A FastAPI and Jinja2 app with one page template, grouped navigation (Start, Evolve, Market, ORFE, Reference; `src/evobots/app/pages.toml`) and these pages:
  - Home, Capital, Settings, Evolution (the grid map, operators, gates, decision);
  - Traders (search a run's lineage) and Trader (rules, generated code, life, what it saw on a chosen day, family, actions);
  - Career, Life, Data, Simulator, Paper trading (a stub until M9), Docs (Markdown rendered locally), Gallery, Best bot;
  - Report (the M7 report card), one page per ORFE result, and the old one-page app at `/quick`.
- **Separation.** Every page is a plain dict built in `src/evobots/pages.py` and reached only through `evobots.service`. The app imports nothing else from the package, and nothing outside the app imports it (tested). Charts are SVG text computed in `src/evobots/charts.py`, so the browser never computes a result; a test checks that `app.js` has no arithmetic.
- **Actions.** Run, stop, resume, report, refine, Life and the final test start the matching `evobots` command as a subprocess, with its log under `runs/logs/`. A full search has its own endpoint (`/api/search`), apart from the quick demo run. The final test asks for typed confirmation.
- **Offline.** No page loads anything from the internet (a browser test aborts any non-local request and fails on any console error). It saves a screenshot of each page under `tests/screenshots/`.
- **Docs:** `docs/architecture.md`, `docs/how_to/change_the_ui.md`, `docs/how_to/index.md`.

## ORFE results (obs.; `tools/build_orfe_results.py` → `docs/data/orfe/*.json`)
- **Leaderboard (O-track; the unseen year 2024-03-28 → 2025-03-27).**
  - **Evolved elite:** the evolved elite R101-29627 has the highest log growth (+0.084), but a deflated Sharpe of 0.00 against the 27,167 traders the run tried.
  - **DPDS:** DPDS with ρ = 0.002 (Baltaoglu, Tong & Zhao 2018) makes +0.057 with a deflated Sharpe of 0.98, because it is one of only two settings tried.
  - **Baselines:** persistence makes +0.049 and always-INC +0.037.
  - **Model confidence set:** every strategy is in it, so the year cannot tell them apart.
  - **Perfect foresight** (+1.10) is a bound, not a strategy.
- **Scenarios (O1; 189 test days, 2022-02 → 2025-09).**
  - **Accuracy:** analogue days give the best CRPS (4.38) and pinball loss (2.03), ahead of the regime model (4.67) and the bootstrap (4.78).
  - **The regime model's tails** (t emissions) are far too heavy: excess kurtosis 2,122 against 296 in the real data.
- **Optimiser (O2).** The mean-CVaR LP at λ = 0 makes +0.009 on the unseen year and −0.054 at λ = 1. A one-day-ahead LP on scenario means does not beat simple rules.
- **Portfolio of elites (O3; walk-forward over the 80 elites).**
  - **Results:** mean-variance (γ = 10) +0.57, best single elite +0.59, half Kelly +0.30, equal weight +0.29, risk parity +0.18, mean-CVaR +0.11.
  - **Caveat:** the elites were evolved through these years. The walk-forward is out of sample for the weights only, not for the traders.
- **Battery (O4; 1 MW, 4 MWh, revenue as a share of the perfect-foresight bound).**
  - **Shares:** rolling intrinsic 0.75, stochastic DP 0.26, tuned and evolved threshold policies about 0.12.
  - **Losing years:** the threshold policies lose money in 2021 and 2022.
  - **End-of-day energy** is settled at the day's mean price, so no policy can beat the bound.
- **Risk (O5; always-INC at full size, 99 % one-day VaR and ES).**
  - **2015 → 2018:** every estimator passes Kupiec.
  - **2019 → 2021:** the peaks-over-threshold EVT estimator passes every test.
  - **2022 → 2025-09:** every estimator fails, because breaches cluster.
  - **Cornish–Fisher** breaks down at the observed kurtosis.
- **Search as an OR problem (O8; same budget of 1,500 evaluations, window 2014-03 → 2019-03).**
  - **Hypervolume:** NSGA-II 0.259, MAP-Elites 0.245. NSGA-II's front is larger: 50 points against 23.
  - **Unseen next year:** MAP-Elites' best scores +0.004, NSGA-II's −0.021.
  - **Successive halving** costs 224 trader-years instead of 320 and keeps the top three of the full ranking.
  - **OCBA** puts 56 of 60 re-evaluations on the two closest elites.
- **Price impact (O9; MISO cleared virtual bids, every fifth day 2023-01 → 2025-09, 12,085 hub-hours).** The spread moves by −0.0008 $/MWh per MW² of net virtual position. The clustered standard error is 0.0042 and the 90 % bootstrap interval is −0.008 to +0.006. There is no detectable impact at the hub level. The implied change for a 5 MW position is under one cent. This is an association, not causation: traders bid in the direction they expect the spread to move.

## Decisions taken under delegation
| Topic | Decision | Reason |
|---|---|---|
| Page data | pages are dicts from `pages.py`; templates only lay them out | the UI never computes results (§14.5); a new page needs no template |
| Long jobs from the app | subprocess `evobots` commands with logs, not threads in the server | a crash or restart of the server cannot corrupt a run; the CLI is the one path |
| Quick run vs full search | separate endpoints | a test once started a full search by accident (R102, R103 deleted) |
| Hold-out status on pages | read the access log directly | only `assess/final_test.py` may import the hold-out accessor |
| Price-impact default | β = 0 in the simulator (no impact) | O9 finds no detectable impact at hub level for MW-scale positions |

## Measured vs assumed
- **Measured:** every ORFE number above, from MISO data through 2025-09-21 (the hold-out stays sealed).
- **Assumed:** the battery's size and efficiency, the scenario models' settings, and the fee estimates.

## Checks
- `ruff format` and `ruff check` are clean.
- The fast suite passes: 433 tests.
- The browser pass has no console errors and makes no remote requests.
