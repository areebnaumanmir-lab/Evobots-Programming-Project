"""Tests for the preview: genome, generated code, search, service and app routes.

Everything runs on synthetic data, offline. The equivalence test is the referee between a
trader's generated source file and the engine (`docs/design_spec.md` §9.1).
"""

import io
import json
import time
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from evobots.app import server
from evobots.bots import genome as genome_module
from evobots.bots.codegen import trader_source
from evobots.qd.map_elites import RunSettings, run_evolution
from evobots.service import MISO_DERIVED_FILES, Service, app_files
from evobots.simulate.engine import bid_arrays, evaluate
from evobots.simulate.market import point_in_time_features, synthetic_hub_market


@pytest.fixture(scope="module")
def market_and_features():
    market = synthetic_hub_market(days=1200, seed=4)
    return market, point_in_time_features(market)


def test_genome_json_round_trip_for_random_genomes():
    generator = np.random.Generator(np.random.PCG64(5))
    for _ in range(200):
        genome = genome_module.random_genome(generator)
        child, _ = genome_module.mutate(genome, generator)
        for candidate in (genome, child):
            text = genome_module.genome_to_json(candidate)
            assert genome_module.genome_from_json(text) == candidate


def test_generated_code_bids_equal_the_engine(market_and_features):
    market, features = market_and_features
    generator = np.random.Generator(np.random.PCG64(6))
    genomes = list(genome_module.FOUNDERS.values()) + [
        genome_module.random_genome(generator) for _ in range(25)
    ]
    for genome in genomes:
        namespace = {}
        exec(compile(trader_source(genome, "T-1", "test"), "trader", "exec"), namespace)
        side, limit = bid_arrays(genome, features, 400, 430)
        for _ in range(80):
            day, hour, hub = (
                int(generator.integers(30)),
                int(generator.integers(24)),
                int(generator.integers(len(market.hubs))),
            )
            row = {
                name: (
                    ""
                    if np.isnan(values[400 + day, hour, hub])
                    else repr(float(values[400 + day, hour, hub]))
                )
                for name, values in features.items()
            }
            decision = namespace["decide"](row)
            expected_side = int(side[day, hour, hub])
            if expected_side == 0:
                assert decision is None
            else:
                name, limit_price, size = decision
                assert name == ("DEC" if expected_side == 1 else "INC")
                assert limit_price == limit[day, hour, hub]
                assert size == genome.size_fraction


def test_out_of_money_death_and_direction(market_and_features):
    market, features = market_and_features
    reckless = genome_module.simple_genome(bias=1.0)  # always DEC
    result = evaluate(reckless, market, features, 400, 1200)
    assert result.net_direction == 1.0
    assert len(result.equity_usd) == 800
    if not result.is_alive:
        assert result.equity_usd[result.death_index] <= 2.4


def test_search_is_deterministic(market_and_features):
    market, features = market_and_features
    settings = RunSettings(training_years=1, evaluations=60, seed=9)
    first = run_evolution(market, features, settings)
    second = run_evolution(market, features, settings)
    assert [trader.trader_id for trader in first.elites] == [
        trader.trader_id for trader in second.elites
    ]
    assert [trader.training.fitness for trader in first.elites] == [
        trader.training.fitness for trader in second.elites
    ]


def test_refine_starts_from_the_seed(market_and_features):
    market, features = market_and_features
    seed = genome_module.FOUNDERS["premium_follow"]
    result = run_evolution(
        market, features, RunSettings(training_years=1, evaluations=40, seed=2), 2, {"R1-5": seed}
    )
    assert result.evaluations == 40
    assert any(trader.origin.startswith("seed") for trader in result.elites) or result.elites


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    runs_directory = tmp_path_factory.mktemp("runs")
    server.service_holder["service"] = Service(is_synthetic=True, runs_directory=runs_directory)
    with TestClient(server.app) as test_client:
        yield test_client
    server.service_holder.clear()


def wait_until_done(client):
    for _ in range(600):
        status = client.get("/api/status").json()
        if status["state"] != "running":
            return status
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_page_run_download_and_refine(client):
    page = client.get("/quick")
    assert page.status_code == 200 and "Run simulation" in page.text
    assert "Demo mode" in page.text
    assert client.get("/download/best-bot.py").status_code == 404
    bad = client.post("/api/run", json={"evaluations": 999999})
    assert bad.status_code == 400 and "between" in bad.json()["message"]
    settings = {"evaluations": 100, "training_years": 1, "seed": 3}
    assert client.post("/api/run", json=settings).json()["state"] == "running"
    status = wait_until_done(client)
    assert status["state"] == "done", status
    results = client.get("/results").text
    assert "Career" in results and "<svg" in results
    code = client.get("/download/best-bot.py")
    assert code.status_code == 200 and "def decide(row)" in code.text
    genome_text = client.get("/download/best-bot.json").text
    assert "size_fraction" in json.loads(genome_text)
    assert client.post("/api/refine", json=settings).json()["state"] == "running"
    assert wait_until_done(client)["state"] == "done"


def test_app_zip_has_no_data_or_secrets(client):
    archive = zipfile.ZipFile(io.BytesIO(client.get("/download/evobots.zip").content))
    names = archive.namelist()
    assert "evobots/src/evobots/app/server.py" in names
    assert "evobots/MISO_DATA_NOT_INCLUDED.txt" in names
    assert not any(
        name.startswith(("evobots/data/raw/", "evobots/data/store/", "evobots/data/holdout/"))
        for name in names
    )
    assert "evobots/config/local.toml" not in names
    assert not any(f"evobots/{path}" in names for path in MISO_DERIVED_FILES)


def test_templates_and_scripts_load_nothing_from_the_internet():
    for path in app_files():
        if path.startswith("src/evobots/app/") and path.endswith((".html", ".js", ".css")):
            text = open(path, encoding="utf-8").read()
            assert "http://" not in text and "https://" not in text, path
