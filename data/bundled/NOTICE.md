# Data bundled with evobots: sources and conditions of reproduction

These files let evobots run on real data straight after download. On first start, `evobots` copies them into `data/store/` and `data/raw/series/` (`src/evobots/data/bundled.py`). Nothing is downloaded.

## MISO prices: `store/hub_prices.csv.gz`
- **Source:** Midcontinent Independent System Operator, Inc. (MISO), public market reports at misoenergy.org:
  - day-ahead LMPs: the `da_lmp` reports before 2015-03-01, ex-post after;
  - real-time final LMPs.
- **Contents:**
  - per day, hour and trading hub: the LMP and its congestion and loss components, as built by `evobots data build --stage A`;
  - from 2005-04-01 to 2025-09-21, plus forward days from 2026-09-22;
  - nothing from the sealed year 2025-09-22 → 2026-09-21.
- **Permission:** reproduced with MISO's written permission to use MISO public trading data in this programming project, received by email on 2026-11-06. MISO set two conditions: explicit acknowledgement of the source, and that the conditions of reproduction are made clear to others. This notice is how both are met.

**If you reproduce, share or reuse these MISO files:**
1. **Acknowledge the source** explicitly: "Price data: Midcontinent Independent System Operator, Inc. (MISO), public market reports, misoenergy.org."
2. **The permission was given to this project.** Any other use is governed by MISO's Terms of Use, which otherwise prohibit publishing or redistributing MISO's content, so ask MISO for permission for your own use.
3. **Keep this notice** with the files.

## Other sources
| File | Source | Terms |
|---|---|---|
| `store/hub_forecasts.csv.gz` | National Weather Service Point Forecast Matrices, archived by the Iowa Environmental Mesonet, Iowa State University | public domain; derived from NWS forecasts (not an official NWS product, no NWS endorsement); attributing IEM is appreciated |
| `series/eia_henry_hub/` | U.S. Energy Information Administration, Henry Hub natural gas spot price (RNGWHHD) | public domain; acknowledge "Source: U.S. Energy Information Administration" with the download date (2026-10-28) |
| `series/epu/` | Baker, Bloom & Davis, US Economic Policy Uncertainty index, policyuncertainty.com | CC BY 4.0; credit the authors and the site |
| `series/fred_dtb3/` | Board of Governors of the Federal Reserve System (US), 3-Month Treasury Bill Secondary Market Rate, Discount Basis [DTB3], retrieved from FRED, Federal Reserve Bank of St. Louis | cite as given |
| `series/gpr/` | Caldara & Iacoviello (2022), "Measuring Geopolitical Risk", *American Economic Review* 112(4), matteoiacoviello.com | CC BY; cite the paper |

The full record of every source and its terms is in `docs/data_sources.md`.
