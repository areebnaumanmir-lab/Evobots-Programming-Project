# Maths

Every formula in evobots, with a worked example, the function that implements it, and the test that checks it (`CLAUDE.md` §14.2). The worked examples use the real numbers of [capital_sizing.md](capital_sizing.md). Each was reproduced from the downloaded MISO archive in round 21 ([data/claude_science_check.csv](data/claude_science_check.csv)).

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
- **Daily log return:** holding it to maturity earns r = −ln(P) / 91 per calendar day. In fitness (§10.2 of `CLAUDE.md`), r_f T is the sum of r over the days of the window, each day using the newest quote visible at its decision time.
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

## 4. Still to write
- The market simulator (M3);
- fitness under the career model (M5);
- MAP-Elites (M6);
- the report-card statistics (M7);
- every ORFE module (`CLAUDE.md` §20).
