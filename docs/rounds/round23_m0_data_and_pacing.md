# Round 23: weather offices, cleared bids, the weather fetch, and pacing

Date: 2026-10-24. Four questions were asked in the conversation at the end of round 22; Areeb picked the recommended option each time.

## 1. Decisions

| # | Question | Areeb's answer | What it means |
|---|---|---|---|
| 1 | Which NWS office feeds each hub's weather features? | **Nearest-load rule** | the office whose forecast towns sit nearest the hub's load centre (table below) |
| 2 | How much of MISO's cleared-bids report to fetch? | **Every day** | from 2023-01-01, the first day on the server, to the newest published day; hub liquidity medians become measured on all days instead of 33, and O9 (§20.12) gets enough data for intervals |
| 3 | Start the weather fetch now? | **Start now** | running in the background while M0 continues |
| 4 | How to pace the work? | **Continue, stop at check-ins** | work through the milestones in order, committing each round; stop only at the §2.4 check-ins (end of M0, M1.5, M3, M4, M7, M9); ask questions in the conversation as they come up |

### 1.1 Hub → NWS office

| Hub | Office | Why |
|---|---|---|
| MINN | MPX (Minneapolis) | Twin Cities load |
| MICHIGAN | DTX (Detroit) | south-east Michigan load |
| INDIANA | IND (Indianapolis) | central Indiana load |
| ILLINOIS | **ILX** (Lincoln, central Illinois) | MISO's Illinois zone is Ameren Illinois (central and southern Illinois); Chicago (ComEd) is in PJM, so LOT's towns are mostly outside MISO [verify against the PFM town lists while parsing, M1] |
| ARKANSAS | LZK (Little Rock) | central Arkansas load |
| MS | JAN (Jackson) | central Mississippi load |
| LOUISIANA | **LIX** (New Orleans / Baton Rouge) | the two largest Louisiana load centres |
| TEXAS | **LCH** (Lake Charles) | MISO's Texas zone is Entergy Texas in south-east Texas, inside LCH's area |

LOT (Chicago) is still fetched. It feeds no hub; it stays available for a sensitivity check and for stage D/C locations near Chicago, if any.

The rejected option was a blend of two offices per hub (ILLINOIS = ILX + LOT, LOUISIANA = LIX + LCH). It is smoother, but it mixes in Chicago weather, which is mostly not MISO's.

## 2. Weather fetch (`tools/fetch_nws_forecasts.py`, new)
- **One request per office per decision day.** Each asks IEM for the newest PFM issue entered in the 24 hours before 10:30 Eastern Prevailing Time on the decision day D−1 (§6.4, decided round 20). The time-window query with `limit=1` returns the newest issue in the window (obs.: for MPX on 2024-07-15, the cutoff 14:30 UTC returned the issue entered at 10:46 local time, 21,567 bytes).
- **The same issue** serves as "yesterday's forecast" for operating day D+1 (feature 12, `temp_fcst_change`), so no second request is needed.
- **Scale:** 9 offices × 7,878 decision days (2005-03-31 → 2026-10-24) = 70,902 requests.
- **Polite (§5.4):**
  - 2 workers, each waiting 0.5 s before every request; measured about 146 requests a minute, so about 8 hours in total;
  - 3 retries with backoff;
  - write-then-rename;
  - the contact email from `config/local.toml` in the User-Agent;
  - every request logged to `data/raw/nws/downloads.jsonl` (URL, cutoff, SHA-256), so a stopped run resumes where it left off.
- **Hold-out:** forecasts whose operating day falls in 2025-09-22 → 2026-09-21 go to `data/holdout/raw/nws/` and are never opened.
- **Reading rules** (case-insensitive search, header-driven columns, §7.4) are implemented in the parser at M1, not in the fetcher.

## 3. Cleared bids (`tools/fetch_miso_prices.py --report cleared_bids`)
- **What is fetched:** for every day from 2023-01-01, `{YYYYMMDD}_bids_cb.zip` and the DA ex-ante prices `{YYYYMMDD}_da_exante_lmp.csv` used to attribute cleared bids to hubs (`capital_sizing.md` §2).
- **Probed on 2026-10-24 (obs., HEAD requests):**

  | File | Status |
  |---|---|
  | `20221215_bids_cb.zip` | 404 |
  | `20230101_bids_cb.zip` | 200, 3.8 MB |
  | `20250601_bids_cb.zip` | 200, 2.2 MB |
  | `20260725_bids_cb.zip` | 200 |
  | `20260731_bids_cb.zip`, `20260801_bids_cb.zip` | 404 |

  So the report starts on 2023-01-01 and is published about **90 days late**.
- **Retry window:** a 404 for a cleared-bids day younger than 150 days is retried on the next run (`CLEARED_BIDS_RETRY_MISSING_DAYS`). Price files keep their 14 days.
- **Size:** about 1,393 days × (2–4 MB + ~1 MB) ≈ **5 GB**. That is less than the ~8 GB estimated when asking.
- **Hold-out:** days in the hold-out go to `data/holdout/raw/miso/`, unopened.
- **Not used before M1:**
  - **the 90-day lag** matters for O9 and for any paper-live use of liquidity, so it is recorded in `market_rules.md`;
  - **the liquidity caps** stay at the 33-day medians until M1 recomputes them on all days. Any change to a cap is reported before it is adopted, because the caps feed the 936 MWh/day footprint that the tests pin.

## 4. Measured vs assumed
- **Measured:**
  - the probe results above;
  - the fetch rates (146/min weather, 96/min MISO);
  - the MPX 2024-07-15 issue selection.
- **Assumed:**
  - that ILX's and LCH's forecast towns match the hub load centres (checked at M1);
  - that cleared-bids publication stays about 90 days late.
