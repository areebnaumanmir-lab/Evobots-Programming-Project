# Data sources

Every external source evobots reads: what it is used for, how it is fetched, what is in the repository, and the terms that decide whether it can be bundled (`docs/design_spec.md` §7.9, §7.11). Started in M0 (round 23) with the redistribution check; M1 adds the per-file formats.

Provenance marks (`docs/design_spec.md` §2.2): **(obs.)** = read on the source's own page on the date given, quoted below. **[verify]** = from a secondary source or not yet read in full.

## 1. Sources

| Source | Role | Fetched by | In the repository |
|---|---|---|---|
| MISO market reports, `docs.misoenergy.org/marketreports/` | DA/RT LMP (bot input), DA ex-ante LMP and cleared bids (liquidity, O9) | `tools/fetch_miso_prices.py` (`--report prices`, `--report cleared_bids`) | raw files and the parsed store are git-ignored; `data/manifest.toml` (URL, SHA-256, size, date) and derived statistics in `docs/data/` are committed |
| NWS Point Forecast Matrices via the Iowa Environmental Mesonet (IEM) | weather forecasts (bot input, features 10–16) | `tools/fetch_nws_forecasts.py` | raw text git-ignored; the parsed table is built at M1 |
| IEM ASOS observations | forecast skill (reporting only) | M1 | – |
| EIA Henry Hub spot, WTI spot, EIA-860M | gas features 19–21 (input); oil (reporting); capacity features 17–18 (input) | M1 | – |
| Economic Policy Uncertainty (Baker, Bloom & Davis) | feature 22 (input) | M1 | – |
| Geopolitical Risk (Caldara & Iacoviello) | reporting only | M1 | – |
| World Bank Pink Sheet | global commodity context (reporting only) | M1 | – |
| FRED 3-month T-bill (DTB3), Federal Reserve H.15 | the risk-free rate in fitness (decided round 28) | M1 | – |

## 1b. File formats and readers (M1, round 28)

All series files are downloaded once by `tools/fetch_series.py` into `data/raw/series/<source>/` (git-ignored), named `<download date>_<original name>`, and logged in `data/raw/series/downloads.jsonl` (URL, SHA-256, size, time), from which `data/manifest.toml` is written. Readers live in `src/evobots/data/sources/series.py`; each cuts its series at 2025-09-21 unless given the hold-out accessor's permission.

| Source | File | Layout (obs., round 28) | Reader | Coverage before the cut |
|---|---|---|---|---|
| FRED DTB3 | `fredgraph.csv?id=DTB3` → `DTB3.csv` | header `observation_date,DTB3`; blank value on holidays | `read_fred_dtb3` | 1954-01-04 → 2025-09-19; 5,123 days from 2005-04-01 |
| EIA Henry Hub | `RNGWHHDd.xls` | sheet `Data 1`: row 1 `Sourcekey, RNGWHHD`, row 2 `Date, …`, then Excel serial date and $/MMBtu | `read_eia_daily_spot(path, "RNGWHHD")` | 1997-01-07 → 2025-09-19, 5,444 trading days |
| EIA WTI | `RWTCd.xls` | same layout, key `RWTC`, $/barrel | `read_eia_daily_spot(path, "RWTC")` | 1986-01-02 → 2025-09-19 (minimum −$36.98, 2020-04-20) |
| EPU | `All_Daily_Policy_Data.csv` | header `day,month,year,daily_policy_index` | `read_epu` | 1985-01-01 → 2025-09-21 |
| GPR | `data_gpr_daily_recent.xls` | one sheet; `DAY` as yyyymmdd text, `GPRD`, `GPRD_THREAT`, `GPRD_ACT`, moving averages, `event`, `var_name` | `read_gpr` (three series) | 1985-01-01 → 2025-09-21 |
| World Bank Pink Sheet | `CMO-Historical-Data-Monthly.xlsx` (URL changes monthly; read from the commodity-markets page) | sheet `Monthly Prices`: four title rows, names in row 4, units in row 5, then `1960M01` rows; missing values printed `…` | `read_pink_sheet` (US, Europe and Japan gas, Brent, Australian coal; cut at 2025-08, the last month ending before the hold-out) | 1960-01 → 2025-08; US gas for 2022-08 is $8.79, against $8.81 from EIA's daily Henry Hub |
| EIA-860M | newest `{month}_generator{year}.xlsx` (September 2026 on 2026-10-28; superseded months redirect to the archive) | reader at M1 | – | – |

## 2. Terms of use and what they allow (checked 2026-10-24)

| Source | Terms | Status | May it be bundled? |
|---|---|---|---|
| **EIA** | "U.S. government publications are in the public domain and are not subject to copyright protection." "You may use and/or distribute any of our data, files, databases, reports …"; "you should use an acknowledgment, which includes the publication date", e.g. "Source: U.S. Energy Information Administration (Oct 2008)". The EIA logo and third-party material are excluded. | (obs., `eia.gov/about/copyrights_reuse.php`) | **yes**, with the acknowledgment and download date |
| **NWS** | NWS information is "in the public domain, unless specifically noted otherwise, and may be used without charge for any lawful purpose". Conditions: don't claim it as your own; don't present modified content as official; don't imply NOAA/NWS endorsement; don't use the NWS name or logo; works consisting predominantly of NWS material must say which NWS material they include. | (obs., `weather.gov/disclaimer`) | **yes**, labelled as derived from NWS forecasts and not official |
| **IEM** (the archive the NWS text comes from) | "The materials found on this website are in the public domain and may be used freely by anyone for any lawful purpose." "Attributing the Iowa Environmental Mesonet of Iowa State University would be appreciated." | (obs., `mesonet.agron.iastate.edu/disclaimer.php`) | **yes**, crediting IEM |
| **EPU** | "This work is licensed under a Creative Commons Attribution 4.0 International License"; "© 2012-2018 by Economic Policy Uncertainty". | (obs., `policyuncertainty.com` home page) | **yes**, under CC BY 4.0, crediting Baker, Bloom & Davis and the site |
| **GPR** | "All the material in this webpage, including interactive visualizations and code, are completely open access under the Creative Commons BY license. You have the permission to use, distribute, and reproduce these in any medium, provided the source and authors are credited." Cite as Caldara & Iacoviello (2022), *American Economic Review* 112(4), 1194–1225, plus the website and download date. | (obs., `matteoiacoviello.com/gpr.htm`) | **yes**, with that citation |
| **World Bank Pink Sheet** | The Commodity Markets page links, under "Using this Data", to the World Bank's summary terms. These say data are "under a Creative Commons Attribution 4.0 International License" unless "indicated otherwise in the data or indicator metadata", and ask for attribution as "The World Bank: Dataset name: Data source". The monthly file is `CMO-Historical-Data-Monthly.xlsx` on `thedocs.worldbank.org`. | (obs., round 27: worldbank.org/en/research/commodity-markets and data.worldbank.org/summary-terms-of-use) | **not for now** (round 28): the downloaded workbook (updated 2026-10-02) carries no licence text, and its Description sheet names Bloomberg Finance L.P. and Thomson Reuters Datastream among the sources, which may be the "indicated otherwise" case. It is reporting only, so it stays private until the World Bank confirms CC BY for these series [verify] |
| **FRED (DTB3)** | The series page labels DTB3 "Public Domain: Citation Requested". FRED's legal page: "These series may be under copyright or in the public domain and may be used without permission, provided you do not engage in any prohibited use. When using, please cite the data source and acknowledge that you obtained the data" from FRED. Prohibited uses include scraping that is "disruptive, or adversely impacts the stability" of the service. | (obs., round 28: `fred.stlouisfed.org/series/DTB3` and `/legal/`) | **yes**, cited as "Board of Governors of the Federal Reserve System (US), 3-Month Treasury Bill Secondary Market Rate, Discount Basis [DTB3], retrieved from FRED, Federal Reserve Bank of St. Louis", with the download date |
| **MISO** | Read in full on 2026-10-24 from the text of MISO's *Privacy Notice and Terms of Use* (`misoenergy.org/meet-miso/legal-and-privacy/`), pasted by Areeb because the page refuses scripts. Two clauses matter. **Redistribution:** "You are not permitted to modify, publish, transmit, participate in the transfer or sale of, reproduce, create derivative works of, distribute, publicly perform, publicly display or in any way exploit any of the materials or content on this Website or the App in whole or in part." **Automated access:** "You agree not use any automated means, including, without limitation, agents, robots, scripts, or spiders, to access, monitor, or copy any part of this Website or the App." The terms also say some services "may be subject to additional posted conditions", which prevail in a conflict; whether the market-report pages or the Data Exchange carry such conditions was not checked then. Round 27: searching for such conditions found none. MISO's Data Exchange information sheet says the public pricing reports stop updating from 2025-12-12 and "remain available on the public website until the end of their retention", and states no licence (search summary). The only "personal and non-commercial use" terms found belong to an unrelated UK company also called Miso (Dotted Eyes Ltd, misoportal.com), not to the grid operator. | (obs., text supplied by Areeb) | **no**: build locally, never redistribute (round 25), with a user switch for the day MISO grants permission. **Scripted downloading is also in question: see §5** |

## 3. Consequences for the bundle (decided round 25)

- **The repository is private** (obs., 2026-10-24). No MISO price file or parsed price table is committed: `data/raw/`, `data/store/` and `data/holdout/` are git-ignored.
- **Committed MISO-derived files** are statistics and aggregates, not price series:
  - hub spread statistics;
  - the trailing 1-in-100-day loss;
  - coverage counts;
  - the daily full-size benchmark P&L, which sums (DA − RT) × cap over 8 hubs and 24 hours (`docs/data/benchmark_full_size_daily_pnl.csv`).
- **MISO's terms also forbid "derivative works".** These files are for private use in a private repository. If the repository is ever made public, every MISO-derived file in `docs/data/` (and the benchmark fixture the tests read) must be reviewed first. The `data_sources.md` list above is the checklist.
- **Decided (round 25):**
  1. **MISO data: build locally, never redistribute.** Each user makes their own copy. Your own offline bundle is unaffected.
  2. **A user switch,** `is_miso_redistribution_allowed`, default **false**, arrives with the bundle builder (M1). When false, the builder leaves MISO-derived files out of any shareable bundle. Flip it only with MISO's written permission.
  3. **The other sources** (NWS/IEM, EIA, EPU, GPR) may be shared with their acknowledgments.
- **Acknowledgments** go in the app's About text and the README at M1.5:
  - EIA (with download date);
  - "derived from National Weather Service forecasts, archived by the Iowa Environmental Mesonet, Iowa State University";
  - EPU (CC BY 4.0) and GPR (CC BY, with the AER citation);
  - FRED DTB3 (the citation above);
  - MISO as the source of price data.

## 4. MISO's "no automated means" clause (round 25)
- **What was done before the clause was read:**
  - `tools/fetch_miso_prices.py` downloaded the price archive (3,208 files, round 20) and 1,119 days of cleared bids with ex-ante prices (round 23);
  - `tools/fetch_rule_documents.py` and the probe scripts made smaller requests to `cdn.misoenergy.org` and `docs.misoenergy.org` (round 18).

  All were polite (≤ 2 parallel requests, 0.5 s spacing, identified by a User-Agent with a contact email), but they were scripts.
- **Whether `docs.misoenergy.org`, which serves the market-report files linked from the website, is part of "this Website"** is not stated in the terms. The safe reading is yes.
- **Stopped on 2026-10-24** when the clause was read: the cleared-bids fetch, at operating day 2026-01-23. No further scripted request is made to any MISO host until Areeb decides. The weather fetch (IEM, public domain) continues.
- **Decided by Areeb (round 26):** keep everything already downloaded, for private use only. Areeb's reason: "the fine print says that data is only restricted if you're using it for explicitly commercial purposes".
  - The Terms of Use text Areeb pasted in round 25 contains no commercial/non-commercial distinction (obs.: no occurrence of "commercial" in it).
  - The commercial-only reading may come from other fine print, such as conditions posted on the market-reports pages, which the terms say prevail. That source is not yet in the project; round 27's search found no such clause for MISO (see the MISO row above). Areeb may paste or link it.
  - **Scripted downloading stays paused** until that source is recorded, or Areeb explicitly says to resume. Nothing before M9 needs new MISO downloads.
- **Areeb's note (round 32):** "It states that the use of MISO data for non-commercial purposes is fine as long as credit is given."
  - Recorded in his words; the text it quotes is still not in the project. It confirms the round-26 position: private, non-commercial use with credit (the README's acknowledgments carry the credit line).
  - It speaks to **use**, not to **access**. The Terms of Use separately forbid "any automated means … to access, monitor, or copy any part of this Website", so scripted MISO downloads stay off. Paper trading (M9) reads MISO files that Areeb saves into `data/inbox/` by hand.

## 5. Measured vs assumed
- **Measured:** MISO's Terms of Use (full text, supplied by Areeb); the EIA, NWS, IEM, EPU and GPR statements above, read on their pages on 2026-10-24; the World Bank catalog licence for the Global Economic Monitor; the repository's visibility.
- **Assumed or unread:**
  - MISO's additional posted conditions for market reports or the Data Exchange, if any;
  - the Pink Sheet's licence;
  - that a private, single-user build is personal use under MISO's terms.
