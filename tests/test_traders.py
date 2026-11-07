"""M4: the trader language, operators, ids, and the generated source code (design spec §9).

The equivalence test is the referee of §9.1 and §18: on many random days, a trader's
generated file bids exactly what the vectorised engine bids (side, limit and MW, compared
with ==, not approximately).
"""

import types

import numpy as np
import pytest

from evobots.bots.founders import FOUNDERS
from evobots.bots.grammar import (
    Binary,
    Compare,
    Constant,
    Feature,
    GrammarError,
    Member,
    check,
    parse_python,
    python_source,
)
from evobots.bots.random_trees import ConstantRanges
from evobots.bots.source import genome_from_source, input_rows, rows_to_csv, trader_source
from evobots.bots.trader import (
    behaviour_id,
    genome_from_json,
    genome_id,
    genome_to_json,
    trader_decisions,
    trader_name,
)
from evobots.bots.variation import INITIAL_OPERATOR_WEIGHTS, OperatorBandit, random_genome, vary
from evobots.config.capital import CapitalSettings
from evobots.features.inputs import synthetic_feature_inputs
from evobots.features.store import build_feature_store
from evobots.simulate.market import synthetic_hub_market
from evobots.simulate.settlement import round_down_to_step
from evobots.units import DEGF


@pytest.fixture(scope="module")
def store():
    market = synthetic_hub_market(days=400, seed=9)
    return build_feature_store(market, synthetic_feature_inputs(market.days, market.hubs, seed=4))


@pytest.fixture(scope="module")
def caps(store):
    caps_by_hub = CapitalSettings().hub_caps_mw()
    return np.array([caps_by_hub[hub] for hub in store.locations])


def population(count, seed):
    generator = np.random.Generator(np.random.PCG64(seed))
    ranges = ConstantRanges.from_catalogue()
    genomes = list(FOUNDERS.values()) + [random_genome(generator, ranges) for _ in range(count)]
    bandit = OperatorBandit()
    for _ in range(count * 4):
        parent = genomes[int(generator.integers(len(genomes)))]
        partner = genomes[int(generator.integers(len(genomes)))]
        child, _ = vary(parent, generator, ranges, bandit.choose(generator), partner)
        genomes.append(child)
    return genomes


def test_unit_errors_are_rejected():
    with pytest.raises(GrammarError):
        check(Binary("+", Feature("spread_mean_7d"), Feature("temp_max_fcst")))
    with pytest.raises(GrammarError):
        check(Compare(">", Feature("da_last"), Constant(70.0, DEGF)))
    with pytest.raises(GrammarError):
        parse_python("__import__('os').system('true')")
    check(Compare(">", Feature("temp_max_fcst"), Constant(70.0, DEGF)))


def test_member_sets_must_be_sorted_known_names():
    with pytest.raises(GrammarError):
        check(Member("loc_type", ("Loadzone", "Hub")))
    with pytest.raises(GrammarError):
        check(Member("loc_type", ("Shed",)))


def test_every_genome_round_trips_through_json_and_source():
    for genome in population(60, seed=1):
        assert genome_from_json(genome_to_json(genome)) == genome
        assert genome_from_source(trader_source(genome, {"trader_id": "R1-1"})) == genome
        for slot in ("where", "when", "score"):
            tree = getattr(genome, slot)
            assert parse_python(python_source(tree)) == tree


def test_genome_ids_follow_genes_not_identity():
    first, second = FOUNDERS["always_inc"], FOUNDERS["always_dec"]
    assert genome_id(first) == genome_id(genome_from_json(genome_to_json(first)))
    assert genome_id(first) != genome_id(second)
    assert len(genome_id(first)) == 64
    assert trader_name("R3-9") == trader_name("R3-9")


def test_bandit_keeps_a_floor_and_learns():
    bandit = OperatorBandit()
    for _ in range(200):
        bandit.reward("crossover", True)
        bandit.reward("hoist", False)
    probabilities = bandit.probabilities()
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert min(probabilities.values()) >= 0.05
    assert probabilities["crossover"] > probabilities["hoist"]
    assert set(probabilities) == set(INITIAL_OPERATOR_WEIGHTS)


def module_from_source(text):
    module = types.ModuleType("generated_trader")
    exec(compile(text, "generated_trader.py", "exec"), module.__dict__)  # noqa: S102
    return module


def test_generated_file_bids_exactly_what_the_engine_bids(store, caps, tmp_path):
    generator = np.random.Generator(np.random.PCG64(77))
    genomes = population(40, seed=2)
    checked_bids = 0
    for number, genome in enumerate(genomes):
        module = module_from_source(trader_source(genome, {"trader_id": f"R1-{number}"}))
        for day_index in generator.integers(60, len(store.days), size=3):
            day_index = int(day_index)
            decisions = trader_decisions(genome, store, day_index, day_index + 1, caps)
            features = genome.features()
            # Through the CSV the file reads, to test its parser too.
            path = tmp_path / f"day_{number}_{day_index}.csv"
            path.write_text(rows_to_csv(input_rows(store, day_index, caps, features), features))
            rows = list(module.read_rows(str(path)))
            scale = float(generator.uniform(0.05, 1.0))
            for row in rows:
                location = store.locations.index(row["location"])
                hour = int(row["hour"]) - 1
                bid = module.decide(row, row["cap_mw"])
                side = int(decisions.side[0, hour, location])
                if bid is None:
                    assert side == 0, (genome, row)
                    continue
                assert bid[0] == side
                assert bid[1] == decisions.limit_usd_per_mwh[0, hour, location]
                assert bid[2] == decisions.full_size_mw[0, hour, location]
                engine_scaled = round_down_to_step(
                    scale * decisions.full_size_mw[0, hour, location]
                )
                assert module.round_down_to_step(scale * bid[2]) == engine_scaled
                checked_bids += 1
    assert checked_bids > 1000


def test_behaviour_id_sees_behaviour_not_code(store, caps):
    # 1 × spread_mean_28d and spread_mean_28d + 0 $/MWh are different code, same bids.
    plain = FOUNDERS["premium_fade"]
    padded = genome_from_json(
        genome_to_json(plain).replace(
            '{"name":"spread_mean_28d","node":"feature"}',
            '{"left":{"name":"spread_mean_28d","node":"feature"},"node":"binary","operator":"+",'
            '"right":{"node":"constant","unit":"mwh^-1*usd","value":0.0}}',
        )
    )
    assert genome_id(plain) != genome_id(padded)
    window = (100, 160)
    assert behaviour_id(trader_decisions(plain, store, *window, caps)) == behaviour_id(
        trader_decisions(padded, store, *window, caps)
    )
    assert behaviour_id(trader_decisions(plain, store, *window, caps)) != behaviour_id(
        trader_decisions(FOUNDERS["premium_follow"], store, *window, caps)
    )


def test_founders_are_small_and_valid():
    for name, genome in FOUNDERS.items():
        assert genome.node_count() <= 15, name
    # heat_dec's score is 0.4 $/MWh per cooling degree-day: a $/MWh quantity.
    assert "cdd_fcst" in FOUNDERS["heat_dec"].features()
