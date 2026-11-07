"""Mutation, crossover and the adaptive choice of operator (`docs/design_spec.md` §9.6).

- subtree: replace a random subtree of a slot by a new random tree of the same kind and unit (PTC2)
- point: swap one node for another of the same type and arity: `+`↔`−`, `min`↔`max`, `>`↔`<`,
  `and`↔`or`, a feature for another of the same unit; add or remove one member of a category set
- hoist: replace a subtree by one of its own subtrees of the same kind and unit (removes code)
- crossover: size-fair crossover (Langdon 2000): a subtree of one parent replaced by a type- and
  unit-matched subtree of similar size from the same slot of the other
- constant (2 %, 10 %, 30 %): Gaussian step on one constant, σ = step × its unit's range width,
  clipped; for the numeric genes, iso+line-DD (Vassiliades & Mouret 2018): x + σ_iso·w·N(0,1) +
  σ_line·(y − x)·N(0,1) with y another elite

**Never mutated:** the hard caps, the skeleton, the type and unit system.

**Adaptive operator choice** (round 20; Thierens 2005 adaptive pursuit / probability
matching, Cully 2021 bandits in MAP-Elites): each arm keeps a quality q, updated
q ← q + α(r − q) with reward r = 1 when its child enters or improves the archive, and is chosen
with probability p_min + (1 − K·p_min) · q / Σq, so every operator keeps at least 5 %.
Starting weights: subtree 0.25, point 0.20, constant 0.30 (0.10 per step size), hoist 0.10,
crossover 0.15. Draws use the run's seeded generator, so runs stay byte-reproducible.

Example:
    >>> import numpy as np
    >>> from evobots.bots.founders import FOUNDERS
    >>> from evobots.bots.random_trees import ConstantRanges
    >>> generator = np.random.Generator(np.random.PCG64(2))
    >>> ranges = ConstantRanges.from_catalogue()
    >>> child, operator = vary(FOUNDERS["heat_dec"], generator, ranges, "subtree")
    >>> operator, child != FOUNDERS["heat_dec"]
    ('subtree', True)
"""

import dataclasses

import numpy as np

from evobots.bots.grammar import (
    BOOL,
    NUMBER,
    Binary,
    Compare,
    Constant,
    Feature,
    Logic,
    Member,
    kind_of,
    node_at,
    nodes_with_paths,
    replace_at,
    size,
    unit_of,
)
from evobots.bots.random_trees import NUMBER_FEATURES, random_tree
from evobots.bots.trader import GENE_NAMES, GENE_RANGES, MAX_SLOT_SIZE, SLOT_NAMES, Genome
from evobots.features.catalogue import FEATURE_BY_NAME

INITIAL_OPERATOR_WEIGHTS = {
    "subtree": 0.25,
    "point": 0.20,
    "constant_small": 0.10,
    "constant_medium": 0.10,
    "constant_large": 0.10,
    "hoist": 0.10,
    "crossover": 0.15,
}
CONSTANT_STEP_BY_OPERATOR = {
    "constant_small": 0.02,
    "constant_medium": 0.10,
    "constant_large": 0.30,
}
OPERATOR_FLOOR_PROBABILITY = 0.05
OPERATOR_LEARNING_RATE = 0.1
# iso+line-DD: the line step σ_line (Vassiliades & Mouret 2018 use 0.2).
LINE_STEP = 0.2
# Most new subtrees are small: target size uniform in 1 … this (and within the slot limit).
SUBTREE_MAX_TARGET_SIZE = 7
ATTEMPTS = 10


def slot_type(node):
    """(kind, unit) of a node; unit None for conditions."""
    kind = kind_of(node)
    return kind, (unit_of(node) if kind == NUMBER else None)


def choose_slot(generator, genome, is_weighted_by_size=True):
    """A slot name, chosen with probability proportional to its size (or uniformly)."""
    weights = np.array([size(getattr(genome, name)) for name in SLOT_NAMES], dtype=float)
    if not is_weighted_by_size:
        weights = np.ones(len(SLOT_NAMES))
    return SLOT_NAMES[int(generator.choice(len(SLOT_NAMES), p=weights / weights.sum()))]


def with_slot(genome, name, tree):
    """A genome with one slot replaced, or None if it breaks the size limit or the types."""
    if size(tree) > MAX_SLOT_SIZE:
        return None
    try:
        return dataclasses.replace(genome, **{name: tree})
    except ValueError:
        return None


def subtree_mutation(genome, generator, ranges):
    """Replace a random subtree by a new random tree of the same kind and unit."""
    for _ in range(ATTEMPTS):
        name = choose_slot(generator, genome)
        tree = getattr(genome, name)
        paths = [path for path, _ in nodes_with_paths(tree)]
        path = paths[int(generator.integers(len(paths)))]
        old = node_at(tree, path)
        room = MAX_SLOT_SIZE - (size(tree) - size(old))
        target = int(generator.integers(1, max(1, min(SUBTREE_MAX_TARGET_SIZE, room)) + 1))
        kind, unit = slot_type(old)
        replacement = random_tree(generator, ranges, kind, unit, target_size=target, max_size=room)
        child = with_slot(genome, name, replace_at(tree, path, replacement))
        if child is not None and child != genome:
            return child
    return None


def point_alternatives(node):
    """Same-type, same-arity replacements of one node (without changing its children)."""
    if isinstance(node, Binary):
        groups = [("+", "-"), ("min", "max")]
        for group in groups:
            if node.operator in group:
                return [
                    dataclasses.replace(node, operator=other)
                    for other in group
                    if other != node.operator
                ]
        if unit_of(node.right).is_dimensionless():
            other = "/" if node.operator == "*" else "*"
            return [dataclasses.replace(node, operator=other)]
        return []
    if isinstance(node, Compare):
        return [dataclasses.replace(node, operator="<" if node.operator == ">" else ">")]
    if isinstance(node, Logic):
        return [dataclasses.replace(node, operator="or" if node.operator == "and" else "and")]
    if isinstance(node, Feature):
        unit = FEATURE_BY_NAME[node.name].unit
        return [
            Feature(other.name)
            for other in NUMBER_FEATURES
            if other.unit == unit and other.name != node.name
        ]
    if isinstance(node, Member):
        categories = FEATURE_BY_NAME[node.feature].categories
        alternatives = []
        for category in categories:
            members = set(node.members) ^ {category}
            if members and len(members) < len(categories):
                alternatives.append(Member(node.feature, tuple(sorted(members))))
        return alternatives
    return []


def point_mutation(genome, generator):
    """Swap one node for a same-type, same-arity alternative (see `point_alternatives`)."""
    candidates = []
    for name in SLOT_NAMES:
        for path, node in nodes_with_paths(getattr(genome, name)):
            if point_alternatives(node):
                candidates.append((name, path, node))
    if not candidates:
        return None
    name, path, node = candidates[int(generator.integers(len(candidates)))]
    options = point_alternatives(node)
    replacement = options[int(generator.integers(len(options)))]
    return with_slot(genome, name, replace_at(getattr(genome, name), path, replacement))


def hoist_mutation(genome, generator):
    """Replace a subtree by one of its own same-kind, same-unit subtrees."""
    candidates = []
    for name in SLOT_NAMES:
        tree = getattr(genome, name)
        for path, node in nodes_with_paths(tree):
            wanted = slot_type(node)
            for inner_path, inner in nodes_with_paths(node):
                if inner_path and slot_type(inner) == wanted:
                    candidates.append((name, path, inner))
    if not candidates:
        return None
    name, path, inner = candidates[int(generator.integers(len(candidates)))]
    return with_slot(genome, name, replace_at(getattr(genome, name), path, inner))


def size_fair_crossover(first, second, generator):
    """A child of `first` with one subtree replaced by a matched subtree of `second`.

    Size-fair (Langdon 2000): the donor subtree has the same kind and unit, comes from the
    same slot, and is at most 1 + 2 × the size of the subtree it replaces; donors closer in
    size are more likely.
    """
    for _ in range(ATTEMPTS):
        name = choose_slot(generator, first)
        receiver_tree = getattr(first, name)
        paths = [path for path, _ in nodes_with_paths(receiver_tree)]
        path = paths[int(generator.integers(len(paths)))]
        replaced = node_at(receiver_tree, path)
        wanted = slot_type(replaced)
        limit = 1 + 2 * size(replaced)
        donors = [
            node
            for _, node in nodes_with_paths(getattr(second, name))
            if slot_type(node) == wanted and size(node) <= limit and node != replaced
        ]
        if not donors:
            continue
        weights = np.array([1.0 / (1 + abs(size(node) - size(replaced))) for node in donors])
        donor = donors[int(generator.choice(len(donors), p=weights / weights.sum()))]
        child = with_slot(first, name, replace_at(receiver_tree, path, donor))
        if child is not None and child != first:
            return child
    return None


def clip_gene(name, value):
    """A gene value clipped to its range (pause_days rounded to an integer)."""
    low, high = GENE_RANGES[name]
    value = float(np.clip(value, low, high))
    return int(round(value)) if name == "pause_days" else value


def constant_mutation(genome, generator, ranges, step, partner=None):
    """A Gaussian step on one tree constant, or iso+line-DD on the numeric genes."""
    tree_constants = [
        (name, path, node)
        for name in SLOT_NAMES
        for path, node in nodes_with_paths(getattr(genome, name))
        if isinstance(node, Constant)
    ]
    gene_share = len(GENE_NAMES) / (len(GENE_NAMES) + len(tree_constants))
    if not tree_constants or generator.random() < min(gene_share, 0.5):
        genes = genome.genes()
        changed = {}
        for gene in GENE_NAMES:
            low, high = GENE_RANGES[gene]
            width = high - low
            value = genes[gene] + step * width * generator.standard_normal()
            if partner is not None:
                value += (
                    LINE_STEP * (partner.genes()[gene] - genes[gene]) * generator.standard_normal()
                )
            changed[gene] = clip_gene(gene, value)
        return dataclasses.replace(genome, **changed)
    name, path, node = tree_constants[int(generator.integers(len(tree_constants)))]
    low, high = ranges.range_for(node.unit)
    value = node.value + step * ranges.width(node.unit) * generator.standard_normal()
    replacement = Constant(
        float(np.clip(value, min(low, node.value), max(high, node.value))), node.unit
    )
    return with_slot(genome, name, replace_at(getattr(genome, name), path, replacement))


def vary(genome, generator, ranges, operator, partner=None):
    """Apply one operator; returns (child, operator). Falls back to a constant step."""
    child = None
    if operator == "subtree":
        child = subtree_mutation(genome, generator, ranges)
    elif operator == "point":
        child = point_mutation(genome, generator)
    elif operator == "hoist":
        child = hoist_mutation(genome, generator)
    elif operator == "crossover" and partner is not None:
        child = size_fair_crossover(genome, partner, generator)
    elif operator in CONSTANT_STEP_BY_OPERATOR:
        child = constant_mutation(
            genome, generator, ranges, CONSTANT_STEP_BY_OPERATOR[operator], partner
        )
    if child is None or child == genome:
        operator = "constant_medium"
        child = constant_mutation(genome, generator, ranges, 0.10, partner)
    return child, operator


@dataclasses.dataclass
class OperatorBandit:
    """Adaptive operator choice (probability matching with a floor; see the docstring)."""

    quality: dict = dataclasses.field(default_factory=lambda: dict(INITIAL_OPERATOR_WEIGHTS))
    tries: dict = dataclasses.field(
        default_factory=lambda: {name: 0 for name in INITIAL_OPERATOR_WEIGHTS}
    )
    successes: dict = dataclasses.field(
        default_factory=lambda: {name: 0 for name in INITIAL_OPERATOR_WEIGHTS}
    )

    def probabilities(self):
        """{operator: probability of being chosen}."""
        total = sum(self.quality.values()) or 1.0
        count = len(self.quality)
        return {
            name: OPERATOR_FLOOR_PROBABILITY
            + (1 - count * OPERATOR_FLOOR_PROBABILITY) * quality / total
            for name, quality in self.quality.items()
        }

    def choose(self, generator):
        """Draw an operator."""
        probabilities = self.probabilities()
        names = list(probabilities)
        weights = np.array([probabilities[name] for name in names])
        return names[int(generator.choice(len(names), p=weights / weights.sum()))]

    def reward(self, operator, is_success):
        """Update an operator's quality after its child was judged."""
        if operator not in self.quality:
            return
        self.tries[operator] += 1
        self.successes[operator] += int(is_success)
        self.quality[operator] += OPERATOR_LEARNING_RATE * (
            float(is_success) - self.quality[operator]
        )

    def success_rates(self):
        """{operator: (successes, tries)} for the Evolution page."""
        return {name: (self.successes[name], self.tries[name]) for name in self.quality}


def random_genome(generator, ranges):
    """A random trader: PTC2 slots (where/when often empty) and uniform genes."""
    from evobots.bots.trader import empty_condition
    from evobots.units import USD_PER_MWH

    where = (
        empty_condition()
        if generator.random() < 0.4
        else random_tree(generator, ranges, BOOL, max_size=MAX_SLOT_SIZE)
    )
    when = (
        empty_condition()
        if generator.random() < 0.4
        else random_tree(generator, ranges, BOOL, max_size=MAX_SLOT_SIZE)
    )
    score = random_tree(generator, ranges, NUMBER, USD_PER_MWH, max_size=MAX_SLOT_SIZE)
    genes = {}
    for gene in GENE_NAMES:
        low, high = GENE_RANGES[gene]
        genes[gene] = clip_gene(gene, generator.uniform(low, high))
    genes["pause_days"] = int(generator.integers(0, 4)) if generator.random() < 0.3 else 0
    return Genome(where, when, score, **genes)
