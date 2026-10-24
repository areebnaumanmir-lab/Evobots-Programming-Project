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
- **Tests:** `tests/test_sizing.py::test_trailing_p99_equals_claude_science_on_every_day`, `::test_section_4b_table`, `::test_look_ahead_changing_d_minus_5_onwards_changes_nothing`, `::test_breach_rate_by_year_2015_2025`.

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

## 2. Still to write
- The market simulator (M3);
- fitness under the career model (M5);
- MAP-Elites (M6);
- the report-card statistics (M7);
- every ORFE module (`CLAUDE.md` §20).
