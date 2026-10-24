"""O0: the DC OPF's duals against hand-derived answers and brute force (CLAUDE.md §20.3)."""

import dataclasses

import numpy as np
import pytest

from evobots.orfe.dc_opf import (
    THREE_BUS_EXAMPLE,
    Generator,
    Line,
    Network,
    ptdf_matrix,
    solve_dc_opf,
)


def with_extra_load(network, bus, extra_mw):
    loads = list(network.load_mw_by_bus)
    loads[bus] += extra_mw
    return dataclasses.replace(network, load_mw_by_bus=tuple(loads))


def test_three_bus_hand_derivation():
    # docs/maths.md §2.3: g_A ≤ 90 from 50 + g_A/3 ≤ 80, so g_B = 60; cost 90·20 + 60·50.
    result = solve_dc_opf(THREE_BUS_EXAMPLE)
    assert result["dispatch_mw"] == pytest.approx([90, 60])
    assert result["flow_mw"] == pytest.approx([10, 80, 70])
    assert result["total_cost_usd"] == pytest.approx(4_800)
    assert result["lmp_usd_per_mwh"] == pytest.approx([20, 50, 80])
    assert result["energy_component_usd_per_mwh"] == pytest.approx(80)
    assert result["congestion_component_usd_per_mwh"] == pytest.approx([-60, -30, 0])
    assert result["line_shadow_price_usd_per_mwh"] == pytest.approx([0, 90, 0])


@pytest.mark.parametrize("bus", [0, 1, 2])
def test_lmp_equals_cost_of_one_more_mw(bus):
    base = solve_dc_opf(THREE_BUS_EXAMPLE)
    plus_one = solve_dc_opf(with_extra_load(THREE_BUS_EXAMPLE, bus, 1.0))
    increase = plus_one["total_cost_usd"] - base["total_cost_usd"]
    assert increase == pytest.approx(base["lmp_usd_per_mwh"][bus])


def test_line_shadow_price_equals_saving_from_one_more_mw_of_limit():
    base = solve_dc_opf(THREE_BUS_EXAMPLE)
    lines = list(THREE_BUS_EXAMPLE.lines)
    lines[1] = dataclasses.replace(lines[1], limit_mw=81.0)
    relaxed = solve_dc_opf(dataclasses.replace(THREE_BUS_EXAMPLE, lines=tuple(lines)))
    saving = base["total_cost_usd"] - relaxed["total_cost_usd"]
    assert saving == pytest.approx(base["line_shadow_price_usd_per_mwh"][1])


def test_without_a_binding_limit_every_bus_has_the_same_price():
    lines = tuple(dataclasses.replace(line, limit_mw=None) for line in THREE_BUS_EXAMPLE.lines)
    result = solve_dc_opf(dataclasses.replace(THREE_BUS_EXAMPLE, lines=lines))
    assert result["lmp_usd_per_mwh"] == pytest.approx([20, 20, 20])
    assert result["congestion_component_usd_per_mwh"] == pytest.approx([0, 0, 0])


def test_prices_do_not_depend_on_the_reference_bus():
    # The split into energy and congestion moves with the reference bus; the LMPs do not.
    for reference_bus in (0, 1):
        result = solve_dc_opf(dataclasses.replace(THREE_BUS_EXAMPLE, reference_bus=reference_bus))
        assert result["lmp_usd_per_mwh"] == pytest.approx([20, 50, 80])
    at_bus_a = solve_dc_opf(dataclasses.replace(THREE_BUS_EXAMPLE, reference_bus=0))
    assert at_bus_a["energy_component_usd_per_mwh"] == pytest.approx(20)


def test_limit_binding_in_the_reverse_direction():
    # Load at A, cheap generation at C: the A–C line carries flow C→A (negative) and binds.
    network = Network(
        bus_names=("A", "B", "C"),
        lines=(Line(0, 1, 1.0), Line(0, 2, 1.0, limit_mw=80.0), Line(1, 2, 1.0)),
        generators=(Generator(2, 20.0, 200.0), Generator(1, 50.0, 200.0)),
        load_mw_by_bus=(150.0, 0.0, 0.0),
        reference_bus=0,
    )
    result = solve_dc_opf(network)
    assert result["flow_mw"][1] == pytest.approx(-80)
    assert result["lmp_usd_per_mwh"] == pytest.approx([80, 50, 20])
    for bus in range(3):
        increase = (
            solve_dc_opf(with_extra_load(network, bus, 1.0))["total_cost_usd"]
            - result["total_cost_usd"]
        )
        assert increase == pytest.approx(result["lmp_usd_per_mwh"][bus])


def test_ptdf_flows_satisfy_kirchhoff():
    # Any injection pattern balanced at the reference bus: the flows into each other bus
    # equal its injection, and loop flows obey equal-reactance splits.
    lines = [Line(0, 1, 1.0), Line(0, 2, 2.0), Line(1, 2, 0.5), Line(2, 3, 1.0), Line(1, 3, 1.5)]
    ptdf = ptdf_matrix(4, lines, reference_bus=3)
    injections = np.array([30.0, -10.0, 25.0, 0.0])
    flows = ptdf @ injections
    for bus in range(3):
        net_out = sum(flow for flow, line in zip(flows, lines) if line.from_bus == bus) - sum(
            flow for flow, line in zip(flows, lines) if line.to_bus == bus
        )
        assert net_out == pytest.approx(injections[bus])


def test_infeasible_network_is_reported():
    too_much_load = with_extra_load(THREE_BUS_EXAMPLE, 2, 500.0)
    with pytest.raises(ValueError, match="no solution"):
        solve_dc_opf(too_much_load)
