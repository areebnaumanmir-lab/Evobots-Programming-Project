"""The MAP-Elites map: cells by behaviour, one elite per cell (`docs/design_spec.md` §11, §11.6).

- **Horizontal axis, net direction:** (DEC MWh − INC MWh) ÷ cleared MWh, −1 (only INC) … +1
  (only DEC), in 10 columns.
- **Vertical axis, selectivity:** the share of priced location-hours bid on, log scale from
  0.1 % to 100 %, in 8 rows.

A trader that never trades has no cleared MWh; it is placed in the middle column and the
bottom row (selectivity 0 is clipped to 0.1 %).

Example:
    >>> cell_of(-1.0, 1.0), cell_of(1.0, 0.0001), cell_of(0.05, 0.03)
    ((0, 7), (9, 0), (5, 3))
"""

import dataclasses
import math

DIRECTION_BINS = 10
SELECTIVITY_BINS = 8
SELECTIVITY_LOG_RANGE = (-3.0, 0.0)


def cell_of(net_direction, selectivity):
    """(column, row) of a trader with these descriptors."""
    column = min(DIRECTION_BINS - 1, max(0, int((net_direction + 1) / 2 * DIRECTION_BINS)))
    low, high = SELECTIVITY_LOG_RANGE
    log_share = math.log10(max(selectivity, 10**low))
    row = min(
        SELECTIVITY_BINS - 1, max(0, int((log_share - low) / (high - low) * SELECTIVITY_BINS))
    )
    return column, row


def cell_bounds(cell):
    """((direction low, high), (selectivity low, high)) of a cell, for the map's legend."""
    column, row = cell
    width = 2 / DIRECTION_BINS
    low, high = SELECTIVITY_LOG_RANGE
    height = (high - low) / SELECTIVITY_BINS
    return (
        (-1 + column * width, -1 + (column + 1) * width),
        (10 ** (low + row * height), 10 ** (low + (row + 1) * height)),
    )


@dataclasses.dataclass
class Elite:
    """An archive entry: a trader, its genome and its evaluation on the current window.

    Attributes:
        record: its BirthRecord.
        genome: its Genome.
        evaluation: its Evaluation on the current training window.
        forward: its Evaluation on the next unseen year (filled at checkpoints), or None.
        forward_doubled_costs: the same at doubled costs, or None.
        gates: {gate: (passed, detail)} from the last quick-gate check.
    """

    record: object
    genome: object
    evaluation: object
    forward: object = None
    forward_doubled_costs: object = None
    gates: dict = dataclasses.field(default_factory=dict)

    @property
    def trader_id(self):
        """The trader's id."""
        return self.record.trader_id

    def cell(self):
        """Its cell on the current window."""
        return cell_of(self.evaluation.net_direction, self.evaluation.selectivity)

    def passes_quick_gates(self):
        """True when every quick gate checked so far passed (and some were checked)."""
        return bool(self.gates) and all(passed for passed, _ in self.gates.values())

    def first_failed_gate(self):
        """(gate, detail) of the first failed gate, or None."""
        for gate, (passed, detail) in self.gates.items():
            if not passed:
                return gate, detail
        return None


def ranked(elites):
    """Elites best first (fitness, then the smaller program, then birth order)."""
    return sorted(
        elites,
        key=lambda elite: (
            -elite.evaluation.fitness,
            elite.genome.node_count(),
            elite.record.birth,
        ),
    )
