# Round 20: literature review, decisions fixed, MISO data downloaded, visual style

Date: 2026-10-24. Areeb asked:
- for a literature review of questions 1–4 (what a trader is, what it starts with, how it is identified, how it mutates), with pros and cons;
- for an ongoing write-up of the logic behind every decision, including the decision logs and the 20 questions;
- to fix any suboptimal earlier decision now;
- for a minimal, utilitarian UI from a reference image (simpler, less colour, words instead of button boxes);
- for the MISO data to be downloaded.

## 1. What was done

| Item | Where |
|---|---|
| Living rationale for every decision (literature, options, pros/cons, status) | [design_rationale.md](../design_rationale.md) |
| 77 references checked: 66 verified, 2 partial, 9 not found (old conference papers and one book with no Crossref record; cited with [verify]); 29 abstracts stored | [references.md](../references.md), `data/references_checked.json`, `tools/check_references.py` |
| MISO DA and RT prices for every location, 2005-04-01 → 2026-10-24 | `tools/fetch_miso_prices.py`; [data_coverage.md](../data_coverage.md); `data/manifest.toml` |
| Hub table, location list, daily coverage | `tools/build_miso_hub_prices.py` → `data/store/` (git-ignored) |
| Visual reference saved; theme tokens; preview page on real data | `design/visual_reference/reference_dashboard.png`, `design/theme.css`, `design/preview_data_page.html`, `tools/build_design_preview.py` |
| Briefing revised | `CLAUDE.md` (round-20 notes at the top) |

**Download size:** about 5.3 GB of raw files (4.4 GB evolution and forward period, 0.86 GB hold-out). That is above the briefing's "tell me first" line of 1 GB; Areeb instructed the download explicitly. Politeness:
- 3 parallel requests (limit 4), 0.5 s apart;
- a contact email in the User-Agent;
- write-then-rename;
- every file hashed.

**Decision logs:** `docs/decisions_log.md` and the rounds 3–16 docs have not been uploaded. The rationale reconstructs rounds 1–16 from the briefing and will be reconciled when they arrive.

## 2. Decisions changed (reasons in the rationale)

1. **Training window 1 → 5 years**, rolling by a year. On 1 year a Sharpe ratio has a standard error of about 1. The briefing's own MinBTL table allows ~3 independent trials at Sharpe 1 on 1 year, versus ~45 on 5.
2. **Elites re-evaluated whenever the window moves.** The briefing's loop compared a child and an elite scored on different windows.
3. **Ids:**
   - trader id = run + birth number;
   - genome id = SHA-256 shown as the shortest unique prefix of at least 10 hex characters;
   - a new behaviour id.

   Round 19's 8-hex id would give ~116 colliding pairs per million traders, and merged twins.
4. **Start:** PTC2 random trees replace ramped half-and-half, and a no-founder control run is required.
5. **Variation:**
   - size-fair crossover;
   - iso+line-DD for numeric genes;
   - bandit-adapted operator rates;
   - neutral children skipped by behaviour id.
6. **Code ⇄ genome round trip:** hand-written or edited traders can join as `founder:human`.
7. **Language-model mutation of code rejected**, for the same hindsight-leak reason as news-reading (round 9).
8. **UI:** white only, hairlines, ink plus one signal red, words as actions, title + one-line description + value for every metric.

## 3. Decided under delegation (reversible)
- **Round 19:** R19-1 rank-weighted selection, pressure 0.5; R19-2 Life mode as M6b; R19-3 mixed founders; R19-4 out of money = can't post collateral; R19-5 no futures; R19-6 names + comments.
- **Round 18:** D1 10:30 EPT on D−1 for all years; D2 flag the Sunday and the following Monday; D3 labelled placeholder fees.

## 4. Facts measured in the data (obs.)

| Fact | Value |
|---|---|
| Days with DA / RT prices outside the hold-out | 7,512 / 7,507 (only the newest 5 RT days missing: not yet published) |
| History start | 2005-04-01 (2005-03 is a 404): ~21.5 years exist, not 25 |
| Locations ever priced | 5,519 (generators 3,619, hub-type 630, interfaces 110, load zones 1,160) |
| Hours | hour-ending EST all year (24 per day) |
| MCC/MLC components | from 2005-06-16 |
| Trading hubs | CINERGY 2005-04-01 → 2011-12-31; FE 2005-09-01 → 2011-05-31; INDIANA from 2011-03-01; ARKANSAS, LOUISIANA, TEXAS from 2013-12-19; MS from 2017-12-01 |
| CINERGY vs INDIANA, 7,344 overlapping hours | not a rename: DA median abs. difference $0.23/MWh, maximum $17.74 |
| Hub spreads 2019-01 → 2025-09-21 | reproduce Claude Science: 58,944 hours per hub; mean $0.04–0.96; median abs. $2.57–4.73; std $30.2–62.2; excess kurtosis 561–3,322 |
| Hold-out rows in the hub table | 0 |

Script for the CINERGY/INDIANA comparison: the round-20 session ran it inline on `data/store/hub_prices.csv.gz` (pairs of hours where both hubs have a price, 2011-03-01 → 2011-12-31). It moves into a test in M1.

## 5. Still needed from Areeb
- **R1:** MISO's *Market Settlements Rates Factors* file (browser download into `data/inbox/`).
- The rounds 1–16 decision logs and project files, to reconcile the rationale and run the 40 tests.

## 6. Measured vs assumed
- **Measured:** everything in §4; reference metadata; the download log and hashes; the preview page's lack of console errors and network requests (headless Chromium).
- **Assumed:** claims about paper contents marked (memory) [verify] in the rationale; speed and generation estimates; that the pre-2015 `da_lmp` files are ex-post prices [verify].
