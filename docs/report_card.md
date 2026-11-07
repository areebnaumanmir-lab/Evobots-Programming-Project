# The report card

Explanation document for M7 (`docs/design_spec.md` §12). Code: `src/evobots/assess/`. Command: `evobots report runs/R12` writes `runs/R12/report_<trader>.json` and `.html`.

## What it answers
How deployable one trader is: does it survive, is its edge more than luck after counting every trial the search made, does it survive doubled costs, the year after its training window, the named shocks, and, once, the sealed 12 months?

## The gates
| Gate | Question | How it is measured |
|---|---|---|
| G1 survival | would it survive a different ordering of history? | 1,000 stationary-bootstrap paths of its daily returns over the evolution period, mean block length by Politis–White; ≥ 95 % must stay within a 50 % loss |
| G2 skill vs trials | is its Sharpe ratio more than the luck of the search? | deflated Sharpe ratio ≥ 0.95 against the run's effective trials; MinBTL years needed ≤ years available |
| G3 overfitting | does the in-sample best stay good out of sample? | PBO by CSCV across the archive's elites ≤ 0.5 |
| G4 cost stress | is the edge bigger than the costs' uncertainty? | positive with fees and uplift doubled, on the unseen year and the whole period |
| G5 scale-up | does it survive at full size, and on every location? | at the MW cap without position scaling; Stage C rescoring at M8 |
| G6 walk-forward | did it work on the year after its training window? | positive log growth, drawdown within the 50 % mandate |
| G7 shock periods | how did it do in COVID, Uri, Elliott, the 2022 gas spike, the 2014 polar vortex? | each event's return; alive through all of them |
| G8 hold-out | the sealed 2025-09-22 → 2026-09-21, once per run | `evobots final-test`, logged; the lineage's sealed test is then spent |

## Also in the report
- **Rolling next-year results.** One row per window. Only the last row is unseen by the trader's lineage, and the report says so.
- **Storm sensitivity.** Fitness with all days, and with Uri and Elliott set flat.
- **Hindsight check.** The trader re-scored with `epu` and the gas features missing (their history may hold revised values).
- **O7 inference:** the Reality Check and SPA p-values for "some elite beats doing nothing" on the unseen year, and the Romano–Wolf list of elites that beat it at 5 %.
- **A 90 % bootstrap interval** on the yearly log growth, and the smallest annual Sharpe the data can detect.
- **MW by hub and location type**, the features read, equity and drawdown charts (thinned to 2,000 points, spikes kept), the caveats and an honest-expectation note.

## The first real report
See round 38 for the 30,000-trader run R101 and its report card.
