# Round 22: building independently; the capital slice rebuilt and proven

Date: 2026-10-24. Areeb asked: "Why can't you make the project independently and ask all the questions you need directly here?" and sent four more CSVs.

## 1. Why the work had waited, and what changes
The briefing (§4) said: "If something is missing, list it and ask; don't recreate it from this prompt unless I say so." Areeb's message says so. From now on:
- missing files are **rebuilt** from the briefing and the docs, and proven against the recorded numbers;
- questions are asked directly in the conversation;
- if an original file arrives later, it is compared with the rebuild and the differences are reported.

`CLAUDE.md` §4 now says this.

## 2. Files received
`fixed_cost_capital_floor.csv`, `hub_volume_stats.csv`, `trailing_breach_rate_by_year_2015_2025.csv` and `trailing_p99_daily_loss.csv`, placed in `docs/data/`.

## 3. The capital slice, rebuilt

| File | What it does |
|---|---|
| `src/evobots/config/capital.py` | `CapitalSettings`: defaults, bounds, per-hub caps (0.1 MW step, halves up), footprint, Virtual MWh Limit, optional floors, warnings |
| `src/evobots/config/__init__.py` | `load_capital`: code defaults < TOML `[capital]` < command line; unknown keys rejected |
| `src/evobots/sizing.py` | point-in-time trailing p99 (D−6, 365 days, 90-day warm-up, worse direction), position scale, benchmark equity simulation, worst rolling loss |
| `src/evobots/storms.py` | fitness with and without storm days (reporting only) |
| `src/evobots/calibration.py` | the full-size benchmark P&L from the hub table (refuses hold-out dates); fixed-cost formulas |
| `src/evobots/cli.py` | `python -m evobots.cli capital [config] [flags]`; the only home of `CALIBRATION_ONLY_FULL_SAMPLE_P99_USD` |
| `configs/10_miso_hubs.toml` | the `[capital]` table |
| `tools/build_benchmark_fixture.py` → `docs/data/benchmark_full_size_daily_pnl.csv` | the daily full-size benchmark P&L, 2015-03-01 → 2025-09-21 (3,858 days, gapless), committed so the tests run offline |
| `docs/maths.md` §1, `docs/config_reference.md` | formulas with worked examples, functions and tests; every TOML key |

**Changes from the Claude Science original:**
- **Names** follow §14.1. This is the M0 naming pass done at rebuild time: `daily_risk_budget` → `daily_risk_budget_fraction`, `credit_share` → `credit_share_fraction`, plus `liquidity_share_fraction`.
- **Capital floors** are off by default (round 19).
- **The MPD** is no longer a setting (round 19, §13.1).

## 4. Proof: what the 133 tests check (obs.)

| Recorded in Claude Science | Result |
|---|---|
| `trailing_p99_daily_loss.csv`, every one of 2,456 days | identical (to $1) |
| `trailing_breach_rate_by_year_2015_2025.csv`, 11 years | identical rates and day counts |
| §4b table (8 rows), warm-up end 2019-04-06 | identical |
| §4 benchmark numbers (mean day, p99, worst days and dates) | identical |
| `capital_sweep.csv` (10 rows × 5 values) | identical |
| `headroom_trailing.csv` (39 rows: headroom, worst 20 days trailing and full-sample, both survival flags) | identical |
| `fixed_cost_capital_floor.csv` (5 rows × 5 values) | identical |
| §7b storm sensitivity: always-INC 0.540 / 0.684 / Uri +0.069 / Elliott −0.212; always-DEC −0.411, ruined 2022-01-21 | identical |
| 936 MWh/day (not 960); MS.HUB 4 MW; collateral $22,464; credit limit 15,625 MWh/day | identical |
| Look-ahead: changing anything from D−5 on leaves the estimate for D unchanged; D−6 changes it | passes |
| `CALIBRATION_ONLY_*` used only in `cli.py` | passes |

**Definitions pinned down by reproducing the numbers** (`capital_sizing.md` describes them in words only):
1. **Worst k-day loss:** the loss over the run divided by equity at the run's start.
2. **The capital sweep's "worst 20 days, full sample":** a constant scale from starting capital × the worst 20-day full-size loss ($484,372) ÷ capital.
3. **`headroom_trailing.csv`'s full-sample column:** equity-based sizing with the constant p99.
4. **`fixed_cost_capital_floor.csv`:** its printed shares (0.721, 0.707) are rounded; its MWh column carries the measured shares (0.72128, 0.70718).

**Fixed during the build:** a doctest example I had worked out by hand was wrong (96.06; the correct value is 98.07). `src/` doctests were not collected at all; `pyproject.toml` now collects them.

## 5. Measured vs assumed
- **Measured:** everything in §4.
- **Assumed:** that the hub table's gapless daily index is what `sizing.py` used. It must have been: every day's value agrees.
