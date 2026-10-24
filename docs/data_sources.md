# Data sources

Every external source evobots reads: what it is used for, how it is fetched, what is in the repository, and the terms that decide whether it can be bundled (`CLAUDE.md` §7.9, §7.11). Started in M0 (round 23) with the redistribution check; M1 adds the per-file formats.

Provenance marks (`CLAUDE.md` §2.2): **(obs.)** = read on the source's own page on the date given, quoted below. **[verify]** = from a secondary source or not yet read in full.

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

## 2. Terms of use and what they allow (checked 2026-10-24)

| Source | Terms | Status | May it be bundled? |
|---|---|---|---|
| **EIA** | "U.S. government publications are in the public domain and are not subject to copyright protection." "You may use and/or distribute any of our data, files, databases, reports …"; "you should use an acknowledgment, which includes the publication date", e.g. "Source: U.S. Energy Information Administration (Oct 2008)". The EIA logo and third-party material are excluded. | (obs., `eia.gov/about/copyrights_reuse.php`) | **yes**, with the acknowledgment and download date |
| **NWS** | NWS information is "in the public domain, unless specifically noted otherwise, and may be used without charge for any lawful purpose". Conditions: don't claim it as your own; don't present modified content as official; don't imply NOAA/NWS endorsement; don't use the NWS name or logo; works consisting predominantly of NWS material must say which NWS material they include. | (obs., `weather.gov/disclaimer`) | **yes**, labelled as derived from NWS forecasts and not official |
| **IEM** (the archive the NWS text comes from) | "The materials found on this website are in the public domain and may be used freely by anyone for any lawful purpose." "Attributing the Iowa Environmental Mesonet of Iowa State University would be appreciated." | (obs., `mesonet.agron.iastate.edu/disclaimer.php`) | **yes**, crediting IEM |
| **EPU** | "This work is licensed under a Creative Commons Attribution 4.0 International License"; "© 2012-2018 by Economic Policy Uncertainty". | (obs., `policyuncertainty.com` home page) | **yes**, under CC BY 4.0, crediting Baker, Bloom & Davis and the site |
| **GPR** | "All the material in this webpage, including interactive visualizations and code, are completely open access under the Creative Commons BY license. You have the permission to use, distribute, and reproduce these in any medium, provided the source and authors are credited." Cite as Caldara & Iacoviello (2022), *American Economic Review* 112(4), 1194–1225, plus the website and download date. | (obs., `matteoiacoviello.com/gpr.htm`) | **yes**, with that citation |
| **World Bank Pink Sheet** | Data-catalog datasets are typically "Creative Commons Attribution 4.0" (obs. for the Global Economic Monitor entry). The Pink Sheet's own catalog entry was not reached; a third-party aggregator lists it as CC BY 4.0. The World Bank's general (non-dataset) terms allow only non-commercial use and no derivative works. | **[verify]** | **not until checked**; reporting only, so it can stay a download-on-demand item |
| **MISO** | MISO's Legal and Privacy page (`misoenergy.org/meet-miso/legal-and-privacy/`) returns HTTP 403 to scripts (Cloudflare), so it was **not read**. A search-index summary of it says website materials are protected by MISO's copyrights, users may not "modify, publish, transmit, reproduce, create derivative works of, distribute …" them, and access "does not confer any license". Whether that covers the market-report files, and whether the Data Exchange terms differ, is unknown. | **[verify]**: open the page in a browser | **not for others** until checked (below) |

## 3. Consequences for the bundle (proposal for the end-of-M0 check-in)

- **The repository is private** (obs., 2026-10-24). No MISO price file or parsed price table is committed: `data/raw/`, `data/store/` and `data/holdout/` are git-ignored.
- **Committed MISO-derived files** are statistics and aggregates, not price series:
  - hub spread statistics;
  - the trailing 1-in-100-day loss;
  - the daily full-size benchmark P&L, which sums (DA − RT) × cap over 8 hubs and 24 hours (`docs/data/benchmark_full_size_daily_pnl.csv`).

  The last is the closest to a derived series. It stays private with the repository.
- **Proposal:**
  1. Treat MISO data as **"build locally, never redistribute"** until Areeb reads MISO's terms in a browser. `evobots data build --download` makes each user's own copy from MISO's public server, so the offline bundle on Areeb's own machine is unaffected.
  2. The NWS/IEM, EIA, EPU and GPR parts of the bundle may be shared with their acknowledgments.
  3. If the repository or a bundle is ever made public, decide first whether the benchmark P&L series may go with it. If not, regenerate it locally from the store as the tests' fixture.
- **Acknowledgments** go in the app's About text and the README at M1.5:
  - EIA (with download date);
  - "derived from National Weather Service forecasts, archived by the Iowa Environmental Mesonet, Iowa State University";
  - EPU (CC BY 4.0) and GPR (CC BY, with the AER citation);
  - MISO as the source of price data.

## 4. Measured vs assumed
- **Measured:** the EIA, NWS, IEM, EPU and GPR statements above, read on their pages on 2026-10-24; the World Bank catalog licence for the Global Economic Monitor; the repository's visibility.
- **Assumed or unread:**
  - MISO's terms (page blocked to scripts; only a search-index summary was seen);
  - the Pink Sheet's licence;
  - that a private, single-user build is personal use under MISO's terms.
