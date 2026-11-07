# How to change the app's look and pages

One file per kind of change (`docs/design_spec.md` §14.5). Start the app with `uv run evobots serve` and reload the page after each edit.

| Change | Edit | Example |
|---|---|---|
| A colour | `src/evobots/app/static/theme.css`, the `--colour-…` variables at the top | `--colour-signal: #a3271f;` is the losses colour |
| The font or sizes | the same file, `--font-family`, `--font-size-…` | `--font-size-body: 15px;` |
| Spacing | the same file, `--space-1` … `--space-5` | |
| A label or a page's text | `src/evobots/pages.py`, in that page's function (`home_page`, `trader_page`, …) | `section("Status", "What this copy … has done.", …)` |
| The navigation | `src/evobots/app/pages.toml` | add `{ title = "My page", path = "/mine" }` |
| A new page | a `mine_page()` function in `pages.py`, `"mine": "mine_page"` in `service.PAGE_BUILDERS`, the path in `pages.toml`, and a route (pages without arguments: add the name to `SIMPLE_PAGES` in `server.py`) | |
| A chart | `src/evobots/charts.py` (`line_chart`, `bar_chart`, `grid_map`); use it from a page as `section(…, "chart", svg=…)` | |
| How a kind of section is drawn | `src/evobots/app/templates/page.html` | |

Check: `uv run pytest tests/test_app_pages.py` loads every page in a headless browser with the internet blocked and saves screenshots to `tests/screenshots/`.
