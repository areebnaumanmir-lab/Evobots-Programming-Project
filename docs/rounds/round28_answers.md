# Round 28: Areeb's answers to the round-27 questions

Date: 2026-10-28. The four multiple-choice questions of `round27_verification.md` §6 were answered.

## 1. Decisions

| # | Question | Answer | What it means |
|---|---|---|---|
| 1 | How to settle the MISO-only cost facts | **"I'll download the file"** | Areeb downloads MISO's *Market Settlements Rates Factors* workbook in a browser and attaches it. Claude saves it in `data/inbox/` (git-ignored) and records its SHA-256 in `data/manifest.toml`. Until it arrives, the simulator uses labelled estimates, as decided in round 20 (D3). |
| 2 | Risk-free rate source | **FRED 3-month T-bill (DTB3)** | the fitness's r_f comes from one keyless CSV, read by `src/evobots/data/sources/fred.py` (M1) |
| 3 | Sunday NERC holiday | **Sunday and Monday** | D2 (round 20) confirmed: a Sunday holiday also flags the following Monday |
| 4 | Battery round-trip efficiency default (O4) | **82 % (EIA fleet average)** | the `[battery]` default is 0.82 round trip, split as η_c = η_d = √0.82 ≈ 0.906 unless the battery study sets them separately |

## 2. What the Rates Factors file does and doesn't settle
- **It settles:** the fee rates (Schedules 17 and 24) and the RSG rate history (group F of `docs/verify_register.md`).
- **It doesn't settle the MPD** (group P). MISO publishes the yearly MPD on its credit pages, not in the settlement rates. Round 27 showed the MPD can't be recomputed from public price data.
- **Until a published MPD series is available:** the MPD is the $12 floor every year, labelled "estimate". At Stage A collateral is $22,464 at full size against $1.5M equity, so this can't change any Stage A result. The MPD only matters at stages D and C, where the Virtual MWh Limit can bind.
- **If Areeb wants it:** the MPD values are on MISO's credit pages (the exact page wasn't reachable by script; searching misoenergy.org for "MPD" or "Virtual Transaction" should find it [verify]). A copy of the yearly MPD notices, attached like the Rates Factors file, would close group P. Nothing before M8 needs it.

## 3. FRED DTB3 (obs., read 2026-10-28)
- **Series:** "3-Month Treasury Bill Secondary Market Rate, Discount Basis". Source: Board of Governors of the Federal Reserve System, release H.15 Selected Interest Rates. Units: percent, not seasonally adjusted, daily.
- **Terms:**
  - the series page labels it **"Public Domain: Citation Requested"**;
  - FRED's legal page: "These series may be under copyright or in the public domain and may be used without permission, provided you do not engage in any prohibited use. When using, please cite the data source and acknowledge that you obtained the data" from FRED.
  - Prohibited uses include scraping that is "disruptive, or adversely impacts the stability, performance, or availability" of the service. One CSV download per build is not that.
- **So it may be bundled,** citing "Board of Governors of the Federal Reserve System (US), 3-Month Treasury Bill Secondary Market Rate, Discount Basis [DTB3], retrieved from FRED, Federal Reserve Bank of St. Louis" with the download date.
- **Conversion to a daily risk-free return** (in `maths.md` when the reader lands): the discount-basis rate d (percent) of a 91-day bill converts to a bond-equivalent yield, then to a daily log return. Formula and worked example at M1.
- **Point in time:** H.15 rates are published the next business day. The rate visible on decision day D−1 is the one for D−2 or earlier. The risk-free rate enters only the fitness, not bot inputs, so a one-day lag is the conservative choice, not a look-ahead fix.

## 4. M1 progress: the daily series (same round)
- **Downloaded once** by the new `tools/fetch_series.py` (2026-10-28; 7 files, 19 MB): FRED DTB3, EIA Henry Hub and WTI, EPU, GPR, the World Bank Pink Sheet, and EIA-860M (September 2026, the newest on the current path). SHA-256s are in `data/manifest.toml`, which now also lists the 2,238 cleared-bids and ex-ante files of round 23 that it had missed.
- **Readers** in `src/evobots/data/sources/series.py` for DTB3, Henry Hub, WTI, EPU and GPR, with 16 tests (hand-made files, plus checks against the real downloads when present). Each cuts at 2025-09-21 unless given the hold-out accessor's permission. Rates are stored as fractions (DTB3's 5 % becomes 0.05, `CLAUDE.md` §14.1).
- **Facts re-measured (obs.):**
  - DTB3 has 5,123 trading days in 2005-04-01 → 2025-09-21 (round 27's count);
  - Henry Hub starts 1997-01-07; WTI's minimum is −$36.98 on 2020-04-20;
  - mean GPR over 2022-02-24 → 03-31 is 318 (`CLAUDE.md` §7.7);
  - mean EPU over 2020-03-09 → 04-30 is 512.6, so "513" holds. **Correction:** `CLAUDE.md` §7.6 said that mean was "above every 2015–19 baseline day". One day is higher: 2016-06-25, at 586.6, the day after the Brexit vote. The mean is 3.5× the highest 53-day mean of 2015–19 (144.7). The briefing now says so.
- **Not read:** anything after 2025-09-21 in these files. The briefing's 2026 facts (gas peak, Iran war GPR) are inside the hold-out and stay unverified until `final-test`.
- **NWS forecast parser** (`src/evobots/data/sources/nws_pfm.py`, 6 tests on trimmed real issues), run over every file downloaded so far (36,700 office-days, 2005-03-31 → 2016-05):
  - columns are placed by the UTC hour row; the max/min values fall under the ~7 p.m. and ~7 a.m. local columns, as NWS defines them;
  - **19 town blocks are corrupted in the archive** (another row spliced into the hour rows). Each is skipped and reported, and the rest of its issue is kept;
  - **fetcher bug found and fixed:** when no issue exists in the 24-hour window, IEM answers "ERROR: Could not Find: PFMLZK". That text contains "PFM", so 31 such answers had been saved as forecasts (27 of them LZK). The check now looks for the product's own `PFM…` line, the 31 records were re-logged as missing, and the download was restarted with the fix;
  - one Indianapolis issue (2015-07-16) is a backup office's placeholder ("AREA 1"), with no usable town;
  - towns change over the years (Indianapolis's office went from 8 towns to 46 in 2008), and coordinates are re-surveyed by 0.01–0.03°, so towns are identified by zone code and name. One source error was seen: Port Arthur TX printed at 3.93°W. Which towns feed each hub is question 1 below.
- **EIA-860M reader** (`src/evobots/data/sources/eia860m.py`, 4 tests): MISO's fleet by month and technology from the operating and retirement months. Against `CLAUDE.md` §7.8, coal, wind, solar and battery agree to 0.1 GW; **natural gas is 0.7 GW lower in every month** (78.6 vs 79.3 GW in 2005-04; 83.2 vs 83.9 in 2015-01). The likely cause is a different grouping (e.g. "Other Gases", 0.5–1.2 GW, counted as gas), but this wasn't confirmed. Plant → hub area is question 2 below.
- **A slip, reported:** checking the reader printed the fleet for August 2026, a month inside the sealed hold-out. These are generator counts the briefing already quotes, not prices or results, but the rule is that nothing from the hold-out is printed. `nameplate_mw_by_group` now refuses months after 2025-09 without the hold-out accessor's permission, and a test checks it.
- **Next in M1:** the two questions below, then regional weather and capacity features' inputs, the Pink Sheet reader, `visible()`, the store, and `evobots data build --stage A`.

## 5. Files changed
- `CLAUDE.md` §13.1 (risk-free source), §17.2 (battery efficiency decided), §20.7 (battery default 82 %).
- `docs/decisions_log.md`, `docs/design_rationale.md` (D-86 … D-89), `docs/change_ledger.md`, `docs/data_sources.md` (FRED row and terms), `docs/market_rules.md` §4.1 (MPD estimate), `tools/list_verify_markers.py` and the regenerated register.
- M1: `tools/fetch_series.py`, `tools/write_data_manifest.py`, `data/manifest.toml`, `src/evobots/data/sources/series.py`, `tests/test_series.py`, `docs/maths.md` §3.1, `docs/data_sources.md` §1b, `CLAUDE.md` §7.6.

## 6. Measured vs assumed
- **Measured:** the FRED terms and the DTB3 series metadata, read on their pages on 2026-10-28; the series facts in §4, computed by `tests/test_series.py`.
- **Assumed:**
  - equal charge and discharge efficiencies (√0.82 each), unless the battery study chooses otherwise;
  - MPD = $12 every year, labelled "estimate", until MISO's published values are supplied;
  - a one-business-day publication lag for H.15.
