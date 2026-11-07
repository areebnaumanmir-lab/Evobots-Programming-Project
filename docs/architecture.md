# Architecture

Explanation document for M1.5 (`docs/design_spec.md` §15). How the pieces fit, and where each kind of change goes.

```
browser page (template + theme.css + app.js)
        │  HTML, and JSON for actions, over localhost only
        ▼
app/server.py      routes only
        ▼
service.py         the single bridge: validates input, returns plain data
        ├──► pages.py  builds every page as sections (metrics, tables, SVG charts…)
        ├──► core: data · features · simulate · bots · career · qd · assess · orfe
        └──► worker processes: `evobots run | resume | refine | report | final-test | life`
             (each writes runs/<id>/status.json, checkpoints and a log in runs/logs/)
```

## Rules the code enforces
- **The UI imports only the service.** `evobots.app` imports `evobots.service` and nothing else from evobots, and no core module imports the app. `tests/test_app_pages.py` checks both.
- **The browser never computes a result.** Templates place values and SVG charts computed in Python. `app.js` only posts forms and polls job status, and a test rejects arithmetic in it.
- **Nothing loads from the internet.** There are no CDN scripts, web fonts or telemetry, and FastAPI's docs pages are off. A headless-browser test loads every page with non-local requests blocked, and fails on any console error or blocked request.
- **Long work runs in worker processes.** Searches, reports, Life mode and the final test run as `evobots …` subprocesses, so the app stays responsive. They can be stopped (a stop request; the run checkpoints first) and resumed.

## Where things live
| Kind | Where |
|---|---|
| A page's data | `src/evobots/pages.py` (`<name>_page`) |
| A route | `src/evobots/app/server.py` |
| The navigation | `src/evobots/app/pages.toml` |
| The layout and the section template | `src/evobots/app/templates/base.html`, `page.html` |
| Colours, fonts, spacing | `src/evobots/app/static/theme.css` |
| Charts | `src/evobots/charts.py` (SVG in ink and greys) |
| The quick-run page (also the website) | `templates/index.html`, `results.html`, `static/page.js`, `static/site.js`, `static/worker.js`; engine `evobots.service.Service` |

## The quick run and the website
The one-page quick run is the preview of round 29. It has a simplified rule genome and a test year with quick gates. The website (round 30) runs it in the browser with Pyodide, where Numba isn't available. The full engine (rounds 33–38) drives the multi-page app and the command line.
