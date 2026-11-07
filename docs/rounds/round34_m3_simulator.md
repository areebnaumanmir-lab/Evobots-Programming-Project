# Round 34: M3, the market simulator

Date: 2026-11-07. Part of "finish all of this" (round 32).

## What was built
- `src/evobots/simulate/fees.py`: the cost table by day and era, with MISO's netting: administration fee and DA RSG per node, the real-time deviation charge (DDC) on net virtual supply summed over nodes (`docs/market_rules.md` §3.2). Every rate is labelled "estimate" until the Rates Factors file arrives.
- `src/evobots/simulate/collateral.py`: collateral, the Virtual MWh Limit, and the MPD ($12 floor, "estimate", round 28).
- `src/evobots/simulate/settlement.py`: settles a **decision matrix** from any source (side, limit, full-size MW per day, hour and location). It applies clearing, the trader's own two-sided trailing 1-in-100-day sizing, the daily cap and the credit limit (bids cut, never refused), 0.1 MW rounding, fees, pauses, and out-of-money death. There are two versions: a readable NumPy reference and a Numba kernel.
- `docs/maths.md` §4: every simulator formula with a worked example and doctest.

## Done-when check (design spec §16, M3)
- **Baselines reproduce `capital_sizing.md` §4 and §7b** on the real hub table (`tests/test_settlement.py::test_real_benchmarks_reproduce_capital_sizing`):
  - worst full-size days: $492,173 on 2022-12-23 (always-INC) and $176,554 on 2021-02-18 (always-DEC);
  - mean day +$474; 1-in-100 loss $27,897;
  - storm fitness at $1.5M: 0.540 (always-INC) and −0.411 (always-DEC).
  - Offline, the simulator equals `evobots.sizing` exactly on synthetic data.
- **Fast against reference:** the Numba kernel agrees with the reference to 1e-9 relative on random decisions, including caps, pauses and the credit limit.
- **Speed benchmark** (obs., `benchmarks/results.csv`): 244 five-year, 8-hub trader-years per second on one core of this machine.
- **Simulator page:** built with the app pages (later in this build).

## Decisions taken under delegation
| Topic | Decision | Reason |
|---|---|---|
| DA RSG rate before the rate file | $0.05/MWh placeholder from 2008-11 (labelled) | so a DEC isn't free; no published history in the project |
| DDC by era | $0, $1.80 (2008-11 → 2011-03), $0.11 (2011-04 →) | D8's 2008–2012 mean; the IMM's 2024 DDC average |
| CMC | not modelled | needs constraint data; stated in every report |
| Sizing estimate | the trader's own full-size P&L, two-sided p99 (as `sizing.py`), after fees | §9.7: mixed-direction traders need their own tail; two-sided matches the calibrated rule |
| Limits | submitted MWh cut proportionally to the trader's cap and the credit limit, then rounded down | Attachment L counts submitted, not cleared, MWh (`market_rules.md` §4.2) |
| Career stops other than L0 | applied after settlement by the career model (M5), since each freezes the account from its first trigger | the path before a stop is identical |

## Measured vs assumed
- **Measured:** the reproduced benchmark numbers; the speed.
- **Assumed:** every rate (labelled); MPD at the $12 floor; no CMC.
