// Web Worker for the website: loads Python (Pyodide, served from this site) and evobots, then
// relays the page's requests to evobots.web.WebSession. No formulas here: Python computes
// every result, and this file only passes messages (docs/design_spec.md §14.5).
importScripts("../vendor/pyodide/pyodide.js");

let session = null;

function plain(proxy) {
  const value = proxy.toJs({ dict_converter: Object.fromEntries });
  proxy.destroy();
  return value;
}

async function start() {
  try {
    const pyodide = await loadPyodide({ indexURL: "../vendor/pyodide/" });
    await pyodide.loadPackage(["numpy", "jinja2", "markupsafe"]);
    const archive = await (await fetch("../evobots_package.zip")).arrayBuffer();
    pyodide.unpackArchive(archive, "zip", { extractDir: "/home/pyodide/package" });
    pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide/package')");
    self.pyodide = pyodide;
    session = pyodide.runPython("from evobots.web import WebSession\nWebSession()");
    // The site carries MISO's hub prices (with MISO's permission, data/NOTICE.md) when the
    // build allowed it; without the file, the page stays on synthetic demo prices.
    const table = await fetch("../data/hub_prices.csv.gz");
    if (table.ok) {
      postMessage({ type: "status", message: "Loading MISO hub prices, 2005–2025 (about a minute) …" });
      const bytes = new Uint8Array(await table.arrayBuffer());
      pyodide.FS.mkdirTree("/tmp/evobots");
      pyodide.FS.writeFile("/tmp/evobots/hub_prices.csv.gz", bytes);
      plain(session.use_uploaded_table(true));
    }
    postMessage({ type: "ready", data: session.data_status() });
  } catch (error) {
    postMessage({ type: "error", message: "Python could not start in this browser: " + error });
  }
}

const ready = start();

onmessage = async (event) => {
  await ready;
  const request = event.data;
  try {
    if (request.type === "run" || request.type === "refine") {
      const progress = (done, budget) => postMessage({ type: "progress", done, budget });
      const reply = plain(session.run(JSON.stringify(request.values), request.type === "refine", progress));
      postMessage({ type: "result", ...reply });
    } else if (request.type === "table") {
      self.pyodide.FS.mkdirTree("/tmp/evobots");
      self.pyodide.FS.writeFile("/tmp/evobots/hub_prices.csv.gz", new Uint8Array(request.bytes));
      postMessage({ type: "table", ...plain(session.use_uploaded_table()) });
    } else if (request.type === "code" || request.type === "genome") {
      const file = plain(request.type === "code" ? session.best_code() : session.best_genome());
      postMessage({ type: "file", ...file });
    }
  } catch (error) {
    const text = String(error).split("\n").filter((line) => line.trim()).pop();
    postMessage({ type: "error", message: text });
  }
};
