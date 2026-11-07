"""L3: quitting after poor results, a monthly hazard fitted by simulated moments (§10.1, §20.9).

h_m = logistic(β0 + β1·cum_m + β2·r6_m + β3·dd_m + β4·age_m) × (1 − persistence), with
- cum_m: cumulative P&L as a share of starting capital (W_m/W_0 − 1);
- r6_m: return over the last six months (a fraction);
- dd_m: fall from the running peak (a fraction);
- age_m: years since the career began.

**Target** (Barber, Lee, Liu, Odean & Zhang 2020, *Learning, Fast or Slow*): 44 %, 24 % and
15 % of day traders still trading after 1, 2 and 3 years (obs., round 27). The data are
Taiwanese stock day traders, not capitalised power traders, so only the direction and speed of
quitting are borrowed; reports say so.

**Identification** (§20.9): three moments cannot pin five coefficients. β2 = −1, β3 = 1 and
β4 = −0.3 per year are fixed by assumption: recent losses, deep drawdowns and youth raise
the hazard.
β0 and β1 are fitted by the method of simulated moments, minimising the squared gaps between
the population's mean survival at 12, 24 and 36 months and the targets, on a population of
losing baseline traders' equity paths. Standard errors come from a bootstrap over traders.

Example:
    >>> import numpy as np
    >>> hazard = QuitHazard(beta=(-3.0, -1.0, -2.0, 3.0, -0.2))
    >>> covariates = monthly_covariates(np.full(400, 1e6), 1e6, np.arange(29, 400, 30))
    >>> round(float(hazard.monthly_hazards(covariates)[0]), 4)
    0.0467
"""

import dataclasses

import numpy as np
from scipy import optimize

TARGET_SURVIVAL = {12: 0.44, 24: 0.24, 36: 0.15}
FIXED_BETAS = {"beta_recent_return": -1.0, "beta_drawdown": 1.0, "beta_age_per_year": -0.3}
# Bounds keep the fit in a plausible region: a baseline hazard between e^−8 and e^1 odds,
# and losses raising (never lowering) the hazard by at most 10 log-odds per 100 % lost.
FREE_BETA_BOUNDS = ((-8.0, -10.0), (1.0, 0.0))
BOOTSTRAP_DRAWS = 200


def logistic(value):
    """1 / (1 + e^−x)."""
    return 1.0 / (1.0 + np.exp(-np.clip(value, -50, 50)))


def survival_curve(monthly_hazards):
    """S_m = Π_{j ≤ m} (1 − h_j)."""
    return np.cumprod(1.0 - np.asarray(monthly_hazards))


def monthly_covariates(equity_usd, starting_capital_usd, month_end_indices):
    """Covariates (cum, r6, dd, age) at each month end; shape (months, 4)."""
    monthly = np.asarray(equity_usd)[month_end_indices]
    path = np.concatenate([[starting_capital_usd], monthly])
    cumulative = monthly / starting_capital_usd - 1
    six_months_ago = path[np.maximum(np.arange(1, len(path)) - 6, 0)]
    recent = path[1:] / six_months_ago - 1
    peaks = np.maximum.accumulate(path)[1:]
    drawdown = 1 - monthly / peaks
    age = np.arange(1, len(monthly) + 1) / 12
    return np.column_stack([cumulative, recent, drawdown, age])


@dataclasses.dataclass(frozen=True)
class QuitHazard:
    """The L3 hazard (see the module docstring).

    Attributes:
        beta: (β0, β1, β2, β3, β4).
        persistence: 0 … 1; a stubborn trader's hazard is multiplied by 1 − persistence.
    """

    beta: tuple
    persistence: float = 0.0

    def monthly_hazards(self, covariates):
        """h_m for each row of covariates (cum, r6, dd, age)."""
        beta = np.asarray(self.beta)
        linear = beta[0] + np.asarray(covariates) @ beta[1:]
        return logistic(linear) * (1 - self.persistence)


@dataclasses.dataclass(frozen=True)
class HazardFit:
    """The fitted L3 hazard and how well it fits.

    Attributes:
        hazard: the QuitHazard.
        fitted_survival: {months: population mean survival} at 12, 24, 36.
        target_survival: the targets.
        standard_errors: (se β0, se β1) from the bootstrap.
        trader_count: paths used.
        fixed: the assumed coefficients.
    """

    hazard: QuitHazard
    fitted_survival: dict
    target_survival: dict
    standard_errors: tuple
    trader_count: int
    fixed: dict


def population_survival(free_beta, covariates_by_trader, horizon_months=36):
    """Mean survival at 12, 24 and 36 months for (β0, β1) with the fixed coefficients."""
    beta = (
        free_beta[0],
        free_beta[1],
        FIXED_BETAS["beta_recent_return"],
        FIXED_BETAS["beta_drawdown"],
        FIXED_BETAS["beta_age_per_year"],
    )
    hazard = QuitHazard(beta)
    curves = np.array(
        [
            survival_curve(hazard.monthly_hazards(covariates[:horizon_months]))
            for covariates in covariates_by_trader
        ]
    )
    return {months: float(curves[:, months - 1].mean()) for months in TARGET_SURVIVAL}


def fit_moments(covariates_by_trader, start=(-2.5, -1.0)):
    """(β0, β1) minimising the squared survival gaps (least squares)."""

    def gaps(free_beta):
        fitted = population_survival(free_beta, covariates_by_trader)
        return [fitted[months] - target for months, target in TARGET_SURVIVAL.items()]

    lower, upper = FREE_BETA_BOUNDS
    start = np.clip(np.array(start, dtype=float), np.array(lower) + 1e-6, np.array(upper) - 1e-6)
    solution = optimize.least_squares(gaps, x0=start, bounds=(lower, upper), method="trf")
    return solution.x


def fit_quit_hazard(covariates_by_trader, seed=0, bootstrap_draws=BOOTSTRAP_DRAWS):
    """Fit β0, β1 to the 44/24/15 % survival targets; bootstrap their standard errors.

    Args:
        covariates_by_trader: list of (months ≥ 36, 4) covariate arrays of losing traders.
        seed: bootstrap seed.
        bootstrap_draws: resamples.

    Returns:
        HazardFit.
    """
    covariates_by_trader = [np.asarray(covariates) for covariates in covariates_by_trader]
    if any(len(covariates) < 36 for covariates in covariates_by_trader):
        raise ValueError("each path needs at least 36 months")
    free = fit_moments(covariates_by_trader)
    generator = np.random.Generator(np.random.PCG64(seed))
    draws = []
    count = len(covariates_by_trader)
    for _ in range(bootstrap_draws):
        sample = [covariates_by_trader[index] for index in generator.integers(count, size=count)]
        draws.append(fit_moments(sample, start=tuple(free)))
    draws = np.array(draws)
    beta = (
        float(free[0]),
        float(free[1]),
        FIXED_BETAS["beta_recent_return"],
        FIXED_BETAS["beta_drawdown"],
        FIXED_BETAS["beta_age_per_year"],
    )
    return HazardFit(
        hazard=QuitHazard(beta),
        fitted_survival=population_survival(free, covariates_by_trader),
        target_survival=dict(TARGET_SURVIVAL),
        standard_errors=(float(draws[:, 0].std(ddof=1)), float(draws[:, 1].std(ddof=1))),
        trader_count=count,
        fixed=dict(FIXED_BETAS),
    )
