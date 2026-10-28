// Page script for the website (index.html rendered with is_website): shows slider values,
// sends requests to the Python worker, shows its progress, inserts the HTML it rendered, and
// saves downloads. No formulas: it only formats the slider's own value.
const form = document.getElementById("settings");
const statusLine = document.getElementById("status");
const actionIds = ["run", "refine", "download-code", "download-genome"];
const worker = new Worker("static/worker.js");

function showValue(input) {
  const output = document.getElementById(input.id + "-value");
  const value = Number(input.value);
  const kind = output.dataset.format;
  let text = String(value);
  if (kind === "money") text = "$" + value.toLocaleString("en-US");
  else if (kind === "percent") text = (value * 100).toLocaleString("en-US", { maximumFractionDigits: 1 }) + " %";
  else if (output.dataset.unit) text = value.toLocaleString("en-US") + " " + output.dataset.unit;
  output.textContent = text;
}

function settings() {
  const values = {};
  for (const input of form.querySelectorAll("input")) values[input.name] = Number(input.value);
  return values;
}

function setBusy(isBusy) {
  for (const id of actionIds) document.getElementById(id).disabled = isBusy;
}

function say(message, isError) {
  statusLine.textContent = message;
  statusLine.classList.toggle("is-error", Boolean(isError));
}

function save(name, text) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

worker.onmessage = (event) => {
  const message = event.data;
  if (message.type === "ready") {
    document.getElementById("data-status").textContent = message.data;
    say("Ready. Move the sliders, then choose Run simulation.");
    setBusy(false);
  } else if (message.type === "progress") {
    say(`Searching: ${message.done.toLocaleString("en-US")} of ${message.budget.toLocaleString("en-US")} traders scored.`);
  } else if (message.type === "result") {
    say(message.message, message.state === "error");
    if (message.results_html) document.getElementById("results").innerHTML = message.results_html;
    setBusy(false);
  } else if (message.type === "table") {
    say(message.message, message.state === "error");
    if (message.data) document.getElementById("data-status").textContent = message.data;
    setBusy(false);
  } else if (message.type === "file") {
    save(message.name, message.text);
  } else if (message.type === "error") {
    say(message.message, true);
    setBusy(false);
  }
};

function request(type) {
  setBusy(true);
  say(type === "refine" ? "Refining the best bot …" : "Searching …");
  worker.postMessage({ type, values: settings() });
}

for (const input of form.querySelectorAll("input")) {
  showValue(input);
  input.addEventListener("input", () => showValue(input));
}
document.getElementById("run").addEventListener("click", () => request("run"));
document.getElementById("refine").addEventListener("click", () => request("refine"));
document.getElementById("download-code").addEventListener("click", () => worker.postMessage({ type: "code" }));
document.getElementById("download-genome").addEventListener("click", () => worker.postMessage({ type: "genome" }));
document.getElementById("table-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  setBusy(true);
  say("Reading your table in the browser (about a minute for the full history) …");
  const bytes = await file.arrayBuffer();
  worker.postMessage({ type: "table", bytes }, [bytes]);
});
setBusy(true);
say("Loading Python in your browser (about 17 MB on the first visit) …");
