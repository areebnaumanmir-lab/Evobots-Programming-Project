# Round 27: every [verify] marker checked against a primary source

Date: 2026-10-24. Areeb: "Continue the download and independently verify all these markers and facts only stopping to ask me by presenting many choices to chose from them, including a recommended one." Areeb also asked what the Rates Factors file is (§5).

**Method:**
- Each marker was checked against the primary source where one was reachable:
  - Crossref, arXiv, Semantic Scholar and the GP Bibliography for literature;
  - the papers' own PDFs;
  - EIA, FRED, the World Bank, the GPR and EPU sites;
  - the market monitor's reports (Potomac Economics);
  - copies of MISO manuals filed with state commissions;
  - our own downloaded data.
- **MISO's own website was not scripted** (rounds 25–26); search-engine summaries of MISO pages are labelled as such.
- The scripts and downloaded copies are in the session scratchpad; the SHA-256 of each document quoted is given below.

## 1. Results by group (the register's groups, `docs/verify_register.md`)

| Group | Before | Result |
|---|---|---|
| K library licences | 7 | **all checked** on PyPI and in the licence files: numba BSD-2-Clause, xlrd BSD-3-Clause, Jinja2 BSD-3-Clause, the rest as recorded (`dependencies.md`) |
| L literature | 36 | **all checked**. Every citation resolves to a primary record; content claims were checked against abstracts or papers. Corrections: below |
| O ORFE citations and facts | 10 | **all checked**. Citations resolved, plus the 2014 polar vortex dates and battery efficiency (below) |
| A rules and data details | 26 | **checked** where a source exists. Remaining: 3, below |
| R measurable from our data | 3 | 2 done in round 26; 1 (latest forecast issue) waits for the M1 parser |
| F fee and RSG rates | 6 | **open**: second-hand only (question 1) |
| P published MPD | 5 | **open**: MISO's method can't be reproduced (below; question 1) |

## 2. Corrections found
1. **Luke & Spector 1997** (crossover vs mutation) "was marred by statistical flaws" in the authors' own words. Cite their 1998 revision instead (`luke1998`).
2. **"Angeline 1997, *Subtree crossover: building block engine or macromutation?*"** has no Crossref record. The same author's Crossref-listed paper of the same year, *Comparing subtree crossover with macromutation* (doi 10.1007/BFb0014804), makes the point and is now cited.
3. **Revisions:**
   - **GPR:** the briefing said past revisions are unobservable. In fact GPR archives every daily vintage.
   - **EPU:** EPU revises the previous 30 days daily and keeps no vintages. So our EPU history is revised data, a small look-ahead risk for the `epu` feature, covered by the existing hindsight check (§8).
4. **Battery round-trip efficiency:** the briefing assumed 0.85. EIA measured **82 %** for the US battery fleet in 2019 (Today in Energy, 2021-02-12).
5. **Barber et al.'s 44 / 24 / 15 % survival** covers *all* day traders with ≥ 10 days of trading, not only losers (2017 working paper). The L3 calibration (M5) must say so.
6. **Bhattacharyya et al. 2002** reports "more robust performance", not better out-of-sample profit. The rationale now says that.
7. **The deflated Sharpe ratio's title** was incomplete in `references.csv` ("… Backtest Overfitting and Non-Normality"); that is why its DOI check failed.

## 3. Facts confirmed (selection; full list in the edited documents)

| Fact | Source (read 2026-10-24) |
|---|---|
| Virtual bids due **10:30 EPT** on D−1; DA results 13:30 EPT; **DA ex-post LMPs 16:30 EPT** | MISO BPM-002-r19 Exhibit 7-1, effective 2018-10-15 (copy filed with the Missouri PSC; SHA-256 `77907d72…`) |
| MISO's reference bus is load-weighted ("fixed market Load distributed Reference Bus") | BPM-002-r23 §5, effective 2022-09-30 (copy filed with the Kentucky PSC; `9e0954ac…`) |
| $1,000/MWh soft and $2,000/MWh hard energy offer caps | the IMM's 2023 report fn. 40; BPM-002-r23 |
| No MW volume limit on virtuals found. The IMM **screens price-insensitive virtuals** that cause congestion divergence | the IMM's 2024 report, pp. 32–33 (`cfad6625…`) |
| Real-time RSG averaged **$0.11/MWh** in 2024 (DDC rate, excluding CMC and pass-2 RSG) | the IMM's 2024 report p. 33; 2023 appendix fn. 9 |
| Bid curves carry up to 9 blocks; bids use all 9 | our cleared-bids file for 2025-01-15 (obs.) |
| `N10D` = "Number of articles (10 recent newspapers, 1985-)" | the GPR file's own labels |
| EIA-860M estimates "will be corrected without specific acknowledgment … in subsequent month's inventory"; monthly files archived from 2015-01 | EIA's EIA-860M page |
| World Bank data: CC BY 4.0 by default | data.worldbank.org summary terms |
| 3-month T-bill (FRED DTB3): keyless CSV, 1954 → 2026-10-22; 5,123 trading days in 2005-04-01 → 2025-09-21 (218 gaps are holidays) | FRED (`3437358a…`) |
| 2014 polar vortex: **2014-01-06 → 07** (hub mean RT $189.9/MWh on the 7th, peak $1,966); second spell 2014-02-10 → 12 | our hub table (obs.) |
| NERC's list keeps a Sunday holiday on the Sunday (Independence Day, Sunday 2027-07-04, no Monday substitute) | PJM's *NERC 2027 Off-Peak Days* |
| Neely, Weller & Dittmar 1997: "strong evidence of economically significant out-of-sample excess returns"; their 1999 intraday study: none "when realistic transaction costs and trading hours are taken into account" | the working papers' abstracts |
| Cully & Demiris's curiosity score: +1 when a child enters the archive, −0.5 otherwise | arXiv 1708.09251 §III-B3 |
| Getmansky, Lo & Mei: managed-futures attrition 14.4 %/year | abstract on Lo's MIT page |

## 4. MISO's MPD: the method can't be reproduced
- **Attachment L:** "the highest differential between the Day-Ahead and Real-Time Locational Marginal Prices at the 50th percentile over the previous twelve (12) months".
- **Tested reading:** the highest, over the 24 hours of the day, of the median |DA − RT| across all nodes over April → March (`tools/compute_mpd_history.py`, `docs/data/mpd_history.csv`).
- **Against MISO's published values:**
  - **for 2021** it gives $4.87 against MISO's **$4.89**;
  - **for 2006** it gives $18.54 against **$13.33**;
  - **for 2016** it gives $3.59, lower than 2021's, although MISO called 2021 "the lowest level since shortly after MISO's Virtual Market began".
- **So this is not MISO's method,** and the 2021 near-match is a coincidence. The published series isn't available outside MISO's website.
- **Effect:** none at Stage A, where collateral ($22k at full size) is far below equity. At stages D and C the Virtual MWh Limit can bind. **Question 1.**

## 5. What the Rates Factors file is (Areeb asked)
- **What it is:** a spreadsheet MISO publishes on its Market Settlements page, listing the per-MWh rates it charges each month and hour. It covers the administration fees (Schedules 17 and 24) and the uplift rates charged to virtual traders (the RSG rates: DDC, CMC, day-ahead RSG).
- **What it would give us:** the exact cost history for 2005–2026, so the simulator charges each historical trade what MISO actually charged.
- **Without it:**
  - the fee rates are the few months quoted in search results (about $0.09/MWh in 2026);
  - RSG can come from the market monitor's annual averages (e.g. $0.11/MWh in 2024), but not hour by hour.
- It is on MISO's website behind a browser check, so a person has to download it. **Question 1.**

## 6. Questions put to Areeb (multiple choice, recommendation first)
1. How to settle the three MISO-only items (fee rates, RSG history, MPD history).
2. The risk-free rate source.
3. The Sunday-holiday rule (keep D2 or follow NERC strictly).
4. The battery round-trip efficiency default.

## 7. Measured vs assumed
- **Measured:** everything in §§1–4 marked with a source or (obs.).
- **Assumed:**
  - that search-engine snippets of MISO pages reflect the pages (fee rates);
  - that BPM revisions r19/r23, copies filed with state commissions, match MISO's published versions.
