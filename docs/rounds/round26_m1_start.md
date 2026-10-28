# Round 26: MISO data kept for private use; M1 starts

Date: 2026-10-24.

## 1. Decision
- **Areeb:** "Keep everything for private use, the fine print says that data is only restricted if you're using it for explicitly commercial purposes."
- **Recorded:**
  - all downloaded MISO data kept, for private use, never redistributed;
  - Areeb's commercial-only reading noted. The Terms of Use text pasted in round 25 has no such distinction, so its source is [verify] (`round25_miso_terms.md` §7);
  - scripted MISO downloads stay paused until that source is recorded or Areeb says to resume.

## 2. M1 so far

| Item | Result |
|---|---|
| `src/evobots/data/periods.py` | the fixed periods in one place (market start, evolution end, hold-out, forward); `calibration.py` now imports them |
| `src/evobots/data/sources/miso_eras.py` | one reader for all three file eras: header search, padded names, the no-`Value` era, blank-name rows, empty hours. Date-range dispatch picks the file and zip member for any day. It refuses hold-out days without the hold-out accessor's permission. 19 tests |
| `src/evobots/data/sources/miso_cleared_bids.py` | the hub attribution of `capital_sizing.md` §2 as a module. 3 tests on a hand-made day |
| Hub table rebuilt | the 2015-02-19 fix below; only that day changed (1,159,728 rows compared); every Claude Science check still passes (176/176 hub statistics, all benchmark numbers) |

## 3. Findings (obs.)

**The 2015-02-19 day-ahead file.** Two DA files claim that day. Only 2015-02-19 overlaps (the ex-post zip for February holds that one day).

| 2015-02-19, daily mean $/MWh | MINN | ILLINOIS | INDIANA | MICHIGAN | LOUISIANA |
|---|---|---|---|---|---|
| `da_lmp` file | 68.7 | 52.1 | 102.8 | 92.4 | 34.2 |
| `da_expost_lmp` file | 30.9 | 29.2 | 33.2 | 30.5 | 29.9 |
| real-time (final) | 71.2 | 83.9 | 117.2 | 101.6 | 20.9 |

- **The ex-post file doesn't fit a cold-snap day** whose real-time prices tripled; the `da_lmp` file does. The ex-post file also matches no other day in 2014-04 → 2015-03 (closest: 2015-01-13, median gap $1.73).
- **Why the file types change:** MISO's presentation to FERC (Wang, Chatterjee, Li & Merring, "Price Enhancements for Real-Time and Day-Ahead Markets", FERC technical conference, June 22–24, 2015; PDF read, SHA-256 `61acb577…`) says "ELMP went live in the day-ahead and real-time energy markets on March 1, 2015 … Day-Ahead impacts are very limited."
- **Rule:** `da_lmp` before 2015-03-01, `da_expost_lmp` from then on. That answers the [verify] on whether the pre-2015 files are ex-post prices: before ELMP there was one DA price, and these files carry it.
- **Effect:** none on any recorded number. 2015-02-19 is before every calibration window (the fixtures start 2015-03-01).

**Hub volumes reproduced exactly.**
- The cleared-bids attribution reproduces `docs/data/hub_volume_stats.csv` (**64/64 values**) on its 33 sample days, the 15th of each month 2023-01 → 2025-09, counting D and I bids only. So the liquidity caps (5 MW, and 4 MW at MS.HUB) are now measured in this project.
- The report also has "F" and "P" rows (6,474 and 744 on 2023-01-15). They are excluded, as in Claude Science, and their meaning is [verify].

**The size of the loss component (MLC):** at the hubs, |MLC| is a median 2.5 % of the DA LMP (90th percentile 6.1 %; 471,446 hub-hours with |LMP| ≥ $1, 2019-01 → 2025-09). This replaces the [verify] in `explanations/lmp_from_opf.md`.

## 4. Still to come in M1
1. The NWS forecast parser. The fetch is a quarter done and paused at the 2-hour background limit (2005-03-31 → 2010-10-11).
2. Henry Hub, EPU, GPR, EIA-860M and the World Bank readers.
3. `store.py`, `visible.py`, the hold-out accessor, `synthetic.py`, and `evobots data build`.
4. The `is_miso_redistribution_allowed` switch.

## 5. Measured vs assumed
- **Measured:** everything in §3.
- **Assumed:**
  - that the 2015-02-19 ex-post file came from a pre-launch ELMP trial (a guess; it doesn't affect the rule);
  - the meaning of "F" and "P" bid types.
