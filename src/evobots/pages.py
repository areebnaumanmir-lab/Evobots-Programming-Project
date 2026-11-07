"""The data behind every app page (`docs/design_spec.md` §15).

The app reaches it only through `evobots.service`.

A page is a dict: {"title", "description", "sections": [...]}. A section is
{"title", "description", "kind", ...} with kind one of:
- "metrics": {"items": [(label, value, note)]};
- "table": {"headers": [...], "rows": [[...]], "links": optional {row index: url}};
- "chart": {"svg": SVG text computed here};
- "text": {"paragraphs": [...]}; "list": {"items": [...]};
- "code": {"text": ..., "download": url};
- "html": {"html": Markdown rendered to HTML (Docs page only)};
- "actions": {"forms": [{"label", "url", "fields": [...], "confirm": text or None}]}.
The template (`app/templates/page.html`) draws each kind; no number is computed in the browser.

Example:
    >>> page = gallery_page()
    >>> {section["kind"] for section in page["sections"]} >= {"metrics", "table", "chart"}
    True
"""

import csv
import datetime
import json
import pickle
import re
import subprocess
import sys
import time
import tomllib
import urllib.parse
from pathlib import Path

import numpy as np

from evobots import charts

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIRECTORY = REPOSITORY_ROOT / "runs"
DOCS_DIRECTORY = REPOSITORY_ROOT / "docs"
CACHE_DIRECTORY = RUNS_DIRECTORY / "cache"
LOG_DIRECTORY = RUNS_DIRECTORY / "logs"
CAPITAL_SETTINGS_PATH = REPOSITORY_ROOT / "config" / "capital.local.toml"
PAGES_PATH = Path(__file__).resolve().parent / "app" / "pages.toml"
ORFE_DIRECTORY = DOCS_DIRECTORY / "data" / "orfe"
STOP_FILE_NAME = "stop.request"
HOLDOUT_LOG_PATH = REPOSITORY_ROOT / "data" / "holdout_access_log.jsonl"
TRADERS_PER_PAGE = 100
STAGE_CLUSTERS_PATH = REPOSITORY_ROOT / "data" / "store" / "stage_d_clusters.json"
STAGES = (("A", "A: the trading hubs"), ("D", "D: cluster representatives (yearly)"))
STATE = {"evaluator": None, "is_demo": None, "jobs": {}}


# ----- shared helpers -----


def section(title, description, kind, **content):
    """One page section."""
    return {"title": title, "description": description, "kind": kind, **content}


def navigation():
    """The left navigation from pages.toml: [(group, [(title, path)])]."""
    data = tomllib.loads(PAGES_PATH.read_text(encoding="utf-8"))
    groups = []
    for group in data["group"]:
        groups.append((group["name"], [(page["title"], page["path"]) for page in group["page"]]))
    return groups


def evaluator(is_demo=False):
    """The shared evaluator (MISO when built here, else synthetic), loaded once."""
    if STATE["evaluator"] is None or STATE["is_demo"] != is_demo:
        from evobots.qd.evaluation import Evaluator

        loaded = None if is_demo else Evaluator.from_store(REPOSITORY_ROOT)
        STATE["evaluator"] = loaded or Evaluator.synthetic()
        STATE["is_demo"] = is_demo
    return STATE["evaluator"]


def full_runs():
    """Full MAP-Elites runs (those with a checkpoint), newest first, with their status."""
    runs = []
    for directory in RUNS_DIRECTORY.glob("R*"):
        status_path = directory / "status.json"
        if not (directory / "checkpoint.pickle").exists() or not status_path.exists():
            continue
        status = json.loads(status_path.read_text(encoding="utf-8"))
        current_path = directory / "deployable" / "current_bot.json"
        status["current"] = (
            json.loads(current_path.read_text(encoding="utf-8")) if current_path.exists() else None
        )
        status["directory"] = directory
        runs.append(status)
    return sorted(runs, key=lambda status: status.get("updated_at_utc", ""), reverse=True)


def holdout_status_text():
    """'Sealed: never opened' or the latest opening, read from the committed access log.

    Reads the log only (the hold-out accessor itself is imported by the final test alone).
    """
    if not HOLDOUT_LOG_PATH.exists():
        return "Sealed: never opened"
    openings = [
        json.loads(line)
        for line in HOLDOUT_LOG_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not openings:
        return "Sealed: never opened"
    latest = openings[-1]
    return (
        f"Opened on {latest['opened_at_utc'][:10]} for {latest['trader_id']} in {latest['run_id']}"
    )


def best_bot_link():
    """(text, url) of the top-right Best bot link (§11.4)."""
    for status in full_runs():
        current = status["current"]
        if current and current.get("decision") == "trade":
            return (
                f"Best bot: {current['name']}",
                f"/traders/{status['run_id']}/{current['trader_id']}",
            )
    return "Best bot: do nothing", "/best"


def read_checkpoint(run_id):
    """A run's checkpoint state (archive, bandit, counters), or None."""
    path = RUNS_DIRECTORY / run_id / "checkpoint.pickle"
    if not path.exists():
        return None
    return pickle.loads(path.read_bytes())


def table_from_records(records, columns):
    """(headers, rows) from dicts and [(header, key or callable)]."""
    headers = [header for header, _ in columns]
    rows = []
    for record in records:
        row = []
        for _, key in columns:
            value = key(record) if callable(key) else record.get(key)
            row.append("" if value is None else value)
        rows.append(row)
    return headers, rows


def money(value):
    """$1,234,567."""
    return f"${value:,.0f}"


def thin(values, points=1500):
    """Every k-th value so a chart has at most `points` points."""
    step = max(1, len(values) // points)
    return values[::step]


# ----- jobs (long work in worker processes) -----


def start_job(name, arguments):
    """Start `evobots <arguments>` in a worker process, logging to runs/logs/<name>.log."""
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    log = (LOG_DIRECTORY / f"{name}.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "evobots.cli", *arguments],
        cwd=REPOSITORY_ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    STATE["jobs"][name] = {"process": process, "started": time.time(), "arguments": arguments}
    return {"state": "running", "job": name, "message": f"Started: evobots {' '.join(arguments)}"}


def job_status(name):
    """{"state": running | done | failed | unknown, "log": last lines}."""
    job = STATE["jobs"].get(name)
    log_path = LOG_DIRECTORY / f"{name}.log"
    tail = log_path.read_text(encoding="utf-8").splitlines()[-5:] if log_path.exists() else []
    if job is None:
        return {"state": "unknown", "log": tail}
    code = job["process"].poll()
    state = "running" if code is None else ("done" if code == 0 else "failed")
    return {"state": state, "log": tail, "seconds": round(time.time() - job["started"])}


def next_run_id():
    """R<n> after the highest run number in runs/."""
    numbers = [int(path.name[1:]) for path in RUNS_DIRECTORY.glob("R*") if path.name[1:].isdigit()]
    return f"R{max(numbers, default=0) + 1}"


def validated_int(value, label, low, high):
    """An integer in [low, high] or ValueError with a plain message."""
    try:
        number = int(float(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a number") from error
    if not low <= number <= high:
        raise ValueError(f"{label} must be between {low:,} and {high:,}")
    return number


def start_search(values, is_demo=False):
    """Start a MAP-Elites run from the Evolution page's form."""
    evaluations = validated_int(
        values.get("evaluations", 5000), "Traders to evaluate", 100, 10_000_000
    )
    workers = validated_int(values.get("workers", 2), "Worker processes", 1, 64)
    seed = validated_int(values.get("seed", 1), "Random seed", 1, 10**9)
    stage = str(values.get("stage", "A"))
    if stage not in dict(STAGES):
        raise ValueError("Locations must be stage A or D")
    if stage == "D" and not is_demo and not STAGE_CLUSTERS_PATH.exists():
        raise ValueError("Stage D isn't built here: run `evobots data build --stage D` first")
    run_id = next_run_id()
    arguments = [
        "run",
        "--run-id",
        run_id,
        "--evaluations",
        str(evaluations),
        "--workers",
        str(workers),
        "--seed",
        str(seed),
    ]
    if stage != "A" and not is_demo:
        arguments += ["--stage", stage]
    if values.get("no_founders"):
        arguments.append("--no-founders")
    if is_demo:
        arguments.append("--demo")
    return start_job(run_id, arguments)


def stop_search(run_id):
    """Ask a run to stop after its current batch (it checkpoints first)."""
    directory = RUNS_DIRECTORY / run_id
    if not directory.exists():
        raise ValueError(f"no run {run_id}")
    (directory / STOP_FILE_NAME).write_text("stop\n", encoding="utf-8")
    return {
        "state": "stopping",
        "message": f"{run_id} will stop after its current batch and checkpoint.",
    }


def resume_search(run_id, is_demo=False):
    """Continue a stopped run."""
    (RUNS_DIRECTORY / run_id / STOP_FILE_NAME).unlink(missing_ok=True)
    return start_job(
        f"{run_id}-resume",
        ["resume", str(RUNS_DIRECTORY / run_id)] + (["--demo"] if is_demo else []),
    )


def start_report(run_id, trader_id, is_demo=False):
    """Write a trader's report card in a worker."""
    arguments = ["report", str(RUNS_DIRECTORY / run_id), "--trader", trader_id] + (
        ["--demo"] if is_demo else []
    )
    return start_job(f"report-{trader_id}", arguments)


def start_refine(run_id, trader_id, is_demo=False):
    """A Refine run seeded with this trader (§11.5)."""
    new_id = next_run_id()
    arguments = ["refine", str(RUNS_DIRECTORY / run_id), trader_id, "--run-id", new_id] + (
        ["--demo"] if is_demo else []
    )
    return start_job(new_id, arguments)


def run_final_test(run_id, trader_id, confirmation):
    """The sealed test, once per run, only after typing the run id (§12.4)."""
    if confirmation != run_id:
        raise ValueError(
            f"type the run id ({run_id}) to confirm: the sealed test is spent once used"
        )
    return start_job(
        f"final-{run_id}",
        [
            "final-test",
            str(RUNS_DIRECTORY / run_id),
            "--trader",
            trader_id,
            "--yes",
            "--opened-by",
            "app",
        ],
    )


def start_life():
    """Life mode in a worker, saved to runs/life.json."""
    return start_job("life", ["life", "--save", str(RUNS_DIRECTORY / "life.json")])


# ----- pages -----


def home_page(is_demo=False):
    """Home: data, hold-out, runs, the deployable bot, and what needs the internet."""
    store_path = REPOSITORY_ROOT / "data/store/hub_prices.csv.gz"
    evaluation = evaluator(is_demo)
    days = evaluation.store.days
    metrics = [
        (
            "Price data",
            "MISO hubs" if evaluation.store.source == "MISO" else "synthetic demo",
            "built on this machine" if store_path.exists() else "no MISO table built here",
        ),
        ("Days", f"{days[0]} → {days[-1]}", f"{len(days):,} operating days"),
        (
            "Sealed hold-out",
            holdout_status_text(),
            "2025-09-22 → 2026-09-21, opened only by the Final test",
        ),
        ("Runs", str(len(full_runs())), "MAP-Elites runs in runs/"),
    ]
    runs = full_runs()
    headers, rows = table_from_records(
        runs,
        [
            ("Run", "run_id"),
            ("Traders", lambda status: f"{status['evaluations_done']:,}/{status['budget']:,}"),
            ("Window", lambda status: f"{status['window_index'] + 1}/{status['windows']}"),
            ("Elites", "elites"),
            ("Deepest lineage", "deepest_lineage"),
            ("Decision", lambda status: (status["current"] or {}).get("decision", "–")),
            ("Updated (UTC)", "updated_at_utc"),
        ],
    )
    links = {index: f"/evolution?run={status['run_id']}" for index, status in enumerate(runs)}
    internet = [
        "First install: `uv` and the Python packages (the launchers do it once).",
        "Weather forecasts, gas, EPU, GPR and EIA-860M: `tools/fetch_nws_forecasts.py`, "
        "`tools/fetch_series.py` (keyless sources).",
        "MISO prices: download in a browser and save into data/raw/miso/ (MISO forbids automated "
        "access); then `evobots data build`.",
        "Everything else (runs, reports, the app) works offline.",
    ]
    text, url = best_bot_link()
    return {
        "title": "evobots",
        "description": (
            "Evolves small, readable trading bots for MISO virtual bidding, judges each like a "
            "trading career, and hands over the best one, or says “do nothing”."
        ),
        "sections": [
            *(
                []
                if evaluation.store.source == "MISO"
                else [
                    section(
                        "Running on demo prices",
                        "No MISO data on this computer yet, so every page shows synthetic prices.",
                        "list",
                        items=[
                            "Have a data pack? Put evobots-data-pack.zip in this folder or "
                            "in your Downloads folder, close this app's window and start it "
                            "again: it is imported automatically.",
                            "Or build your own from MISO's files: docs/tutorial.md, step 7.",
                        ],
                    )
                ]
            ),
            section(
                "Status", "What this copy of evobots has and has done.", "metrics", items=metrics
            ),
            section(
                "Deployable bot",
                "The best trader passing the quick gates in the newest run (§11.4).",
                "list",
                items=[f"[{text}]({url})"],
            ),
            section(
                "Runs",
                "Click a run for its map, progress and best bot.",
                "table",
                headers=headers,
                rows=rows,
                links=links,
            ),
            section(
                "Needs the internet",
                "Only these steps go online; each has an offline alternative.",
                "list",
                items=internet,
            ),
            section(
                "Quick run",
                "The one-page slider app: a short search with downloads.",
                "list",
                items=["[Open the quick run page](/quick)"],
            ),
        ],
    }


def capital_page(values=None):
    """Capital: what the capital settings imply (§13), with badges."""
    from evobots.cli import calibration_capital_summary
    from evobots.config.capital import CapitalSettings

    saved = {}
    if CAPITAL_SETTINGS_PATH.exists():
        saved = tomllib.loads(CAPITAL_SETTINGS_PATH.read_text(encoding="utf-8")).get("capital", {})
    choices = {
        **saved,
        **{key: float(value) for key, value in (values or {}).items() if value not in ("", None)},
    }
    settings = CapitalSettings(**choices)
    summary = calibration_capital_summary(settings)
    fields = [
        ("starting_capital_usd", "Starting capital", "USD", 250_000, 5_000_000, 50_000),
        ("daily_risk_budget_fraction", "Daily risk budget", "fraction", 0.005, 0.05, 0.005),
        ("credit_share_fraction", "Credit share", "fraction", 0.05, 0.8, 0.05),
        ("max_mw_per_hub_hour", "MW cap per hub-hour", "MW", 0.5, 20, 0.5),
    ]
    form = {
        "label": "Recalculate",
        "url": "/capital",
        "method": "get",
        "fields": [
            {
                "name": name,
                "label": label,
                "unit": unit,
                "type": "range",
                "min": low,
                "max": high,
                "step": step,
                "value": getattr(settings, name),
                "badge": "Your choice",
            }
            for name, label, unit, low, high, step in fields
        ],
    }
    save = {
        "label": "Save as my defaults",
        "url": "/api/capital",
        "fields": form["fields"],
        "confirm": None,
    }
    caps = settings.hub_caps_mw()
    metrics = [
        (
            "Full size",
            f"{summary['full_size_mwh_per_day']:,.0f} MWh/day",
            "Σ caps × 24 h (From market data: each hub's typical volume)",
        ),
        (
            "Capital for full size",
            money(summary["full_size_capital_usd"]),
            "1-in-100-day loss ÷ budget (full-sample calibration only)",
        ),
        (
            "Collateral at full size",
            money(summary["collateral_at_full_size_usd"]),
            "MWh × $12 MPD × 2 days (From market data, estimate)",
        ),
        (
            "Virtual MWh Limit",
            f"{summary['virtual_mwh_limit_mwh_per_day']:,.0f} MWh/day",
            "what the pledged credit supports",
        ),
    ]
    return {
        "title": "Capital",
        "description": (
            "How much money each trader starts with and how much risk it may take; every number "
            "below is computed in Python."
        ),
        "sections": [
            section(
                "Settings",
                "Move a slider and press Recalculate; Save keeps them for new runs.",
                "actions",
                forms=[form, save],
            ),
            section("What they imply", "", "metrics", items=metrics),
            section(
                "Caps by hub",
                "min(cap, 5 % of the hub's median cleared virtual MW), rounded to 0.1 MW.",
                "table",
                headers=["Hub", "MW"],
                rows=[[hub, f"{cap:g}"] for hub, cap in caps.items()],
            ),
            section("Warnings", "", "list", items=summary["warnings"] or ["None."]),
        ],
    }


def save_capital(values):
    """Write the capital choices to config/capital.local.toml (git-ignored)."""
    from evobots.config.capital import CapitalSettings

    choices = {key: float(value) for key, value in values.items() if value not in ("", None)}
    CapitalSettings(**choices)  # validates
    lines = ["# Saved from the app's Capital page.", "[capital]"] + [
        f"{key} = {value!r}" for key, value in sorted(choices.items())
    ]
    CAPITAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CAPITAL_SETTINGS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "state": "saved",
        "message": f"Saved to {CAPITAL_SETTINGS_PATH.relative_to(REPOSITORY_ROOT)}",
    }


def docs_page():
    """Docs: every document, grouped."""
    groups = {"Explanation": [], "Rounds": [], "Reference": []}
    for path in sorted(DOCS_DIRECTORY.rglob("*.md")):
        relative = path.relative_to(DOCS_DIRECTORY).as_posix()
        title = (
            path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            if path.stat().st_size
            else relative
        )
        group = (
            "Rounds"
            if relative.startswith("rounds/")
            else (
                "Reference"
                if relative
                in (
                    "config_reference.md",
                    "dependencies.md",
                    "glossary.md",
                    "verify_register.md",
                    "references.md",
                )
                else "Explanation"
            )
        )
        groups[group].append(f"[{title}](/docs/{relative})")
    return {
        "title": "Docs",
        "description": "Every document of the project, rendered here from docs/.",
        "sections": [section(name, "", "list", items=items) for name, items in groups.items()],
    }


def doc_page(relative):
    """One Markdown document rendered to HTML (internal links rewritten to /docs/…)."""
    import markdown

    path = (DOCS_DIRECTORY / relative).resolve()
    if DOCS_DIRECTORY.resolve() not in path.parents or path.suffix != ".md" or not path.exists():
        raise FileNotFoundError(relative)
    text = path.read_text(encoding="utf-8")
    base = path.parent.relative_to(DOCS_DIRECTORY.resolve()).as_posix()

    def rewrite(match):
        target = match.group(2)
        if "://" in target or target.startswith(("#", "/")):
            return match.group(0)
        resolved = (Path(base) / target).as_posix() if base != "." else target
        parts = []
        for part in resolved.split("/"):
            if part == ".." and parts:
                parts.pop()
            elif part not in ("", "."):
                parts.append(part)
        return f"[{match.group(1)}](/docs/{'/'.join(parts)})"

    text = re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", rewrite, text)
    rendered = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])
    return {
        "title": path.stem.replace("_", " "),
        "description": f"docs/{relative}",
        "sections": [section("", "", "html", html=rendered)],
    }


def gallery_page():
    """Gallery: every component in the current theme."""
    points = [(f"day {index}", float(np.sin(index / 9) * 100 + index)) for index in range(120)]
    cells = {
        (column, row): (column * row, f"cell {column},{row}")
        for column in range(10)
        for row in range(8)
        if (column + row) % 3
    }
    return {
        "title": "Gallery",
        "description": (
            "Every component in the current theme (edit app/static/theme.css and reload)."
        ),
        "sections": [
            section(
                "Metrics",
                "Title, one-line description, value.",
                "metrics",
                items=[
                    ("Final equity", "$1,645,210", "unseen test year"),
                    ("Worst fall", "12 %", "from the running peak"),
                ],
            ),
            section(
                "Table",
                "Plain table with tabular figures.",
                "table",
                headers=["Trader", "Fitness"],
                rows=[["R1-12", "+0.123"], ["R1-40", "−0.051"]],
            ),
            section(
                "Line chart",
                "Ink line; spikes kept when thinned.",
                "chart",
                svg=charts.line_chart(points, "example"),
            ),
            section(
                "Bar chart",
                "Losses in the signal colour.",
                "chart",
                svg=charts.bar_chart([("gain", 3.0), ("loss", -2.0)], "bars"),
            ),
            section(
                "Map",
                "The MAP-Elites grid: darker = fitter, white = empty.",
                "chart",
                svg=charts.grid_map(cells, 10, 8),
            ),
            section(
                "Code",
                "Generated source, with a download link.",
                "code",
                text="def decide(x):\n    return None\n",
                download=None,
            ),
            section(
                "Actions",
                "Every action is a word, never a boxed button.",
                "actions",
                forms=[
                    {"label": "Do something", "url": "/api/noop", "fields": [], "confirm": None}
                ],
            ),
        ],
    }


def settings_page():
    """Settings: every value with who sets it (§13.1)."""
    rows = [
        ["Starting capital", "Your choice", "Capital page"],
        ["Daily risk budget", "Your choice", "Capital page"],
        ["Credit share", "Your choice", "Capital page"],
        ["MW cap per hub-hour (5 MW, 5 % of volume)", "Your choice", "Capital page"],
        ["Each hub's median cleared MW", "From market data", "cleared-bids reports 2023–2025"],
        ["MPD", "From market data", "$12 floor, estimate (round 28)"],
        [
            "Fees and RSG",
            "From market data",
            "labelled estimates until the Rates Factors file arrives",
        ],
        ["Risk-free rate", "From market data", "FRED DTB3"],
        [
            "Career preset and layers",
            "Your choice",
            "`evobots run`; individual (out of money) by default",
        ],
        ["Fixed yearly costs ($50k)", "Your choice, assumption", "L4 only"],
        [
            "Collateral, position scale, trailing 1-in-100 loss",
            "From the trader's account",
            "computed each day",
        ],
    ]
    return {
        "title": "Settings",
        "description": "Every value and who sets it. Only “Your choice” values are editable.",
        "sections": [
            section("Values", "", "table", headers=["Value", "Badge", "Where"], rows=rows)
        ],
    }


def cached_json(name, compute):
    """A JSON cache in runs/cache (recomputed when missing)."""
    path = CACHE_DIRECTORY / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = compute()
    CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str), encoding="utf-8")
    return data


def data_page(is_demo=False):
    """Data: coverage, feature status and distributions."""
    from evobots.features.catalogue import FEATURES
    from evobots.features.store import feature_summary

    evaluation = evaluator(is_demo)
    store = evaluation.store
    summary = cached_json(
        f"feature_summary_{store.source.replace(' ', '_')}", lambda: feature_summary(store)
    )
    feature_rows = []
    for feature in FEATURES:
        entry = summary[feature.name]
        quantiles = " / ".join(
            f"{entry[label]:.3g}" for label in ("p5", "p50", "p95") if label in entry
        )
        feature_rows.append(
            [
                feature.display_name,
                feature.unit.label() if feature.kind == "number" else feature.kind,
                entry["first_day"] or "–",
                f"{entry['missing_fraction']:.1%}",
                quantiles,
            ]
        )
    market = evaluation.market
    hub_rows = []
    for index, hub in enumerate(market.hubs):
        known = ~np.isnan(market.day_ahead[:, :, index]).all(axis=1)
        if known.any():
            first, last = np.flatnonzero(known)[[0, -1]]
            hub_rows.append(
                [hub, str(market.days[first]), str(market.days[last]), f"{known.mean():.1%}"]
            )
    daily = np.nanmean(market.day_ahead, axis=(1, 2))
    points = thin(
        [(str(day), float(value)) for day, value in zip(market.days, daily) if value == value]
    )
    return {
        "title": "Data",
        "description": (
            f"{store.source}: {store.days[0]} → {store.days[-1]}. Every input a trader reads, "
            "point-in-time."
        ),
        "sections": [
            section(
                "Hubs",
                "First and last day with DA prices, and the share of days priced.",
                "table",
                headers=["Hub", "First", "Last", "Days priced"],
                rows=hub_rows,
            ),
            section(
                "Average DA price",
                "Daily mean over hubs and hours ($/MWh).",
                "chart",
                svg=charts.line_chart(points, "DA", unit=""),
            ),
            location_stages_section(is_demo),
            section(
                "The 25 features",
                "Populated status and 5th / 50th / 95th percentiles (docs/features.md).",
                "table",
                headers=["Feature", "Unit", "First day", "Missing", "p5 / p50 / p95"],
                rows=feature_rows,
            ),
        ],
    }


def location_stages_section(is_demo=False):
    """Data page: which location stages are built here (§7.10: A hubs, D clusters, C all)."""
    from evobots.data.location_store import LOCATION_STORE_DIRECTORY, LocationStore

    store = LocationStore(REPOSITORY_ROOT / LOCATION_STORE_DIRECTORY)
    years = [] if is_demo else store.years()
    clusters = (
        None
        if is_demo or not STAGE_CLUSTERS_PATH.exists()
        else json.loads(STAGE_CLUSTERS_PATH.read_text(encoding="utf-8"))
    )
    groups = {entry["year"]: entry for entry in clusters["years"]} if clusters else {}
    rows = [
        [
            year,
            f"{store.index(year)['day_count']:,}",
            f"{len(store.index(year)['locations']):,}",
            f"{len(groups[year]['representatives']):,} of {groups[year]['candidates']:,}"
            if year in groups and groups[year]["candidates"]
            else "hubs only"
            if year in groups
            else "–",
        ]
        for year in years
    ]
    description = (
        f"Stage C: {len(years)} years built, {store.size_bytes() / 2**30:.1f} GB on disk. "
        + (
            f"Stage D: groups cut at 1 − ρ = {clusters['threshold']} (Spearman, average linkage)."
            if clusters
            else "Stage D: not built (`evobots data build --stage D`)."
        )
        if years
        else "Only Stage A (the trading hubs) is built here: `evobots data build --stage D` "
        "builds every location (Stage C) and the yearly groups (Stage D)."
    )
    return section(
        "Location stages",
        description,
        "table",
        headers=["Year", "Days", "Locations (Stage C)", "Stage D groups"],
        rows=rows,
    )


def simulator_page(is_demo=False):
    """Simulator: the baselines at full size reproduce capital_sizing.md §4."""
    from evobots.config.capital import CapitalSettings
    from evobots.simulate.settlement import AccountRules, constant_decisions, settle

    evaluation = evaluator(is_demo)
    market = evaluation.market

    def compute():
        start = (
            market.day_index(datetime.date(2019, 1, 1))
            if market.days[0] < datetime.date(2019, 1, 1)
            else 0
        )
        caps_by_hub = CapitalSettings().hub_caps_mw()
        caps = np.array([caps_by_hub.get(hub, 5.0) for hub in market.hubs])
        rules = AccountRules(cost_multiple=0.0, is_rounding=False)
        rows = []
        for name, side in (("always INC", -1), ("always DEC", 1)):
            result = settle(
                constant_decisions(market, side, caps),
                market,
                start,
                len(market.days),
                rules,
                history_start=start,
            )
            full = result.full_size_daily_pnl_usd
            worst = int(np.argmin(full))
            rows.append(
                [
                    name,
                    f"{full.mean():+,.0f}",
                    f"{np.percentile(-full, 99):,.0f}",
                    f"{-full.min():,.0f}",
                    str(result.days[worst]),
                ]
            )
        return {"rows": rows, "first": str(market.days[start])}

    data = cached_json(f"simulator_{market.source.replace(' ', '_')}", compute)
    return {
        "title": "Simulator",
        "description": (
            "Clearing, fees, sizing, credit and death (docs/maths.md §4). The baselines at full "
            "size, unrounded and without costs, reproduce capital_sizing.md §4 on MISO data."
        ),
        "sections": [
            section(
                "Baselines at full size",
                f"From {data['first']}; capital_sizing.md: always-INC mean +$474, 1-in-100 loss "
                "$27,897, worst $492,173 on 2022-12-23; always-DEC worst $176,554 on 2021-02-18.",
                "table",
                headers=[
                    "Baseline",
                    "Mean day ($)",
                    "1-in-100 loss ($)",
                    "Worst day ($)",
                    "Worst day",
                ],
                rows=data["rows"],
            ),
            section(
                "Costs",
                "Labelled estimates until MISO's rate file arrives.",
                "list",
                items=[
                    "Schedule 17 + 24: $0.0902/MWh on |net| per node-hour",
                    "DA RSG on net virtual demand: $0.05/MWh from 2008-11 (placeholder)",
                    "DDC on net virtual supply: $0 / $1.80 / $0.11 by era",
                    "Constraint Management Charge: not modelled",
                ],
            ),
        ],
    }


def lineage_store(run_id):
    """A run's lineage store."""
    from evobots.qd.lineage import LineageStore

    path = RUNS_DIRECTORY / run_id / "lineage.sqlite"
    if not path.exists():
        raise FileNotFoundError(run_id)
    return LineageStore(path)


def traders_page(run_id=None, query="", page_number=1):
    """Traders: search a run's lineage by id, name, origin or operator.

    Shows TRADERS_PER_PAGE at a time, newest first.
    """
    runs = full_runs()
    if run_id is None and runs:
        run_id = runs[0]["run_id"]
    if run_id is None:
        return {
            "title": "Traders",
            "description": "No run yet: start one on the Evolution page.",
            "sections": [],
        }
    store = lineage_store(run_id)
    page_number = max(1, int(page_number))
    records = store.search(
        query, limit=TRADERS_PER_PAGE + 1, offset=(page_number - 1) * TRADERS_PER_PAGE
    )
    has_more = len(records) > TRADERS_PER_PAGE
    records = records[:TRADERS_PER_PAGE]
    headers = [
        "Trader",
        "Name",
        "Origin",
        "Generation",
        "Fitness",
        "Alive",
        "Offspring",
        "In the archive",
    ]
    rows = [
        [
            record.trader_id,
            record.name,
            record.origin,
            record.generation,
            "" if record.fitness is None else f"{record.fitness:+.3f}",
            "yes" if record.is_alive else f"no ({record.death_cause})",
            record.offspring,
            "yes" if record.has_entered_archive else "",
        ]
        for record in records
    ]
    links = {index: f"/traders/{run_id}/{record.trader_id}" for index, record in enumerate(records)}
    form = {
        "label": "Search",
        "url": "/traders",
        "method": "get",
        "fields": [
            {"name": "run", "label": "Run", "type": "text", "value": run_id},
            {
                "name": "query",
                "label": "Id, name, origin or operator",
                "type": "text",
                "value": query,
            },
        ],
    }
    query_text = urllib.parse.urlencode({"run": run_id, "query": query})
    pager = {
        "text": f"Page {page_number}",
        "previous": f"/traders?{query_text}&page={page_number - 1}" if page_number > 1 else None,
        "next": f"/traders?{query_text}&page={page_number + 1}" if has_more else None,
    }
    return {
        "title": "Traders",
        "pager": pager,
        "description": (
            f"Run {run_id}: {store.count():,} traders, {store.distinct_behaviours():,} distinct "
            "behaviours. Newest first."
        ),
        "sections": [
            section("Search", "", "actions", forms=[form]),
            section(
                "Traders",
                "Click one for its code, rules, life and family.",
                "table",
                headers=headers,
                rows=rows,
                links=links,
            ),
        ],
    }


def trader_genome(run_id, trader_id, is_demo=False):
    """(record, genome) of a trader, stored or regenerated from its birth record."""
    from evobots.bots.trader import genome_from_json
    from evobots.qd.run import Run

    store = lineage_store(run_id)
    record = store.record(trader_id)
    if record is None:
        raise FileNotFoundError(trader_id)
    stored = store.genome_json(record.genome_id)
    if stored is not None:
        return record, genome_from_json(stored)
    run = Run.resume(RUNS_DIRECTORY / run_id, evaluator(is_demo))
    return record, run.regenerate(trader_id)


def trader_source_text(run_id, trader_id, is_demo=False):
    """(file name, the trader's generated Python file)."""
    from evobots.bots.source import trader_source

    record, genome = trader_genome(run_id, trader_id, is_demo)
    text = trader_source(
        genome,
        {
            "trader_id": trader_id,
            "parent_ids": record.parent_ids,
            "operator": record.origin,
            "evaluation": record.birth,
            "run_id": run_id,
        },
    )
    return f"trader_{trader_id}.py", text


def trader_page(run_id, trader_id, day_text=None, is_demo=False):
    """Trader: rules, code, life, what it saw, family, actions (§9.4, §15.1)."""
    from evobots.bots.source import input_rows
    from evobots.bots.trader import describe, trader_decisions

    record, genome = trader_genome(run_id, trader_id, is_demo)
    evaluation_engine = evaluator(is_demo)
    store = lineage_store(run_id)
    state = read_checkpoint(run_id)
    start_index = evaluation_engine.index_of(datetime.date.fromisoformat(record.window_first_day))
    end_index = evaluation_engine.index_of(datetime.date.fromisoformat(record.window_last_day)) + 1
    life = evaluation_engine.evaluate(genome, start_index, end_index)
    equity_points = thin(
        [
            (str(evaluation_engine.day(start_index + index)), float(value))
            for index, value in enumerate(life.equity_usd)
        ]
    )
    day = (
        datetime.date.fromisoformat(day_text) if day_text else evaluation_engine.day(end_index - 1)
    )
    day_index = evaluation_engine.index_of(day)
    features = genome.features()
    rows = input_rows(evaluation_engine.store, day_index, evaluation_engine.caps_mw, features)
    decisions = trader_decisions(
        genome, evaluation_engine.store, day_index, day_index + 1, evaluation_engine.caps_mw
    )
    seen_rows = []
    for row in rows:
        location = evaluation_engine.store.locations.index(row["location"])
        hour = int(row["hour"]) - 1
        side = int(decisions.side[0, hour, location])
        if side == 0 and hour not in (0, 12):
            continue
        bid = (
            "–"
            if side == 0
            else f"{'DEC' if side > 0 else 'INC'} "
            f"{decisions.full_size_mw[0, hour, location]:.2f} MW at "
            f"${decisions.limit_usd_per_mwh[0, hour, location]:.2f}"
        )
        seen_rows.append(
            [row["location"], int(row["hour"])]
            + [
                (
                    "–"
                    if row[name] is None
                    else (f"{row[name]:.4g}" if isinstance(row[name], float) else row[name])
                )
                for name in features
            ]
            + [bid]
        )
    chosen = state is not None and any(
        elite.trader_id == trader_id for elite in state["archive"].values()
    )
    current = (
        json.loads((RUNS_DIRECTORY / run_id / "deployable" / "current_bot.json").read_text())
        if (RUNS_DIRECTORY / run_id / "deployable" / "current_bot.json").exists()
        else {}
    )
    is_chosen = (
        current.get("trader_id") == trader_id or current.get("nearest_candidate") == trader_id
    )
    parents = [f"[{parent}](/traders/{run_id}/{parent})" for parent in record.parent_ids] or [
        "none (founder or random)"
    ]
    children = [
        f"[{child}](/traders/{run_id}/{child})" for child in store.children(trader_id)[:40]
    ] or ["none yet"]
    forms = [
        {
            "label": "What did it see? (pick a day)",
            "url": f"/traders/{run_id}/{trader_id}",
            "method": "get",
            "fields": [
                {"name": "day", "label": "Operating day", "type": "date", "value": day.isoformat()}
            ],
        },
        {
            "label": "Refine (new run seeded with this trader)",
            "url": f"/api/refine/{run_id}/{trader_id}",
            "fields": [],
            "confirm": None,
        },
        {
            "label": "Write its report card",
            "url": f"/api/report/{run_id}/{trader_id}",
            "fields": [],
            "confirm": None,
        },
    ]
    if is_chosen:
        forms.append(
            {
                "label": "Final test (sealed 12 months, once per run)",
                "url": f"/api/final-test/{run_id}/{trader_id}",
                "fields": [
                    {
                        "name": "confirmation",
                        "label": f"Type {run_id} to spend this run's sealed test",
                        "type": "text",
                        "value": "",
                    }
                ],
                "confirm": "The sealed year can be used once per run and every opening is logged.",
            }
        )
    report_path = RUNS_DIRECTORY / run_id / f"report_{trader_id}.html"
    links = [
        f"[Download code](/download/trader/{run_id}/{trader_id}.py)",
        f"[Download genome](/download/genome/{run_id}/{trader_id}.json)",
    ]
    if report_path.exists():
        links.append(f"[Report card](/report/{run_id}/{trader_id})")
    links.append(
        "Forward test (2026-09-22 on): needs forward data in data/inbox/ (paper trading, M9)."
    )
    return {
        "title": f"{record.name} ({trader_id})",
        "description": (
            f"Run {run_id}, born at evaluation {record.birth:,} by {record.origin}; generation "
            f"{record.generation}; {record.offspring} offspring; "
            f"{'in the archive' if chosen else 'not an elite now'}."
        ),
        "sections": [
            section(
                "Rules",
                "Its program in plain English (display names).",
                "list",
                items=describe(genome),
            ),
            section(
                "Life",
                f"Equity on its training window {record.window_first_day} → "
                f"{record.window_last_day}.",
                "metrics",
                items=[
                    ("Fitness", f"{life.fitness:+.3f}", "log growth − risk-free − parsimony"),
                    ("Final equity", money(life.final_equity_usd), ""),
                    ("Worst fall", f"{life.max_drawdown_fraction:.0%}", "from the running peak"),
                    ("Outcome", "alive" if life.is_alive else f"stopped: {life.stop_cause}", ""),
                ],
            ),
            section("Equity", "", "chart", svg=charts.line_chart(equity_points, "equity")),
            section("Actions", "", "actions", forms=forms),
            section("Links", "", "list", items=links),
            section(
                f"What did it see on {day}?",
                "The inputs it read at 10:30 Eastern on the day before, and its bids (full size, "
                "before the position scale). Hours without bids are hidden except hours ending 1 "
                "and 13.",
                "table",
                headers=["Location", "Hour"] + features + ["Bid"],
                rows=seen_rows,
            ),
            section("Parents", "", "list", items=parents),
            section("Children", "", "list", items=children),
            section(
                "View code",
                "Its standalone Python file, generated from its genome.",
                "code",
                text=trader_source_text(run_id, trader_id, is_demo)[1],
                download=f"/download/trader/{run_id}/{trader_id}.py",
            ),
        ],
    }


def evolution_page(run_id=None, is_demo=False):
    """Evolution: progress, the map, operators, lineage, the deployable bot, start/stop."""
    from evobots.qd.archive import DIRECTION_BINS, SELECTIVITY_BINS

    runs = full_runs()
    start_form = {
        "label": "Start a run",
        "url": "/api/search",
        "fields": [
            {
                "name": "evaluations",
                "label": "Traders to evaluate",
                "type": "number",
                "value": 20000,
                "badge": "Your choice",
            },
            {
                "name": "workers",
                "label": "Worker processes",
                "type": "number",
                "value": 2,
                "badge": "Your choice",
            },
            {
                "name": "seed",
                "label": "Random seed",
                "type": "number",
                "value": 1,
                "badge": "Your choice",
            },
            {
                "name": "stage",
                "label": "Locations",
                "type": "select",
                "options": STAGES,
                "value": "A",
                "badge": "Your choice",
            },
            {
                "name": "no_founders",
                "label": "No founders (control run)",
                "type": "checkbox",
                "value": "",
            },
        ],
        "confirm": None,
    }
    if run_id is None and runs:
        run_id = runs[0]["run_id"]
    sections = [
        section(
            "New run",
            "Runs in a worker process; checkpoints every 10 minutes; the page stays responsive.",
            "actions",
            forms=[start_form],
        )
    ]
    if run_id is None:
        return {"title": "Evolution", "description": "No run yet.", "sections": sections}
    status = next((status for status in runs if status["run_id"] == run_id), None)
    state = read_checkpoint(run_id)
    if status is None or state is None:
        sections.append(
            section(
                run_id,
                "No checkpoint yet: the run is starting.",
                "text",
                paragraphs=[str(job_status(run_id))],
            )
        )
        return {"title": f"Evolution: {run_id}", "description": "", "sections": sections}
    cells = {
        cell: (
            elite.evaluation.fitness,
            f"{elite.trader_id} {elite.record.name}: F {elite.evaluation.fitness:+.3f}, growth "
            f"{elite.evaluation.log_growth:+.3f}",
        )
        for cell, elite in state["archive"].items()
    }
    by_cell = {cell: elite.trader_id for cell, elite in state["archive"].items()}
    current = status["current"] or {}
    decision = current.get("decision", "–")
    detail = (
        current.get("trader_id")
        or f"nearest candidate {current.get('nearest_candidate')}: "
        f"{' — '.join(current.get('failed_gate') or [])}"
    )
    operator_rows = [
        [name, successes, tries, f"{successes / tries:.0%}" if tries else "–"]
        for name, (successes, tries) in state["bandit"].success_rates().items()
    ]
    stop_forms = [
        {
            "label": "Stop after the current batch",
            "url": f"/api/stop/{run_id}",
            "fields": [],
            "confirm": None,
        },
        {"label": "Resume", "url": f"/api/resume/{run_id}", "fields": [], "confirm": None},
    ]
    top = sorted(state["archive"].values(), key=lambda elite: -elite.evaluation.fitness)[:15]
    elite_rows = [
        [
            elite.trader_id,
            elite.record.name,
            elite.record.origin,
            f"{elite.evaluation.fitness:+.3f}",
            "" if elite.forward is None else f"{elite.forward.log_growth:+.3f}",
            (
                "passes"
                if elite.passes_quick_gates()
                else (elite.first_failed_gate() or ("not checked",))[0]
            ),
        ]
        for elite in top
    ]
    return {
        "title": f"Evolution: {run_id}",
        "description": "MAP-Elites over traders (docs/qd_explained.md).",
        "sections": sections
        + [
            section(
                "Progress",
                "Counted in traders scored; two counters stand in for generations.",
                "metrics",
                items=[
                    ("Traders", f"{status['evaluations_done']:,} / {status['budget']:,}", ""),
                    ("Batches done", f"{status['batches_done']:,}", ""),
                    (
                        "Window",
                        f"{status['window_index'] + 1} of {status['windows']}",
                        "5 years, stepped by 1",
                    ),
                    ("Lineage depth", str(status["deepest_lineage"]), "longest chain of ancestors"),
                    (
                        "Elites",
                        str(status["elites"]),
                        f"of {DIRECTION_BINS * SELECTIVITY_BINS} cells",
                    ),
                ],
            ),
            section(
                "Deployable decision",
                "From the quick gates at the last checkpoint (§11.4).",
                "list",
                items=[f"{decision}: {detail}"],
            ),
            section(
                "Map of surviving trader kinds",
                "How to read this: left = mostly INC, right = mostly DEC; bottom = bids rarely, "
                "top = bids almost every location-hour. Darker = fitter on the current window; "
                "white = no survivor of that kind yet. Click a cell to open its trader.",
                "chart",
                svg=charts.grid_map(
                    cells,
                    DIRECTION_BINS,
                    SELECTIVITY_BINS,
                    link=lambda column, row: f"/traders/{run_id}/{by_cell[(column, row)]}",
                ),
            ),
            section(
                "Top elites",
                "By fitness on the current window; walk-forward is the next unseen year.",
                "table",
                headers=["Trader", "Name", "Origin", "Fitness", "Next year", "Quick gates"],
                rows=elite_rows,
                links={
                    index: f"/traders/{run_id}/{elite.trader_id}" for index, elite in enumerate(top)
                },
            ),
            section(
                "Operators",
                "Children that entered or improved the archive, per operator (the bandit's "
                "evidence).",
                "table",
                headers=["Operator", "Successes", "Tries", "Rate"],
                rows=operator_rows,
            ),
            section("Run control", "", "actions", forms=stop_forms),
        ],
    }


def report_page(run_id, trader_id):
    """Report card: the HTML written by `evobots report`."""
    path = RUNS_DIRECTORY / run_id / f"report_{trader_id}.json"
    if not path.exists():
        return {
            "title": "Report card",
            "description": "Not written yet.",
            "sections": [
                section(
                    "Write it",
                    "Takes about a minute.",
                    "actions",
                    forms=[
                        {
                            "label": "Write the report card",
                            "url": f"/api/report/{run_id}/{trader_id}",
                            "fields": [],
                            "confirm": None,
                        }
                    ],
                )
            ],
        }
    card = json.loads(path.read_text(encoding="utf-8"))
    gate_rows = [[name, entry["status"], entry["detail"]] for name, entry in card["gates"].items()]
    return {
        "title": f"Report card: {card['identity']['name']} ({trader_id})",
        "description": card["what_happened"],
        "sections": [
            section(
                "Gates",
                "Each test before a trader counts as deployable (§12.2).",
                "table",
                headers=["Gate", "Result", "Detail"],
                rows=gate_rows,
            ),
            section(
                "Equity",
                "Whole evolution period.",
                "chart",
                svg=charts.line_chart(card["charts"]["equity"], "equity"),
            ),
            section(
                "Rolling next years",
                card["rolling_note"],
                "table",
                headers=["Year", "Log growth", "Drawdown"],
                rows=[
                    [
                        row["year"],
                        f"{row['log_growth']:+.3f}",
                        f"{row['max_drawdown_fraction']:.0%}",
                    ]
                    for row in card["rolling_next_years"]
                ],
            ),
            section(
                "Shock periods",
                "",
                "table",
                headers=["Event", "Days", "Return"],
                rows=[
                    [
                        row["event"],
                        f"{row['first_day']} → {row['last_day']}",
                        f"{row['return_fraction']:+.1%}"
                        if row.get("return_fraction") is not None
                        else "not covered",
                    ]
                    for row in card["shock_periods"]
                ],
            ),
            section(
                "Hindsight check",
                "Re-scored with EPU and gas features missing.",
                "metrics",
                items=[
                    ("With", f"{card['hindsight_check']['log_growth_with']:+.3f}", ""),
                    ("Without", f"{card['hindsight_check']['log_growth_without']:+.3f}", ""),
                    (
                        "Suspect",
                        "yes" if card["hindsight_check"]["is_hindsight_suspect"] else "no",
                        "",
                    ),
                ],
            ),
            section("Caveats", "", "list", items=card["caveats"] + [card["honest_expectation"]]),
            section(
                "Export",
                "",
                "list",
                items=[f"[Download as one HTML file](/download/report/{run_id}/{trader_id}.html)"],
            ),
        ],
    }


def best_page():
    """The Do nothing page when no trader passes the gates."""
    runs = full_runs()
    if not runs:
        return {"title": "Best bot", "description": "No run yet.", "sections": []}
    current = runs[0]["current"] or {}
    return {
        "title": "Do nothing: no trader passes the gates",
        "description": (
            f"Run {runs[0]['run_id']}. The nearest candidate is "
            f"{current.get('nearest_candidate')}; it failed "
            f"{' — '.join(current.get('failed_gate') or [])}."
        ),
        "sections": [
            section(
                "Nearest candidate",
                "",
                "list",
                items=[
                    f"[{current.get('nearest_candidate')}](/traders/{runs[0]['run_id']}/{current.get('nearest_candidate')})"
                ],
            )
        ],
    }


def career_page():
    """Career: layers, presets, the quit-hazard fit, ARL table, survival curves."""
    from evobots.career.model import PRESETS
    from evobots.career.sequential import average_run_length_table
    from evobots.career.survival import kaplan_meier

    preset_rows = [
        [
            name,
            preset.floor_usd(1_500_000) and money(preset.floor_usd(1_500_000)) or "–",
            "–"
            if preset.drawdown_limit_fraction is None
            else f"{preset.drawdown_limit_fraction:.0%}",
            "on" if preset.is_edge_check_on else "off",
            "–"
            if preset.investor_withdrawal_hazard_per_month is None
            else f"{preset.investor_withdrawal_hazard_per_month:.2%}/month",
        ]
        for name, preset in PRESETS.items()
    ]
    sections = [
        section(
            "Presets",
            "L0 (out of money) is always on; every other layer is optional (§10.1).",
            "table",
            headers=["Preset", "Floor at $1.5M", "Loss limit", "Edge check", "Withdrawals"],
            rows=preset_rows,
        ),
        section(
            "CUSUM thresholds",
            "h for one false retirement per 10 years while the edge lasts, and the delay once it "
            "is gone (Siegmund).",
            "table",
            headers=["Edge (σ/month)", "k", "h", "Delay (months)"],
            rows=[
                [f"{edge:g}", f"{reference:g}", f"{threshold:.2f}", f"{delay:.1f}"]
                for edge, reference, threshold, delay in average_run_length_table(
                    [0.25, 0.5, 1.0], [0.25, 0.5], 120
                )
            ],
        ),
    ]
    fit_path = DOCS_DIRECTORY / "data" / "quit_hazard_fit.json"
    if fit_path.exists():
        fit = json.loads(fit_path.read_text(encoding="utf-8"))
        sections.append(
            section(
                "Quit hazard (L3) fit",
                f"{fit['losing_traders_used']} losing random traders, {fit['window'][0]} → "
                f"{fit['window'][1]}; targets from {fit['source_of_targets']}.",
                "table",
                headers=["Months", "Fitted survival", "Target"],
                rows=[
                    [
                        months,
                        f"{fit['fitted_survival'][months]:.1%}",
                        f"{fit['target_survival'][months]:.0%}",
                    ]
                    for months in fit["fitted_survival"]
                ],
            )
        )
    runs = full_runs()
    if runs:
        store = lineage_store(runs[0]["run_id"])
        rows = store.connection.execute(
            "SELECT origin, window_first_day, death_day FROM traders WHERE is_alive IS NOT NULL"
        ).fetchall()
        groups = {}
        for origin, first, death in rows:
            key = (
                "founder"
                if origin.startswith("founder")
                else ("random" if origin == "random" else "bred")
            )
            duration = (
                (datetime.date.fromisoformat(death) - datetime.date.fromisoformat(first)).days
                if death
                else 5 * 365
            )
            groups.setdefault(key, ([], []))
            groups[key][0].append(duration)
            groups[key][1].append(1 if death else 0)
        kaplan_meier_rows = []
        for key, (durations, events) in groups.items():
            times, survival, _ = kaplan_meier(durations, events)
            kaplan_meier_rows.append(
                [
                    key,
                    len(durations),
                    sum(events),
                    f"{survival[-1]:.1%}" if len(survival) else "100%",
                ]
            )
        sections.append(
            section(
                "Careers in the newest run",
                "Kaplan–Meier survival through each trader's 5-year window, by origin (deaths = "
                "out of money).",
                "table",
                headers=["Origin", "Traders", "Deaths", "Survival at the end"],
                rows=kaplan_meier_rows,
            )
        )
    return {
        "title": "Career",
        "description": "When a trader stops, and how fitness is scored (docs/maths.md §5).",
        "sections": sections,
    }


def orfe_page(section_name):
    """The ORFE pages: Scenarios, Optimizer, Portfolio, Battery, Risk, Leaderboard."""
    titles = {
        "scenarios": (
            "Scenarios",
            "O1: generators of tomorrow's spreads, validated against what happened.",
        ),
        "risk": ("Risk", "O5: estimators of the 1-in-100-day loss and their backtests."),
        "battery": (
            "Battery",
            "O4: a 5 MW / 20 MWh battery at ILLINOIS.HUB; a study, not a deployable strategy.",
        ),
        "leaderboard": ("Methods leaderboard", "Every strategy class under one protocol (§20.11)."),
        "portfolio": ("Portfolio", "O3: portfolios of the run's elites, walk-forward."),
        "impact": ("Price impact", "O9: do virtual bids move prices?"),
        "search": ("Search as OR", "O8: MAP-Elites vs NSGA-II, successive halving, OCBA."),
    }
    title, description = titles[section_name]
    path = ORFE_DIRECTORY / f"{section_name}.json"
    if not path.exists():
        return {
            "title": title,
            "description": description,
            "sections": [
                section(
                    "Not computed yet",
                    "Run `uv run python tools/build_orfe_results.py --sections "
                    + section_name
                    + "` (needs the MISO data).",
                    "text",
                    paragraphs=[],
                )
            ],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    sections = []
    if section_name == "scenarios":
        table = data["table"]
        keys = [
            "crps",
            "pinball",
            "mean",
            "standard_deviation",
            "p1",
            "p99",
            "excess_kurtosis",
            "cross_hub_correlation",
            "spike_day_share",
        ]
        sections.append(
            section(
                "Validation",
                f"{data['test_days']} test days, {data['first_test_day']} → "
                f"{data['last_test_day']}; lower CRPS and pinball are better; the other columns "
                "compare simulated with real spreads.",
                "table",
                headers=["Generator"] + keys,
                rows=[
                    [generator]
                    + [("" if key not in values else f"{values[key]:.3g}") for key in keys]
                    for generator, values in table.items()
                ],
            )
        )
    elif section_name == "risk":
        sections.append(
            section(
                "Backtests",
                "Breach rate (target 1 %) and p-values: Kupiec (rate), Christoffersen "
                "(independence, coverage), Acerbi–Székely (expected shortfall). Small p-values "
                "reject the estimator.",
                "table",
                headers=[
                    "Estimator",
                    "Period",
                    "Days",
                    "Breaches",
                    "Kupiec",
                    "Independence",
                    "Coverage",
                    "ES test",
                ],
                rows=[
                    [
                        row["estimator"],
                        row["period"],
                        row["days"],
                        f"{row['breach_rate']:.2%}",
                        f"{row['kupiec']:.3f}",
                        f"{row['christoffersen_independence']:.3f}",
                        f"{row['christoffersen_coverage']:.3f}",
                        f"{row['acerbi_szekely_significance']:.3f}",
                    ]
                    for row in data["rows"]
                ],
            )
        )
    elif section_name == "battery":
        sections.append(
            section(
                "Share of the perfect-foresight bound",
                f"{data['battery']['days']:,} days; revenue includes end-of-day energy at the "
                "day's mean price.",
                "chart",
                svg=charts.bar_chart(
                    [(policy, value) for policy, value in data["bound_ratio"].items()],
                    "bound ratio",
                    unit="%",
                ),
            )
        )
        sections.append(
            section(
                "Revenue by year",
                "USD.",
                "table",
                headers=["Year"] + list(data["total_usd"]),
                rows=[
                    [year] + [f"{values[policy]:,.0f}" for policy in data["total_usd"]]
                    for year, values in data["revenue_by_year_usd"].items()
                ],
            )
        )
        sections.append(
            section(
                "Sensitivity",
                "Perfect-foresight mean daily revenue by efficiency and wear cost.",
                "table",
                headers=["Parameters", "USD/day"],
                rows=[
                    [key, f"{value:,.0f}"]
                    for key, value in data["perfect_foresight_daily_mean_by_parameters_usd"].items()
                ],
            )
        )
    elif section_name == "leaderboard":
        rows = [
            [
                row["strategy"],
                row["class"],
                row["trials"],
                f"{row['log_growth']:+.3f}",
                f"{row['log_growth_doubled_costs']:+.3f}",
                f"{row['annual_sharpe']:.2f}",
                f"{row['deflated_sharpe']:.2f}",
                f"{row['max_drawdown_fraction']:.0%}",
                "yes" if row["in_model_confidence_set"] else "",
            ]
            for row in data["rows"]
        ]
        sections.append(
            section(
                "Leaderboard",
                f"{data['period'][0]} → {data['period'][1]}; the model confidence set holds the "
                "strategies not significantly worse than the best (90 %).",
                "table",
                headers=[
                    "Strategy",
                    "Class",
                    "Trials",
                    "Log growth",
                    "Doubled costs",
                    "Sharpe",
                    "Deflated Sharpe",
                    "Drawdown",
                    "In the MCS",
                ],
                rows=rows,
            )
        )
    elif section_name == "portfolio":
        sections.append(
            section(
                "Walk-forward",
                data["note"],
                "table",
                headers=["Model", "Log growth", "Sharpe", "Worst day", "Holdings"],
                rows=[
                    [
                        model,
                        f"{values['out_of_sample_log_growth']:+.3f}",
                        f"{values['annual_sharpe']:.2f}",
                        f"{values['worst_day_fraction']:.2%}",
                        f"{values['average_holdings']:.1f}",
                    ]
                    for model, values in data["walk_forward"].items()
                ],
            )
        )
    elif section_name == "impact":
        sections.append(
            section(
                "Estimate",
                data["sample"],
                "metrics",
                items=[
                    (
                        "β ($/MWh per MW)",
                        f"{data['coefficient']:.5f}",
                        f"day-clustered s.e. {data['clustered_standard_error']:.5f}",
                    ),
                    (
                        "90 % interval",
                        f"{data['bootstrap_interval_90'][0]:.5f} → "
                        f"{data['bootstrap_interval_90'][1]:.5f}",
                        "bootstrap over days",
                    ),
                    (
                        "Our 5 MW",
                        f"${data['implied_spread_change_for_5_mw_usd_per_mwh']:.4f}/MWh",
                        "implied spread change",
                    ),
                    ("Observations", f"{data['observations']:,}", f"{data['days']} days"),
                ],
            )
        )
        sections.append(section("Caveats", "", "list", items=data["caveats"]))
    elif section_name == "search":
        sections.append(
            section(
                "Equal budget",
                f"{data['budget_each']:,} evaluations each, window {data['window'][0]} → "
                f"{data['window'][1]}.",
                "table",
                headers=["Measure", "MAP-Elites", "NSGA-II"],
                rows=[
                    [
                        "Hypervolume (growth, −drawdown, −CVaR)",
                        f"{data['hypervolume']['map_elites']:.4f}",
                        f"{data['hypervolume']['nsga2']:.4f}",
                    ],
                    ["Front size", data["front_size"]["map_elites"], data["front_size"]["nsga2"]],
                    [
                        "Best next-year fitness",
                        f"{data['best_next_year_fitness']['map_elites']:+.3f}",
                        f"{data['best_next_year_fitness']['nsga2']:+.3f}",
                    ],
                ],
            )
        )
        halving = data["successive_halving"]
        sections.append(
            section(
                "Successive halving",
                "Racing 64 random traders through 1, 2.5 and 5 years.",
                "metrics",
                items=[
                    (
                        "Cost",
                        f"{halving['cost_trader_years']:.0f} trader-years",
                        f"vs {halving['full_cost_trader_years']} scoring all fully",
                    ),
                    (
                        "Survivors' full-scoring ranks",
                        ", ".join(map(str, halving["survivor_full_rank"])),
                        "0 = best",
                    ),
                ],
            )
        )
    sections.append(
        section(
            "Computed",
            f"{data.get('computed_on')} in {data.get('seconds', 0):.0f} s by "
            "tools/build_orfe_results.py.",
            "text",
            paragraphs=[],
        )
    )
    return {"title": title, "description": description, "sections": sections}


def life_page():
    """Life mode: the market-time ecology (M6b)."""
    path = RUNS_DIRECTORY / "life.json"
    forms = [
        {
            "label": "Run Life mode (a few minutes)",
            "url": "/api/life",
            "fields": [],
            "confirm": None,
        }
    ]
    if not path.exists():
        return {
            "title": "Life",
            "description": (
                "Traders live through history day by day, reproduce at 2× capital and die when out "
                "of money."
            ),
            "sections": [section("Run", "", "actions", forms=forms)],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    population = thin(list(zip(data["days"], data["population_by_day"])))
    return {
        "title": "Life",
        "description": (
            f"{data['traders']} traders lived from {data['days'][0]} to {data['days'][-1]}; the "
            f"deepest lineage reached {data['deepest_generation']} generations."
        ),
        "sections": [
            section(
                "Population",
                "Living traders each day.",
                "chart",
                svg=charts.line_chart(
                    [(day, float(value)) for day, value in population], "population", unit=""
                ),
            ),
            section(
                "Families",
                "The largest families (traders descended from one founder or random trader).",
                "table",
                headers=["Root", "Descendants", "Generations"],
                rows=data["families"][:15],
            ),
            section("Run again", "", "actions", forms=forms),
        ],
    }


def paper_page():
    """Paper trading (M9): the next day's bids and the running ledger of each paper trader."""
    from evobots.deploy.paper import PAPER_DIRECTORY, read_paper_result

    folders = sorted(
        (REPOSITORY_ROOT / PAPER_DIRECTORY).glob("*/summary.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    description = (
        "Simulated money on forward data (2026-09-22 on); nothing is sent to MISO. Drop MISO's "
        "daily DA and final RT files into data/inbox/miso/, then run `evobots paper runs/<id>` "
        "(add --trader <id> for a named trader, --fetch to save today's EPU, GPR and Henry Hub "
        "files; needs internet)."
    )
    if not folders:
        return {"title": "Paper trading", "description": description, "sections": []}
    sections = []
    for path in folders:
        summary, ledger, bids = read_paper_result(path.parent)
        settled = [row for row in ledger if row["status"] == "settled"]
        points = [(row["day"], float(row["equity_usd"])) for row in settled]
        sections.append(
            section(
                summary["trader"],
                summary["note"],
                "metrics",
                items=[
                    ("Settled days", f"{summary['settled_days']}", "DA and final RT both in"),
                    (
                        "Waiting for RT",
                        f"{summary['waiting_days']}",
                        "final RT comes ~5 days later",
                    ),
                    ("P&L", f"${summary['pnl_usd']:+,.0f}", "after fees, simulated"),
                    ("Cleared", f"{summary['cleared_mwh']:,.0f} MWh", "settled days"),
                    (
                        "Next day",
                        summary["next_day"] or "–",
                        f"{summary['next_bids']} bids"
                        if not summary["is_doing_nothing"]
                        else "do nothing",
                    ),
                ],
            )
        )
        if len(points) >= 2:
            sections.append(section("Equity", "", "chart", svg=charts.line_chart(points, "equity")))
        if bids:
            sections.append(
                section(
                    f"Bids for {summary['next_day']}",
                    "Full-size MW × the position scale is what would be submitted.",
                    "table",
                    headers=["Hub", "Hour", "Side", "Full-size MW", "Scale", "Limit $/MWh"],
                    rows=[
                        [
                            bid["hub"],
                            bid["hour_ending"],
                            bid["side"],
                            bid["full_size_mw"],
                            bid["position_scale"],
                            bid["limit_usd_per_mwh"],
                        ]
                        for bid in bids
                    ],
                )
            )
        sections.append(
            section(
                "Ledger",
                "",
                "table",
                headers=["Day", "Status", "Bids", "Cleared MWh", "Fees $", "P&L $", "Equity $"],
                rows=[
                    [
                        row["day"],
                        row["status"],
                        row["bids"],
                        row["cleared_mwh"],
                        row["fees_usd"],
                        row["pnl_usd"],
                        row["equity_usd"],
                    ]
                    for row in reversed(ledger)
                ],
            )
        )
    return {"title": "Paper trading", "description": description, "sections": sections}


def csv_rows(path):
    """Rows of a CSV file as dicts."""
    with open(path, newline="", encoding="utf-8") as table:
        return list(csv.DictReader(table))
