"""The local web app: routes only (`docs/design_spec.md` §15).

Every result comes from evobots.service.

Run with `evobots serve` (opens the browser) or `uvicorn evobots.app.server:app`.
Localhost only; no CDN, fonts or telemetry; FastAPI's own docs pages are switched off (§14.4).
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from evobots import service as bridge
from evobots.service import Service, app_zip_bytes

APP_DIRECTORY = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=APP_DIRECTORY / "templates")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=APP_DIRECTORY / "static"), name="static")
service_holder = {}


def service():
    """The one Service of this process, created on first use."""
    if "service" not in service_holder:
        service_holder["service"] = Service()
    return service_holder["service"]


@app.get("/quick", response_class=HTMLResponse)
def quick(request: Request):
    """The quick-run page: sliders, a short search, downloads (also the website's page)."""
    current = service()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "sliders": current.slider_definitions(),
            "data_status": current.data_status(),
            "status": current.status,
            "results": current.results_view(),
        },
    )


@app.post("/api/refine")
async def refine(request: Request):
    """Start a refine run seeded with the current best bot and mutants of it."""
    return start(await request.json(), is_refine=True)


def start(values, is_refine):
    """Start a run or return the validation message."""
    try:
        return service().start(values, is_refine=is_refine)
    except ValueError as error:
        return JSONResponse({"state": "error", "message": str(error)}, status_code=400)


@app.post("/api/stop")
def stop():
    """Stop the running search after the current trader."""
    service().stop()
    return {"state": "stopping"}


@app.get("/api/status")
def status():
    """Progress of the current run."""
    return service().status


@app.get("/results", response_class=HTMLResponse)
def results(request: Request):
    """The results section, rendered on the server."""
    return templates.TemplateResponse(
        request, "results.html", {"results": service().results_view(), "status": service().status}
    )


@app.get("/download/best-bot.py")
def download_code():
    """The best bot's standalone Python file."""
    try:
        name, source = service().best_code()
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    return Response(
        source,
        media_type="text/x-python",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/download/best-bot.json")
def download_genome():
    """The best bot's genome as JSON."""
    try:
        name, text = service().best_genome()
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    return Response(
        text,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/download/evobots.zip")
def download_app():
    """The whole application as a zip (no data, no secrets, no MISO-derived tables)."""
    return Response(
        app_zip_bytes(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="evobots.zip"'},
    )


# ----- the multi-page app (M1.5) -----

app_settings = {"is_demo": False}


def render_page(request, data, status_code=200):
    """Draw a page dict (evobots.pages) with the shared layout."""
    link_text, link_url = bridge.best_bot_link()
    return templates.TemplateResponse(
        request,
        "page.html",
        {
            "page": data,
            "navigation": bridge.navigation(),
            "best_text": link_text,
            "best_url": link_url,
            "path": request.url.path,
        },
        status_code=status_code,
    )


def builder(page_name, **arguments):
    """A page's data, with the demo switch where the page reads market data."""
    if page_name in ("home", "data", "simulator", "trader", "evolution"):
        arguments["is_demo"] = app_settings["is_demo"]
    return bridge.page(page_name, **arguments)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Home: data, hold-out, runs, the deployable bot."""
    return render_page(request, builder("home"))


@app.get("/capital", response_class=HTMLResponse)
def capital(request: Request):
    """Capital: sliders and what they imply."""
    values = {key: value for key, value in request.query_params.items()}
    try:
        return render_page(request, builder("capital", values=values))
    except ValueError as error:
        data = builder("capital")
        data["description"] = f"Not valid: {error}"
        return render_page(request, data, 400)


SIMPLE_PAGES = (
    "docs",
    "gallery",
    "settings",
    "data",
    "simulator",
    "career",
    "life",
    "paper",
    "best",
)


@app.get("/docs/{relative:path}", response_class=HTMLResponse)
def doc(request: Request, relative: str):
    """One document rendered."""
    try:
        return render_page(request, builder("doc", relative=relative))
    except FileNotFoundError as error:
        raise HTTPException(404, "no such document") from error


@app.get("/traders", response_class=HTMLResponse)
def traders(request: Request, run: str | None = None, query: str = ""):
    """Traders: search a run's lineage."""
    return render_page(request, builder("traders", run_id=run, query=query))


@app.get("/traders/{run_id}/{trader_id}", response_class=HTMLResponse)
def trader(request: Request, run_id: str, trader_id: str, day: str | None = None):
    """Trader: rules, code, life, what it saw, family, actions."""
    try:
        return render_page(
            request, builder("trader", run_id=run_id, trader_id=trader_id, day_text=day)
        )
    except FileNotFoundError as error:
        raise HTTPException(404, "no such trader") from error


@app.get("/evolution", response_class=HTMLResponse)
def evolution(request: Request, run: str | None = None):
    """Evolution: progress, map, operators, controls."""
    return render_page(request, builder("evolution", run_id=run))


@app.get("/report/{run_id}/{trader_id}", response_class=HTMLResponse)
def report(request: Request, run_id: str, trader_id: str):
    """A trader's report card."""
    return render_page(request, builder("report", run_id=run_id, trader_id=trader_id))


@app.get("/orfe/{name}", response_class=HTMLResponse)
def orfe(request: Request, name: str):
    """The ORFE pages."""
    try:
        return render_page(request, builder("orfe", section_name=name))
    except KeyError as error:
        raise HTTPException(404, "no such page") from error


def simple_route(name):
    """A route for a page without arguments."""

    def route(request: Request):
        return render_page(request, builder(name))

    route.__name__ = f"{name}_page"
    route.__doc__ = f"The {name} page."
    return route


for page_name in SIMPLE_PAGES:
    app.add_api_route(
        f"/{page_name}", simple_route(page_name), methods=["GET"], response_class=HTMLResponse
    )


async def act(name, request, **arguments):
    """Run an action; validation errors come back as 400 with a plain message."""
    try:
        body = await request.json() if (await request.body()) else {}
    except ValueError:
        body = {}
    try:
        return bridge.action(name, **arguments, **body)
    except (ValueError, FileNotFoundError) as error:
        return JSONResponse({"state": "error", "message": str(error)}, status_code=400)


@app.post("/api/run")
async def run(request: Request):
    """Quick run page: start a short search with the posted slider values."""
    return start(await request.json(), is_refine=False)


@app.post("/api/search")
async def start_search(request: Request):
    """Evolution page: start a full MAP-Elites run in a worker process."""
    try:
        return bridge.action("run", values=await request.json(), is_demo=app_settings["is_demo"])
    except ValueError as error:
        return JSONResponse({"state": "error", "message": str(error)}, status_code=400)


@app.post("/api/stop/{run_id}")
async def stop_run(request: Request, run_id: str):
    """Ask a run to stop after its current batch."""
    return await act("stop", request, run_id=run_id)


@app.post("/api/resume/{run_id}")
async def resume_run(request: Request, run_id: str):
    """Continue a stopped run."""
    return await act("resume", request, run_id=run_id, is_demo=app_settings["is_demo"])


@app.post("/api/report/{run_id}/{trader_id}")
async def write_report(request: Request, run_id: str, trader_id: str):
    """Write a report card in a worker."""
    return await act(
        "report", request, run_id=run_id, trader_id=trader_id, is_demo=app_settings["is_demo"]
    )


@app.post("/api/refine/{run_id}/{trader_id}")
async def refine_trader(request: Request, run_id: str, trader_id: str):
    """Start a Refine run seeded with this trader."""
    return await act(
        "refine", request, run_id=run_id, trader_id=trader_id, is_demo=app_settings["is_demo"]
    )


@app.post("/api/final-test/{run_id}/{trader_id}")
async def final_test(request: Request, run_id: str, trader_id: str):
    """The sealed test, after typed confirmation."""
    return await act("final_test", request, run_id=run_id, trader_id=trader_id)


@app.post("/api/life")
async def life(request: Request):
    """Start Life mode."""
    return await act("life", request)


@app.post("/api/capital")
async def save_capital(request: Request):
    """Save the capital choices."""
    body = await request.json()
    try:
        return bridge.action("capital", values=body)
    except (ValueError, TypeError) as error:
        return JSONResponse({"state": "error", "message": str(error)}, status_code=400)


@app.get("/api/job/{name}")
def job(name: str):
    """Progress of a worker job."""
    return bridge.job_status(name)


@app.get("/download/trader/{run_id}/{trader_id}.py")
def download_trader(run_id: str, trader_id: str):
    """A trader's standalone Python file."""
    name, text = bridge.trader_file(run_id, trader_id, app_settings["is_demo"])
    return Response(
        text,
        media_type="text/x-python",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/download/genome/{run_id}/{trader_id}.json")
def download_trader_genome(run_id: str, trader_id: str):
    """A trader's genome."""
    name, text = bridge.trader_genome_file(run_id, trader_id, app_settings["is_demo"])
    return Response(
        text,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/download/report/{run_id}/{trader_id}.html")
def download_report(run_id: str, trader_id: str):
    """A report card as one HTML file."""
    try:
        name, text = bridge.report_file(run_id, trader_id)
    except FileNotFoundError as error:
        raise HTTPException(404, "write the report card first") from error
    return Response(
        text,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
