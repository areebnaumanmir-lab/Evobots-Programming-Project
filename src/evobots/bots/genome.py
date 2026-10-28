"""The trader's genome (preview form): readable rules that evolution changes.

A trader decides, for every hub and hour of operating day D, whether to bid, on which side,
at what limit price and how big (`CLAUDE.md` §9.2). The preview genome keeps that skeleton
with simple slots; the full typed-GP trees replace `conditions` and `score_terms` at M4:

```
where/when : every condition holds (feature > or < threshold) and hour in [first, last]
score      : bias + Σ weight × feature           ($/MWh; > 0 means RT expected above DA)
side       : DEC if score > dec_threshold, INC if score < −inc_threshold, else no bid
price      : limit = da_last + offset (DEC) or da_last − offset (INC)
size       : size_fraction × the hub's MW cap × the trader's position scale
```

Score terms use only $/MWh features, so the score is in $/MWh (unit-consistent, §9.3).
Conditions may use any feature. A missing feature makes its comparison false (§8).

Example:
    >>> genome = FOUNDERS["always_inc"]
    >>> genome_from_json(genome_to_json(genome)) == genome
    True
    >>> describe(genome)[0]
    'where/when: every hub, hours 1–24'
"""

import dataclasses
import hashlib
import json

import numpy as np

from evobots.simulate.market import FEATURE_NAMES, FEATURE_UNITS

# Features a score may use (all in $/MWh, so the score has one unit).
SCORE_FEATURES = tuple(name for name in FEATURE_NAMES if FEATURE_UNITS[name] == "$/MWh")
MAX_CONDITIONS = 3
MAX_SCORE_TERMS = 3
# Typical ranges of each feature, used to draw and mutate thresholds (rough historical
# ranges at the hubs, 2005–2025; constants are clipped to them, §8).
FEATURE_RANGES = {
    "spread_mean_7d": (-20.0, 20.0),
    "spread_mean_28d": (-15.0, 15.0),
    "spread_std_28d": (0.0, 80.0),
    "spread_pos_frac_28d": (0.0, 1.0),
    "spread_spike_frac_28d": (0.0, 0.3),
    "da_last": (0.0, 200.0),
    "hour": (1.0, 24.0),
    "weekday": (0.0, 6.0),
}
WEIGHT_RANGE = (-2.0, 2.0)
BIAS_RANGE_USD_PER_MWH = (-10.0, 10.0)
THRESHOLD_RANGE_USD_PER_MWH = (0.0, 15.0)
OFFSET_RANGE_USD_PER_MWH = (0.0, 50.0)
SIZE_FRACTION_RANGE = (0.05, 1.0)


@dataclasses.dataclass(frozen=True)
class Condition:
    """One comparison: feature > threshold (is_above) or feature < threshold."""

    feature: str
    is_above: bool
    threshold: float


@dataclasses.dataclass(frozen=True)
class Genome:
    """A trader's rules. See the module docstring for how each slot is used.

    Attributes:
        conditions: comparisons that must all hold (0–3).
        first_hour: first hour ending traded (1–24).
        last_hour: last hour ending traded (≥ first_hour).
        score_terms: (feature, weight) pairs, $/MWh features only (1–3).
        score_bias_usd_per_mwh: constant added to the score.
        dec_threshold_usd_per_mwh: DEC when score is above this (≥ 0).
        inc_threshold_usd_per_mwh: INC when score is below minus this (≥ 0).
        price_offset_usd_per_mwh: distance of the limit price from yesterday's DA (≥ 0).
        size_fraction: share of the hub cap bid at full size (0.05–1).
    """

    conditions: tuple
    first_hour: int
    last_hour: int
    score_terms: tuple
    score_bias_usd_per_mwh: float
    dec_threshold_usd_per_mwh: float
    inc_threshold_usd_per_mwh: float
    price_offset_usd_per_mwh: float
    size_fraction: float

    def size(self):
        """Number of rule elements, for the parsimony penalty (§10.2)."""
        return len(self.conditions) + len(self.score_terms) + 1


def genome_to_json(genome):
    """Canonical JSON text of a genome (sorted keys, so equal genomes give equal text)."""
    data = dataclasses.asdict(genome)
    data["score_terms"] = [list(term) for term in genome.score_terms]
    return json.dumps(data, sort_keys=True)


def genome_from_json(text):
    """The genome a canonical JSON text describes (exact round trip)."""
    data = json.loads(text)
    data["conditions"] = tuple(Condition(**condition) for condition in data["conditions"])
    data["score_terms"] = tuple((feature, float(weight)) for feature, weight in data["score_terms"])
    return Genome(**data)


def genome_id(genome):
    """SHA-256 of the canonical JSON, shortened to 12 hex characters (§9.4)."""
    return hashlib.sha256(genome_to_json(genome).encode("utf-8")).hexdigest()[:12]


def describe(genome):
    """The trader's rules as plain-English lines (display names, §9.2)."""
    from evobots.simulate.market import FEATURE_DISPLAY_NAMES

    where = [
        f"{FEATURE_DISPLAY_NAMES[condition.feature]} "
        f"{'>' if condition.is_above else '<'} {condition.threshold:.3g}"
        for condition in genome.conditions
    ]
    hours = f"hours {genome.first_hour}–{genome.last_hour}"
    terms = " ".join(
        f"{'+' if weight >= 0 else '−'} {abs(weight):.3g} × {FEATURE_DISPLAY_NAMES[feature]}"
        for feature, weight in genome.score_terms
    )
    return [
        "where/when: " + (" and ".join(where) + ", " if where else "every hub, ") + hours,
        f"score: {genome.score_bias_usd_per_mwh:.3g} $/MWh {terms}".rstrip(),
        f"side: DEC if score > {genome.dec_threshold_usd_per_mwh:.3g}, "
        f"INC if score < −{genome.inc_threshold_usd_per_mwh:.3g}, else no bid",
        f"price: yesterday's DA ± {genome.price_offset_usd_per_mwh:.3g} $/MWh",
        f"size: {genome.size_fraction:.0%} of each hub's MW cap, times the position scale",
    ]


def simple_genome(score_terms=(), bias=0.0, dec=0.0, inc=0.0, offset=30.0, conditions=()):
    """A genome with all hours, a given score and thresholds (used for founders)."""
    return Genome(
        conditions=tuple(conditions),
        first_hour=1,
        last_hour=24,
        score_terms=tuple(score_terms),
        score_bias_usd_per_mwh=bias,
        dec_threshold_usd_per_mwh=dec,
        inc_threshold_usd_per_mwh=inc,
        price_offset_usd_per_mwh=offset,
        size_fraction=1.0,
    )


# Hand-written starting traders, each with its reason (§9.5).
FOUNDERS = {
    # INC everywhere: mean DA − RT is slightly positive at every hub (capital_sizing.md §1).
    "always_inc": simple_genome(bias=-1.0),
    # DEC everywhere: the mirror; profits in RT spikes.
    "always_dec": simple_genome(bias=1.0),
    # Bet the recent premium continues: INC when DA has been above RT (score = −spread).
    "premium_follow": simple_genome(score_terms=(("spread_mean_28d", -1.0),), dec=1.0, inc=1.0),
    # Bet it reverses.
    "premium_fade": simple_genome(score_terms=(("spread_mean_28d", 1.0),), dec=1.0, inc=1.0),
    # Persistence: follow the last visible week's sign.
    "persistence": simple_genome(score_terms=(("spread_mean_7d", -1.0),), dec=0.5, inc=0.5),
}


def random_condition(generator):
    """A random comparison on any feature, threshold drawn from its range."""
    feature = FEATURE_NAMES[generator.integers(len(FEATURE_NAMES))]
    low, high = FEATURE_RANGES[feature]
    return Condition(feature, bool(generator.integers(2)), float(generator.uniform(low, high)))


def random_genome(generator):
    """A random, valid genome (uniform sizes up to the slot limits)."""
    condition_count = int(generator.integers(0, MAX_CONDITIONS + 1))
    term_count = int(generator.integers(1, MAX_SCORE_TERMS + 1))
    first_hour = int(generator.integers(1, 25))
    last_hour = int(generator.integers(first_hour, 25))
    return Genome(
        conditions=tuple(random_condition(generator) for _ in range(condition_count)),
        first_hour=first_hour,
        last_hour=last_hour,
        score_terms=tuple(
            (
                SCORE_FEATURES[generator.integers(len(SCORE_FEATURES))],
                float(generator.uniform(*WEIGHT_RANGE)),
            )
            for _ in range(term_count)
        ),
        score_bias_usd_per_mwh=float(generator.uniform(*BIAS_RANGE_USD_PER_MWH)),
        dec_threshold_usd_per_mwh=float(generator.uniform(*THRESHOLD_RANGE_USD_PER_MWH)),
        inc_threshold_usd_per_mwh=float(generator.uniform(*THRESHOLD_RANGE_USD_PER_MWH)),
        price_offset_usd_per_mwh=float(generator.uniform(*OFFSET_RANGE_USD_PER_MWH)),
        size_fraction=float(generator.uniform(*SIZE_FRACTION_RANGE)),
    )


def nudged(value, value_range, generator, step_fraction):
    """Value plus Gaussian noise of step_fraction × range width, clipped to the range."""
    low, high = value_range
    return float(np.clip(value + generator.normal(0, step_fraction * (high - low)), low, high))


def mutate(genome, generator):
    """One random change to a genome; returns (child, operator name).

    Operators (§9.6, preview form): nudge a constant (step 2 %, 10 % or 30 % of its range),
    swap a feature, add or remove a condition or score term, shift the hour window.
    """
    operator = str(
        generator.choice(["constant", "constant", "constant", "feature", "add", "remove", "hours"])
    )
    step = float(generator.choice([0.02, 0.10, 0.30]))
    fields = dataclasses.asdict(genome)
    fields["conditions"] = list(genome.conditions)
    fields["score_terms"] = list(genome.score_terms)
    if operator == "constant":
        target = str(
            generator.choice(["bias", "dec", "inc", "offset", "size", "weight", "threshold"])
        )
        if target == "bias":
            fields["score_bias_usd_per_mwh"] = nudged(
                genome.score_bias_usd_per_mwh, BIAS_RANGE_USD_PER_MWH, generator, step
            )
        elif target == "dec":
            fields["dec_threshold_usd_per_mwh"] = nudged(
                genome.dec_threshold_usd_per_mwh, THRESHOLD_RANGE_USD_PER_MWH, generator, step
            )
        elif target == "inc":
            fields["inc_threshold_usd_per_mwh"] = nudged(
                genome.inc_threshold_usd_per_mwh, THRESHOLD_RANGE_USD_PER_MWH, generator, step
            )
        elif target == "offset":
            fields["price_offset_usd_per_mwh"] = nudged(
                genome.price_offset_usd_per_mwh, OFFSET_RANGE_USD_PER_MWH, generator, step
            )
        elif target == "size":
            fields["size_fraction"] = nudged(
                genome.size_fraction, SIZE_FRACTION_RANGE, generator, step
            )
        elif target == "weight" and fields["score_terms"]:
            index = int(generator.integers(len(fields["score_terms"])))
            feature, weight = fields["score_terms"][index]
            fields["score_terms"][index] = (feature, nudged(weight, WEIGHT_RANGE, generator, step))
        elif target == "threshold" and fields["conditions"]:
            index = int(generator.integers(len(fields["conditions"])))
            condition = fields["conditions"][index]
            fields["conditions"][index] = dataclasses.replace(
                condition,
                threshold=nudged(
                    condition.threshold, FEATURE_RANGES[condition.feature], generator, step
                ),
            )
    elif operator == "feature":
        if fields["score_terms"] and generator.integers(2):
            index = int(generator.integers(len(fields["score_terms"])))
            feature = SCORE_FEATURES[generator.integers(len(SCORE_FEATURES))]
            fields["score_terms"][index] = (feature, fields["score_terms"][index][1])
        elif fields["conditions"]:
            index = int(generator.integers(len(fields["conditions"])))
            fields["conditions"][index] = random_condition(generator)
    elif operator == "add":
        if generator.integers(2) and len(fields["conditions"]) < MAX_CONDITIONS:
            fields["conditions"].append(random_condition(generator))
        elif len(fields["score_terms"]) < MAX_SCORE_TERMS:
            feature = SCORE_FEATURES[generator.integers(len(SCORE_FEATURES))]
            fields["score_terms"].append((feature, float(generator.uniform(*WEIGHT_RANGE))))
    elif operator == "remove":
        if fields["conditions"] and generator.integers(2):
            fields["conditions"].pop(int(generator.integers(len(fields["conditions"]))))
        elif len(fields["score_terms"]) > 1:
            fields["score_terms"].pop(int(generator.integers(len(fields["score_terms"]))))
    elif operator == "hours":
        first_hour = int(np.clip(genome.first_hour + generator.integers(-3, 4), 1, 24))
        last_hour = int(np.clip(genome.last_hour + generator.integers(-3, 4), first_hour, 24))
        fields["first_hour"], fields["last_hour"] = first_hour, last_hour
    fields["conditions"] = tuple(fields["conditions"])
    fields["score_terms"] = tuple(fields["score_terms"])
    return Genome(**fields), f"{operator}"


def crossover(first, second, generator):
    """A child taking each slot from one parent or the other (slot-wise crossover)."""
    fields = {}
    for field in dataclasses.fields(Genome):
        parent = first if generator.integers(2) else second
        fields[field.name] = getattr(parent, field.name)
    if fields["last_hour"] < fields["first_hour"]:
        fields["last_hour"] = fields["first_hour"]
    return Genome(**fields)
