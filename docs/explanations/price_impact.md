# Do our bids move prices? (O9)

evobots assumes its bids don't move prices: a price taker. The 5 MW cap per hub-hour enforces it. This page tests that assumption with MISO's own data (`docs/design_spec.md` §20.12).

## Data
- **Source:** MISO's cleared-bids reports, with the hub attribution of [capital_sizing.md](../capital_sizing.md) §2.
- **Which hub-hours count:** a bid counts for a hub only when that hub alone has the bid's ex-ante price and the Region field is blank. Only these "observable" hub-hours are used (25–48 % of them).
- **Sample:** every fifth day with a cleared-bids file, 2023-01-01 → 2025-09-17. That is 199 days and 12,085 hub-hours, all inside the evolution period.

## Estimate
For each observable hub-hour, the regression is

  spread = a_{hub,hour} + β · net MW + ε

- **spread:** DA − RT, in $/MWh.
- **net MW:** cleared DEC − INC.
- **a:** hub-by-hour fixed effects, removed by demeaning.
- **Uncertainty:** standard errors are clustered by day; a bootstrap over days gives the 90 % interval.
- **Code:** `evobots.orfe.price_impact`; `tools/build_orfe_results.py --sections impact` writes [data/orfe/impact.json](../data/orfe/impact.json).

| | Value (obs.) |
|---|---|
| β, $/MWh per MW | −0.00077 |
| clustered standard error | 0.0042 |
| 90 % bootstrap interval | −0.0079 to +0.0060 |
| spread change from our 5 MW cap, β × 5 | −0.004 $/MWh |

**Reading:**
- **No detectable impact.** The interval contains zero.
- **Small at our size.** Even the interval's upper end moves the spread by 3 cents per MWh at 5 MW.
- **Expected sign.** Virtual demand raises DA, so a positive β is the expected sign. The estimate isn't distinguishable from zero.

## Caveats (they apply to every use of this number)
- **Endogeneity.** Traders bid more DEC when they expect RT above DA. β therefore mixes any impact with anticipation, so it is an **association, not a causal effect**.
- **A causal estimate would need an instrument.** It must move virtual volume but not the spread directly. Candidates to study:
  - changes in MISO's virtual-bid fees or credit rules;
  - outages of a large virtual participant (not observable in public data);
  - weather-forecast surprises that change volume through risk limits.

  None is used here.
- **Selection.** Only observable hub-hours are used, and they may differ from the others.

## Sensitivity run
The simulator has an optional linear impact (`AccountRules.price_impact_usd_per_mwh_per_mw`). A cleared bid of q MW moves its own DA price by β·q against itself, which costs β·q² per hub-hour. Price-taking stays the default.

The run uses R101's nearest candidate, R101-29627, on its unseen year (2024-03-28 → 2025-03-27), with the same decisions and the same sizing:

| Impact assumed | β | Log growth | Fees and impact cost |
|---|---|---|---|
| price-taking | 0 | +0.0503 | $16,972 |
| upper end of the 90 % interval | 0.0060 | +0.0489 | $19,109 |
| 10 × that (stress) | 0.060 | +0.0366 | $38,335 |

**Conclusion:** at evobots' size, price impact is not what decides whether a trader is worth deploying. Costs and selection bias (the gates G2 and G3) are.
