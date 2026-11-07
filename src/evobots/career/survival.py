"""O6: survival statistics of traders' careers (`docs/design_spec.md` §20.9).

- **Kaplan–Meier:** S(t) = Π_{t_i ≤ t} (1 − d_i / n_i), with Greenwood's variance.
- **Cox proportional hazards:** h(t | x) = h₀(t)·exp(β·x), fitted by Newton–Raphson on the
  Breslow partial likelihood; standard errors from the inverse information.
- **Proportional-hazards check:** for each covariate, the correlation between its Schoenfeld
  residual and the rank of the event time, with a t-test (a simplified Grambsch–Therneau test).

Example:
    >>> times, survival, _ = kaplan_meier([1, 2, 2, 3], [1, 1, 0, 1])
    >>> times.tolist(), [round(float(value), 4) for value in survival]
    ([1.0, 2.0, 3.0], [0.75, 0.5, 0.0])
"""

import math

import numpy as np
from scipy import stats

NEWTON_STEPS = 50


def kaplan_meier(durations, events):
    """(event times, survival, Greenwood variance) from durations and event flags (1 = died)."""
    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=int)
    times = np.unique(durations[events == 1])
    survival, variance_sum, curve, variances = 1.0, 0.0, [], []
    for time in times:
        at_risk = int((durations >= time).sum())
        deaths = int(((durations == time) & (events == 1)).sum())
        survival *= 1 - deaths / at_risk
        if at_risk > deaths:
            variance_sum += deaths / (at_risk * (at_risk - deaths))
        curve.append(survival)
        variances.append(survival**2 * variance_sum)
    return times, np.array(curve), np.array(variances)


def cox_proportional_hazards(durations, events, covariates):
    """β, standard errors and log partial likelihood of a Cox model (Breslow ties).

    Args:
        durations: time to death or censoring.
        events: 1 = died, 0 = censored.
        covariates: (n, p) array.

    Returns:
        (beta, standard_errors, log_likelihood).
    """
    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=int)
    covariates = np.asarray(covariates, dtype=float)
    if covariates.ndim == 1:
        covariates = covariates[:, None]
    order = np.argsort(-durations, kind="stable")
    durations, events, covariates = durations[order], events[order], covariates[order]
    beta = np.zeros(covariates.shape[1])
    log_likelihood = -math.inf
    for _ in range(NEWTON_STEPS):
        risk = np.exp(covariates @ beta)
        gradient = np.zeros_like(beta)
        information = np.zeros((len(beta), len(beta)))
        log_likelihood = 0.0
        for time in np.unique(durations[events == 1]):
            in_risk_set = durations >= time
            dying = (durations == time) & (events == 1)
            deaths = int(dying.sum())
            weight = risk[in_risk_set]
            total = weight.sum()
            mean = (covariates[in_risk_set] * weight[:, None]).sum(axis=0) / total
            second = (covariates[in_risk_set].T * weight) @ covariates[in_risk_set] / total
            gradient += covariates[dying].sum(axis=0) - deaths * mean
            information += deaths * (second - np.outer(mean, mean))
            log_likelihood += float((covariates[dying] @ beta).sum() - deaths * math.log(total))
        step = np.linalg.solve(information, gradient)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            break
    standard_errors = np.sqrt(np.diag(np.linalg.inv(information)))
    return beta, standard_errors, log_likelihood


def schoenfeld_test(durations, events, covariates, beta):
    """Per covariate: (correlation of Schoenfeld residuals with event-time rank, p-value)."""
    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=int)
    covariates = np.asarray(covariates, dtype=float)
    if covariates.ndim == 1:
        covariates = covariates[:, None]
    risk = np.exp(covariates @ np.asarray(beta))
    residuals, event_times = [], []
    for index in np.flatnonzero(events == 1):
        in_risk_set = durations >= durations[index]
        weight = risk[in_risk_set]
        expected = (covariates[in_risk_set] * weight[:, None]).sum(axis=0) / weight.sum()
        residuals.append(covariates[index] - expected)
        event_times.append(durations[index])
    residuals = np.array(residuals)
    ranks = stats.rankdata(event_times)
    results = []
    for column in range(residuals.shape[1]):
        correlation = float(np.corrcoef(residuals[:, column], ranks)[0, 1])
        count = len(ranks)
        student_statistic = correlation * math.sqrt((count - 2) / max(1 - correlation**2, 1e-12))
        results.append((correlation, float(2 * stats.t.sf(abs(student_statistic), count - 2))))
    return results
