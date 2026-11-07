# Round 40: M8, scaling up from the hubs to every location

Date: 2026-11-07. Part of "finish all of this" (round 32).

## What was built
- **Stage C, every location** (`src/evobots/data/location_store.py`; spec §7.11).
  - **Layout:** each calendar year of the evolution period gets float32 DA and RT arrays [day, hour, location] and a float16 DA congestion array, written as `.npy` files and memory-mapped when read. A JSON index holds the year's locations, MISO types and first day.
  - **Build:** resumable (a year with a complete index is skipped) and write-then-rename. It uses the era reader, which refuses hold-out days.
  - **Built here (obs.):** 21 years, 1,471–2,594 locations a year, 3.8 GB, about 6½ minutes with 4 workers.
  - **Check (obs.):** read back for the trading hubs, it equals the Stage A table on every one of 1,043,832 hub-hours with prices, to float32 precision (DA within $0.00006, RT within $0.00012). The gaps are the same.
  - **Precision:** float16 congestion is within $0.25, which is enough for the 28-day congestion-share feature it feeds.
- **Stage D, yearly cluster representatives** (`src/evobots/data/clusters.py`; spec §7.10; the grouping step after arXiv 2210.06543).
  - **Point-in-time:** for year Y, the daily mean DA − RT spread of every location over the 365 visible days ending 6 days before 1 January Y.
  - **Grouping:**
    - Spearman correlation;
    - average-linkage clustering on 1 − ρ, cut at 0.25;
    - groups of one location dropped.
  - **One representative per group:** a trading hub if the group has one, else last year's representative if it is in the group, else the medoid.
  - **The market of a period** holds the trading hubs plus every location that represents a group in any year of the period. A representative's prices are kept for its features in every year, but it can trade only in the years it represents a group (blanked in place after the features are built, which saves a second copy).
  - **Built here (obs.):** 7–85 groups a year from 1,201–2,350 candidate locations; 287 distinct representatives over 2006–2025 (457 before representatives carried over between years).
- **Choosing the stage.**
  - `Evaluator.from_store(stage="A" | "D" | "C", first_day, last_day)`;
  - `SearchSettings.stage` (checkpointed, so resume, refine and report rebuild the same data);
  - `evobots run --stage D --first-day YYYY-MM-DD`;
  - `evobots data build --stage C | D`.
- **G5 at every location** (`src/evobots/assess/scale_up.py`).
  - **What it does:** when the Stage C store is built, the report card re-scores the trader over its unseen year on every location (about 2,500), with 432 warm-up days for the features, the hub-area codes and the sizing history. It reports log growth, survival, drawdown, cleared MWh and the number of locations traded, beside its own stage.
  - **What G5 needs:** alive at the MW cap, and alive at every location.
- **Hidden "8 hubs" assumptions, fixed at the source.**
  - The report card's MW table lists the 20 largest locations and sums the rest.
  - Charts are thinned to 600 points per line on the server.
  - The location type comes from the store, not from "Hub".
- **App.**
  - a **Locations** selector (A or D) on the Evolution page's start form;
  - pagination on the Traders page (100 at a time);
  - a "Location stages" table on the Data page;
  - a `select` field kind in the page template.

## Measured cost (obs.)
| Stage | Locations | Peak memory (2005 → 2025) | One trader, one 5-year window |
|---|---|---|---|
| A | 8 | 0.5 GB | 0.03 s |
| D | 288 | 11.2 GB | 1.3 s |

- **Stage D from 2005** needs 11 GB, so runs on this 15 GB machine start later: `--first-day 2013-01-01` loads from 2011-11 (warm-up included), and the main process used about 4 GB.
- **Stage C** for the whole period would need about ten times Stage D. It is used one year at a time (G5).

## Benchmark: Stage A against Stage D (same seed 7, same budget of 2,000 traders, windows from 2013)
| Run | Stage | Time | Decision | Nearest candidate and failed gate |
|---|---|---|---|---|
| R105 | A | 1½ min (1 worker) | do nothing | R105-1770: G2, deflated Sharpe 0.01 against 204 effective trials |
| R104 | D | 35 min (2 workers) | do nothing | R104-1929: G2, deflated Sharpe 0.11 against 205 effective trials |

- **Same decision, for the same reason.** Neither run finds skill beyond what its number of trials would give by luck.
- **The Stage D search finds higher fitness on its training windows:** the best elite in the last window has F +0.389, against +0.110 on the hubs. It also gets slightly closer to G2. With 288 locations a trader has more places to apply its rule, so a fair comparison needs more budget and seeds than this benchmark.
- **Cost:** about 50 traders a minute with 2 workers at Stage D, against about 1,300 a minute with 1 worker on the hubs.

### The first G5 at every location (obs., `evobots report runs/R104`)
R104's nearest candidate, R104-1929 ("silent-marmot"):
- **Its rule:** on weekdays, DEC where the 7-day average spread is above $15.2, INC where it is below −$10.3, with the limit $66.6 from yesterday's DA.
- **Its own stage (263 locations that year):** +0.206 log growth on the unseen year 2023-12-31 → 2024-12-29, 4 % drawdown.
- **Every location (2,642):** +0.191 on the same year, alive, 2 % drawdown, trading at 2,531 of them. The same capital, risk budget and credit limit spread over more places, so it cleared 41,072 MWh instead of 130,691.
- **G5 passes.** It still fails G2 (deflated Sharpe 0.05; annual Sharpe 0.31 would need 80 years of data) and G3 (PBO 0.74), so the decision stays "do nothing".

**Memory, measured:**
- Scoring every location for one year peaks at 9.4 GB, prices held as float32 (Stage C markets are float32 from the store).
- The report scores it from the checkpoint before it loads the run's own evaluator, then frees it, so the two never share the machine's 15 GB.
- The first attempt, holding both at once in float64, ran out of memory.

## Decisions taken under delegation
| Topic | Decision | Reason |
|---|---|---|
| Stage C precision | float32 prices, float16 congestion | 3.8 GB instead of 7.6; prices exact to float32, congestion only feeds a 28-day ratio |
| Stage D threshold (§17.2, M8) | 1 − ρ ≤ 0.25, Spearman, average linkage | 0.5 leaves 3–13 groups (MISO's spreads share system-wide RT shocks); 0.15 gives up to 154 with many singletons |
| Singletons | dropped | a group of one is an outlier, not a pattern |
| Representative choice | hub, else last year's, else medoid | hubs are the liquid points; carrying over keeps a multi-year market at 287 columns, not 457 |
| Trading outside a representative's years | blocked (prices blanked for settlement only) | §7.10 recomputes the groups every year; features keep the full history |
| G5 at every location | the unseen year only, 432 warm-up days, float32 prices, scored before the run is loaded | the whole period doesn't fit in memory; one year peaks at 9.4 GB |
| Paper and final test at Stage D | the sealed test and paper trading stay at the hubs | the hold-out store is hub-level; extending it is Areeb's call |

## Measured vs assumed
- **Measured:** every count, size, time and memory figure above.
- **Assumed:** that Stage D's groups capture the distinct congestion patterns well enough to stand in for Stage C during the search. G5 checks this at the end.
