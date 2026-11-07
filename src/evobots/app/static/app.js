// Page script of the multi-page app: posts action forms as JSON, shows the answer, and polls
// a started job until it finishes, then reloads. No formulas: every number comes from Python.
for (const form of document.querySelectorAll("form[data-api]")) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
    const status = form.parentElement.querySelector(".status");
    const values = {};
    for (const input of form.querySelectorAll("input")) {
      if (input.type === "checkbox") { if (input.checked) values[input.name] = 1; }
      else if (input.value !== "") values[input.name] = input.value;
    }
    const response = await fetch(form.action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    const answer = await response.json();
    status.textContent = answer.message || answer.state;
    status.classList.toggle("is-error", !response.ok);
    if (response.ok && answer.job) watch(answer.job, status);
  });
}

for (const range of document.querySelectorAll("input[type=range]")) {
  const output = range.parentElement.querySelector("output");
  range.addEventListener("input", () => { if (output) output.textContent = range.value; });
}

async function watch(job, status) {
  const answer = await (await fetch("/api/job/" + encodeURIComponent(job))).json();
  status.textContent = answer.state + (answer.log && answer.log.length ? ": " + answer.log[answer.log.length - 1] : "");
  if (answer.state === "running") setTimeout(() => watch(job, status), 2000);
  else if (answer.state === "done") setTimeout(() => window.location.reload(), 800);
}
