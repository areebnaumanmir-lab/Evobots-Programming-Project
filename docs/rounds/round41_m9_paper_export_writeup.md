# Round 41: M9 (paper trading, export-bot, the single file, tutorial) and the ORFE write-up

Date: 2026-11-07. The last part of "finish all of this" (round 32).

## What was built
- **`evobots export-bot runs/R<n> [--trader ID]`** (`src/evobots/deploy/export.py`; §14.6).
  - Writes `bot_<id>.py`, standard library only, after the equivalence test: on 200 random days, the file (reading its inputs through its own CSV parser) must bid exactly what the engine bids. That covers side, limit, full-size MW, and MW after a random position scale.
  - Any mismatch stops the export.
  - Without `--trader` it exports the deployable bot; when the run's decision is "do nothing" it asks for a trader.
- **Paper trading** (`src/evobots/deploy/paper.py`, `evobots paper runs/R<n> [--trader ID]`, the Paper trading page).
  - **Inputs:** MISO's forward daily files (2026-09-22 on) from `data/inbox/miso/` or `data/raw/miso/`. There is no MISO fetcher: its terms forbid automated access.
  - **Output:** each forward day with final RT is settled under evolution's rules. The next operating day's bids go to `runs/paper/<id>/` with full-size MW, the position scale and the limit.
  - **The sealed year stays sealed:** its days are missing, never read, and features that look back into them are missing.
  - **Gas and EPU** include forward dates (`is_forward_included`). Hold-out dates are still dropped.
- **Sizing across a gap** (`src/evobots/simulate/settlement.py`).
  - **The rule:** a day with no prices at all is "not observed". The trailing 1-in-100-day loss uses the last 365 *observed* days.
  - **Why it was needed:** paper trading would otherwise read the sealed year as a year of zero losses and bid at full size.
  - **No effect on history:** every day of 2005-04 → 2025-09 has prices, so every past result is unchanged. A test checks the fast kernel against the reference on a gap, and pins the estimate.
- **`evobots paper --fetch`** (`src/evobots/deploy/vintages.py`): needs internet. It saves today's EPU, GPR and Henry Hub files under `data/vintages/<source>/<date>_…`, so forward tests can use true point-in-time vintages.
- **The single-file engine** (`tools/build_single_file.py`, shiv): `dist/evobots-0.1.0-linux.pyz`, 115 MB, code and dependencies with no data.
  - **Checked here outside the repository** with Python 3.13: `capital` runs, a 120-trader demo search runs, and `serve` answers 200 on `/`, `/evolution`, `/docs` and the stylesheet.
  - **Shipping it** is Areeb's choice (§14.6, §17.1 question 3).
- **Docs:**
  - `docs/tutorial.md`: steps 2–6 tested here on demo data. That covers capital, run, report and export-bot (the exported file run on an inputs CSV); paper trading was run on real forward data.
  - README updates.
  - `docs/orfe_report/report.md` and `summary.md`.
  - `docs/explanations/price_impact.md`, with the sensitivity run.
  - `docs/maths.md` §7, the ORFE formulas.
  - six figures in `docs/orfe_report/figures/`, drawn by `tools/build_orfe_figures.py`.

## Results (obs.)
- **Paper trading, R101 (decision "do nothing"):** 28 forward days settled (2026-09-22 → 2026-10-19), 5 waiting for final RT, P&L $0.
- **Paper trading, R101-29627 (named; it failed G2 and G3, so it isn't deployable):**
  - **Result:** +$58,558 on $1.5M over the same 28 days. Position scale 0.68, sized from the evolution period's last observed year.
  - **Next day:** 173 bids for 2026-10-25.
  - **Caveat:** this is one month of one candidate, not evidence of skill.
- **Price-impact sensitivity, R101-29627's unseen year:**
  - log growth +0.0503 when price-taking;
  - +0.0489 at the 90 % interval's upper end (β = 0.006 $/MWh per MW);
  - +0.0366 at ten times that.

## Corrections to round 39
- **Battery size:** the battery was 5 MW / 20 MWh at ILLINOIS.HUB, not 1 MW / 4 MWh.
- **Kupiec, 2015-06 → 2018:** only the empirical and EVT estimators pass; GARCH-FHS (p = 0.04) and Cornish–Fisher (p = 0.01) fail.
- **Impact units:** β's unit is $/MWh per MW, not per MW².

The round 39 doc is corrected in place.

## Decisions taken under delegation
| Topic | Decision | Reason |
|---|---|---|
| Paper features across the sealed year | missing, never read | the hold-out stays clean; spread features fill in after ~33 forward days, the hub-area code after 90 |
| Paper sizing | last 365 observed days | zero losses during an unobserved year would size at full scale |
| Paper location set | the trading hubs | the forward files are read per day; Stage D paper trading can follow |
| Exported file name | `bot_<id>.py` (§14.6) | the deployable folder keeps `trader_<id>.py` |
| `.pyz` contents | code and dependencies only | MISO data is never redistributed (round 25) |

## Still open
- **Figures not yet drawn** (report "Figures"):
  - the MAP-Elites heatmap with optimiser points;
  - frontier and weights over time;
  - battery SoC on a storm day;
  - breach timelines;
  - Kaplan–Meier curves;
  - the NSGA-II and MAP-Elites fronts.
- **A PDF of the report:** needs an offline LaTeX toolchain, which this machine doesn't have.
- **The `.pyz` on Windows:** build and check it there.
