"""O8: the search itself treated as an OR problem (`docs/design_spec.md` §20.11).

- **Successive halving** (multi-fidelity racing): score every candidate on a short window,
  keep the best 1/η, score them on a longer one, and so on to the full window. The cost is
  counted in trader-years, so the speed-up against scoring everyone fully is measured.
- **Optimal computing budget allocation** (OCBA; Chen, Lin, Yücesan & Chick 2000): given noisy
  estimates of several elites' fitness, the share of further evaluations each should get to
  maximise the probability of picking the best:
  N_i / N_j = (σ_i/δ_i)² / (σ_j/δ_j)² for non-best i, j (δ = gap to the best),
  N_b = σ_b √(Σ_{i≠b} N_i² / σ_i²).
- **NSGA-II** (Deb et al. 2002): non-dominated sorting and crowding distance over three
  objectives (log growth ↑, maximum drawdown ↓, daily-loss CVaR₉₅ ↓), with the trader operators;
  compared with MAP-Elites by hypervolume (Monte Carlo against a reference point).
- **CMA-ES** (Hansen's tutorial, 2016): a (μ/μ_w, λ) evolution strategy for continuous
  vectors — the trader's numeric genes and constants — usable as a MAP-Elites emitter.

Example:
    >>> import numpy as np
    >>> shares = ocba_allocation(np.array([1.0, 0.9, 0.2]), np.array([0.1, 0.1, 0.1]), 100)
    >>> int(shares.sum()), bool(shares[1] > shares[2])
    (100, True)
"""

import math

import numpy as np


def successive_halving(candidates, score, fidelities, keep_fraction=0.5):
    """Race candidates through increasing fidelities.

    Args:
        candidates: a list of anything `score` accepts.
        score: callable(candidate, fidelity) → fitness (higher is better).
        fidelities: increasing costs (e.g. years of history).
        keep_fraction: share kept at each rung (1/η).

    Returns:
        (survivors with their final scores, total cost = Σ candidates scored × fidelity).
    """
    alive = list(candidates)
    cost = 0.0
    scores = []
    for rung, fidelity in enumerate(fidelities):
        scores = [score(candidate, fidelity) for candidate in alive]
        cost += len(alive) * fidelity
        if rung < len(fidelities) - 1:
            keep = max(1, int(math.ceil(len(alive) * keep_fraction)))
            order = np.argsort(scores)[::-1][:keep]
            alive = [alive[index] for index in order]
    return list(zip(alive, scores)), cost


def ocba_allocation(means, standard_deviations, budget):
    """Integer allocation of `budget` evaluations by OCBA (see the module docstring)."""
    means = np.asarray(means, dtype=float)
    deviations = np.maximum(np.asarray(standard_deviations, dtype=float), 1e-12)
    best = int(np.argmax(means))
    gaps = means[best] - means
    gaps[best] = np.inf
    gaps = np.maximum(gaps, 1e-12)
    ratios = (deviations / gaps) ** 2
    ratios[best] = 0.0
    others = np.arange(len(means)) != best
    ratios[best] = deviations[best] * math.sqrt(np.sum((ratios[others] / deviations[others]) ** 2))
    shares = ratios / ratios.sum()
    allocation = np.floor(shares * budget).astype(int)
    remainder = budget - allocation.sum()
    for index in np.argsort(-(shares * budget - allocation))[:remainder]:
        allocation[index] += 1
    return allocation


def dominates(first, second):
    """True when first is at least as good on every objective and better on one (all maximised)."""
    return np.all(first >= second) and np.any(first > second)


def non_dominated_fronts(objectives):
    """Fast non-dominated sorting: a list of fronts (lists of indices), best first."""
    objectives = np.asarray(objectives, dtype=float)
    count = len(objectives)
    dominated_by = [[] for _ in range(count)]
    domination_count = np.zeros(count, dtype=int)
    fronts = [[]]
    for first in range(count):
        for second in range(count):
            if first == second:
                continue
            if dominates(objectives[first], objectives[second]):
                dominated_by[first].append(second)
            elif dominates(objectives[second], objectives[first]):
                domination_count[first] += 1
        if domination_count[first] == 0:
            fronts[0].append(first)
    while fronts[-1]:
        following = []
        for member in fronts[-1]:
            for other in dominated_by[member]:
                domination_count[other] -= 1
                if domination_count[other] == 0:
                    following.append(other)
        fronts.append(following)
    return fronts[:-1]


def crowding_distance(objectives):
    """Crowding distance of each point within one front."""
    objectives = np.asarray(objectives, dtype=float)
    count, dimensions = objectives.shape
    distance = np.zeros(count)
    if count <= 2:
        return np.full(count, np.inf)
    for dimension in range(dimensions):
        order = np.argsort(objectives[:, dimension])
        span = objectives[order[-1], dimension] - objectives[order[0], dimension] or 1.0
        distance[order[0]] = distance[order[-1]] = np.inf
        for position in range(1, count - 1):
            distance[order[position]] += (
                objectives[order[position + 1], dimension]
                - objectives[order[position - 1], dimension]
            ) / span
    return distance


def nsga2(initial, evaluate, vary, generations, generator):
    """NSGA-II: (μ + μ) selection by front rank, then crowding distance.

    Args:
        initial: the first population (any objects).
        evaluate: callable(member) → objective vector (all maximised).
        vary: callable(parent, partner, generator) → child.
        generations: rounds.
        generator: a seeded NumPy generator.

    Returns:
        (population, objectives) of the final generation.
    """
    population = list(initial)
    objectives = [np.asarray(evaluate(member), dtype=float) for member in population]
    size = len(population)
    for _ in range(generations):
        ranks, crowding = rank_and_crowding(objectives)

        def tournament():
            first, second = generator.integers(size, size=2)
            better = (
                first
                if (ranks[first], -crowding[first]) < (ranks[second], -crowding[second])
                else second
            )
            return population[better]

        children = [vary(tournament(), tournament(), generator) for _ in range(size)]
        children_objectives = [np.asarray(evaluate(child), dtype=float) for child in children]
        merged = population + children
        merged_objectives = objectives + children_objectives
        chosen = []
        for front in non_dominated_fronts(merged_objectives):
            if len(chosen) + len(front) <= size:
                chosen.extend(front)
            else:
                distance = crowding_distance([merged_objectives[index] for index in front])
                order = np.argsort(-distance)
                chosen.extend(front[index] for index in order[: size - len(chosen)])
                break
        population = [merged[index] for index in chosen]
        objectives = [merged_objectives[index] for index in chosen]
    return population, objectives


def rank_and_crowding(objectives):
    """Front rank and crowding distance of every member."""
    ranks = np.zeros(len(objectives), dtype=int)
    crowding = np.zeros(len(objectives))
    for rank, front in enumerate(non_dominated_fronts(objectives)):
        ranks[front] = rank
        crowding[front] = crowding_distance([objectives[index] for index in front])
    return ranks, crowding


def hypervolume(points, reference, samples=20_000, seed=0):
    """Monte Carlo hypervolume dominated by points (all maximised) above a reference point."""
    points = np.asarray(points, dtype=float)
    reference = np.asarray(reference, dtype=float)
    points = points[np.all(points > reference, axis=1)]
    if len(points) == 0:
        return 0.0
    upper = points.max(axis=0)
    generator = np.random.Generator(np.random.PCG64(seed))
    draws = generator.uniform(reference, upper, size=(samples, len(reference)))
    covered = np.zeros(samples, dtype=bool)
    for point in points:
        covered |= np.all(draws <= point, axis=1)
    return float(covered.mean() * np.prod(upper - reference))


def cma_es(objective, start, step, iterations=200, population=None, seed=0):
    """Minimise objective(x) by CMA-ES (rank-μ and rank-one updates, cumulative step size).

    Returns:
        (best x, best value).
    """
    generator = np.random.Generator(np.random.PCG64(seed))
    dimension = len(start)
    population = population or 4 + int(3 * math.log(dimension))
    parents = population // 2
    weights = math.log(parents + 0.5) - np.log(np.arange(1, parents + 1))
    weights /= weights.sum()
    effective = 1 / np.sum(weights**2)
    step_learning_rate = (effective + 2) / (dimension + effective + 5)
    step_damping = (
        1 + 2 * max(0, math.sqrt((effective - 1) / (dimension + 1)) - 1) + step_learning_rate
    )
    path_learning_rate = (4 + effective / dimension) / (dimension + 4 + 2 * effective / dimension)
    rank_one_rate = 2 / ((dimension + 1.3) ** 2 + effective)
    rank_many_rate = min(
        1 - rank_one_rate, 2 * (effective - 2 + 1 / effective) / ((dimension + 2) ** 2 + effective)
    )
    expected_norm = math.sqrt(dimension) * (1 - 1 / (4 * dimension) + 1 / (21 * dimension**2))
    mean = np.asarray(start, dtype=float)
    sigma = float(step)
    covariance = np.eye(dimension)
    path_sigma = np.zeros(dimension)
    covariance_path = np.zeros(dimension)
    best_point, best_value = mean.copy(), objective(mean)
    for generation in range(iterations):
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        eigenvalues = np.maximum(eigenvalues, 1e-20)
        root = eigenvectors @ np.diag(np.sqrt(eigenvalues)) @ eigenvectors.T
        inverse_root = eigenvectors @ np.diag(1 / np.sqrt(eigenvalues)) @ eigenvectors.T
        steps = generator.standard_normal((population, dimension)) @ root.T
        candidates = mean + sigma * steps
        values = np.array([objective(candidate) for candidate in candidates])
        order = np.argsort(values)
        if values[order[0]] < best_value:
            best_point, best_value = candidates[order[0]].copy(), float(values[order[0]])
        selected = steps[order[:parents]]
        weighted_step = weights @ selected
        mean = mean + sigma * weighted_step
        path_sigma = (1 - step_learning_rate) * path_sigma + math.sqrt(
            step_learning_rate * (2 - step_learning_rate) * effective
        ) * (inverse_root @ weighted_step)
        is_stalled = np.linalg.norm(path_sigma) / math.sqrt(
            1 - (1 - step_learning_rate) ** (2 * (generation + 1))
        ) / expected_norm < 1.4 + 2 / (dimension + 1)
        covariance_path = (1 - path_learning_rate) * covariance_path + is_stalled * math.sqrt(
            path_learning_rate * (2 - path_learning_rate) * effective
        ) * weighted_step
        rank_many_update = (selected.T * weights) @ selected
        covariance = (
            (1 - rank_one_rate - rank_many_rate) * covariance
            + rank_one_rate
            * (
                np.outer(covariance_path, covariance_path)
                + (1 - is_stalled) * path_learning_rate * (2 - path_learning_rate) * covariance
            )
            + rank_many_rate * rank_many_update
        )
        sigma *= math.exp(
            (step_learning_rate / step_damping) * (np.linalg.norm(path_sigma) / expected_norm - 1)
        )
    return best_point, best_value
