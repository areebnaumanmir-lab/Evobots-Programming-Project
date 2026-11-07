# Round 38: M7, the report card, and O7 (inference)

Date: 2026-11-07. Part of "finish all of this" (round 32).

## What was built
- `src/evobots/assess/report_card.py`: the report card as JSON. It covers every gate G1–G8, rolling next-year results, shock periods, storm sensitivity, the hindsight check, MW by hub, features read, thinned charts, caveats, an honest-expectation note and a "What happened" paragraph written from templates.
- `src/evobots/assess/report_html.py`: one renderer to a self-contained HTML file (inline CSS and SVG, no network).
- `src/evobots/assess/final_test.py`: G8, the sealed 12 months, the only code that opens the hold-out. It logs before reading, runs once per run, extends the data point-in-time, scores with the run's own rules, and writes `runs/<id>/final_test.json`.
- `src/evobots/assess/inference.py` (O7): White's Reality Check, Hansen's SPA, Romano–Wolf step-down, the model confidence set, bootstrap intervals, and the smallest detectable Sharpe ratio.
- Commands: `evobots report runs/R12`, `evobots final-test runs/R12 --yes`.
- `docs/report_card.md`; `docs/maths.md` §6.

## The first real report card (obs., run R101: 30,000 traders, 15 rolling windows)
The run's decision is **"do nothing"**. The nearest candidate, R101-29627 "frosty-raven", failed the quick G2 on its last window: deflated Sharpe 0.28 against 1,024 effective trials. Its full report card (`docs/data/report_R101-29627.json`):

| Gate | Result | Detail |
|---|---|---|
| G1 survival | pass | 100 % of 1,000 bootstrap paths within a 50 % loss (mean block 10.5 days) |
| G2 skill vs trials | pass over 2005–2025 | deflated Sharpe 0.98 against 1,024 effective trials; annual Sharpe 1.28 needs 6.4 years, 19.7 available |
| G3 overfitting | **fail** | probability of backtest overfitting 0.76 across the 80 elites |
| G4 cost stress | pass | doubled costs: +0.039 unseen year, +0.678 whole period |
| G5 scale-up | pass at the MW cap | Stage C: M8 |
| G6 walk-forward | pass | unseen year 2024-03-28 → 2025-03-27: +0.050 log growth, drawdown 3 % |
| G7 shock periods | pass | Uri +5.3 %, 2022 gas spike +7.5 %, Elliott −0.5 %, COVID +1.1 % |
| G8 hold-out | not run | sealed; Areeb's decision |

- **Its rule:** INC at every hub-hour where yesterday's DA price plus 0.41 × the policy-uncertainty index exceeds about $117/MWh. It bets that DA runs above RT after expensive days and in uncertain times.
- **Rolling next years:** positive in 14 of 15. The lineage saw those years earlier in the run, so they are not out-of-sample evidence, and the report says so.
- **Hindsight check: flagged.** Without EPU it doesn't trade at all, so its edge depends entirely on a series whose history may hold revised values.
- **O7:** no elite beats doing nothing on the unseen year (Reality Check p = 0.50, SPA p = 0.79, no Romano–Wolf rejection).

**Reading:** a profitable-looking, storm-surviving rule that the stricter tests don't accept as skill. G3 and O7 say the archive's in-sample winner is not reliably the out-of-sample winner. "Do nothing" was the right deployable decision.

## Decisions taken under delegation
| Topic | Decision | Reason |
|---|---|---|
| G1 period | the trader's whole evolution period, from its first trading day | the most data; bootstrap reorders it |
| G2 in the report | over the whole period (the quick gate uses the training window) | the report asks about the strategy; MinBTL is shown beside it |
| G6 | the single unseen year after the last training window; the rolling years are reported but flagged | only that year is unseen by the lineage |
| G7 calendar | polar vortex, COVID, Uri, the 2022 gas spike (months approximate, marked), Elliott | events in the evolution period; the 2026 Iran war is in the hold-out |
| Final test | once per run; a named trader may be tested when the decision is "do nothing" | §12.4; the test must not be skipped silently |

## Measured vs assumed
- **Measured:** every number above, from run R101 and the simulator.
- **Assumed:** gate thresholds; the gas-spike months; fee estimates.
