"""A trader's genome and the bids it makes (`docs/design_spec.md` §9.1–9.4).

Every trader has exactly these slots (§9.2):

```
where : Bool tree       which location-hours it considers
when  : Bool tree       (a second condition, usually about time)
score : Number tree     $/MWh; > 0 means it expects RT above DA
side  : DEC if score > dec_threshold, INC if score < −inc_threshold, else no bid
price : limit = da_last + price_offset (DEC) or da_last − price_offset (INC)
size  : cap × size_fraction × min(1, |score| ÷ size_score_scale)   (MW at full size)
risk  : submitted MWh/day ≤ daily_cap_fraction × footprint; after a day losing more than
        pause_loss_fraction of equity, sit out pause_days days
```

The hard caps (each location's MW cap, the out-of-money rule, data visibility) are never part
of the genome and never mutate. Identity (§9.4): the trader id is run + birth number
("R12-184213"); the genome id is the SHA-256 of the canonical genome JSON; the behaviour id
hashes the trader's bids on a fixed reference window, so different code with identical
behaviour is recognised; the name is two words derived from the trader id.

Example:
    >>> from evobots.bots.founders import FOUNDERS
    >>> genome = FOUNDERS["always_inc"]
    >>> genome_from_json(genome_to_json(genome)) == genome
    True
    >>> trader_name("R12-184213")
    'fern-dormouse'
"""

import dataclasses
import hashlib
import json

import numpy as np

from evobots.bots.grammar import (
    BOOL,
    NUMBER,
    Truth,
    check,
    display,
    evaluate,
    features_used,
    from_data,
    kind_of,
    size,
    to_data,
    unit_of,
)
from evobots.simulate.settlement import Decisions
from evobots.units import USD_PER_MWH

HOURS_PER_DAY = 24
MAX_SLOT_SIZE = 15
SLOT_NAMES = ("where", "when", "score")
# Ranges of the numeric genes (inclusive); mutation clips to them.
GENE_RANGES = {
    "dec_threshold_usd_per_mwh": (0.0, 20.0),
    "inc_threshold_usd_per_mwh": (0.0, 20.0),
    "price_offset_usd_per_mwh": (0.0, 100.0),
    "size_fraction": (0.05, 1.0),
    "size_score_scale_usd_per_mwh": (0.5, 50.0),
    "daily_cap_fraction": (0.05, 1.0),
    "pause_loss_fraction": (0.005, 0.2),
    "pause_days": (0, 10),
}
GENE_NAMES = tuple(GENE_RANGES)
GENOME_ID_DISPLAY_LENGTH = 10
BEHAVIOUR_ID_LENGTH = 16


@dataclasses.dataclass(frozen=True)
class Genome:
    """A trader's slots and numeric genes (see the module docstring)."""

    where: object
    when: object
    score: object
    dec_threshold_usd_per_mwh: float = 1.0
    inc_threshold_usd_per_mwh: float = 1.0
    price_offset_usd_per_mwh: float = 30.0
    size_fraction: float = 1.0
    size_score_scale_usd_per_mwh: float = 0.5
    daily_cap_fraction: float = 1.0
    pause_loss_fraction: float = 0.2
    pause_days: int = 0

    def __post_init__(self):
        """Check types, units, slot sizes and gene ranges."""
        for name in ("where", "when"):
            if kind_of(getattr(self, name)) != BOOL:
                raise ValueError(f"{name} must be a condition")
        if kind_of(self.score) != NUMBER or unit_of(self.score) != USD_PER_MWH:
            raise ValueError("score must be a number in $/MWh")
        for name in SLOT_NAMES:
            check(getattr(self, name))
            if size(getattr(self, name)) > MAX_SLOT_SIZE:
                raise ValueError(f"{name} has more than {MAX_SLOT_SIZE} nodes")
        for name, (low, high) in GENE_RANGES.items():
            value = getattr(self, name)
            if not low <= value <= high:
                raise ValueError(f"{name}={value} outside [{low}, {high}]")

    def node_count(self):
        """Total nodes over the three slots (the parsimony penalty's size)."""
        return sum(size(getattr(self, name)) for name in SLOT_NAMES)

    def features(self):
        """Features any slot reads, plus da_last (the limit price)."""
        names = set()
        for name in SLOT_NAMES:
            names.update(features_used(getattr(self, name)))
        names.add("da_last")
        return sorted(names)

    def genes(self):
        """The numeric genes as a dict."""
        return {name: getattr(self, name) for name in GENE_NAMES}


def genome_to_data(genome):
    """Canonical data of a genome."""
    data = {name: to_data(getattr(genome, name)) for name in SLOT_NAMES}
    data.update({name: getattr(genome, name) for name in GENE_NAMES})
    return data


def genome_from_data(data):
    """The genome a `genome_to_data` description gives."""
    genes = {name: data[name] for name in GENE_NAMES}
    genes["pause_days"] = int(genes["pause_days"])
    return Genome(**{name: from_data(data[name]) for name in SLOT_NAMES}, **genes)


def genome_to_json(genome):
    """Canonical JSON text: sorted keys, no spaces, so equal genomes give equal text."""
    return json.dumps(genome_to_data(genome), sort_keys=True, separators=(",", ":"))


def genome_from_json(text):
    """The genome a canonical JSON text describes (exact round trip)."""
    return genome_from_data(json.loads(text))


def genome_id(genome):
    """Full SHA-256 hex of the canonical JSON (shown shortened, `short_genome_id`)."""
    return hashlib.sha256(genome_to_json(genome).encode("utf-8")).hexdigest()


def short_genome_id(genome):
    """The genome id's first 10 hex characters (the lineage store lengthens it on a clash)."""
    return genome_id(genome)[:GENOME_ID_DISPLAY_LENGTH]


def describe(genome, is_code_names=False):
    """The trader's rules as plain-English lines (§9.2's printed form)."""

    def show(name):
        return display(getattr(genome, name), is_code_names)

    return [
        f"where: {show('where')}",
        f"when: {show('when')}",
        f"score: {show('score')}",
        f"side: DEC if score > {genome.dec_threshold_usd_per_mwh:.3g} $/MWh, INC if score < "
        f"−{genome.inc_threshold_usd_per_mwh:.3g} $/MWh, else no bid",
        f"price: limit = yesterday's DA ± {genome.price_offset_usd_per_mwh:.3g} $/MWh",
        f"size: {genome.size_fraction:.0%} of the location's MW cap × min(1, |score| ÷ "
        f"{genome.size_score_scale_usd_per_mwh:.3g} $/MWh), times the position scale",
        f"risk: at most {genome.daily_cap_fraction:.0%} of the daily footprint; "
        + (
            f"pause {genome.pause_days} days after a day losing {genome.pause_loss_fraction:.1%}"
            if genome.pause_days
            else "no pause rule"
        ),
    ]


def trader_decisions(genome, store, start, end, caps_mw, cache=None):
    """The trader's full-size bids for store days start … end−1 (a `Decisions`).

    Args:
        genome: a Genome.
        store: a FeatureStore.
        start: first day index.
        end: one past the last.
        caps_mw: array of each location's hard MW cap.
        cache: optional EvaluationCache shared across a population.
    """
    shape = (end - start, HOURS_PER_DAY, len(store.locations))
    where = np.broadcast_to(evaluate(genome.where, store, start, end, cache), shape)
    when = np.broadcast_to(evaluate(genome.when, store, start, end, cache), shape)
    score = np.broadcast_to(evaluate(genome.score, store, start, end, cache), shape)
    day_ahead_last = store.window("da_last", start, end)
    is_considered = (where == 1.0) & (when == 1.0) & ~np.isnan(score) & ~np.isnan(day_ahead_last)
    side = np.zeros(shape, dtype=np.int8)
    side[is_considered & (score > genome.dec_threshold_usd_per_mwh)] = 1
    side[is_considered & (score < -genome.inc_threshold_usd_per_mwh)] = -1
    limit = np.where(side != 0, day_ahead_last + side * genome.price_offset_usd_per_mwh, 0.0)
    with np.errstate(invalid="ignore"):
        strength = np.minimum(1.0, np.abs(score) / genome.size_score_scale_usd_per_mwh)
    power = np.where(side != 0, caps_mw[None, None, :] * genome.size_fraction * strength, 0.0)
    return Decisions(first_day_index=start, side=side, limit_usd_per_mwh=limit, full_size_mw=power)


def behaviour_id(decisions):
    """Hash of the bids (side, limit, size) on a window: equal bids give equal ids."""
    digest = hashlib.sha256()
    digest.update(decisions.side.tobytes())
    digest.update(np.where(decisions.side != 0, decisions.limit_usd_per_mwh, 0.0).tobytes())
    digest.update(np.where(decisions.side != 0, decisions.full_size_mw, 0.0).tobytes())
    return digest.hexdigest()[:BEHAVIOUR_ID_LENGTH]


def empty_condition():
    """The condition of an unused where/when slot."""
    return Truth(True)


ADJECTIVES = (
    "amber",
    "ashen",
    "azure",
    "bold",
    "brisk",
    "calm",
    "cedar",
    "clever",
    "coral",
    "crimson",
    "dapper",
    "dawn",
    "deft",
    "dusky",
    "eager",
    "early",
    "ember",
    "fabled",
    "fallow",
    "fern",
    "fleet",
    "frosty",
    "gentle",
    "gilded",
    "glad",
    "golden",
    "granite",
    "hardy",
    "hazel",
    "humble",
    "ivory",
    "jade",
    "keen",
    "lively",
    "lunar",
    "maple",
    "mellow",
    "misty",
    "noble",
    "ochre",
    "olive",
    "opal",
    "pale",
    "pine",
    "plucky",
    "quiet",
    "rapid",
    "rustic",
    "sable",
    "sage",
    "scarlet",
    "silent",
    "silver",
    "slate",
    "solar",
    "steady",
    "stout",
    "swift",
    "tawny",
    "teal",
    "umber",
    "velvet",
    "vivid",
    "wild",
)
ANIMALS = (
    "badger",
    "bison",
    "crane",
    "cougar",
    "curlew",
    "dingo",
    "dormouse",
    "egret",
    "elk",
    "falcon",
    "ferret",
    "finch",
    "fox",
    "gannet",
    "gecko",
    "gibbon",
    "grouse",
    "hare",
    "hawk",
    "heron",
    "ibex",
    "ibis",
    "jackal",
    "jaguar",
    "kestrel",
    "kite",
    "koala",
    "lark",
    "lemur",
    "lynx",
    "magpie",
    "marmot",
    "marten",
    "mink",
    "moose",
    "newt",
    "ocelot",
    "orca",
    "osprey",
    "otter",
    "owl",
    "panda",
    "petrel",
    "pika",
    "plover",
    "puffin",
    "quail",
    "raven",
    "robin",
    "salmon",
    "seal",
    "shrew",
    "skink",
    "sparrow",
    "stoat",
    "swift",
    "tapir",
    "tern",
    "thrush",
    "toad",
    "trout",
    "vole",
    "walrus",
    "wren",
)


def trader_name(trader_id):
    """Two words derived from the trader id (for memory, not uniqueness; §9.4)."""
    digest = hashlib.sha256(trader_id.encode("utf-8")).digest()
    return f"{ADJECTIVES[digest[0] % len(ADJECTIVES)]}-{ANIMALS[digest[1] % len(ANIMALS)]}"
