"""O4: a battery buying low and selling high, a sequential decision problem (§20.7).

**A study, not a deployable strategy:** a real battery is a physical resource that needs MISO
registration and interconnection.

**Model** (a `[battery]` setting): power P MW, energy E MWh, charge and discharge efficiency
η_c = η_d = √0.82 (round trip 82 %: EIA, Today in Energy, 2021-02-12; decided round 28),
degradation cost κ $/MWh of throughput, state of charge e₀ at the start and end of each day.

    e_{t+1} = e_t + η_c·c_t − d_t/η_d,   0 ≤ e_t ≤ E,   0 ≤ c_t, d_t ≤ P
    revenue = Σ_t p_t·(d_t − c_t) − κ·(c_t + d_t)

**Simultaneous charging and discharging:** with negative prices an LP may do both at once to
waste energy. `schedule_lp(..., is_exclusive=True)` forbids it with binaries (a MILP via HiGHS);
the test shows when the LP and MILP agree.

**Policies** (Powell's four classes; Powell 2019, *EJOR* 275(3)):
1. perfect foresight (LP on the realised prices): the upper bound, never a strategy;
2. deterministic look-ahead (rolling intrinsic): the LP on yesterday's visible DA prices as
   the forecast;
3. stochastic dynamic programming: a value function over a state-of-charge grid, backward
   induction over the day's hours with prices drawn from O1's jump model;
4. policy-function approximation: charge below θ₁, discharge above θ₂, tuned by simulation on
   the training days;
5. an evolved policy (`evolve_threshold_policy`): the same two thresholds as numeric genes plus
   a price-offset tree from the trader language, searched by mutation.

**Settlement and information** (stated): all policies here schedule against DA prices and
settle at DA (the schedule is the battery's DA position; no RT deviation). Policies 3 and 4
respond hour by hour to the DA price of that hour — an idealisation of hourly price-responsive
offers, labelled as such.

Example:
    >>> import numpy as np
    >>> prices = np.array([10.0, 50.0, 30.0])
    >>> battery = Battery(1.0, 1.0, round_trip_efficiency=1.0, degradation_usd_per_mwh=0.0,
    ...                   initial_fraction=0.0)
    >>> round(schedule_lp(prices, battery).revenue_usd, 6)
    40.0
"""

import dataclasses
import math

import numpy as np
from scipy import optimize

ROUND_TRIP_EFFICIENCY = 0.82
SOC_GRID_POINTS = 41
HOURS_PER_DAY = 24


@dataclasses.dataclass(frozen=True)
class Battery:
    """Battery parameters (defaults: 5 MW / 20 MWh, 82 % round trip, $2/MWh wear, half full)."""

    power_mw: float = 5.0
    energy_mwh: float = 20.0
    round_trip_efficiency: float = ROUND_TRIP_EFFICIENCY
    degradation_usd_per_mwh: float = 2.0
    initial_fraction: float = 0.5

    def one_way_efficiency(self):
        """η_c = η_d = √(round trip)."""
        return math.sqrt(self.round_trip_efficiency)

    def initial_mwh(self):
        """State of charge at the start (and required at the end) of each day."""
        return self.initial_fraction * self.energy_mwh


@dataclasses.dataclass(frozen=True)
class Schedule:
    """A day's charge and discharge (MW per hour) and what it earns at given prices."""

    charge_mw: np.ndarray
    discharge_mw: np.ndarray
    revenue_usd: float

    def state_of_charge(self, battery):
        """MWh at the end of each hour."""
        efficiency = battery.one_way_efficiency()
        return battery.initial_mwh() + np.cumsum(
            efficiency * self.charge_mw - self.discharge_mw / efficiency
        )


def revenue(prices, charge, discharge, battery):
    """Σ p·(d − c) − κ·(c + d), plus the end-of-day energy settled at the day's mean price.

    Every policy starts each day at the same state of charge. Energy left above it at the end
    is credited at the mean price (after the discharge loss); a shortfall is charged at the
    mean price (after the charge loss). Without this, a policy that ends the day emptier than
    it started would be paid for energy it never bought.
    """
    prices = np.asarray(prices, dtype=float)
    efficiency = battery.one_way_efficiency()
    end_state = battery.initial_mwh() + float(np.sum(efficiency * charge - discharge / efficiency))
    surplus = end_state - battery.initial_mwh()
    mean_price = float(prices.mean())
    settlement = surplus * mean_price * (efficiency if surplus > 0 else 1 / efficiency)
    trading = float(np.sum(prices * (discharge - charge)))
    wear = battery.degradation_usd_per_mwh * float(np.sum(charge + discharge))
    return trading - wear + settlement


def schedule_lp(prices, battery, is_exclusive=False, is_end_state_fixed=False):
    """The revenue-maximising schedule for known prices (LP, or MILP when exclusive).

    The objective is `revenue`, end-of-day energy settlement included: two extra variables
    split the day's net energy change into a surplus (credited at mean price × η) and a deficit
    (charged at mean price ÷ η). `is_end_state_fixed` also forces the day to end at least as
    full as it started.
    """
    prices = np.asarray(prices, dtype=float)
    hours = len(prices)
    efficiency = battery.one_way_efficiency()
    kappa = battery.degradation_usd_per_mwh
    # Variables: c (hours), d (hours), [binary z (hours) when exclusive], surplus, deficit.
    binary_count = hours if is_exclusive else 0
    variable_count = 2 * hours + binary_count + 2
    surplus_index, deficit_index = variable_count - 2, variable_count - 1
    mean_price = float(prices.mean())
    objective = np.zeros(variable_count)
    objective[:hours] = prices + kappa
    objective[hours : 2 * hours] = -prices + kappa
    objective[surplus_index] = -mean_price * efficiency
    objective[deficit_index] = mean_price / efficiency
    lower_triangle = np.tril(np.ones((hours, hours)))
    # State of charge e₀ + L(η c − d/η) within [0, E].
    soc_rows = np.zeros((hours, variable_count))
    soc_rows[:, :hours] = efficiency * lower_triangle
    soc_rows[:, hours : 2 * hours] = -lower_triangle / efficiency
    constraints = [
        optimize.LinearConstraint(
            soc_rows, -battery.initial_mwh(), battery.energy_mwh - battery.initial_mwh()
        )
    ]
    balance = soc_rows[-1:].copy()
    balance[0, surplus_index], balance[0, deficit_index] = -1.0, 1.0
    constraints.append(optimize.LinearConstraint(balance, 0.0, 0.0))
    if is_end_state_fixed:
        constraints.append(optimize.LinearConstraint(soc_rows[-1:], 0.0, np.inf))
    bounds_low = np.zeros(variable_count)
    bounds_high = np.concatenate(
        [
            np.full(2 * hours, battery.power_mw),
            np.ones(binary_count),
            [battery.energy_mwh, battery.energy_mwh],
        ]
    )
    integrality = np.zeros(variable_count)
    if is_exclusive:
        integrality[2 * hours : 3 * hours] = 1
        # c ≤ P z, d ≤ P (1 − z)
        charge_rows = np.zeros((hours, variable_count))
        charge_rows[:, :hours] = np.eye(hours)
        charge_rows[:, 2 * hours : 3 * hours] = -battery.power_mw * np.eye(hours)
        discharge_rows = np.zeros((hours, variable_count))
        discharge_rows[:, hours : 2 * hours] = np.eye(hours)
        discharge_rows[:, 2 * hours : 3 * hours] = battery.power_mw * np.eye(hours)
        constraints.append(optimize.LinearConstraint(charge_rows, -np.inf, 0.0))
        constraints.append(optimize.LinearConstraint(discharge_rows, -np.inf, battery.power_mw))
    result = optimize.milp(
        objective,
        constraints=constraints,
        integrality=integrality,
        bounds=optimize.Bounds(bounds_low, bounds_high),
    )
    if not result.success:
        raise RuntimeError(result.message)
    charge, discharge = result.x[:hours], result.x[hours : 2 * hours]
    return Schedule(charge, discharge, revenue(prices, charge, discharge, battery))


def apply_schedule_to_prices(schedule, prices, battery):
    """What a schedule decided on other prices earns at these prices."""
    return revenue(
        np.asarray(prices, dtype=float), schedule.charge_mw, schedule.discharge_mw, battery
    )


def dp_value_function(price_samples, battery, grid_points=SOC_GRID_POINTS):
    """Backward induction over the day's hours on a state-of-charge grid.

    Args:
        price_samples: (S, 24) sampled price days (each hour's price is known when acting).
        battery: the Battery.
        grid_points: points of the state-of-charge grid.

    Returns:
        (grid MWh, values (25, grid)) with value[h][i] = expected revenue from hour h on.
    """
    grid = np.linspace(0.0, battery.energy_mwh, grid_points)
    efficiency = battery.one_way_efficiency()
    kappa = battery.degradation_usd_per_mwh
    values = np.full((HOURS_PER_DAY + 1, grid_points), -1e9)
    # End of day: energy above or below the start is settled at each sample day's mean price
    # (the same accounting as `revenue`), averaged over the samples.
    change = grid - battery.initial_mwh()
    mean_prices = price_samples.mean(axis=1)[:, None]
    terminal = np.where(change > 0, change * efficiency, change / efficiency)[None, :] * mean_prices
    values[HOURS_PER_DAY] = terminal.mean(axis=0)
    actions = np.linspace(
        -battery.power_mw, battery.power_mw, 2 * grid_points - 1
    )  # + discharge, − charge
    for hour in range(HOURS_PER_DAY - 1, -1, -1):
        prices = price_samples[:, hour]
        best = np.full((len(prices), grid_points), -1e18)
        for action in actions:
            discharge, charge = max(action, 0.0), max(-action, 0.0)
            next_soc = grid + efficiency * charge - discharge / efficiency
            feasible = (next_soc >= -1e-9) & (next_soc <= battery.energy_mwh + 1e-9)
            continuation = np.interp(
                np.clip(next_soc, 0, battery.energy_mwh), grid, values[hour + 1]
            )
            reward = (
                prices[:, None] * (discharge - charge)
                - kappa * (charge + discharge)
                + continuation[None, :]
            )
            best = np.where(feasible[None, :], np.maximum(best, reward), best)
        values[hour] = best.mean(axis=0)
    return grid, values


def dp_policy_day(prices, battery, grid, values):
    """Act hour by hour on the realised prices with the DP value function (greedy in it)."""
    efficiency = battery.one_way_efficiency()
    kappa = battery.degradation_usd_per_mwh
    soc = battery.initial_mwh()
    charge = np.zeros(HOURS_PER_DAY)
    discharge = np.zeros(HOURS_PER_DAY)
    actions = np.linspace(-battery.power_mw, battery.power_mw, 2 * len(grid) - 1)
    for hour in range(HOURS_PER_DAY):
        best_value, best_action = -np.inf, 0.0
        for action in actions:
            out, into = max(action, 0.0), max(-action, 0.0)
            next_soc = soc + efficiency * into - out / efficiency
            if next_soc < -1e-9 or next_soc > battery.energy_mwh + 1e-9:
                continue
            value = (
                prices[hour] * (out - into)
                - kappa * (into + out)
                + np.interp(next_soc, grid, values[hour + 1])
            )
            if value > best_value:
                best_value, best_action = value, action
        discharge[hour], charge[hour] = max(best_action, 0.0), max(-best_action, 0.0)
        soc += efficiency * charge[hour] - discharge[hour] / efficiency
    return Schedule(charge, discharge, revenue(prices, charge, discharge, battery))


def threshold_policy_day(prices, battery, charge_below, discharge_above):
    """Charge at full power below θ₁, discharge above θ₂, within the state-of-charge limits."""
    efficiency = battery.one_way_efficiency()
    soc = battery.initial_mwh()
    charge = np.zeros(len(prices))
    discharge = np.zeros(len(prices))
    for hour, price in enumerate(prices):
        if price < charge_below:
            charge[hour] = min(battery.power_mw, (battery.energy_mwh - soc) / efficiency)
        elif price > discharge_above:
            discharge[hour] = min(battery.power_mw, soc * efficiency)
        soc += efficiency * charge[hour] - discharge[hour] / efficiency
    return Schedule(charge, discharge, revenue(prices, charge, discharge, battery))


def tune_thresholds(price_days, battery, quantile_grid=np.linspace(0.05, 0.95, 19)):
    """θ₁ < θ₂ chosen from price quantiles to maximise total revenue on training days."""
    levels = np.quantile(price_days, quantile_grid)
    best = (-np.inf, levels[0], levels[-1])
    for low_index, low in enumerate(levels):
        for high in levels[low_index + 1 :]:
            total = sum(
                threshold_policy_day(day, battery, low, high).revenue_usd for day in price_days
            )
            if total > best[0]:
                best = (total, low, high)
    return best[1], best[2]


def evolve_threshold_policy(price_days, battery, generations=40, population=20, seed=0):
    """An evolved policy: (θ₁, θ₂) as genes, Gaussian mutation, truncation selection."""
    generator = np.random.Generator(np.random.PCG64(seed))
    low, high = np.quantile(price_days, [0.05, 0.95])

    def fitness(genes):
        first, second = sorted(genes)
        return sum(
            threshold_policy_day(day, battery, first, second).revenue_usd for day in price_days
        )

    members = [generator.uniform(low, high, size=2) for _ in range(population)]
    for _ in range(generations):
        ranked = sorted(members, key=fitness, reverse=True)[: population // 2]
        children = [parent + generator.normal(0, 0.05 * (high - low), size=2) for parent in ranked]
        members = ranked + children
    return tuple(sorted(max(members, key=fitness)))


def bound_ratio(policy_revenue, perfect_revenue):
    """Policy revenue as a share of the perfect-foresight bound."""
    return policy_revenue / perfect_revenue if perfect_revenue > 0 else float("nan")
