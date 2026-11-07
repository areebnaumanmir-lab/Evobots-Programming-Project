"""The website's bridge: the same service, run inside the browser by Pyodide (round 30).

GitHub Pages serves static files only, so the public website runs evobots' Python in the
visitor's browser (Pyodide, Python compiled to WebAssembly) inside a Web Worker. This module
is what the worker calls. It reuses `evobots.service.Service` for validation, every number,
chart and paragraph, and renders the same `results.html` template as the local app, so the
page shows exactly what the local app shows. The JavaScript only passes messages.

There are no threads in the browser, so a run is a plain function call that reports progress
through a callback. The website loads the MISO hub table it carries (MISO's written
permission, round 42; conditions in the site's data/NOTICE.md) and falls back to synthetic
demo data without it; a visitor can also load their own hub table, which stays in their
browser.

Example:
    >>> session = WebSession(runs_directory=None, is_small_demo=True)
    >>> reply = session.run('{"evaluations": 100, "training_years": 1}', False)
    >>> reply["state"], "Career" in reply["results_html"]
    ('done', True)
"""

import json
from pathlib import Path

import jinja2

from evobots.qd.map_elites import run_evolution
from evobots.service import Service
from evobots.simulate.market import (
    point_in_time_features,
    read_miso_hub_market,
    synthetic_hub_market,
)

TEMPLATE_DIRECTORY = Path(__file__).resolve().parent / "app" / "templates"
UPLOADED_TABLE_PATH = Path("/tmp/evobots/hub_prices.csv.gz")
UPLOADED_CACHE_PATH = Path("/tmp/evobots/hub_arrays.npz")
# How often (in traders) progress is reported to the page.
PROGRESS_EVERY_TRADERS = 10
# The smaller demo market used by the doctest (the site uses the full 10-year one).
SMALL_DEMO_DAYS = 1200


class WebSession:
    """One visitor's session: the market in use, the latest run and its best bot."""

    def __init__(self, runs_directory="/tmp/evobots/runs", is_small_demo=False):
        """Start on synthetic demo data.

        Args:
            runs_directory: where the service saves runs (in the browser's memory file system).
            is_small_demo: a shorter synthetic market (tests only).
        """
        self.service = Service(is_synthetic=True, runs_directory=runs_directory or "/tmp/runs")
        if is_small_demo:
            self.service.market = synthetic_hub_market(days=SMALL_DEMO_DAYS)
            self.service.features = point_in_time_features(self.service.market)
        self.is_bundled_table = False
        self.templates = jinja2.Environment(
            loader=jinja2.FileSystemLoader(TEMPLATE_DIRECTORY), autoescape=True
        )

    def data_status(self):
        """One line on which data the page is using."""
        days = self.service.market.days
        if self.service.market.source == "MISO" and self.is_bundled_table:
            return (
                f"MISO hub prices, {days[0]} → {days[-1]}. Source: Midcontinent Independent "
                "System Operator, Inc. (MISO), public market reports, misoenergy.org; reproduced "
                "with MISO's permission for this project. If you reuse them, read data/NOTICE.md "
                "on this site for the conditions. The sealed hold-out year is never read."
            )
        if self.service.market.source == "MISO":
            return (
                f"Your MISO hub table, {days[0]} → {days[-1]}, loaded in this browser only "
                "(nothing is uploaded to a server). The sealed hold-out year is never read."
            )
        return (
            "Demo mode: synthetic prices with a planted pattern (DA above RT by $2/MWh in hours "
            "7–22) for the search to find. The MISO table couldn't be loaded here; if you built "
            "it with the downloadable app, load it below. It stays in your browser."
        )

    def use_uploaded_table(self, is_bundled=False):
        """Switch to the hub table the page wrote to UPLOADED_TABLE_PATH; return a reply.

        `is_bundled` marks the site's own MISO table (loaded at start-up) rather than one the
        visitor chose.
        """
        UPLOADED_CACHE_PATH.unlink(missing_ok=True)
        market = read_miso_hub_market(UPLOADED_TABLE_PATH, UPLOADED_CACHE_PATH)
        if market is None:
            return {"state": "error", "message": "No table was loaded."}
        self.service.market = market
        self.service.features = point_in_time_features(market)
        self.service.result = None
        self.is_bundled_table = is_bundled
        return {
            "state": "idle",
            "message": "MISO hub prices loaded." if is_bundled else "Your MISO table is loaded.",
            "data": self.data_status(),
        }

    def run(self, values_json, is_refine, progress=None):
        """Run a search (or a refine run) and return the reply for the page.

        Args:
            values_json: the slider values as JSON text.
            is_refine: start from the current best bot and variations of it.
            progress: optional callable(done, budget) for the page's status line.

        Returns:
            {"state": "done" | "error", "message": text, "results_html": HTML}.
        """
        service = self.service
        try:
            settings = service.run_settings_from(json.loads(values_json))
        except ValueError as error:
            return {"state": "error", "message": str(error), "results_html": ""}
        seeds = None
        if is_refine:
            trader = service.chosen_trader()
            if trader is None:
                return {
                    "state": "error",
                    "message": "Run a simulation first: there is no bot to refine.",
                    "results_html": "",
                }
            seeds = {trader.trader_id: trader.genome}
        service.run_number += 1

        def report(done, budget, best_fitness):
            if progress is not None and (done % PROGRESS_EVERY_TRADERS == 0 or done == budget):
                progress(done, budget)

        result = run_evolution(
            service.market,
            service.features,
            settings,
            run_number=service.run_number,
            seed_genomes=seeds,
            progress=report,
        )
        service.result, service.result_settings = result, settings
        message = service.what_happened()
        service.status = {"state": "done", "message": message}
        return {"state": "done", "message": message, "results_html": self.results_html()}

    def results_html(self):
        """The results section, rendered from the same template as the local app."""
        return self.templates.get_template("results.html").render(
            results=self.service.results_view(), status=self.service.status
        )

    def best_code(self):
        """{"name": file name, "text": the best bot's standalone Python file}."""
        name, text = self.service.best_code()
        return {"name": name, "text": text}

    def best_genome(self):
        """{"name": file name, "text": the best bot's genome JSON}."""
        name, text = self.service.best_genome()
        return {"name": name, "text": text}
