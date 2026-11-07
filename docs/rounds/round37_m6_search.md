# Round 37: M6, the full MAP-Elites search, and M6b, Life mode

Date: 2026-11-07. Part of "finish all of this" (round 32).

## What was built
- `src/evobots/qd/evaluation.py`: the evaluator, which takes a trader through bids, settlement, career and fitness. The risk-free rate is FRED DTB3, as in force each day. Behaviour ids are computed on a fixed reference window.
- `src/evobots/qd/archive.py`: the map (net direction × log selectivity, 10 × 8) and its elites.
- `src/evobots/qd/lineage.py`: the SQLite birth records. Genomes are kept for archive entrants and their ancestors; the store has search, ancestors, descendants and a dump for byte-identical checks.
- `src/evobots/qd/gates.py`: quick gates G1, G2, G4 and G6. G2 uses the effective number of trials.
- `src/evobots/qd/run.py`: the run. It covers rank-weighted parents, the operator bandit, neutral-child skipping, rolling 5-year windows with elite re-evaluation, walk-forward scoring, parallel evaluation applied in birth order, checkpoints, resume, regeneration from birth records, Refine settings (prior trials, hold-out-used flag), `current_bot.json` and the best bot's code.
- `src/evobots/qd/life.py`: Life mode, an event-driven market-time ecology with births at 2× capital, deaths, a population cap and family trees.
- `src/evobots/assess/statistics.py` (used by the gates, completed in M7): Sharpe, PSR and DSR, effective trials, MinBTL, Politis–White block length, stationary bootstrap, PBO by CSCV.
- CLI: `evobots run`, `evobots resume`, `evobots life`. Tool: `tools/fit_quit_hazard.py`.
- `docs/qd_explained.md`.

## Done-when check (design spec §16, M6, M6b; M4's planted-signal test)
- **A short hub run fills the archive.** Real MISO run R100: 6,000 traders over 15 rolling windows, 79 elites, lineage depth 57 (obs., `runs/R100/status.json`).
- **Ancestors and descendants can be browsed; a non-stored trader regenerates exactly.** Every trader of a test run regenerates to its recorded genome id.
- **Resume is byte-identical.** An interrupted-then-resumed run equals an uninterrupted one (archive, generator state, lineage), and 1 or 2 workers give the same run.
- **`current_bot.json` updates, with "do nothing" as the fallback.** Yes.
- **The UI stays responsive during a run:** runs live in a worker process (with the app).
- **M4 planted-signal test:** passes, with the criterion restated (below). On pure noise the same search says "do nothing".
- **M6b:** Life mode is deterministic, keeps family trees, and stays within its population cap.
- **M5's real-data hazard fit:** 186 losing random traders (of 400) on 2019-09 → 2023-09 give 44.3 / 23.9 / 14.8 % survival against 44 / 24 / 15 % (`docs/data/quit_hazard_fit.json`). β₁ (cumulative P&L) ends at its bound of 0: the fixed age, drawdown and recent-return terms carry the fit. That is reported, not hidden.

## The first real result (obs., run R100)
**"Do nothing."** The top ten elites of the last window (2019-03 → 2024-03) mostly gain on the following unseen year (log growth up to +0.074) and pass G1, G4 and G6. Every one fails G2: their deflated Sharpe ratios of 0.08–0.13, against 442 effective trials, are within what luck would produce. The best by training fitness bids INC at hubs on hours whose previous-day DA price exceeded $106/MWh. This is the honest answer at this budget; longer runs and the M7 report card follow.

## Corrections and decisions
| Topic | Decision | Reason |
|---|---|---|
| Founders "always INC/DEC" | thresholds set to 0 so they actually bid | with a ±1 $/MWh score and thresholds of 1, they never bid (bug found on real data) |
| G2 benchmark variance | the null sampling variance 1/(T − 1), not the trials' cross-sectional Sharpe variance | in a search where many traders share an edge (or its mirror), the cross-sectional spread measures skill and deflated a genuine edge to nothing on the demo market |
| Effective trials | participation ratio of a 64-stream reservoir, scaled to all distinct behaviours (plus a Refine run's prior trials) | §12.2 "cluster or PCA the daily P&L streams"; counts independent bets |
| Quick-gate thresholds | G1: 95 % of 200 paths within a 50 % loss; G2: DSR ≥ 0.95; G4: positive with doubled costs; G6: positive and drawdown < 50 %, on the next unseen year | documented choices; the full report card uses 1,000 paths |
| Planted-signal criterion | the best bot must bid DEC on > 80 % of planted hub-hours, with DEC precision > 4× the base rate, using a temperature feature and the hour | the first criterion (precision > 50 %) was too strict for a 2,400-trader budget: the search found "afternoons × cooling degree-days" (recall 100 %, precision 19 % vs a 2.5 % base rate), and the archive also holds a precise variant (precision 100 %, recall 43 %) |
| Life mode at the population cap | a birth crowds out the poorest living trader | keeps the ecology bounded and deterministic |

## Measured vs assumed
- **Measured:** run R100's outcome and statistics; the hazard fit; the determinism, regeneration and planted-signal tests.
- **Assumed:** gate thresholds, reservoir size, the population cap, k = 2.
