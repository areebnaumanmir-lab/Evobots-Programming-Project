"""O0: why prices differ by location. A DC optimal power flow and its shadow prices.

The market operator dispatches generators at least cost subject to power balance and line
limits. In the DC (linearised, lossless) model a line's flow is a fixed linear function of the
bus injections, given by the power transfer distribution factor (PTDF) matrix. The LMP at a
bus is the increase in total cost when one more MW is consumed there: the dual (shadow price)
of power balance plus the duals of the binding line limits weighted by the bus's PTDFs. When
no line binds, every bus has the same price; when one binds, prices separate, and the
difference is the congestion component (MISO's MCC). Losses (MISO's MLC) are left out.

Maths: docs/maths.md §2; walk-through: docs/explanations/lmp_from_opf.md (docs/design_spec.md §20.3).
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog


@dataclass(frozen=True)
class Line:
    """A transmission line between two buses.

    Attributes:
        from_bus: index of the sending bus (flow is positive from here to to_bus).
        to_bus: index of the receiving bus.
        reactance_per_unit: series reactance; only ratios between lines matter here.
        limit_mw: thermal limit in either direction, MW; None = unlimited.
    """

    from_bus: int
    to_bus: int
    reactance_per_unit: float
    limit_mw: float | None = None


@dataclass(frozen=True)
class Generator:
    """A generator with a constant marginal cost.

    Attributes:
        bus: index of the bus it injects at.
        cost_usd_per_mwh: marginal cost (its offer price).
        capacity_mw: maximum output, MW.
    """

    bus: int
    cost_usd_per_mwh: float
    capacity_mw: float


@dataclass(frozen=True)
class Network:
    """A small power network for the DC OPF.

    Attributes:
        bus_names: one name per bus.
        lines: the transmission lines.
        generators: the generators.
        load_mw_by_bus: demand at each bus, MW (same order as bus_names).
        reference_bus: the bus whose price is the energy component (PTDFs are zero there).
    """

    bus_names: tuple
    lines: tuple
    generators: tuple
    load_mw_by_bus: tuple
    reference_bus: int = 0


def ptdf_matrix(bus_count, lines, reference_bus):
    """Power transfer distribution factors: line flow per MW injected at a bus, MW/MW.

    Entry [line, bus] is the flow on the line when 1 MW is injected at the bus and withdrawn
    at the reference bus. Built from the bus susceptance matrix B (DC power flow):
    angles θ = B_r⁻¹ p on the non-reference buses, flow = (θ_from − θ_to) / x.

    Args:
        bus_count: number of buses.
        lines: sequence of Line.
        reference_bus: index of the reference (slack) bus.

    Returns:
        A (line count × bus count) numpy array; the reference bus's column is zero.

    Maths: docs/maths.md §2.1.

    Example:
        >>> triangle = [Line(0, 1, 1.0), Line(0, 2, 1.0), Line(1, 2, 1.0)]
        >>> ptdf_matrix(3, triangle, reference_bus=2).round(4).tolist()
        [[0.3333, -0.3333, 0.0], [0.6667, 0.3333, 0.0], [0.3333, 0.6667, 0.0]]
    """
    susceptance = np.zeros((bus_count, bus_count))
    for line in lines:
        admittance = 1.0 / line.reactance_per_unit
        susceptance[line.from_bus, line.from_bus] += admittance
        susceptance[line.to_bus, line.to_bus] += admittance
        susceptance[line.from_bus, line.to_bus] -= admittance
        susceptance[line.to_bus, line.from_bus] -= admittance
    others = [bus for bus in range(bus_count) if bus != reference_bus]
    reactance_matrix = np.zeros((bus_count, bus_count))
    reactance_matrix[np.ix_(others, others)] = np.linalg.inv(susceptance[np.ix_(others, others)])
    return np.array(
        [
            (reactance_matrix[line.from_bus] - reactance_matrix[line.to_bus])
            / line.reactance_per_unit
            for line in lines
        ]
    )


def solve_dc_opf(network):
    """Least-cost dispatch and the LMP at every bus, from the linear program's duals.

    Linear program (decision: output g_k of each generator k, MW):
        minimise   Σ_k c_k g_k
        subject to Σ_k g_k = Σ_n d_n                      (power balance; dual λ)
                   −F_l ≤ Σ_n PTDF[l,n] (G_n − d_n) ≤ F_l  (line limits; duals μ_l)
                   0 ≤ g_k ≤ capacity_k
    where G_n is the output at bus n. The LMP at bus n is ∂cost/∂d_n = λ + Σ_l μ_l PTDF[l,n]
    with the sign conventions of scipy's HiGHS marginals (μ ≤ 0 on a binding upper limit).

    Args:
        network: a Network.

    Returns:
        A dict with dispatch_mw (per generator), flow_mw (per line), lmp_usd_per_mwh,
        energy_component_usd_per_mwh (λ, the same at every bus) and
        congestion_component_usd_per_mwh (per bus), line_shadow_price_usd_per_mwh (per line:
        the cost saved per MW of extra limit), and total_cost_usd.

    Maths: docs/maths.md §2.2.

    Decision: docs/design_spec.md §20.3 (O0); losses are left out, so there is no loss component.

    Example:
        >>> result = solve_dc_opf(THREE_BUS_EXAMPLE)
        >>> [round(price, 2) for price in result["lmp_usd_per_mwh"]]
        [20.0, 50.0, 80.0]
    """
    bus_count = len(network.bus_names)
    ptdf = ptdf_matrix(bus_count, network.lines, network.reference_bus)
    load_mw = np.asarray(network.load_mw_by_bus, dtype=float)
    # Bus of each generator as an incidence matrix: column k has a 1 at generator k's bus.
    incidence = np.zeros((bus_count, len(network.generators)))
    for generator_index, generator in enumerate(network.generators):
        incidence[generator.bus, generator_index] = 1.0
    costs = [generator.cost_usd_per_mwh for generator in network.generators]
    flow_per_generator_mw = ptdf @ incidence
    flow_from_load_mw = ptdf @ load_mw
    limited = [index for index, line in enumerate(network.lines) if line.limit_mw is not None]
    limits = np.array([network.lines[index].limit_mw for index in limited])
    upper_rows = np.vstack([flow_per_generator_mw[limited], -flow_per_generator_mw[limited]])
    upper_bounds = np.concatenate(
        [limits + flow_from_load_mw[limited], limits - flow_from_load_mw[limited]]
    )
    result = linprog(
        costs,
        A_ub=upper_rows if limited else None,
        b_ub=upper_bounds if limited else None,
        A_eq=np.ones((1, len(network.generators))),
        b_eq=[load_mw.sum()],
        bounds=[(0.0, generator.capacity_mw) for generator in network.generators],
        method="highs",
    )
    if not result.success:
        raise ValueError(f"DC OPF has no solution: {result.message}")
    energy_price = result.eqlin.marginals[0]
    line_duals = np.zeros(len(network.lines))
    if limited:
        forward, backward = np.split(result.ineqlin.marginals, 2)
        line_duals[limited] = forward - backward
    congestion = ptdf.T @ line_duals
    dispatch = result.x
    return {
        "dispatch_mw": dispatch.tolist(),
        "flow_mw": (flow_per_generator_mw @ dispatch - flow_from_load_mw).tolist(),
        "lmp_usd_per_mwh": (energy_price + congestion).tolist(),
        "energy_component_usd_per_mwh": float(energy_price),
        "congestion_component_usd_per_mwh": congestion.tolist(),
        # "+ 0.0" turns −0.0 into 0.0 for display.
        "line_shadow_price_usd_per_mwh": (-line_duals + 0.0).tolist(),
        "total_cost_usd": float(result.fun),
    }


# The worked example of docs/maths.md §2.3: three buses in a triangle of equal lines, a cheap
# generator at bus A, an expensive one at bus B, 150 MW of load at bus C, and an 80 MW limit
# on line A–C. Illustrative numbers, not MISO data.
THREE_BUS_EXAMPLE = Network(
    bus_names=("A", "B", "C"),
    lines=(Line(0, 1, 1.0), Line(0, 2, 1.0, limit_mw=80.0), Line(1, 2, 1.0)),
    generators=(Generator(0, 20.0, 200.0), Generator(1, 50.0, 200.0)),
    load_mw_by_bus=(0.0, 0.0, 150.0),
    reference_bus=2,
)
