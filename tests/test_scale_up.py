"""M8: the all-location store (Stage C), yearly clusters (Stage D) and G5 at every location."""

import datetime
from pathlib import Path

import numpy as np
import pytest

from evobots.assess.scale_up import every_location_rescore
from evobots.bots.founders import FOUNDERS
from evobots.data.clusters import cluster_year, clustered_markets
from evobots.data.location_store import LocationStore, day_values, write_year
from evobots.data.sources.miso_eras import HoldoutRefusedError
from evobots.qd.evaluation import Evaluator

HUBS = ("ILLINOIS.HUB", "MINN.HUB")


def synthetic_store(directory, years=(2010, 2011), seed=0):
    """Two hubs and three groups of three nodes whose spreads move together; node C3 leaves in
    the second year."""
    generator = np.random.default_rng(seed)
    names = [*HUBS] + [f"{group}{member}" for group in "ABC" for member in (1, 2, 3)]
    types = ["Hub", "Hub"] + ["Gennode"] * 9
    for year in years:
        first = datetime.date(year, 1, 1)
        day_count = (datetime.date(year + 1, 1, 1) - first).days
        level = 30 + generator.normal(0, 3, size=(day_count, 24, 1))
        group_spreads = {group: generator.normal(0, 5, size=(day_count, 1, 1)) for group in "ABC"}
        day_ahead = np.repeat(level, len(names), axis=2).astype(float)
        real_time = day_ahead.copy()
        for column, name in enumerate(names):
            common = group_spreads[name[0]] if name[0] in "ABC" else group_spreads["A"]
            noise = generator.normal(0, 0.5, size=(day_count, 24))
            real_time[:, :, column] -= common[:, :, 0] + noise
        if year == years[-1]:
            day_ahead[:, :, names.index("C3")] = np.nan
            real_time[:, :, names.index("C3")] = np.nan
        write_year(
            directory, year, first, names, types, day_ahead, real_time, np.zeros_like(day_ahead)
        )
    return LocationStore(directory)


def test_store_reads_columns_across_years_and_leaves_gaps_missing(tmp_path):
    store = synthetic_store(tmp_path)
    assert store.years() == [2010, 2011]
    market = store.market(datetime.date(2010, 12, 30), datetime.date(2011, 1, 2), ["C3", "A1"])
    assert market.hubs == ("C3", "A1")
    assert market.day_ahead.shape == (4, 24, 2)
    assert not np.isnan(market.day_ahead[:2, :, 0]).any()
    assert np.isnan(market.day_ahead[2:, :, 0]).all()
    assert market.types() == ("Gennode", "Gennode")
    assert (
        store.market(datetime.date(2009, 12, 31), datetime.date(2010, 1, 1)).day_ahead.shape[0] == 2
    )


def test_holdout_days_are_refused_by_the_reader():
    with pytest.raises(HoldoutRefusedError):
        day_values((Path("data/raw/miso"), datetime.date(2025, 10, 1)))


def test_clusters_find_the_groups_point_in_time_and_prefer_hubs(tmp_path):
    store = synthetic_store(tmp_path)
    clusters = cluster_year(store, 2011, threshold=0.5)
    assert clusters.window == ("2009-12-27", "2010-12-26")
    assert len(clusters.representatives) == 3
    assert sorted(clusters.sizes) == [3, 3, 5]
    # the group that holds both hubs is represented by a hub
    assert clusters.representatives[0] in HUBS
    assert cluster_year(store, 2010).representatives == []  # no visible history


def test_clustered_stage_trades_only_where_a_location_represents_its_year(tmp_path):
    store = synthetic_store(tmp_path)
    clusters = {
        "years": [
            {"year": 2010, "representatives": ["A1"]},
            {"year": 2011, "representatives": ["B2"]},
        ]
    }
    features, settlement = clustered_markets(
        datetime.date(2010, 1, 1), datetime.date(2011, 12, 31), store, clusters
    )
    assert features.hubs == ("A1", "B2", *HUBS)
    first_2011 = features.days.index(datetime.date(2011, 1, 1))
    column_first, column_second = 0, 1
    assert not np.isnan(features.day_ahead[first_2011:, :, column_first]).any()
    assert np.isnan(settlement.day_ahead[first_2011:, :, column_first]).all()
    assert not np.isnan(settlement.day_ahead[:first_2011, :, column_first]).any()
    assert np.isnan(settlement.day_ahead[:first_2011, :, column_second]).all()
    assert not np.isnan(settlement.day_ahead[:, :, 2]).any()  # hubs always trade


def test_every_location_rescore_reports_both_stages():
    evaluator = Evaluator.synthetic(days=900, seed=4)
    genome = FOUNDERS["always_inc"]
    first, last = evaluator.store.days[500], evaluator.store.days[864]
    result = every_location_rescore(
        genome, evaluator, first, last, every_location_evaluator=evaluator
    )
    assert result["period"] == [first.isoformat(), last.isoformat()]
    assert result["stage_c"] == result["own_stage"]
    assert result["stage_c"]["locations_traded"] == len(evaluator.store.locations)
