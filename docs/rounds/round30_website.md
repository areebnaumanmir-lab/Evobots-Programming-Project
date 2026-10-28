# Round 30: the website on GitHub Pages

Date: 2026-10-28. Areeb: "can you also make it a website people can open directly from github".

## 1. How it works
- **Static site.** GitHub Pages serves static files only, so the website runs evobots' own Python in the visitor's browser: Pyodide 0.27.7 (Python 3.12 compiled to WebAssembly), with numpy and Jinja2, in a Web Worker.
- **One source of results.** The worker calls `src/evobots/web.py`, which reuses `evobots.service.Service` and the app's `results.html` template. The website and the local app therefore show the same numbers, charts and wording. The JavaScript (`static/site.js`, `static/worker.js`) only passes messages and saves downloads; no formulas in JavaScript (§14.5).
- **Self-contained.** `tools/build_website.py` renders the page once from the app's template (website mode) and adds:
  - the scripts and theme;
  - evobots' source as `evobots_package.zip`;
  - the whole-app zip;
  - the Pyodide files, pinned and checked by SHA-256.

  Everything is served from the site: no CDN at run time (§14.4). The browser test blocks every non-local request and sees none.
- **Publishing.** `.github/workflows/pages.yml` builds and publishes the site on every push to `main` (or by hand).

## 2. Data
- **Demo data only.** MISO's terms forbid publishing its data, so the website starts on synthetic prices.
- **A planted, labelled pattern** gives the search something to find: DA above RT by $2/MWh in hours 7–22, like MISO's real day-ahead premium. In the demo the always-INC founder finds it.
- **Your own data.** A visitor who built the MISO hub table with the downloadable app can load it on the page. It is read inside their browser and never uploaded.

## 3. Measured (headless Chromium, the internet blocked)
- Python ready: 4.4–6.8 s (from localhost; on the internet the first visit also downloads about 17 MB).
- A 200-trader search: 7–8 s in the browser.
- Best-bot download, refine, no console errors, no external requests.
- `tests/test_website.py` repeats this with 100 traders.

## 4. What Areeb has to do (repository settings Claude can't change)
1. **Visibility.** GitHub Pages needs a public repository, or a paid plan for a private one. This repository was private when last checked (round 25).
   - Making it public also publishes `docs/`, including the MISO-derived summary tables in `docs/data/` (`docs/data_sources.md` §3 asks for a review first).
   - The website itself carries no MISO data.
2. **Turn Pages on:** Settings → Pages → Source: "GitHub Actions".
3. **Merge to `main`.** This branch merges into `main`, and the workflow publishes the site.

## 5. Measured vs assumed
- **Measured:** the timings and checks above; the pinned files' SHA-256 values; Pyodide's licence (MPL-2.0, from its package metadata).
- **Assumed:** that GitHub Pages serves `.wasm` files with the right type (it does for standard static hosting; verify on the first deploy) [verify].
