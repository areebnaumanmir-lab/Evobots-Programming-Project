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

## 5. Two more questions, answered the same day

| # | Question | Answer |
|---|---|---|
| 1 | Which towns make up a hub's weather forecast? | **Load-centre town**: one fixed town per hub |
| 2 | Which hub area does a generator belong to? | **Nearest hub town**: the nearest of the same eight towns, by great-circle distance |

**The eight towns** (`src/evobots/data/regions.py`; zone codes and coordinates as printed in the forecasts, obs.):

| Hub | Office | Zone | Town | Coordinates |
|---|---|---|---|---|
| MINN | MPX | MNZ060 | Minneapolis | 44.88N 93.22W |
| MICHIGAN | DTX | MIZ076 | Detroit | 42.43N 83.02W |
| INDIANA | IND | INZ047 | Indianapolis airport | 39.73N 86.28W |
| ILLINOIS | ILX | ILZ029 | Peoria | 40.67N 89.68W |
| ARKANSAS | LZK | ARZ044 | Little Rock | 34.73N 92.24W |
| MS | JAN | MSZ049 | Jackson | 32.32N 90.08W |
| LOUISIANA | LIX | LAZ061 | New Orleans | 29.98N 90.25W (30.00N from about 2012) |
| TEXAS | LCH | TXZ215 | Beaumont | 29.95N 94.03W |

- Towns are matched by zone code and the start of the name, since printed coordinates and county suffixes changed (e.g. "BEAUMONT-JEFFERSON TX" and "BEAUMONT-TEXAS TX").
- **Presence (obs.):** each of the eight towns appears in at least 98 % of its office's parsed issues in every year 2005–2021 (every third downloaded file sampled).
- If a hub's town is missing from an issue, that hub's weather inputs are missing that day; no other town is substituted (`CLAUDE.md` §8).
- **What the area rule does** (MISO generators in the September 2026 workbook; months up to 2025-09):
  - North Dakota, South Dakota, Montana, most of Wisconsin and Michigan's Upper Peninsula go to MINN; most of Missouri and eastern Iowa to ILLINOIS; Kentucky to INDIANA;
  - **Iowa is split** near Des Moines (345 km from Peoria, 367 km from Minneapolis). Of Iowa's 12.9 GW of wind operating in 2025-09, 10.2 GW counts for MINN and 2.7 GW for ILLINOIS;
  - wind by area in 2025-09: MINN 20.0 GW, ILLINOIS 6.5, MICHIGAN 3.8, INDIANA 2.1, ARKANSAS 0.3, the three southern hubs 0.0. Solar: ILLINOIS 5.1, INDIANA 4.4, MINN 2.4, ARKANSAS 2.4, MICHIGAN 2.0, MS 0.9, LOUISIANA 0.6, TEXAS 0.5.

## 5b. Point-in-time access and the hold-out accessor (M1)
- **`src/evobots/data/visible.py`:** the decision time (10:30 Eastern on D−1, daylight saving followed), one publication rule per source, a `Column` type whose observations carry `available_at`, and `visible(column, decision_time)`. The look-ahead test changes every observation published after a random decision time and adds new ones, 50 times, and checks that nothing visible changes. The final-RT rule reproduces `sizing.py`'s D−6.
- **D-92 (Claude, reversible):** the briefing's "lag 1 day" didn't say at what time of day. H.15 posts the T-bill rate in the afternoon, and EPU and GPR post at unrecorded times, so those three are usable from the start of the second day after the observation (business days for the T-bill). Gas and oil spot prices are public by the evening of the trade day, so they stay at the next business day.
- **`src/evobots/data/holdout.py`:** `open_holdout(run, trader, who)` appends to the committed `data/holdout_access_log.jsonl` and returns the only object readers accept for hold-out days; a permission can't be made any other way. Tests check that no module other than the accessor (and the future final-test module) imports it or names the hold-out folder, and that the committed log says "Sealed: never opened".

## 5c. `evobots data build --stage A`, the synthetic market and the redistribution switch (M1)
- **`evobots data build --stage A`** (`src/evobots/data/build.py`, 5 tests on a hand-made archive) reads each operating day 2005-04-01 → 2025-09-21 through the era reader (offline, from the files on disk), writes `data/store/hub_prices.csv.gz` (1,153,392 day-hour-hub rows), and checks itself. Run on the real archive (7 minutes on 4 cores):
  - `hub_volume_stats.csv`: **64 of 64** values agree;
  - `hub_price_stats.csv`: **176 of 176** values agree at the recorded precision, after one correction below;
  - the evolution-period rows are identical to the round-26 table built by `tools/build_miso_hub_prices.py`; the old table also held the forward days after the hold-out (2026-09-22 → 2026-10-24), which the stage-A build leaves out.
- **Correction to round 21.** Round 21 reported "176/176 values agree to rounding", but its check allowed a 0.05 % relative tolerance. The eight excess-kurtosis values were about 0.01 % low (e.g. ARKANSAS 3,165.124 against 3,165.393). Claude Science used the bias-corrected sample kurtosis (pandas' `kurt`), which reproduces all eight to the third decimal. The builder and `tools/check_against_claude_science.py` now use it (`maths.md` §3.2), and `CLAUDE.md` §7.0 says so. Nothing else used kurtosis.
- **`src/evobots/data/synthetic.py`** (7 tests): seeded synthetic hub prices with noise, GARCH(1,1) or regime-switching spreads, and an optional planted rule (RT raised on hot afternoons), for M4's planted-signal test.
- **`is_miso_redistribution_allowed`** (decided round 25): a `[data]` table in `configs/10_miso_hubs.toml`, default false; `shareable_sources()` leaves MISO out of any shareable bundle unless it is switched on (4 tests; `config_reference.md`).

- **Pink Sheet reader** (`read_pink_sheet`, reporting only): monthly gas, oil and coal prices to 2025-08 (September 2025's average includes hold-out days). Its US gas series matches the mean of EIA's daily Henry Hub to 2 cents (2022-08: $8.79 against $8.81). **Licence:** the workbook has no licence text and names Bloomberg and Refinitiv among its sources, so it is kept private and left out of shareable bundles until CC BY is confirmed for these series (`data_sources.md` §2).

## 6. Files changed
- `CLAUDE.md` §13.1 (risk-free source), §17.2 (battery efficiency decided), §20.7 (battery default 82 %).
- `docs/decisions_log.md`, `docs/design_rationale.md` (D-86 … D-89), `docs/change_ledger.md`, `docs/data_sources.md` (FRED row and terms), `docs/market_rules.md` §4.1 (MPD estimate), `tools/list_verify_markers.py` and the regenerated register.
- Hub areas: `src/evobots/data/regions.py`, `tests/test_regions.py`, `CLAUDE.md` §7.4 and §7.8.
- M1: `tools/fetch_series.py`, `tools/write_data_manifest.py`, `data/manifest.toml`, `src/evobots/data/sources/series.py`, `tests/test_series.py`, `docs/maths.md` §3.1, `docs/data_sources.md` §1b, `CLAUDE.md` §7.6.

## 7. Measured vs assumed
- **Measured:** the FRED terms and the DTB3 series metadata, read on their pages on 2026-10-28; the series facts in §4, computed by `tests/test_series.py`.
- **Assumed:**
  - equal charge and discharge efficiencies (√0.82 each), unless the battery study chooses otherwise;
  - MPD = $12 every year, labelled "estimate", until MISO's published values are supplied;
  - a one-business-day publication lag for H.15;
  - that a single load-centre town represents a hub's weather, and that distance to these towns is a fair proxy for which hub's prices a generator affects (both chosen by Areeb, round 28).
