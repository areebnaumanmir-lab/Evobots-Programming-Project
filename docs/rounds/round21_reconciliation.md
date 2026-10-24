# Round 21: decisions log and capital files received; Claude Science reproduced

Date: 2026-10-24. Areeb uploaded the decisions log (rounds 1–16), `capital_sizing.md`, and three of its CSVs.

## 1. Files added

| File | Where (layout of `CLAUDE.md` §4) |
|---|---|
| Decisions log, rounds 1–16 (pasted) | [decisions_log.md](../decisions_log.md), verbatim; rounds 17–21 appended |
| `capital_sizing.md` | [capital_sizing.md](../capital_sizing.md), verbatim except its one figure link (below) |
| `capital_sweep.csv`, `headroom_trailing.csv`, `hub_price_stats.csv` | `docs/data/` |

`capital_sizing.md` §4b linked to a figure stored inside Claude Science (`{{artifact:…}}`), which can't display here. It now points to a redrawn figure, `data/figures/point_in_time_full_size_threshold.svg`, with a one-line note saying so. No other text was changed.

## 2. Claude Science's numbers, recomputed from the round-20 archive (obs.)

Script: `tools/check_against_claude_science.py`. Every comparison is in `data/claude_science_check.csv` (196 rows). Period 2019-01-01 → 2025-09-21; the sealed hold-out is not touched.

| Check | Result |
|---|---|
| `hub_price_stats.csv`, every column, 8 hubs | **176 / 176** values agree to rounding |
| §4 benchmark P&L at full size (always-INC, always-DEC): mean day, 1-in-100 and 1-in-1,000 day loss, worst day, worst 5 and 20 days | **12 / 12** agree to the dollar; worst days 2022-12-23 (INC) and 2021-02-18 (DEC), as recorded |
| §4b point-in-time trailing p99 (365 days, newest day D−6, 90-day warm-up) | the 8 table rows agree exactly; range $10,432–$44,843, median $24,155 (C_full median $1.21M); first trading day 2019-04-06 |
| §4b breach rate | **2.16 %** of 2,361 days; by year 1.9 / 0.8 / 1.9 / **4.7** / 0.8 / 2.2 / 3.0 % for 2019–2025, as recorded |

**What this means:**
- The archive downloaded in round 20 is the same data Claude Science used.
- The rules of `sizing.py`, which hasn't arrived yet, are now pinned down by an independent reimplementation that gives the same numbers. When `sizing.py` arrives, its outputs can be tested against this script.
- The sizing and benchmark figures in the briefing (§13) are therefore **(obs.) in this project** too.

## 3. Reconciliation of the rationale with the log

[design_rationale.md](../design_rationale.md) Part C is rewritten from the log, as 47 entries with round, logic and a round-21 review.
- **Round 20's reconstruction** had 14 wrong round attributions and was missing 7 decisions; both lists are at the end of Part C.
- **No conflicts** were found between the log and the current briefing. Every difference is a later round replacing an earlier one:
  - multi-instrument scope → electricity (round 4);
  - RT visible to D−2 → D−6 (round 15);
  - the persistent 387-location universe → whatever exists each day (round 8);
  - the 2/3 floor as default → out-of-money death (round 19).
- **Facts corrected by the data:**
  - round 7 counted CINERGY/INDIANA as one persistent hub; they are different node sets (round 20);
  - round 13's "$500k per a filing; a blog says $1M" is settled by Attachment L §III.C.1 (round 18).
- **Resolved [verify]:** the meaning of `credit_share` is in the round-14 log (share of capital pledged as collateral, setting the Virtual MWh Limit). `CLAUDE.md` §13.1 is updated.

## 4. Still missing (`CLAUDE.md` §4)
- **Code:** `src/evobots/` (all files), `configs/10_miso_hubs.toml`, `tests/test_capital.py`, `tests/test_sizing.py`, `tests/test_floor_caps_storms.py`, and in `tools/` `build_hub_sample.py`, `fetch_2015_2018.py`, `capital_analysis.py`, `capital_explorer.html`.
- **Docs:** `design_spec.md`, `bot_inputs_and_representation.md`, `decision_questions.md`, `paper_digest.md`, `github_comparison.md`, `inventory.md`, `iso_comparison.md`, rounds 3–8, and `plans/`.
- **Data:** `hub_volume_stats.csv` (read by `test_floor_caps_storms.py`) and the other `docs/data/` CSVs and figures.

Following §4, none of these has been recreated. Step zero (the 40 tests) still waits for the code.

## 5. Measured vs assumed
- **Measured:** everything in §2.
- **Assumed:** that NumPy's default (linear) quantile matches Claude Science's method. It does here: every quantile agrees, which suggests the same method was used.
