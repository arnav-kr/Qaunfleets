// Presentation surface: every indicator uses the currently displayed result.
let tariffChart;
function renderProof() {
  const audit = result.validation_report,
    ok = audit?.passed === true;
  const strip = $("validation-strip");
  strip.replaceChildren();
  for (const text of [
    ok ? "✓ Independently validated" : "No validated plan",
    audit
      ? audit.confirmed_ready +
        "/" +
        audit.mandatory_vehicles +
        " departures ready"
      : "Readiness unverified",
    audit
      ? audit.capacity_violations + " capacity violations"
      : "Capacity unverified",
    ok ? "✓ Charger and energy checks passed" : "Checks not passed",
  ])
    strip.append(node("span", text));
  strip.classList.toggle("failed", !ok);
  const f = result.forecast_evidence || {},
    e = result.execution_evidence || {};
  const box = $("execution-path");
  box.replaceChildren();
  const rows = [
    [
      "01 · Predict",
      f.source === "qcloud"
        ? "QCloud · " + f.qubits + " qubits / " + f.shots + " shots"
        : f.source === "classical"
          ? "Classical predictor"
          : "Confirmed departures only",
      f.source === "qcloud"
        ? f.backend + " · simulator"
        : "No quantum prediction in this run",
    ],
    [
      "02 · Allocate",
      e.provider || result.solver || "Scheduler",
      e.quantum_hardware
        ? "Physical hardware"
        : e.problem_class
          ? e.problem_class + " · classical local solver"
          : "Classical optimization",
    ],
    [
      "03 · Verify",
      ok ? "Accepted charging plan" : "No accepted plan",
      Number.isFinite(result.seconds)
        ? result.seconds.toFixed(2) + " s scheduler runtime"
        : "Runtime unavailable",
    ],
  ];
  for (const [title, value, sub] of rows) {
    const el = node("div", undefined, "execution-step");
    el.append(
      node("span", title, "small"),
      node("strong", value),
      node("span", sub, "small"),
    );
    box.append(el);
  }
  const note = node(
    "div",
    f.source === "qcloud"
      ? "Quantum features inform an experimental unplug-time preference. Confirmed departures stay mandatory. Simulator execution; no demonstrated quantum advantage."
      : "This run uses confirmed commitments without a quantum prediction.",
    "small",
  );
  box.append(note);
}
function renderTariff(slot) {
  if (!tariffChart) {
    tariffChart = echarts.init($("tariff-chart"));
    new ResizeObserver(() => tariffChart.resize()).observe($("tariff-chart"));
  }
  const n = scenario.tariffs.length;
  tariffChart.setOption(
    {
      animation: false,
      grid: { left: 50, right: 24, top: 15, bottom: 30 },
      tooltip: {
        trigger: "axis",
        formatter: (items) =>
          time(items[0].value[0]) +
          " · $" +
          items[0].value[1].toFixed(3) +
          "/kWh",
      },
      xAxis: {
        type: "value",
        min: 0,
        max: n,
        interval: Math.max(1, Math.ceil(n / 4)),
        axisLabel: { formatter: (v) => time(v) },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        min: 0,
        axisLabel: { formatter: (v) => "$" + v.toFixed(2) },
        splitLine: { lineStyle: { color: "#edf1ed" } },
      },
      series: [
        {
          name: "Tariff",
          type: "line",
          step: "end",
          symbol: "none",
          data: scenario.tariffs
            .map((v, i) => [i, v])
            .concat([[n, scenario.tariffs.at(-1)]]),
          lineStyle: { color: "#8270af", width: 2 },
          areaStyle: { color: "#e8e2f3", opacity: 0.6 },
          markLine: {
            symbol: "none",
            data: [{ xAxis: slot }],
            label: { show: false },
            lineStyle: { color: "#263f37", type: "solid" },
          },
        },
      ],
    },
    true,
  );
}
function renderEvents(slot) {
  const el = $("event-summary");
  el.replaceChildren();
  const n = scenario.tariffs.length;
  if (!result.schedule?.length) {
    el.textContent = "No accepted allocation to play.";
    return;
  }
  if (slot >= n) {
    el.textContent =
      "Shift complete · vehicles have left at their confirmed departure times.";
    return;
  }
  const load = result.aggregate_site_kw?.[slot];
  const pending = scenario.vehicles
    .filter((v) => v.deadline > slot)
    .sort((a, b) => a.deadline - b.deadline)[0];
  const done = result.schedule.filter(
    (p) =>
      p.end_slot <= slot &&
      scenario.vehicles.find((v) => v.id === p.vehicle).deadline > slot,
  ).length;
  for (const text of [
    num(scenario.capacity_kw - load) + " kW headroom",
    pending
      ? "Next departure: " + pending.id + " at " + time(pending.deadline)
      : "All departures complete",
    done + " charged and parked",
    "Tariff $" + scenario.tariffs[slot].toFixed(3) + "/kWh",
  ])
    el.append(node("span", text));
}
$("inspect-method").onclick = () =>
  document.querySelector("[data-tab=algorithm]").click();
// Keep solver alternatives available for questions, outside the main demo path.
const settings = document.querySelector(".settings-content");
settings.prepend($("scenario").parentElement);
const nav = document.querySelector("nav");
const more = document.createElement("details");
more.innerHTML = "<summary>Evidence & presentation</summary>";
for (const name of ["benchmarks", "pitch"])
  more.append(document.querySelector("[data-tab=" + name + "]"));
nav.append(more);
let eventBusy = false;
async function replan(kind) {
  if (eventBusy) return;
  eventBusy = true;
  const buttons = ["early-event", "surge-event", "reset-event"];
  buttons.forEach((id) => ($(id).disabled = true));
  try {
    const d = structuredClone(scenario);
    if (kind === "early") {
      const v = d.vehicles.find((v) => v.id === "V1") || d.vehicles[0];
      v.deadline = Math.max(
        v.arrival + 1,
        v.deadline - Math.ceil(60 / d.slot_minutes),
      );
      $("event-status").textContent =
        v.id + " departure changed to " + time(v.deadline) + ". Replanning…";
    } else {
      const start = Math.min(+$("slot").value, d.tariffs.length - 1);
      for (
        let i = start;
        i < Math.min(d.tariffs.length, start + Math.ceil(60 / d.slot_minutes));
        i++
      )
        d.base_load_kw[i] += 8;
      $("event-status").textContent =
        "Building load increased by 8 kW from " + time(start) + ". Replanning…";
    }
    $("input").value = JSON.stringify(d, null, 2);
    await $("run").onclick();
    $("event-status").textContent = $("status").textContent.startsWith(
      "Run failed",
    )
      ? "Replan failed. Previous plan retained."
      : result.schedule?.length
        ? "Updated plan accepted. Playback restarted."
        : "No feasible plan accepted for this change. Reduce demand or revise the departure requirement.";
  } finally {
    eventBusy = false;
    buttons.forEach((id) => ($(id).disabled = false));
  }
}
$("early-event").onclick = () => replan("early");
$("surge-event").onclick = () => replan("surge");
$("reset-event").onclick = () => {
  $("scenario").value = "tariff_and_peak";
  $("solver").value = "opt_qubo";
  saved();
  $("event-status").textContent = "Original recorded plan restored.";
};
