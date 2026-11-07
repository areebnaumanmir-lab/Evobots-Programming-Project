# Round 31: the weather download finished; the hub forecast table

Date: 2026-10-28.

## 1. The download
- `tools/fetch_nws_forecasts.py` finished after a container restart (relaunched; it resumes from its log).
- **70,938 office-days** (9 offices; decision days from 2005-03-31 to the newest available):
  - 70,898 downloaded;
  - 40 with no issue in the 24 hours before the deadline. 31 of these are the IEM error pages re-logged in round 28.
- Sizes: 2.5 GB under `data/raw/nws/`, and 133 MB (3,285 office-days) in the sealed `data/holdout/raw/nws/`, never opened.

## 2. The hub forecast table (`data/store/hub_forecasts.csv.gz`, git-ignored)
- **First build:** six hubs had a forecast high on 99.6–100 % of operating days, but LOUISIANA had 83.1 % and TEXAS 87.6 %.
- **Cause (obs.):** NWS renumbered two forecast zones. The town name and coordinates stayed the same:
  - New Orleans: LAZ061 → LAZ077 ("New Orleans-Western Orleans LA") from the 2022-04-06 issue;
  - Beaumont: TXZ215 → TXZ515 from the 2023-03-09 issue.
- **Fix:** `src/evobots/data/regions.py` lets a town carry several zone codes. Tests cover both renumberings, and a test checks that "East New Orleans" (LAZ078) is not matched.
- **Also seen:** in 2007–08 the Lake Charles office alternated two coordinate pairs for "BEAUMONT-TEXAS TX" (29.95N 94.03W and 30.08N 94.15W). Same zone and name, so the same town for our purposes.
- **Results after the fix** (obs., rebuilt table, 7,479 operating days per hub, 2005-04-01 → 2025-09-21):

| Hub | Days with a forecast high |
|---|---|
| ARKANSAS | 99.60 % |
| ILLINOIS | 99.93 % |
| INDIANA | 99.95 % |
| LOUISIANA | 99.96 % (was 83.1 %) |
| MICHIGAN | 99.95 % |
| MINN | 99.96 % |
| MS | 99.96 % |
| TEXAS | 99.97 % (was 87.6 %) |

- **Row statuses** (both target days): 119,552 ok, 66 unparsed issue (corrupted archive blocks), 18 missing town, 18 missing file, 2 bad issue time (the "4305" typo).
- **No stored issue is later than its decision time** (0 rows).

## 3. Measured vs assumed
- **Measured:** the counts above (`data/raw/nws/downloads.jsonl`); the zone switch dates (a scan of every downloaded issue for each town's block).
- **Assumed:** that a renumbered zone with the same town name and printed coordinates is the same forecast point.
