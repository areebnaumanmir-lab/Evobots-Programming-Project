"""Random well-typed trees by PTC2, and the ranges constants are drawn from.

**PTC2** (Luke 2000, *IEEE Trans. Evol. Comput.* 4(3)) builds a tree of a chosen size: pick a
target size, start from a random function node, keep filling a random open child slot with
another function node until the nodes plus open slots reach the target, then fill every
remaining slot with a terminal. Target sizes are drawn uniformly up to the slot limit, so
sizes spread evenly (decided round 20), which ramped half-and-half does not achieve.

**Types and units:** a slot asks for a Bool or a Number of a given unit. Function choices
that can't make that unit aren't offered; `×` and `÷` pick one factor's unit from the
catalogue's feature units, so the other factor gets the derived unit (usually a constant,
e.g. 0.4 $/MWh/(°F·day) × cdd_fcst).

**Constant ranges** come from the feature store's measured quantiles (5th–95th percentile
of every feature with that unit) when available, else from the catalogue's typical ranges.
A derived unit's range is its magnitude (product or quotient of the named units') ±2×.

Example:
    >>> import numpy as np
    >>> generator = np.random.Generator(np.random.PCG64(1))
    >>> ranges = ConstantRanges.from_catalogue()
    >>> tree = random_tree(generator, ranges, NUMBER, USD_PER_MWH, target_size=5)
    >>> unit_of(tree) == USD_PER_MWH and size(tree) <= 7
    True
"""

import dataclasses

from evobots.bots.grammar import (
    BOOL,
    NUMBER,
    Absolute,
    Binary,
    Compare,
    Constant,
    Feature,
    Flag,
    IfElse,
    Logic,
    Member,
    Negate,
    size,
    unit_of,  # noqa: F401  (used in the doctest)
)
from evobots.features.catalogue import FEATURE_BY_NAME, FEATURES
from evobots.units import FRACTION, USD_PER_MWH  # noqa: F401  (USD_PER_MWH: doctest)

NUMBER_FEATURES = tuple(feature for feature in FEATURES if feature.kind == "number")
CATEGORY_FEATURES = tuple(feature for feature in FEATURES if feature.kind == "category")
BOOLEAN_FEATURES = tuple(feature for feature in FEATURES if feature.kind == "boolean")
FEATURE_UNITS = tuple(
    sorted({feature.unit for feature in NUMBER_FEATURES}, key=lambda unit: unit.code())
)
# Relative chances of each function when a slot is filled (illustrative weights, chosen so
# trees mix arithmetic and comparisons; the search decides what survives).
NUMBER_FUNCTION_WEIGHTS = {
    "+": 2,
    "-": 2,
    "*": 3,
    "/": 1,
    "min": 1,
    "max": 1,
    "abs": 0.5,
    "if": 0.5,
}
BOOL_FUNCTION_WEIGHTS = {"compare": 4, "and": 2, "or": 1, "not": 0.5}
# Chance that a terminal of a feature's unit is the feature rather than a constant.
FEATURE_TERMINAL_CHANCE = 0.7
# Chance that a comparison's right side is a constant (thresholds are the common case).
CONSTANT_THRESHOLD_CHANCE = 0.8
# Constants of derived units range over ± this many magnitudes.
DERIVED_RANGE_MAGNITUDES = 2.0


@dataclasses.dataclass(frozen=True)
class ConstantRanges:
    """(low, high) for constants of each named unit; magnitudes for derived ones."""

    range_by_unit: dict

    @classmethod
    def from_catalogue(cls):
        """Ranges from the catalogue's typical ranges (before data is measured)."""
        return cls.from_feature_ranges(
            {feature.name: feature.typical_range for feature in NUMBER_FEATURES}
        )

    @classmethod
    def from_summary(cls, summary):
        """Ranges from `features.store.feature_summary` (5th–95th percentiles)."""
        feature_ranges = {}
        for feature in NUMBER_FEATURES:
            entry = summary.get(feature.name, {})
            if "p5" in entry and entry["p95"] > entry["p5"]:
                feature_ranges[feature.name] = (entry["p5"], entry["p95"])
            else:
                feature_ranges[feature.name] = feature.typical_range
        return cls.from_feature_ranges(feature_ranges)

    @classmethod
    def from_feature_ranges(cls, range_by_feature):
        """Merge per-feature ranges into per-unit ranges."""
        by_unit = {}
        for name, (low, high) in range_by_feature.items():
            unit = FEATURE_BY_NAME[name].unit
            if unit in by_unit:
                by_unit[unit] = (min(by_unit[unit][0], low), max(by_unit[unit][1], high))
            else:
                by_unit[unit] = (low, high)
        by_unit.setdefault(FRACTION, (0.0, 1.0))
        return cls(by_unit)

    def magnitude(self, unit):
        """A typical size of a quantity in `unit` (> 0)."""
        if unit in self.range_by_unit:
            low, high = self.range_by_unit[unit]
            return max(abs(low), abs(high), 1e-6)
        for top, top_range in self.range_by_unit.items():
            for bottom in self.range_by_unit:
                if top / bottom == unit:
                    return self.magnitude(top) / self.magnitude(bottom)
                if top * bottom == unit:
                    return self.magnitude(top) * self.magnitude(bottom)
        return 1.0

    def range_for(self, unit):
        """(low, high) for a constant of this unit."""
        if unit in self.range_by_unit:
            return self.range_by_unit[unit]
        magnitude = self.magnitude(unit)
        return (-DERIVED_RANGE_MAGNITUDES * magnitude, DERIVED_RANGE_MAGNITUDES * magnitude)

    def width(self, unit):
        """Width of the range (the scale of mutation steps)."""
        low, high = self.range_for(unit)
        return max(high - low, 1e-9)


def random_constant(generator, ranges, unit):
    """A constant drawn uniformly from its unit's range."""
    low, high = ranges.range_for(unit)
    return Constant(float(generator.uniform(low, high)), unit)


def features_with_unit(unit):
    """Number features with exactly this unit."""
    return [feature for feature in NUMBER_FEATURES if feature.unit == unit]


def number_terminal(generator, ranges, unit):
    """A feature of the unit (when one exists, usually) or a constant."""
    candidates = features_with_unit(unit)
    if candidates and generator.random() < FEATURE_TERMINAL_CHANCE:
        return Feature(candidates[generator.integers(len(candidates))].name)
    return random_constant(generator, ranges, unit)


def bool_terminal(generator):
    """A category membership (random non-empty subset) or the holiday flag."""
    if BOOLEAN_FEATURES and generator.random() < 0.15:
        return Flag(BOOLEAN_FEATURES[generator.integers(len(BOOLEAN_FEATURES))].name)
    feature = CATEGORY_FEATURES[generator.integers(len(CATEGORY_FEATURES))]
    count = int(generator.integers(1, len(feature.categories)))
    chosen = generator.choice(len(feature.categories), size=count, replace=False)
    return Member(feature.name, tuple(sorted(feature.categories[index] for index in chosen)))


def weighted_choice(generator, weights):
    """A key drawn with probability proportional to its weight."""
    keys = list(weights)
    values = [weights[key] for key in keys]
    total = sum(values)
    return keys[int(generator.choice(len(keys), p=[value / total for value in values]))]


@dataclasses.dataclass
class OpenNode:
    """A node under construction: its function and its (still open or filled) children."""

    function: str
    kind: str
    unit: object
    payload: object = None
    child_slots: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Slot:
    """A child position waiting to be filled with a node of a kind and unit."""

    kind: str
    unit: object
    filled: object = None


def open_function(generator, kind, unit):
    """A random function node of the required kind and unit, with its open child slots."""
    if kind == BOOL:
        function = weighted_choice(generator, BOOL_FUNCTION_WEIGHTS)
        if function == "compare":
            compared_unit = FEATURE_UNITS[generator.integers(len(FEATURE_UNITS))]
            operator = ">" if generator.integers(2) else "<"
            return OpenNode(
                "compare",
                BOOL,
                None,
                operator,
                [Slot(NUMBER, compared_unit), Slot(NUMBER, compared_unit)],
            )
        if function in ("and", "or"):
            return OpenNode(function, BOOL, None, function, [Slot(BOOL, None), Slot(BOOL, None)])
        return OpenNode("not", BOOL, None, None, [Slot(BOOL, None)])
    function = weighted_choice(generator, NUMBER_FUNCTION_WEIGHTS)
    if function in ("+", "-", "min", "max"):
        return OpenNode(function, NUMBER, unit, function, [Slot(NUMBER, unit), Slot(NUMBER, unit)])
    if function == "*":
        factor = FEATURE_UNITS[generator.integers(len(FEATURE_UNITS))]
        return OpenNode("*", NUMBER, unit, "*", [Slot(NUMBER, unit / factor), Slot(NUMBER, factor)])
    if function == "/":
        divisor = FEATURE_UNITS[generator.integers(len(FEATURE_UNITS))]
        return OpenNode(
            "/", NUMBER, unit, "/", [Slot(NUMBER, unit * divisor), Slot(NUMBER, divisor)]
        )
    if function == "abs":
        return OpenNode("abs", NUMBER, unit, None, [Slot(NUMBER, unit)])
    return OpenNode(
        "if", NUMBER, unit, None, [Slot(BOOL, None), Slot(NUMBER, unit), Slot(NUMBER, unit)]
    )


def random_tree(generator, ranges, kind, unit=None, target_size=None, max_size=15):
    """A random tree of the kind (and unit) by PTC2; target size uniform in 1 … max_size.

    The finished tree may exceed the target by up to the last function's arity − 1, and is
    regenerated until it fits max_size.
    """
    for _ in range(100):
        target = (
            int(target_size)
            if target_size is not None
            else int(generator.integers(1, max_size + 1))
        )
        root = Slot(kind, unit)
        if target > 1:
            root.filled = open_function(generator, kind, unit)
            open_slots = list(root.filled.child_slots)
            count = 1
            while open_slots and count + len(open_slots) < target:
                slot = open_slots.pop(int(generator.integers(len(open_slots))))
                slot.filled = open_function(generator, slot.kind, slot.unit)
                # A comparison's right side is usually a threshold constant.
                if (
                    slot.filled.function == "compare"
                    and generator.random() < CONSTANT_THRESHOLD_CHANCE
                ):
                    threshold_slot = slot.filled.child_slots[1]
                    threshold_slot.filled = None
                    left_slot = slot.filled.child_slots[0]
                    open_slots.append(left_slot)
                    slot.filled.child_slots[1] = ConstantSlot(
                        threshold_slot.kind, threshold_slot.unit
                    )
                else:
                    open_slots.extend(slot.filled.child_slots)
                count += 1
        tree = close_all(generator, ranges, root)
        if size(tree) <= max_size:
            return tree
    raise RuntimeError("could not build a tree within the size limit")


@dataclasses.dataclass
class ConstantSlot(Slot):
    """A slot that must become a constant (a comparison threshold)."""


def close_all(generator, ranges, slot):
    """The finished node of a slot: a terminal if never opened, a constant if it must be."""
    if isinstance(slot, ConstantSlot):
        return random_constant(generator, ranges, slot.unit)
    if slot.filled is None:
        if slot.kind == BOOL:
            return bool_terminal(generator)
        return number_terminal(generator, ranges, slot.unit)
    node = slot.filled
    child_nodes = [close_all(generator, ranges, child) for child in node.child_slots]
    if node.function == "compare":
        return Compare(node.payload, *child_nodes)
    if node.function in ("and", "or"):
        return Logic(node.payload, *child_nodes)
    if node.function == "not":
        return Negate(child_nodes[0])
    if node.function == "abs":
        return Absolute(child_nodes[0])
    if node.function == "if":
        return IfElse(*child_nodes)
    return Binary(node.payload, *child_nodes)
