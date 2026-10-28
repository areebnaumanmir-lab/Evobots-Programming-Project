// Page script for index.html: shows slider values, starts runs, polls progress, and swaps in
// the server-rendered results. No formulas: it only formats the slider's own value.
const form = document.getElementById("settings");
const statusLine = document.getElementById("status");

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

async function start(path) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings()),
  });
  const status = await response.json();
  report(status);
  if (status.state === "running") poll();
}

function report(status) {
  statusLine.classList.toggle("is-error", status.state === "error");
  if (status.state === "running") {
    statusLine.textContent = `${status.message}: ${status.done.toLocaleString("en-US")} of ${status.budget.toLocaleString("en-US")} traders scored.`;
  } else {
    statusLine.textContent = status.message;
  }
  document.getElementById("run").disabled = status.state === "running";
  document.getElementById("refine").disabled = status.state === "running";
}

async function poll() {
  const status = await (await fetch("/api/status")).json();
  report(status);
  if (status.state === "running") {
    setTimeout(poll, 1000);
  } else if (status.state === "done") {
    document.getElementById("results").innerHTML = await (await fetch("/results")).text();
  }
}

for (const input of form.querySelectorAll("input")) {
  showValue(input);
  input.addEventListener("input", () => showValue(input));
}
document.getElementById("run").addEventListener("click", () => start("/api/run"));
document.getElementById("refine").addEventListener("click", () => start("/api/refine"));
document.getElementById("stop").addEventListener("click", () => fetch("/api/stop", { method: "POST" }));
poll();
