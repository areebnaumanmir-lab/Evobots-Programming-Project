"""The local web app: routes only (`docs/design_spec.md` §15). Every result comes from evobots.service.

Run with `evobots serve` (opens the browser) or `uvicorn evobots.app.server:app`.
Localhost only; no CDN, fonts or telemetry; FastAPI's own docs pages are switched off (§14.4).
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """The single page: settings, actions, status and results."""
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


@app.post("/api/run")
async def run(request: Request):
    """Start a search with the posted slider values."""
    return start(await request.json(), is_refine=False)


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
