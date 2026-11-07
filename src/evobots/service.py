"""The single bridge between the app and the core (`docs/design_spec.md` §14.5, §15).

The app (`evobots.app`) calls only this module. It validates input, runs searches in a
background thread (one at a time), and returns plain data or finished HTML/SVG fragments
computed in Python, so the browser never computes a result.

Runs are saved under runs/<run id>/ (git-ignored): the settings, a summary, and the best
bot's genome and generated code.
"""

import dataclasses
import datetime
import html
import io
import json
import subprocess
import threading
import zipfile
from pathlib import Path

import numpy as np

from evobots.bots.codegen import trader_source
from evobots.bots.genome import describe, genome_id, genome_to_json
from evobots.config import load_data_settings
from evobots.config.capital import CapitalSettings
from evobots.qd.map_elites import (
    DIRECTION_BINS,
    SELECTIVITY_BINS,
    RunSettings,
    first_failed_gate,
    run_evolution,
)
from evobots.simulate.market import (
    point_in_time_features,
    read_miso_hub_market,
    synthetic_hub_market,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIRECTORY = REPOSITORY_ROOT / "runs"
# Sliders: (label, one-line explanation, minimum, maximum, step, default, unit, format).
SLIDERS = {
    "starting_capital_usd": (
        "Starting capital",
        "Money each trader starts with; it dies if it can no longer post MISO collateral.",
        250_000,
        5_000_000,
        50_000,
        1_500_000,
        "USD",
        "money",
    ),
    "daily_risk_budget_fraction": (
        "Daily risk budget",
        "Share of equity a 1-in-100 bad day may cost; the leverage knob.",
        0.005,
        0.05,
        0.005,
        0.02,
        "fraction",
        "percent",
    ),
    "max_mw_per_hub_hour": (
        "MW cap per hub-hour",
        "Largest bid at one hub in one hour; also capped at 5 % of the hub's typical volume.",
        0.5,
        20,
        0.5,
        5,
        "MW",
        "number",
    ),
    "training_years": (
        "Training years",
        "History each trader is scored on before the unseen test year (2024-09 → 2025-09).",
        1,
        10,
        1,
        5,
        "years",
        "integer",
    ),
    "evaluations": (
        "Traders to evaluate",
        "Search budget; about 30 per second on this machine.",
        100,
        5000,
        100,
        600,
        "traders",
        "integer",
    ),
    "selection_pressure": (
        "Selection pressure",
        "0 = every elite equally likely to have offspring; 1 = the fittest strongly favoured.",
        0,
        1,
        0.1,
        0.5,
        "",
        "number",
    ),
    "cost_multiple": (
        "Cost multiple",
        "Fees and uplift (estimates: $0.20/MWh) times this; 2 is the stress test.",
        1,
        3,
        0.5,
        1,
        "×",
        "number",
    ),
    "seed": (
        "Random seed",
        "Same settings and seed give exactly the same run.",
        1,
        999,
        1,
        1,
        "",
        "integer",
    ),
}
INTEGER_SETTINGS = {"training_years", "evaluations", "seed"}
# Files never put in the downloadable app: data, local secrets, run outputs, and (unless
# the user's [data] switch allows it) MISO-derived tables (docs/data_sources.md §3).
EXCLUDED_PREFIXES = ("data/raw/", "data/store/", "data/holdout/", "data/inbox/", "runs/")
EXCLUDED_FILES = ("config/local.toml",)
MISO_DERIVED_FILES = (
    "docs/data/benchmark_full_size_daily_pnl.csv",
    "docs/data/capital_sweep.csv",
    "docs/data/claude_science_check.csv",
    "docs/data/fixed_cost_capital_floor.csv",
    "docs/data/headroom_trailing.csv",
    "docs/data/hub_price_stats.csv",
    "docs/data/hub_volume_stats.csv",
    "docs/data/mpd_history.csv",
    "docs/data/trailing_breach_rate_by_year_2015_2025.csv",
    "docs/data/trailing_p99_daily_loss.csv",
    "docs/data/figures/point_in_time_full_size_threshold.svg",
    "docs/design/preview_data_page.html",
    "tools/capital_explorer.html",
)


class Service:
    """Holds the market data, the current job and the latest result."""

    def __init__(self, is_synthetic=False, runs_directory=None):
        """Load MISO hub data if built on this machine, else synthetic demo data.

        Args:
            is_synthetic: use synthetic demo data even when MISO data is built.
            runs_directory: where runs are saved (default runs/ in the repository).
        """
        self.runs_directory = Path(runs_directory) if runs_directory else RUNS_DIRECTORY
        market = (
            None
            if is_synthetic
            else read_miso_hub_market(
                REPOSITORY_ROOT / "data/store/hub_prices.csv.gz",
                REPOSITORY_ROOT / "data/store/hub_arrays.npz",
            )
        )
        self.market = market or synthetic_hub_market()
        self.features = point_in_time_features(self.market)
        self.lock = threading.Lock()
        self.status = {"state": "idle", "done": 0, "budget": 0, "message": "No run yet."}
        self.result = None
        self.result_settings = None
        self.run_number = (
            len(list(self.runs_directory.glob("R*"))) if self.runs_directory.exists() else 0
        )
        self.is_stop_requested = False

    # ----- inputs -----
    def slider_definitions(self):
        """Every slider with its explanation and badge, for the page."""
        return [
            {
                "name": name,
                "label": label,
                "explanation": explanation,
                "minimum": minimum,
                "maximum": maximum,
                "step": step,
                "default": default,
                "unit": unit,
                "format": value_format,
            }
            for name, (
                label,
                explanation,
                minimum,
                maximum,
                step,
                default,
                unit,
                value_format,
            ) in SLIDERS.items()
        ]

    def run_settings_from(self, values):
        """Validate slider values into RunSettings; raise ValueError with a plain message."""
        clean = {}
        for name, (label, _, minimum, maximum, _, default, _, _) in SLIDERS.items():
            value = values.get(name, default)
            try:
                number = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"{label} must be a number") from error
            if not minimum <= number <= maximum:
                raise ValueError(f"{label} must be between {minimum} and {maximum}")
            clean[name] = int(number) if name in INTEGER_SETTINGS else number
        settings = RunSettings(**clean)
        settings.capital_settings()  # validates the capital values
        return settings

    # ----- jobs -----
    def start(self, values, is_refine=False):
        """Start a run (or a refine run seeded with the best bot) in the background."""
        settings = self.run_settings_from(values)
        with self.lock:
            if self.status["state"] == "running":
                raise ValueError("A run is already going; wait for it or stop it.")
            seeds = None
            if is_refine:
                trader = self.chosen_trader()
                if trader is None:
                    raise ValueError("Run a simulation first: there is no bot to refine.")
                seeds = {trader.trader_id: trader.genome}
            self.run_number += 1
            run_number = self.run_number
            self.is_stop_requested = False
            self.status = {
                "state": "running",
                "done": 0,
                "budget": settings.evaluations,
                "message": ("Refining " + next(iter(seeds))) if seeds else "Searching",
                "run": f"R{run_number}",
            }
        thread = threading.Thread(target=self._run, args=(settings, run_number, seeds), daemon=True)
        thread.start()
        return self.status

    def stop(self):
        """Ask the running search to stop after the current trader."""
        self.is_stop_requested = True

    def _run(self, settings, run_number, seeds):
        def progress(done, budget, best_fitness):
            self.status.update(done=done, budget=budget, best_training_fitness=best_fitness)

        try:
            result = run_evolution(
                self.market,
                self.features,
                settings,
                run_number=run_number,
                seed_genomes=seeds,
                progress=progress,
                should_stop=lambda: self.is_stop_requested,
            )
            with self.lock:
                self.result, self.result_settings = result, settings
                self.status.update(state="done", message=self.what_happened())
            self._save(run_number, settings, result)
        except Exception as error:  # report any failure on the page instead of hanging
            self.status.update(state="error", message=f"The run failed: {error}")

    def _save(self, run_number, settings, result):
        """Write the run's settings, summary and best bot under runs/R<n>/."""
        folder = self.runs_directory / f"R{run_number}"
        folder.mkdir(parents=True, exist_ok=True)
        summary = {
            "settings": dataclasses.asdict(settings),
            "data": self.market.source,
            "evaluations": result.evaluations,
            "elites": len(result.elites),
            "best": result.best.trader_id if result.best else None,
            "what_happened": self.what_happened(),
            "saved_at_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        }
        (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        trader = self.chosen_trader()
        if trader is not None:
            (folder / f"{trader.trader_id}.json").write_text(
                genome_to_json(trader.genome), encoding="utf-8"
            )
            (folder / f"{trader.trader_id}.py").write_text(self.best_code()[1], encoding="utf-8")

    # ----- outputs -----
    def chosen_trader(self):
        """The best bot, or the nearest candidate when no bot passes the gates."""
        if self.result is None:
            return None
        return self.result.best or self.result.nearest_candidate

    def what_happened(self):
        """A deterministic paragraph about the latest run (§15.2)."""
        result = self.result
        if result is None:
            return "No run yet."
        settings = self.result_settings
        start = settings.starting_capital_usd
        parts = [
            f"Scored {result.evaluations:,} traders on {self.market.source} from "
            f"{result.training_days[0]} to {result.training_days[1]}; "
            f"{len(result.elites)} kinds of trader survived and hold a cell of the map."
        ]
        trader = result.best
        if trader is not None:
            parts.append(
                f"The best bot, {trader.trader_id}, turned ${start:,.0f} into "
                f"${trader.test.final_equity_usd:,.0f} in the unseen test year "
                f"{result.test_days[0]} to {result.test_days[1]} "
                f"(${trader.test_doubled_costs.final_equity_usd:,.0f} with doubled costs), "
                f"with a worst fall from peak of {trader.test.max_drawdown_fraction:.1%}."
            )
        elif result.nearest_candidate is not None:
            nearest = result.nearest_candidate
            parts.append(
                "Do nothing: no trader passes the gates. The nearest candidate, "
                f"{nearest.trader_id}, {first_failed_gate(nearest)}."
            )
        return " ".join(parts)

    def results_view(self):
        """Plain data for the results section (all numbers computed here)."""
        trader = self.chosen_trader()
        if trader is None:
            return None
        result = self.result

        def career(evaluation):
            return {
                "final_equity": f"${evaluation.final_equity_usd:,.0f}",
                "fitness": f"{evaluation.fitness:+.3f}",
                "drawdown": f"{evaluation.max_drawdown_fraction:.1%}",
                "alive": "survived" if evaluation.is_alive else "ran out of money",
                "direction": f"{evaluation.net_direction:+.2f}",
                "selectivity": f"{evaluation.selectivity:.1%}",
            }

        return {
            "is_best": result.best is not None,
            "trader_id": trader.trader_id,
            "genome_id": genome_id(trader.genome),
            "origin": trader.origin,
            "parents": ", ".join(trader.parent_ids) or "none",
            "rules": describe(trader.genome),
            "training": career(trader.training),
            "test": career(trader.test),
            "test_doubled": career(trader.test_doubled_costs),
            "failed_gate": first_failed_gate(trader),
            "equity_svg": self.equity_svg(trader),
            "map_svg": self.map_svg(),
            "elites": [
                {
                    "trader_id": elite.trader_id,
                    "origin": elite.origin,
                    "training": f"{elite.training.fitness:+.3f}",
                    "test": f"{elite.test.fitness:+.3f}",
                    "gate": first_failed_gate(elite) or "passes",
                }
                for elite in result.elites[:12]
            ],
            "training_window": f"{result.training_days[0]} → {result.training_days[1]}",
            "test_window": f"{result.test_days[0]} → {result.test_days[1]}",
        }

    def equity_svg(self, trader, width=640, height=180):
        """Equity over training then test year as an inline SVG (ink line, test shaded)."""
        training = trader.training.equity_usd
        test = trader.test.equity_usd * (training[-1] / self.result_settings.starting_capital_usd)
        values = np.concatenate([training, test])
        if len(values) < 2:
            return ""
        low, high = float(values.min()), float(values.max())
        span = high - low or 1.0
        horizontal_scale = (width - 2) / (len(values) - 1)
        points = " ".join(
            f"{index * horizontal_scale + 1:.1f},{height - 20 - (value - low) / span * (height - 40):.1f}"
            for index, value in enumerate(values)
        )
        test_start_position = len(training) * horizontal_scale
        return (
            f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
            f'aria-label="Equity over training and test">'
            f'<rect x="{test_start_position:.1f}" y="0" width="{width - test_start_position:.1f}" height="{height}" '
            f'fill="none" stroke="var(--colour-hairline)" stroke-dasharray="3 3"/>'
            f'<polyline points="{points}" fill="none" stroke="var(--colour-ink)" stroke-width="1"/>'
            f'<text x="2" y="12" class="axis">${high:,.0f}</text>'
            f'<text x="2" y="{height - 4}" class="axis">${low:,.0f}</text>'
            f'<text x="{test_start_position + 4:.1f}" y="12" class="axis">test year</text></svg>'
        )

    def map_svg(self, cell_size=28):
        """The MAP-Elites grid: each cell's greyness = its elite's training fitness."""
        result = self.result
        cells = {elite.cell(): elite for elite in result.elites}
        fitness_values = [elite.training.fitness for elite in result.elites] or [0.0]
        low, high = min(fitness_values), max(fitness_values)
        width, height = DIRECTION_BINS * cell_size, SELECTIVITY_BINS * cell_size
        parts = [
            f'<svg viewBox="0 0 {width + 2} {height + 2}" width="{width + 2}" role="img" '
            f'aria-label="Map of surviving trader kinds">'
        ]
        for column in range(DIRECTION_BINS):
            for row in range(SELECTIVITY_BINS):
                left, top = column * cell_size + 1, (SELECTIVITY_BINS - 1 - row) * cell_size + 1
                elite = cells.get((column, row))
                if elite is None:
                    fill = "#ffffff"
                    title = "empty"
                else:
                    share = (elite.training.fitness - low) / ((high - low) or 1.0)
                    grey = int(230 - share * 200)
                    fill = f"rgb({grey},{grey},{grey})"
                    title = f"{elite.trader_id}: F {elite.training.fitness:+.3f}"
                parts.append(
                    f'<rect x="{left}" y="{top}" width="{cell_size}" height="{cell_size}" '
                    f'fill="{fill}" stroke="var(--colour-hairline)"><title>'
                    f"{html.escape(title)}</title></rect>"
                )
        parts.append("</svg>")
        return "".join(parts)

    def best_code(self):
        """(file name, source) of the chosen trader's generated Python file."""
        trader = self.chosen_trader()
        if trader is None:
            raise ValueError("No bot yet: run a simulation first.")
        origin = trader.origin + (
            f" (parents {', '.join(trader.parent_ids)})" if trader.parent_ids else ""
        )
        return f"trader_{trader.trader_id}.py", trader_source(
            trader.genome, trader.trader_id, origin
        )

    def best_genome(self):
        """(file name, canonical JSON) of the chosen trader's genome."""
        trader = self.chosen_trader()
        if trader is None:
            raise ValueError("No bot yet: run a simulation first.")
        return f"trader_{trader.trader_id}.json", genome_to_json(trader.genome)

    def data_status(self):
        """One line on which data the app is using."""
        if self.market.source == "MISO":
            return (
                f"MISO hub prices {self.market.days[0]} → {self.market.days[-1]}, built on this "
                "machine; the sealed hold-out (2025-09-22 → 2026-09-21) is never read."
            )
        return (
            "Demo mode: synthetic prices with a planted pattern (DA above RT by $2/MWh in "
            "hours 7–22), as no MISO data is built on this machine. To use real data, see "
            "“Use real MISO data” in README.md."
        )


def app_files(root=REPOSITORY_ROOT):
    """Relative paths of the files that go into the downloadable app."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        listed = [
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.parts and ".venv" not in path.parts
        ]
    is_miso_allowed = load_data_settings(
        root / "configs/10_miso_hubs.toml"
    ).is_miso_redistribution_allowed
    files = []
    for relative in listed:
        if relative.startswith(EXCLUDED_PREFIXES) or relative in EXCLUDED_FILES:
            continue
        if relative in MISO_DERIVED_FILES and not is_miso_allowed:
            continue
        if (root / relative).is_file():
            files.append(relative)
    return sorted(files)


def app_zip_bytes(root=REPOSITORY_ROOT):
    """The whole app as a zip, without data, secrets or (by default) MISO-derived tables."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in app_files(root):
            archive.write(root / relative, f"evobots/{relative}")
        archive.writestr(
            "evobots/MISO_DATA_NOT_INCLUDED.txt",
            "MISO's terms forbid redistributing its data, so this copy has no MISO prices or "
            "MISO-derived tables. The app starts in demo mode with synthetic prices. To use "
            "real data, follow 'Use real MISO data' in README.md on your own machine.\n",
        )
    return buffer.getvalue()


def default_capital_note():
    """The capital defaults shown on the page (for the badge text)."""
    settings = CapitalSettings()
    return f"Defaults: ${settings.starting_capital_usd:,.0f}, {settings.daily_risk_budget_fraction:.0%} risk budget."
