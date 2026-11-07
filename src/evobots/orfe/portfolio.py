"""O3: a portfolio of elites instead of one trader (`docs/design_spec.md` §20.6).

Data: R, a (T, m) matrix of the elites' daily returns on the training window (each elite
at its own sizing). Capital is split with weights w ≥ 0, Σ w = 1, so the portfolio's daily
return is R·w. Because every elite already respects each hub's MW cap, a convex combination
does too: the combined net position |Σ w_i q_i| ≤ Σ w_i |q_i| ≤ cap.

- mean-CVaR: max mean(R·w) − λ·CVaR_α(−R·w) (an LP, Rockafellar–Uryasev)
- mean-variance: max mean(R·w) − (γ/2)·wᵀΣw (a QP)
- growth-optimal: max Σ_t ln(1 + R_t·w) (concave), and fractional Kelly: a share of it, the rest in
  cash
- risk parity: equal risk contributions w_i(Σw)_i (iterative)
- equal weight, best single elite: baselines

Protocol (§20.6): re-optimise every month on the trailing window, apply the weights to the next
month (walk-forward), and count the portfolio as one more selection step in the trial count.
Netting saves fees: one trader's opposite positions at a node net before Schedules 17/24 and
DA RSG are charged (`market_rules.md` §3.2); `netting_fee_saving` measures it.

Example:
    >>> import numpy as np
    >>> returns = np.array([[0.01, -0.01], [-0.01, 0.01], [0.01, -0.01], [-0.01, 0.01]])
    >>> weights = mean_variance_weights(returns, risk_aversion=10.0)
    >>> [round(float(w), 3) for w in weights]
    [0.5, 0.5]
"""

import numpy as np
from scipy import optimize, sparse

RISK_PARITY_ITERATIONS = 500


def mean_cvar_weights(returns, risk_aversion=1.0, alpha=0.95):
    """Max mean(R·w) − λ CVaR_α(−R·w), w ≥ 0, Σ w = 1 (an LP)."""
    returns = np.asarray(returns, dtype=float)
    days, assets = returns.shape
    objective = np.concatenate(
        [
            -returns.mean(axis=0),
            [risk_aversion],
            np.full(days, risk_aversion / ((1 - alpha) * days)),
        ]
    )
    # −R_t·w − ζ − u_t ≤ 0
    inequality = sparse.hstack(
        [
            sparse.csr_matrix(-returns),
            sparse.csr_matrix(-np.ones((days, 1))),
            -sparse.identity(days, format="csr"),
        ]
    )
    equality = sparse.csr_matrix(np.concatenate([np.ones(assets), np.zeros(1 + days)])[None, :])
    bounds = [(0, 1)] * assets + [(None, None)] + [(0, None)] * days
    result = optimize.linprog(
        objective,
        A_ub=inequality,
        b_ub=np.zeros(days),
        A_eq=equality,
        b_eq=[1.0],
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise RuntimeError(result.message)
    return result.x[:assets]


def mean_variance_weights(returns, risk_aversion=10.0):
    """Max mean(R·w) − (γ/2) wᵀΣw, w ≥ 0, Σ w = 1."""
    returns = np.asarray(returns, dtype=float)
    mean = returns.mean(axis=0)
    covariance = (
        np.cov(returns, rowvar=False) if returns.shape[1] > 1 else np.array([[returns.var(ddof=1)]])
    )
    assets = returns.shape[1]

    # Daily returns are ~1e-3: rescale so the solver's tolerances bite.
    scale = 1.0 / max(float(np.abs(mean).max()), float(np.abs(covariance).max()), 1e-12)

    def loss(weights):
        return scale * (-(mean @ weights) + risk_aversion / 2 * weights @ covariance @ weights)

    def gradient(weights):
        return scale * (-mean + risk_aversion * covariance @ weights)

    result = optimize.minimize(
        loss,
        np.full(assets, 1 / assets),
        jac=gradient,
        bounds=[(0, 1)] * assets,
        constraints=[
            {
                "type": "eq",
                "fun": lambda weights: weights.sum() - 1,
                "jac": lambda weights: np.ones(assets),
            }
        ],
        method="SLSQP",
        options={"ftol": 1e-14, "maxiter": 500},
    )
    return np.clip(result.x, 0, 1) / np.clip(result.x, 0, 1).sum()


def growth_optimal_weights(returns, kelly_fraction=1.0):
    """Max Σ ln(1 + R_t·w), w ≥ 0, Σ w ≤ 1; then scaled by kelly_fraction (rest in cash)."""
    returns = np.asarray(returns, dtype=float)
    assets = returns.shape[1]

    def loss(weights):
        growth = 1 + returns @ weights
        if np.any(growth <= 0):
            return 1e12
        return -np.log(growth).sum()

    def gradient(weights):
        growth = 1 + returns @ weights
        return -(returns / growth[:, None]).sum(axis=0)

    result = optimize.minimize(
        loss,
        np.full(assets, 1 / (2 * assets)),
        jac=gradient,
        bounds=[(0, 1)] * assets,
        constraints=[
            {
                "type": "ineq",
                "fun": lambda weights: 1 - weights.sum(),
                "jac": lambda weights: -np.ones(assets),
            }
        ],
        method="SLSQP",
    )
    return np.clip(result.x, 0, 1) * kelly_fraction


def risk_parity_weights(returns):
    """Equal risk contributions w_i (Σw)_i, by multiplicative updates."""
    returns = np.asarray(returns, dtype=float)
    covariance = (
        np.cov(returns, rowvar=False) if returns.shape[1] > 1 else np.array([[returns.var(ddof=1)]])
    )
    covariance = covariance + 1e-12 * np.eye(len(covariance))
    weights = np.full(len(covariance), 1 / len(covariance))
    for _ in range(RISK_PARITY_ITERATIONS):
        contributions = weights * (covariance @ weights)
        target = contributions.mean()
        weights = weights * np.sqrt(target / np.maximum(contributions, 1e-18))
        weights /= weights.sum()
    return weights


def walk_forward(returns, weight_function, refit_days=30, training_days=365):
    """Portfolio returns re-optimised every refit_days on the trailing training_days.

    Returns:
        (out-of-sample daily returns from day training_days on, list of weight vectors).
    """
    returns = np.asarray(returns, dtype=float)
    out_of_sample, weights_over_time = [], []
    for start in range(training_days, len(returns), refit_days):
        weights = weight_function(returns[start - training_days : start])
        weights_over_time.append(weights)
        out_of_sample.append(returns[start : start + refit_days] @ weights)
    return (np.concatenate(out_of_sample) if out_of_sample else np.array([])), weights_over_time


def netting_fee_saving(positions_by_elite, weights, admin_usd_per_mwh):
    """Fees saved by netting: admin·(Σ_i w_i|q_i| − |Σ_i w_i q_i|), summed (USD).

    Args:
        positions_by_elite: (m, days, 24, locations) cleared signed MW (+ DEC, − INC).
        weights: (m,).
        admin_usd_per_mwh: the administration fee rate.
    """
    weighted = np.tensordot(weights, positions_by_elite, axes=1)
    gross = np.tensordot(weights, np.abs(positions_by_elite), axes=1)
    return float(admin_usd_per_mwh * (gross - np.abs(weighted)).sum())


def frontier(returns, risk_aversions=(0.0, 0.5, 1.0, 2.0, 5.0, 10.0), alpha=0.95):
    """Points (λ, mean daily return, CVaR) of the mean-CVaR frontier."""
    points = []
    for risk_aversion in risk_aversions:
        weights = mean_cvar_weights(returns, risk_aversion, alpha)
        portfolio = np.asarray(returns) @ weights
        losses = -portfolio
        threshold = np.quantile(losses, alpha)
        points.append(
            (risk_aversion, float(portfolio.mean()), float(losses[losses >= threshold].mean()))
        )
    return points
