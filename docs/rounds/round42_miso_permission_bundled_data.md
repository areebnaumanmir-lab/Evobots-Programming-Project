# Round 42: MISO's written permission, and real data in every download

Date: 2026-11-07.

## The permission
On 2026-11-06 the MISO Help Email team replied to Areeb (text supplied by Areeb):

> "We confirm that you can use MISO public trading data in your programming project provided that explicit acknowledgement is made clear of the source and the further conditions of reproduction are elucidated to others."

This changes round 25's decision ("build locally, never redistribute"), which rested on MISO's general Terms of Use. Those terms prohibit publishing MISO content. The written permission is specific to this project.

## What changed
- **The switch:** `configs/10_miso_hubs.toml` now has `is_miso_redistribution_allowed = true`, with the permission cited beside it. The code default stays false, so a copy used for anything else is safe by default.
- **What `data/bundled/` holds (committed):**
  - **the MISO hub price table:** 2005-04-01 → 2025-09-21, plus forward days from 2026-09-22; checked to contain no day of the sealed year;
  - **the parsed weather forecasts:** NWS via IEM;
  - **the newest series files:** Henry Hub (EIA), EPU, DTB3 (FRED) and GPR.
- **The notice:** `data/bundled/NOTICE.md` states the source and MISO's permission, and the conditions of reproduction for anyone who reuses the files. It also gives each other source's terms.
- **Installing it:** `evobots.data.bundled.install_bundled_data` runs before every command except `capital` and `data`, and copies the bundled files into `data/store/` and `data/raw/series/`.
  - A store already built on the machine, or an imported data pack, always wins.
  - So a fresh download runs on real MISO data from the first start, with no steps.
- **The app's "Download the whole app" zip** includes the bundled data while the switch is on. With the switch off, it leaves every MISO file out, as before.
- **Docs:** the README (quick start, real data, acknowledgments) and `docs/data_sources.md` (the MISO row and §3) record the permission and its conditions.

## Not changed
- **The sealed year** is still not in any bundle; only the final-test path reads it.
- **No automated MISO downloads:** the permission covers using the data, not scripted access to MISO's site.
- **The website (changed later in this round, at Areeb's request):**
  - `tools/build_website.py` copies the hub table and `NOTICE.md` into the site's `data/` while the switch is on;
  - the browser loads the table at start-up, about 35 MB on a first visit with Python;
  - the page credits MISO and points to the notice;
  - it falls back to demo prices if the table can't be loaded.
  - **Checked:** the website's browser test, with the internet blocked, loads the table, shows the MISO line and runs a 100-trader search, all in 16 s.

## Checks
- **A fresh copy** of the code, with no store, started on MISO data by itself (round 42 check below).
- **Tests:** the app zip with the switch on and off; the switch and the permission recorded together; the installer's doctest; the fast suite.
