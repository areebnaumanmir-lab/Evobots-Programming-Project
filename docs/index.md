# evobots documentation

The documentation follows the four Diátaxis kinds (`docs/design_spec.md` §14.2). Planned documents are listed without links until they exist.

## Tutorial (learning by doing)
- `tutorial.md`: install, build the data, run a short evolution, read a report card, export a trader. Stub at M1.5; finished and tested on a clean machine at M9.

## How-to guides (a task, step by step)
- `how_to/`, from M1.5: change default capital; add a feature; add a GP primitive; add a career preset; change colours and fonts; add a page; add a chart; add a data source; run offline; export a bot.
- Available now:
  - **see the capital settings:** `python -m evobots.cli capital [configs/10_miso_hubs.toml] [--starting-capital 2000000 …]`;
  - **explore them in a browser:** open `tools/capital_explorer.html`, rebuilt by `python tools/build_capital_explorer.py`;
  - **download the data:** `tools/fetch_miso_prices.py`, `tools/fetch_nws_forecasts.py` (see [data_sources.md](data_sources.md)).

## Reference (facts to look up)
- [config_reference.md](config_reference.md): every configuration key.
- [glossary.md](glossary.md): every term, one definition each.
- [data_sources.md](data_sources.md): sources, terms of use, what may be bundled.
- [data_coverage.md](data_coverage.md): what the downloaded MISO archive covers.
- [dependencies.md](dependencies.md): every library, its licence and purpose.
- [references.md](references.md): the literature, with how each citation was checked.
- Planned: a symbol index generated from docstrings (`reference/`).

## Explanation (why things are as they are)
- [market_rules.md](market_rules.md): how MISO's virtual market works, with sources.
- [maths.md](maths.md): every formula, with a worked example, its function and its test.
- [explanations/lmp_from_opf.md](explanations/lmp_from_opf.md): where locational prices come from (O0).
- [capital_sizing.md](capital_sizing.md): the evidence behind the capital defaults.
- [design_rationale.md](design_rationale.md): the logic behind every decision.
- [decisions_log.md](decisions_log.md) and the round docs in `rounds/`: what was decided, when and by whom.
- [change_ledger.md](change_ledger.md): one row per change.
- Planned: `features.md` (M2), `architecture.md` (M1.5), `qd_explained.md` (M6), `report_card.md` (M7).
