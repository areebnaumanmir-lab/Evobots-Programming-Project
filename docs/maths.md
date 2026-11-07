# Maths

Every formula in evobots, with a worked example, the function that implements it, and the test that checks it (`docs/design_spec.md` §14.2). The worked examples use the real numbers of [capital_sizing.md](capital_sizing.md). Each was reproduced from the downloaded MISO archive in round 21 ([data/claude_science_check.csv](data/claude_science_check.csv)).

Notation: W is equity (USD); b the daily risk budget (a fraction); L₉₉ the 1-in-100-day loss at full size (USD); D the operating day; x_t the full-size always-INC P&L on day t (USD; always-DEC is −x_t).

## 1. Capital and sizing

### 1.1 The sizing rule
s(D) = min(1, b · W(D−1) / L₉₉(D)), and s = 0 when L₉₉ is not yet available (warm-up).
- Full size is reached at C_full = L₉₉ / b.
- **Worked example:**
  - b = 0.02 and the full-sample L₉₉ = $27,897, so C_full = $1,394,850;
  - at W = $1.5M: s = min(1, 30,000 / 27,897) = 1;
  - at W = $250k: s = 5,000 / 27,897 = 0.1792.
- **Function:** `evobots.sizing.position_scale`; `CapitalSettings.full_size_capital_usd`.
- **Run as a doctest** (`pytest` collects the examples in this file):

  ```python
  >>> from evobots.sizing import position_scale
  >>> round(position_scale(250_000, 27_897, 0.02), 4)
  0.1792

  ```
- **Tests:** `tests/test_sizing.py::test_position_scale_rules`, `tests/test_calibration_tables.py::test_capital_sweep`.

### 1.2 Caps, footprint and benchmark P&L
- **Cap at hub h:** cap_h = round₀.₁( min(M, φ · median_h) ), with M = 5 MW and φ = 0.05. MISO's bid step is 0.1 MW; halves round up.
- **Footprint:** Σ_h cap_h × 24 MWh/day.
- **INC P&L of q MW in one hour:** q · (DA − RT).
- **Worked example:**
  - MS.HUB: min(5, 0.05 × 79.0) = 3.95 → 4.0 MW; every other hub gets 5 MW;
  - footprint (7 × 5 + 4) × 24 = **936 MWh/day**;
  - before MS.HUB existed (to 2017-11): 35 × 24 = 840.
- **Function:** `CapitalSettings.hub_caps_mw`, `CapitalSettings.full_size_mwh_per_day`, `evobots.calibration.full_size_benchmark_daily_pnl`.
- **Tests:** `tests/test_capital.py::test_full_size_is_936_not_960_mwh_per_day`, `::test_full_size_before_ms_hub_existed_is_840_mwh_per_day`, `::test_caps_are_five_mw_except_ms_hub`.

### 1.3 Collateral and the Virtual MWh Limit
- **Collateral** (Attachment L): L_MWh × max(MPD, 12) × VMEW, with VMEW = 2 days ([market_rules.md](market_rules.md) §4.1).
- **Limit the pledged credit supports:** L_MWh = c · C / (max(MPD, 12) · 2), where c is the credit share.
- **Worked example:**
  - 936 × 12 × 2 = **$22,464**;
  - with c = 0.25 and C = $1.5M: 375,000 / 24 = **15,625 MWh/day**, 16.7 × the footprint.
- **Function:** `CapitalSettings.virtual_mwh_limit`.
- **Tests:** `tests/test_capital.py::test_collateral_at_full_size_is_22464_usd`, `::test_virtual_mwh_limit_at_defaults_is_about_15600`.

### 1.4 The point-in-time 1-in-100-day loss
L₉₉(D) = max( Q₉₉(−x), Q₉₉(x) ) over x_t for t ∈ [D−6−364, D−6]. The window expands from the start; with fewer than 90 visible days, L₉₉ is undefined and s = 0.
- Q₉₉ is the 99th percentile with linear interpolation (NumPy's default; it reproduces Claude Science's values exactly).
- D−6 is the newest operating day whose final RT price is known at the decision on D−1 ([market_rules.md](market_rules.md) §2.2).
- **Worked example** (2019 cold-start sample):
  - the first estimate exists for D = 2019-04-06;
  - on Uri's worst day, D = 2021-02-18, L₉₉ = $12,261 (the storm is not yet visible);
  - on 2021-02-25 it is $18,777.
- **Function:** `evobots.sizing.trailing_p99_daily_loss`, `trailing_p99_series`.
- **Tests:** `tests/test_sizing.py::test_trailing_p99_equals_claude_science_on_every_day`, `::test_section_4b_table`, `::test_look_ahead_changing_the_five_newest_days_changes_nothing`, `::test_breach_rate_by_year_2015_2025`.

### 1.5 The worst k-day loss as a share of equity
worst = max over i of ( −Σ_{t=i}^{i+k−1} p_t ) / W_i, where p_t is the sized P&L and W_i the equity before day i; k = 20.
- **Worked example:** at C = $1.5M with point-in-time sizing, always-DEC, the run ending 2021-03-08 (Uri) costs **24.57 %** of equity. The headroom to a $1M floor is 33.3 %, so the default survives.
- **Function:** `evobots.sizing.worst_rolling_loss_fraction` with `simulate_benchmark_equity`.
- **Tests:** `tests/test_sizing.py::test_worst_20_day_loss_point_in_time`, `tests/test_calibration_tables.py::test_headroom_trailing`.

### 1.6 Fitness with and without storm days
F = ln(W_T / W_0) − r_f · T. Returns are r_t = p_t / W_{t−1}, compounded as W_t = W_{t−1}(1 + r_t), with r_t set to 0 on storm days; compounding stops when W falls to or below a floor, if one is set.
- **Worked example:**
  - a single −10 % day gives F = ln 0.9 = −0.1054;
  - always-INC at $1.5M with a $1M floor: F = 0.540, and 0.684 without storms (Uri +0.069, Elliott −0.212).
- **Function:** `evobots.storms.compounded_fitness`, `fitness_with_and_without_storms`.
- **Tests:** `tests/test_storms.py`.

### 1.7 Fixed costs per cleared MWh, and the capital they need
- **Cost per cleared MWh:** cost = F_fixed / (s · 936 · 365 · σ), where σ is the share of hub-hours with a cleared position.
- **Capital floor:** C_min = F_fixed · L₉₉ / (b · target · 936 · 365 · σ). It is infinite when even full size can't reach the target.
- **Worked example:**
  - F_fixed = $50,000 and σ = 1: 50,000 / 341,640 = **$0.146/MWh**;
  - C_min for $1/MWh: 50,000 × 27,897 / (0.02 × 341,640) = **$204,140**;
  - σ = 0.1 gives $1.46/MWh even at full size, so C_min is infinite.
- **Function:** `evobots.calibration.fixed_cost_usd_per_cleared_mwh`, `capital_floor_for_fixed_costs`.
- **Tests:** `tests/test_calibration_tables.py::test_fixed_cost_capital_floor`, `::test_capital_sweep`.

## 2. Why prices differ by location: the DC optimal power flow (O0)

Notation: buses n, lines l, generators k with marginal cost c_k ($/MWh) and capacity Ḡ_k (MW); demand d_n (MW); line limits F_l (MW); line reactances x_l. The walk-through is in [explanations/lmp_from_opf.md](explanations/lmp_from_opf.md).

### 2.1 Power transfer distribution factors
With a reference bus r, the DC power flow gives bus angles θ = B_r⁻¹ p, where B is the susceptance matrix (B_nn = Σ 1/x_l over the lines at n; B_nm = −1/x_l for the line n–m), with the reference row and column removed. The flow on line l from i to j is (θ_i − θ_j) / x_l. So PTDF[l, n] = (X[i, n] − X[j, n]) / x_l, with X = B_r⁻¹ padded with zeros at r.
- **Worked example:** a triangle A–B–C of equal reactances, reference C. 1 MW injected at A splits 2/3 on the direct line A–C and 1/3 on the path A–B–C. So the PTDFs of lines (A–B, A–C, B–C) are (1/3, 2/3, 1/3) for bus A and (−1/3, 1/3, 2/3) for bus B.
- **Function:** `evobots.orfe.dc_opf.ptdf_matrix`.
- **Tests:** the docstring example; `tests/test_dc_opf.py::test_ptdf_flows_satisfy_kirchhoff`.

### 2.2 The linear program and its duals
minimise Σ_k c_k g_k over 0 ≤ g_k ≤ Ḡ_k, subject to
- power balance: Σ_k g_k = Σ_n d_n, with dual λ;
- line limits: −F_l ≤ Σ_n PTDF[l, n] (G_n − d_n) ≤ F_l, with duals μ_l, where G_n is the output at bus n.

**LMP:** LMP_n = ∂cost/∂d_n = λ + Σ_l μ_l PTDF[l, n].
- With μ_l the signed dual of line l, λ is the **energy component**, the price at the reference bus.
- Σ_l μ_l PTDF[l, n] is the **congestion component**, MISO's MCC. It is zero at every bus when no line binds.
- The DC model is lossless, so there is no loss component (MLC).
- The LMPs do not depend on the reference bus. The split into energy and congestion does.

**Function:** `evobots.orfe.dc_opf.solve_dc_opf` (HiGHS through `scipy.optimize.linprog`; duals from its marginals).

### 2.3 Worked example (the three-bus network)
- **Network:**
  - generator at A: $20/MWh;
  - generator at B: $50/MWh;
  - load 150 MW at C;
  - limit 80 MW on line A–C.
- **Without the limit:** A would supply all 150 MW, sending 100 MW on A–C, so the limit binds.
- **Flow on A–C:** (2/3)g_A + (1/3)g_B = 50 + g_A/3 ≤ 80. So g_A = 90, g_B = 60, and the cost is 90·20 + 60·50 = **$4,800**.
- **Duals:** both generators are marginal, so
  - 20 = λ − μ·(2/3) and 50 = λ − μ·(1/3);
  - hence μ = 90 (the line's shadow price, $ per MW of extra limit) and λ = 80.
- **LMPs:**
  - **A: $20/MWh** (congestion −60);
  - **B: $50/MWh** (−30);
  - **C: $80/MWh** (0).
- **Check:** one more MW at C needs g_A = 89 and g_B = 62, so the cost rises by exactly $80. That is the price at C, above both generators' costs.
- **Run as a doctest:**

  ```python
  >>> from evobots.orfe.dc_opf import THREE_BUS_EXAMPLE, solve_dc_opf
  >>> result = solve_dc_opf(THREE_BUS_EXAMPLE)
  >>> [round(price, 2) for price in result["lmp_usd_per_mwh"]], round(result["total_cost_usd"])
  ([20.0, 50.0, 80.0], 4800)

  ```
- **Tests:** `tests/test_dc_opf.py`:
  - `::test_three_bus_hand_derivation`;
  - `::test_lmp_equals_cost_of_one_more_mw` (re-solves with +1 MW at each bus);
  - `::test_line_shadow_price_equals_saving_from_one_more_mw_of_limit`;
  - `::test_prices_do_not_depend_on_the_reference_bus`.

## 3. Data series

### 3.1 The risk-free rate from the 3-month Treasury bill
- **Quote:** FRED's DTB3 gives the bill's discount rate in percent (decided round 28); the reader stores it as a fraction d. A 91-day bill quoted at d costs P = 1 − d · 91/360 per dollar of face value.
- **Daily log return:** holding it to maturity earns r = −ln(P) / 91 per calendar day. In fitness (§10.2 of `docs/design_spec.md`), r_f T is the sum of r over the days of the window, each day using the newest quote visible at its decision time.
- **Worked example:** d = 0.05 (quoted 5.00 %):
  - P = 1 − 0.05 × 91/360 = 0.987361;
  - −ln P = 0.0127194, so r = 0.000139774 per day;
  - over 365 days, 5.1018 % continuously compounded.
- **Function:** `evobots.data.sources.series.daily_risk_free_log_return`.
- **Run as a doctest:**

  ```python
  >>> from evobots.data.sources.series import daily_risk_free_log_return
  >>> round(daily_risk_free_log_return(0.05) * 365, 6)
  0.051018

  ```
- **Test:** `tests/test_series.py::test_daily_risk_free_log_return_worked_example`.

### 3.2 Hub spread statistics: excess kurtosis
- **Formula:** for spreads s₁ … sₙ with mean s̄, central moments m₂ = Σ(sᵢ − s̄)²/n and m₄ = Σ(sᵢ − s̄)⁴/n, the moment estimate is g₂ = m₄/m₂² − 3, and the bias-corrected sample estimate is G₂ = ((n + 1) g₂ + 6)(n − 1) / ((n − 2)(n − 3)).
- **Which one `hub_price_stats.csv` uses:** G₂ (round 28). For ARKANSAS.HUB 2019-01-01 → 2025-09-21 (n = 58,944 hours): g₂ = 3,165.124 and G₂ = 3,165.393, the recorded value.
- **Worked example:** s = (5, −5, 0, 2, −2): s̄ = 0, m₂ = 58/5 = 11.6, m₄ = 1,282/5 = 256.4, so g₂ = 256.4/134.56 − 3 = −1.0945 and G₂ = ((6)(−1.0945) + 6)(4)/((3)(2)) = −0.3781.

  ```python
  >>> import numpy as np
  >>> from evobots.data.build import hub_price_statistics
  >>> statistics = hub_price_statistics(np.array([5.0, -5, 0, 2, -2]), np.zeros(5))
  >>> round(statistics["spread_excess_kurtosis"], 4)
  -0.3781

  ```
- **Function:** `evobots.data.build.hub_price_statistics`. **Check:** `evobots data build --stage A` compares all 176 values with the recorded file.

## 4. The market simulator (M3)

Notation: for trader k, day D, hour h and location n: side σ ∈ {+1 DEC, −1 INC, 0}, limit b, full-size power m (MW), position scale s, DA price P^DA, RT price P^RT.

### 4.1 Clearing and P&L
- **Cleared:** c = 1 when σ = +1 and P^DA ≤ b, or σ = −1 and P^DA ≥ b; else 0. Hours without both prices don't trade.
- **Power bid:** q = ⌊10 · s · m⌋ / 10 MW (MISO's 0.1 MW step; below it is no bid).
- **Gross P&L:** Σ_{h,n} c · σ · q · (P^RT − P^DA). DEC earns RT − DA, INC earns DA − RT.
- **Function:** `evobots.simulate.settlement.settle` (fast) and `settle_reference` (readable).
- **Tests:** `tests/test_settlement.py::test_fast_kernel_agrees_with_reference`, `::test_simulator_equals_the_calibrated_sizing_module`, `::test_real_benchmarks_reproduce_capital_sizing` (worst days $492,173 and $176,554; storm fitness 0.540 and −0.411).

### 4.2 Fees with MISO's netting
With net(n, h) = Σ cleared DEC MW − Σ cleared INC MW at node n:
- admin = r_A · Σ_n |net(n, h)|; DA RSG = r_D · Σ_n max(net, 0); DDC = r_R(h) · max(−Σ_n net, 0) ([market_rules.md](market_rules.md) §3.2).
- **Worked example** (rates of 2024, estimates: r_A = $0.0902, r_D = $0.05, r_R = $0.11): 2 MW DEC at one hub and 5 MW INC at another in one hour pays 0.0902 × 7 + 0.05 × 2 + 0.11 × 3 = **$1.0614**. In 2010 (r_R = $1.80) the same hour pays **$6.1314**.

  ```python
  >>> import datetime
  >>> from evobots.simulate.fees import CostTable, hourly_fees_usd
  >>> table = CostTable.estimates()
  >>> round(hourly_fees_usd([2.0, -5.0], table.rates_for_day(datetime.date(2024, 1, 1))), 4)
  1.0614
  >>> round(hourly_fees_usd([2.0, -5.0], table.rates_for_day(datetime.date(2010, 6, 1))), 4)
  6.1314

  ```
- **Function:** `evobots.simulate.fees.hourly_fees_usd`, `CostTable`. **Test:** `tests/test_settlement.py::test_fee_netting_matches_the_rules`.

### 4.3 Daily limits: the trader's cap and the Virtual MWh Limit
The scale is cut so that submitted MWh (cleared or not) stay within both limits:
s' = s · min(1, cap_k / (s · Σ m), c · W / (MPD · 2) / (s · Σ m)).
- **Worked example:** W = $10,000, credit share c = 0.25, MPD $12: the limit is 2,500 / 24 = 104.2 MWh. Bidding 5 MW at 192 hub-hours (960 MWh) at s = 1 is cut to 0.5425 MW per bid, rounded down to **0.5 MW**, so **96 MWh** are submitted.
- **Test:** `tests/test_settlement.py::test_credit_limit_cuts_bids_instead_of_refusing_them`.

### 4.4 Death: out of money (L0)
Dead from the day equity ≤ 0.1 MW × MPD × 2 days = **$2.40** (at the $12 floor): it can no longer post the smallest bid's collateral. Equity then stays frozen.
- **Function:** `AccountRules.out_of_money_equity_usd`. **Test:** `tests/test_settlement.py::test_out_of_money_death_freezes_the_account`.

## 5. Career model and fitness (M5, O6)

### 5.1 Fitness
F = E[ln(W_τ/W₀) − r_f·τ] − μ·size, with τ the end of the career (window end, a hard stop, or an L3 quit), r_f the FRED DTB3 log return per day summed over the days traded, and μ = 0.002 per tree node. With L3 on: E = Σ_m S_{m−1} h_m g_m + S_M g_M, where g_m is the excess log growth to month m and S_m = Π_{j≤m}(1 − h_j).
- **Worked example:** a trader with 3 nodes ending at W_T = $1.65M from $1.5M, r_f = 0, no L3: F = ln(1.1) − 0.006 = **0.0893**.
- **Function:** `evobots.career.model.apply_career`. **Tests:** `tests/test_career.py::test_default_career_is_out_of_money_only`, `::test_fitness_is_deterministic_with_the_quit_hazard`.

### 5.2 L3 quit hazard, fitted by simulated moments
h_m = logistic(β₀ + β₁·cum + β₂·r6 + β₃·dd + β₄·age). β₂ = −1, β₃ = 1 and β₄ = −0.3 per year are assumptions (three moments cannot identify five coefficients). β₀ and β₁ minimise Σ_k (S̄(12k) − target_k)² for targets 44 %, 24 % and 15 % (Barber et al. 2020), with bootstrap standard errors.
- **Function:** `evobots.career.hazard.fit_quit_hazard`. **Test:** `tests/test_career.py::test_quit_hazard_reproduces_the_survival_targets` (within 2.5 points on a simulated losing population).

### 5.3 L4: Page's CUSUM and its average run length
S_m = max(0, S_{m−1} + k − z_m), signal when S_m > h, with z the standardised monthly excess return over (r_f + fixed costs ÷ capital). Siegmund: ARL ≈ (e^{−2Δb} + 2Δb − 1)/(2Δ²), Δ = k − μ, b = h + 1.166 (b² when Δ = 0).
- **Worked example:** k = 0.5, h = 4: ARL 338 months while the edge is a full standard deviation (μ = 1), and 8.3 months once it is gone (μ = 0). 3,000 simulated careers per case agree within 6 %.

  ```python
  >>> from evobots.career.sequential import siegmund_average_run_length
  >>> round(siegmund_average_run_length(1.0, 0.5, 4.0)), round(siegmund_average_run_length(0.0, 0.5, 4.0), 1)
  (338, 8.3)

  ```
- **Threshold chosen for one false retirement per 10 years (ARL 120 months) when the edge is intact,** and the detection delay once it is gone:

  | Edge (σ per month) | k | h | Delay (months) |
  |---|---|---|---|
  | 0.25 | 0.25 | 9.79 | 35.9 |
  | 0.25 | 0.50 | 30.83 | 62.0 |
  | 0.50 | 0.25 | 4.72 | 16.0 |
  | 0.50 | 0.50 | 9.79 | 19.9 |
  | 1.00 | 0.25 | 2.13 | 6.7 |
  | 1.00 | 0.50 | 3.01 | 6.4 |

  A small edge takes years to tell apart from none: the honest consequence of monthly data. The L4 default (k = 0.5, h = 5) is a documented choice, off unless switched on.
- **Function:** `evobots.career.sequential` (CUSUM, Siegmund, simulation, Shiryaev–Roberts, Bayesian online change-point detection). **Tests:** `tests/test_career.py::test_siegmund_approximation_matches_simulation`, `::test_cusum_and_shiryaev_roberts_detect_a_lost_edge`, `::test_bocpd_puts_the_change_where_it_happened`.

### 5.4 Quitting as optimal stopping
V_n(m) = max(0, m + E[V_{n+1}(m′)]), m′ ~ N(m, s_n² − s_{n+1}²), s_n² = 1/(1/s₀² + n/σ²). The trader stops when its posterior mean edge falls below the threshold b_n.
- **Worked example:** with two months left, b₀ solves m + mΦ(m/√v) + √v φ(m/√v) = 0. With one month left, b = 0.
- **Function:** `evobots.career.stopping.stopping_thresholds`. **Test:** `tests/test_career.py::test_stopping_threshold_against_a_two_month_hand_solution`.

### 5.5 Survival of careers
Kaplan–Meier S(t) = Π(1 − d_i/n_i), Greenwood variance; Cox h(t|x) = h₀(t)e^{βx} (Breslow partial likelihood, Newton–Raphson); Schoenfeld-residual check of proportional hazards.
- **Worked example:** durations 2, 3, 3⁺, 5, 6⁺, 6 give S = 0.833, 0.667, 0.444, 0.222.
- **Function:** `evobots.career.survival`. **Tests:** `tests/test_career.py::test_kaplan_meier_and_greenwood_by_hand`, `::test_cox_recovers_a_known_coefficient`.

## 6. Still to write
- MAP-Elites (M6);
- the report-card statistics (M7);
- every ORFE module (`docs/design_spec.md` §20).
