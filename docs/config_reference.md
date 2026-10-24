# Configuration reference

Every TOML key: meaning, unit, default, bounds, who sets it (`CLAUDE.md` §13.1) and its source. Loading order: code defaults < the TOML file < command-line flags (`evobots.config.load_capital`).

## `[capital]` (`configs/10_miso_hubs.toml`)

| Key | Meaning | Unit | Default | Bounds | Set by | Source |
|---|---|---|---|---|---|---|
| `starting_capital_usd` | money the trader starts with | USD | 1,500,000 (final default, round 25) | 250,000–5,000,000 | your choice: change it in the TOML, with `--starting-capital`, or (from M1.5) on the Capital page | [capital_sizing.md](capital_sizing.md) §6 |
| `daily_risk_budget_fraction` | share of equity a 1-in-100 day may cost; the leverage knob | fraction | 0.02 | 0.005–0.05 | your choice | §4 |
| `credit_share_fraction` | share of capital pledged to MISO as collateral; sets the Virtual MWh Limit | fraction | 0.25 | 0.05–0.80 | your choice | §7 |
| `max_mw_per_hub_hour` | absolute cap per hub-hour | MW | 5.0 | 0.1–50 | your choice | §3 |
| `liquidity_share_fraction` | cap as a share of the hub's median cleared virtual MW | fraction | 0.05 | 0–0.25 | your choice | §3 |
| `ruin_floor_fraction` | optional relative capital floor (career layer L1) | fraction of starting capital | off | 0–0.9 | your choice | §6b; off by default since round 19 |
| `ruin_floor_usd` | optional absolute capital floor (career layer L1); must leave ≥ 10 % headroom | USD | off | – | your choice | §6b |

**Not settings** (computed; shown read-only):
- **From market data:** the hub medians of cleared virtual MW (`docs/data/hub_volume_stats.csv`) and the MPD (Attachment L's formula, at least $12/MWh).
- **From the trader's account:** collateral, the Virtual MWh Limit in use, the position scale, and the trailing 1-in-100-day loss.

Command-line flags: `--starting-capital`, `--daily-risk-budget`, `--credit-share`, `--max-mw-per-hub-hour`, `--ruin-floor-fraction`, `--ruin-floor-usd` (`python -m evobots.cli capital --help`).
