# How-to guides

Short recipes for common changes (`docs/design_spec.md` §14.2). Each says which file to edit and how to check the change.

- **[Change the app's look and pages](change_the_ui.md).**
- **Change the default capital.** Open the Capital page, move the sliders, and choose "Save as my defaults". This writes `config/capital.local.toml`. Or edit `[capital]` in `configs/10_miso_hubs.toml` (`src/evobots/config/capital.py` holds the bounds). Check: `uv run evobots capital`.
- **Add a feature.**
  1. Add a `Feature(...)` to `FEATURES` in `src/evobots/features/catalogue.py`.
  2. Compute it in `src/evobots/features/store.py`, through its publication rule: what was public at 10:30 on D−1.
  3. Add a case to the corruption test in `tests/test_features.py`.
  4. Regenerate `docs/features.md` with `uv run python tools/build_feature_docs.py`.
  
  Keep the count at 25 unless Areeb agrees to a swap (§17.2).
- **Add a GP primitive.**
  1. Add a node dataclass in `src/evobots/bots/grammar.py`, with its unit rule in `unit_of` and `check`, and its forms in `to_data`/`from_data`, `display`, `python_source`/`tree_from_ast` and `evaluate_uncached`.
  2. Add the matching helper to the generated file's runtime (`RUNTIME` in `src/evobots/bots/source.py`).
  3. Offer it in `src/evobots/bots/random_trees.py`.
  
  Check: `uv run pytest tests/test_traders.py`. The equivalence test must stay exact.
- **Add a career preset.** Add a `CareerSettings(...)` to `PRESETS` in `src/evobots/career/model.py`. Check: `uv run pytest tests/test_career.py`.
- **Add a chart.** See the chart row of [change the UI](change_the_ui.md).
- **Add a data source.**
  1. Write a reader in `src/evobots/data/sources/`, with a hold-out guard like `series_from_observations`.
  2. Add its publication lag to `PUBLICATION_LAG_DAYS_BY_SERIES`.
  3. Record its URL and terms in `docs/data_sources.md` and its files in `data/manifest.toml`.
  
  Keyless sources only (§18).
- **Run offline.** After the first install, everything runs offline: `uv run evobots serve`, `evobots run`, `evobots report`. Instead of `--download`, drop files into `data/inbox/` (paper trading) or `data/raw/…`.
- **Export a bot.**
  - `uv run evobots export-bot runs/R12 R12-184213` writes a standalone, standard-library `trader_R12-184213.py`.
  - Run it with `python trader_R12-184213.py --inputs day.csv`.
  - The Trader page's "Download code" gives the same file.
