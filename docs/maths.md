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

## 6. The deployment gates and inference (M7, O7)

### 6.1 Expected maximum Sharpe ratio, deflated Sharpe ratio and MinBTL
- E[max of N unskilled trials] = σ((1 − γ)Φ⁻¹(1 − 1/N) + γΦ⁻¹(1 − 1/(Ne))), γ = 0.5772.
- DSR = Φ((ŜR − SR₀)√(T − 1) / √(1 − γ₃ŜR + (γ₄ − 1)ŜR²/4)), with SR₀ the expected maximum for the effective trials and per-day σ = √(1/(T − 1)) (the null; round 37).
- MinBTL = (E[max of N] / SR)² years for annual SR.
- **Worked example:** N = 100 gives E[max] = 2.531σ. At annual SR = 1, 45 trials need **5.0 years**, the figure of §12.3.

  ```python
  >>> from evobots.assess.statistics import expected_maximum_sharpe, minimum_backtest_length_years
  >>> round(float(expected_maximum_sharpe(1.0, 100)), 3), round(float(minimum_backtest_length_years(1.0, 45)), 1)
  (2.531, 5.0)

  ```
- **Function:** `evobots.assess.statistics`. **Test:** doctests there; `tests/test_report_card.py`.

### 6.2 Effective number of trials
N_eff = (Σλ)²/Σλ² × distinct behaviours ÷ reservoir size, with λ the eigenvalues of the correlation matrix of a reservoir of the run's daily P&L streams. Identical streams give a ratio of 1; independent ones give the number of streams.
- **Function:** `evobots.qd.gates.effective_trials`.

### 6.3 Stationary bootstrap and its block length
Blocks start at random positions; their lengths are geometric with mean b. b comes from the automatic rule of Politis & White (2004, corrected 2009): b = (2Ĝ²/D̂)^{1/3} n^{1/3}, with flat-top lag-window estimates of Ĝ = Σ|k|γ(k) and the spectral sum.
- **Worked example:** for an AR(1) series with φ = 0.7 and n = 3,000, b ≈ 34 days; for white noise, b = 1.
- **Function:** `evobots.assess.statistics.politis_white_block_length`, `stationary_bootstrap_indices`.

### 6.4 Probability of backtest overfitting (CSCV)
Split the days into S = 8 blocks. For each of the C(8, 4) = 70 ways to train on half of them, take the in-sample best by Sharpe and find its out-of-sample relative rank ω. The logit is λ = ln(ω/(1 − ω)), and PBO = P(λ ≤ 0).
- **Function:** `evobots.assess.statistics.probability_of_backtest_overfitting`.

### 6.5 Reality Check, SPA, Romano–Wolf, model confidence set, power
- **Reality Check:** V = max_k √T·d̄_k against the bootstrap of max_k √T(d̄*_k − d̄_k).
- **SPA:** studentised; strategies far below the benchmark are recentred to 0 rather than d̄_k.
- **Romano–Wolf step-down:** adjusted p-values by sequentially removing the strongest rejections.
- **Model confidence set:** eliminate the worst model by T_max until the equal-performance hypothesis is not rejected at α = 0.10.
- **Smallest detectable annual Sharpe:** (z₀.₉₅ + z₀.₈₀)/√years, plus E[max of N]/√years for N trials.
- **Worked example:** with one trial and 20.5 years, **0.549**. The project's whole history can only reliably detect a strategy with an annual Sharpe above about 0.55, before any search.

  ```python
  >>> from evobots.assess.inference import minimum_detectable_sharpe
  >>> round(minimum_detectable_sharpe(years=20.5), 3)
  0.549

  ```
- **Function:** `evobots.assess.inference`.

## 7. The ORFE track (O1–O5, O8, O9 and the leaderboard)

Results of every section: [orfe_report/report.md](orfe_report/report.md), computed by `tools/build_orfe_results.py` into [data/orfe/](data/orfe/).

### 7.1 Scenarios (O1) and how they are scored
- **Stationary block bootstrap:** whole visible days (spreads up to D − 6) resampled in blocks of geometric length with the Politis–White mean (§6.3).
- **Regime model:** a two-state hidden Markov chain on the daily mean spread m_t with Student-t emissions, ν = 4: m_t | (state j) ~ μ_j + σ_j·t_ν. It is fitted by EM, writing t_ν as a normal scale mixture (weights w_t = (ν + 1)/(ν + z_t²)).
- **Mean-reverting jumps (levels):** P_{t+1} − P_t = κ(θ − P_t) + σε_t + J_t, fitted by least squares on the AR(1) form P_{t+1} = a + b·P_t + residual, so κ = 1 − b (per day) and θ = a/κ; residuals beyond 3 standard deviations are the jumps: J_t ~ Bernoulli(their share) × Normal(their mean, their deviation); σ is the deviation of the rest. Each hour adds its average shape.
- **Analogue days:** the K visible days nearest tomorrow in standardised (forecast high, gas price, month) space.
- **CRPS of an ensemble** x₁…x_K against the outcome y: CRPS = (1/K)Σ|x_k − y| − (1/(2K²))Σ_{j,k}|x_j − x_k|. For one member it is the absolute error.
- **Pinball loss at quantile τ:** max(τ(y − q_τ), (τ − 1)(y − q_τ)), with q_τ the ensemble's τ-quantile, averaged over τ ∈ {0.1, 0.5, 0.9}.
- **Function:** `evobots.orfe.scenarios`. **Tests:** `tests/test_orfe.py::test_scenarios_see_nothing_after_the_newest_visible_day`, `::test_regime_model_recovers_two_scales`, `::test_crps_of_a_point_ensemble_is_the_absolute_error`.

### 7.2 The mean-CVaR bidder, the perfect-foresight bound and DPDS (O2)
- **Sample-average LP** over K scenarios of the gain g = RT − DA (Rockafellar & Uryasev 2000):

  max (1/K)Σ_k π_k − λ·[ζ + (1/((1 − α)K))Σ_k u_k]
  subject to u_k ≥ −π_k − ζ, u_k ≥ 0, π_k = Σ_{h,n}(q⁺ − q⁻)g_{k,h,n} − f·Σ(q⁺ + q⁻), 0 ≤ q± ≤ cap_n, Σ(q⁺ + q⁻) ≤ the daily MWh limit.
- **Perfect foresight:** the same LP with the realised day as its only scenario; an upper bound.
- **DPDS** (Baltaoglu, Tong & Zhao 2018): for each option k (hub, hour, side), the translated bid x′ clears when x′ ≥ λ′ and pays π′ − λ′. The empirical payoff r̄_k(x′) = (1/t)Σ_s (π′_s − λ′_s)·1{x′ ≥ λ′_s} is a step function. The budget B is spread by dynamic programming on the grid {0, B/α, …, B}: V_k(b) = max_{x ≤ b} r̄_k(x) + V_{k−1}(b − x). The risk-averse variant maximises r̄_k − ρ·(sample variance).
- **Function:** `evobots.orfe.optimizer`. **Tests:** `tests/test_orfe.py::test_mean_cvar_lp_matches_brute_force`, `::test_dpds_budget_allocation_matches_brute_force`, `::test_perfect_foresight_is_an_upper_bound`.

### 7.3 Portfolios of elites (O3)
With R the (T × m) matrix of the elites' daily returns and w ≥ 0, Σw = 1:
- **mean-CVaR:** max mean(Rw) − λ·CVaR_α(−Rw), the LP of 7.2 with returns for gains;
- **mean-variance:** max mean(Rw) − (γ/2)·wᵀΣw;
- **growth-optimal:** max Σ_t ln(1 + R_t·w); **fractional Kelly** puts the share f of it in the elites and 1 − f in cash. For one asset with mean μ and variance σ², w ≈ μ/σ²;
- **risk parity:** w_i(Σw)_i equal for every i;
- **why the caps still hold:** |Σ_i w_i q_i| ≤ Σ_i w_i|q_i| ≤ cap.
- **Function:** `evobots.orfe.portfolio`. **Tests:** `tests/test_orfe.py::test_portfolio_models_agree_on_small_cases`, `::test_growth_optimal_weight_matches_kelly_for_one_asset`.

### 7.4 The battery (O4)
- **Dynamics:** e_{t+1} = e_t + η_c·c_t − d_t/η_d, 0 ≤ e_t ≤ E, 0 ≤ c_t, d_t ≤ P, with η_c = η_d = √0.82.
- **Revenue of a day:** Σ_t p_t(d_t − c_t) − κΣ_t(c_t + d_t), plus the end-of-day energy settled at the day's mean price p̄: a surplus Δ = e_24 − e_0 > 0 earns Δ·p̄·η_d, a deficit costs |Δ|·p̄/η_c. Without it a policy that ends the day emptier than it started is paid for energy it never bought, and could beat the perfect-foresight bound.
- **Stochastic DP:** V_t(e) = E_p[max_{c,d} p(d − c) − κ(c + d) + V_{t+1}(e′)] on a grid of states, with V_24 the end-of-day settlement value.
- **Bound ratio** of a policy: its revenue ÷ the perfect-foresight revenue over the same days.
- **Worked example** (`schedule_lp` docstring): prices 10, 50, 30, a 1 MW / 1 MWh lossless battery starting empty: charge at 10, sell at 50, revenue $40.
- **Function:** `evobots.orfe.battery`. **Tests:** `tests/test_orfe.py::test_battery_lp_matches_a_hand_solved_three_hours`, `::test_exclusive_milp_and_lp_differ_only_when_prices_turn_negative`, `::test_dynamic_program_agrees_with_brute_force_on_a_tiny_grid`.

### 7.5 Value at risk, expected shortfall and their backtests (O5)
- **EVT peaks over threshold:** above u (the 90th percentile of losses), excesses follow a generalised Pareto(ξ, β). With N_u exceedances of n: VaR_p = u + (β/ξ)[((n/N_u)(1 − p))^{−ξ} − 1] and ES_p = (VaR_p + β − ξu)/(1 − ξ).
- **GARCH(1,1) filtered historical simulation:** σ²_t = ω + αL²_{t−1} + βσ²_{t−1}; VaR = σ̂_{t+1}·quantile_p(L_s/σ_s).
- **Cornish–Fisher:** z_CF = z + (z² − 1)S/6 + (z³ − 3z)K/24 − (2z³ − 5z)S²/36, with S the skewness and K the excess kurtosis. It stops being monotone in z at extreme K; the 2022–2025 failure in the results is that breakdown.
- **Kupiec:** LR = −2 ln[(1 − p)^{T−x}p^x / ((1 − x/T)^{T−x}(x/T)^x)] ~ χ²₁, with x breaches in T days.
- **Christoffersen independence:** a likelihood ratio of a two-state Markov chain of breaches against independence, χ²₁. Conditional coverage adds Kupiec, χ²₂.
- **Acerbi–Székely Z₂:** Z₂ = Σ_t L_t·1{L_t > VaR_t}/(T(1 − p)·ES_t) − 1. Its significance is simulated under the estimated tail.
- **Worked example:** 2 breaches in 100 days at p = 0.01 give Kupiec significance 0.376 (the `risk` module doctest).
- **Function:** `evobots.orfe.risk`. **Tests:** `tests/test_orfe.py::test_kupiec_and_estimators_on_normal_losses`, `::test_evt_tail_on_pareto_losses`.

### 7.6 The search as an OR problem (O8)
- **Successive halving:** at each rung keep ⌈η⁻¹·n⌉ candidates; cost = Σ_rungs n_r × fidelity_r (trader-years).
- **OCBA** (Chen et al. 2000): for non-best i, j, N_i/N_j = (σ_i/δ_i)²/(σ_j/δ_j)², δ the gap to the best b; N_b = σ_b·√(Σ_{i≠b} N_i²/σ_i²).
- **NSGA-II:** fast non-dominated sorting, then crowding distance d_i = Σ_objectives (f_{i+1} − f_{i−1})/(f_max − f_min) inside a front; (μ + μ) survival by (rank, −distance).
- **Hypervolume** against a reference point r: the Monte Carlo share of the box [r, max] dominated by the front, times its volume.
- **CMA-ES** (Hansen 2016): rank-one and rank-μ covariance updates with cumulative step-size adaptation.
- **Function:** `evobots.orfe.search_or`. **Tests:** `tests/test_orfe.py::test_ocba_picks_the_best_more_often_than_equal_allocation`, `::test_cma_es_minimises_rosenbrock`, `::test_nsga2_returns_a_spread_non_dominated_front`, `::test_successive_halving_counts_cost`.

### 7.7 Price impact (O9)
- **Regression with hub × hour fixed effects:** s_{h,d,t} = a_{h,t} + β·net_{h,d,t} + ε, estimated on values demeaned within each (hub, hour); net = DEC − INC cleared MW. Standard errors are clustered by day, with a bootstrap over days for the interval.
- **Implied spread change** of our own position of q MW: β·q. Under linear impact its cost is β·q² per hub-hour, which `AccountRules.price_impact_usd_per_mwh_per_mw` charges in a sensitivity run.
- **Worked example:** β = −0.00077 $/MWh per MW (obs.) and q = 5 MW give −0.004 $/MWh.
- **Function:** `evobots.orfe.price_impact`. **Test:** its doctest (a planted β is recovered within 3 clustered standard errors).

### 7.8 Stage D groups (M8)
Spearman correlation ρ of the daily mean spreads over the 365 visible days before a year; average-linkage clustering on 1 − ρ, cut at 0.25; one representative per group of at least 2 (a trading hub if there is one, else last year's representative, else the medoid argmax_i mean_j ρ_ij).
- **Function:** `evobots.data.clusters`. **Test:** `tests/test_scale_up.py::test_clusters_find_the_groups_point_in_time_and_prefer_hubs`.
