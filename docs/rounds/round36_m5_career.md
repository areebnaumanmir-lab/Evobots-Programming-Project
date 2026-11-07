# Round 36: M5, the career model, and O6 (sequential analysis and survival)

Date: 2026-11-07. Part of "finish all of this" (round 32).

## What was built
- `src/evobots/career/model.py`: the career layers applied to a settled path:
  - L0 out of money (from the simulator);
  - L1 capital floor (relative or absolute);
  - L2 loss limit from the peak;
  - L3 quit hazard, as a survival probability;
  - L4 CUSUM retirement against risk-free plus fixed costs;
  - hedge-fund investor withdrawal.
  
  It also has the presets (individual, MISO-eligible $500k floor, two-thirds floor, prop trader, hedge fund) and the fitness F = E[ln(W_τ/W₀) − r_f τ] − 0.002 × nodes.
- `src/evobots/career/hazard.py`: the L3 hazard, fitted by the method of simulated moments to 44/24/15 % survival, with bootstrap standard errors. Three coefficients are fixed by assumption, as identification requires.
- `src/evobots/career/sequential.py`: Page's CUSUM, Siegmund's ARL approximation, simulated ARLs, thresholds for a target ARL, Shiryaev–Roberts, and Bayesian online change-point detection (Adams & MacKay).
- `src/evobots/career/stopping.py`: quitting as Bayesian optimal stopping, solved by backward induction.
- `src/evobots/career/survival.py`: Kaplan–Meier with Greenwood variance, the Cox model (Newton–Raphson, Breslow ties), and a Schoenfeld-residual check.
- `docs/maths.md` §5, including the ARL table.

## Done-when check (design spec §16, M5; §20.9 O6)
- **With only L0 on, out-of-money deaths carry their day and cause:** `CareerOutcome.stop_index`, `stop_cause`.
- **With the quit hazard on, losing baselines give about 44/24/15 % survival:** the fit reproduces the targets within 2.5 points on a simulated losing population. The real-data fit on random traders after costs runs with M6 (round 37), because it needs the evaluation loop.
- **Fitness is deterministic:** yes, including with L3.
- **O6:** ARL tables, the stopping rule, the moment fit with standard errors and the survival methods exist, each tested on simulated data with a known answer:
  - Siegmund agrees with 3,000 simulated careers within 6 %;
  - the Cox model recovers β = 0.7 within 3 standard errors;
  - the stopping threshold matches a two-month hand solution.
- **Career page:** with the app.

## Decisions taken under delegation
| Topic | Decision | Reason |
|---|---|---|
| Parsimony μ | 0.002 per node | ≤ 0.09 for the largest trader, small beside typical F ~ 0.1–0.5 |
| L3 fixed coefficients | β₂ = −1 (6-month return), β₃ = 1 (drawdown), β₄ = −0.3 per year (age) | identification; direction from §10.1 |
| L4 default | k = 0.5, h = 5 standardised; standardisation from the first 12 months | documented choice; ARL table shows the trade-off |
| L5 peers | not modelled | traders are price-takers and don't interact; stated in reports |
| Hedge-fund preset | 14.4 %/year withdrawal, doubled after two losing years; 25 % loss limit | Getmansky, Lo & Mei 2004; the doubling is an assumption |
| Prop-trader preset | 10 % loss limit, floor at half the capital | §10.1 example values |

## Measured vs assumed
- **Measured:** none on market data yet. The real-data hazard fit comes with M6.
- **Assumed:** the fixed hazard coefficients, the presets' numbers, the $50k fixed costs.
