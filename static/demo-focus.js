// Presentation surface: every indicator uses the currently displayed result.
let tariffChart;
function renderProof() {
  const audit = result.validation_report,
    ok = audit?.passed === true;
  const strip = $("validation-strip");
  strip.replaceChildren();
  for (const text of [
    ok ? "✓ Physical checks passed" : "Physical checks failed / unavailable",
    audit
      ? audit.confirmed_ready +
        "/" +
        audit.mandatory_vehicles +
        " departures ready"
      : "Readiness unverified",
    audit
      ? audit.capacity_violations + " capacity violations"
      : "Capacity unverified",
    result.validated
      ? "All energy commitments met"
      : "Service shortfall / no compliant plan",
  ])
    strip.append(node("span", text));
  strip.classList.toggle("failed", !ok || !result.validated);
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
        ? f.backend +
          " · simulator" +
          (f.reused_at_event ? " · arrival prediction reused" : "")
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
      result.validated ? "Accepted charging plan" : "Service exception",
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
  renderReplay();
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
      "Shift complete · check reported departures and energy shortfalls.";
    return;
  }
  const load = result.aggregate_site_kw?.[slot];
  const pending = scenario.vehicles
    .filter((v) => (v.actual_departure ?? v.deadline) > slot)
    .sort((a, b) => a.deadline - b.deadline)[0];
  const done = result.schedule.filter(
    (p) =>
      p.end_slot <= slot &&
      p.battery_kwh >=
        scenario.vehicles.find((v) => v.id === p.vehicle).kwh - 1e-5 &&
      (scenario.vehicles.find((v) => v.id === p.vehicle).actual_departure ??
        scenario.vehicles.find((v) => v.id === p.vehicle).deadline) > slot,
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
const nav = document.querySelector("nav");
const more = document.createElement("details");
more.innerHTML = "<summary>Evidence & presentation</summary>";
for (const name of ["benchmarks", "pitch"])
  more.append(document.querySelector("[data-tab=" + name + "]"));
nav.append(more);
let eventBusy = false;
async function replan(kind) {
  if (eventBusy) return;
  stop();
  const now = +$("slot").value,
    horizon = scenario.tariffs.length;
  if (now >= horizon) {
    $("event-status").textContent =
      "Choose a time before the end of the shift.";
    return;
  }
  const vehicle = scenario.vehicles.find(
    (v) => v.id === $("event-vehicle").value,
  );
  const duration = Math.ceil(60 / scenario.slot_minutes);
  const event =
    kind === "early"
      ? { type: "depart_now", vehicle: vehicle.id }
      : kind === "occupied"
        ? {
            type: "occupied",
            charger: $("event-charger").value,
            until: Math.min(horizon, now + duration),
          }
        : {
            type: "load",
            delta_kw: 8,
            until: Math.min(horizon, now + duration),
          };
  eventBusy = true;
  const controls = [
    "early-event",
    "surge-event",
    "occupied-event",
    "reset-event",
    "run",
    "play",
    "slot",
  ];
  controls.forEach((id) => ($(id).disabled = true));
  $("event-status").textContent =
    "Applying event at " +
    time(now) +
    "; preserving delivered energy and replanning future slots…";
  try {
    const response = await fetch("/replan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario, result, slot: now, event }),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || "Replan failed");
    scenario = data.scenario;
    result = data.result;
    $("slot").value = now;
    $("input").value = JSON.stringify(scenario, null, 2);
    render();
    $("status").textContent =
      "Execution replay · " +
      result.status +
      " · future solver: " +
      result.replay.future_solver_status;
    $("event-status").textContent = result.replay.future_plan_found
      ? "Future plan updated. Past charging and energy cost are unchanged."
      : "No compliant future plan found. Future charging is held; unmet energy is shown below.";
  } catch (error) {
    $("event-status").textContent = "Event not applied: " + error.message;
  } finally {
    eventBusy = false;
    controls.forEach((id) => ($(id).disabled = false));
  }
}
function renderReplay() {
  const selector = $("event-vehicle");
  const selected = selector.value;
  selector.replaceChildren();
  for (const v of scenario.vehicles) {
    const option = node("option", v.id);
    option.value = v.id;
    selector.append(option);
  }
  if ([...selector.options].some((o) => o.value === selected))
    selector.value = selected;
  const chargers = $("event-charger");
  const current = chargers.value;
  chargers.replaceChildren();
  for (const c of scenario.chargers) {
    const o = node("option", c.id);
    o.value = c.id;
    chargers.append(o);
  }
  if ([...chargers.options].some((o) => o.value === current))
    chargers.value = current;
  const replay = result.replay;
  const panel = $("replay-results");
  panel.classList.toggle("hidden", !replay);
  if (!replay) return;
  $("replay-cost").textContent =
    "Executed through " +
    time(replay.slot) +
    " · energy cost incurred " +
    money(replay.realized_energy_cost) +
    " · peak reached " +
    num(replay.historical_peak_kw) +
    " kW";
  table(
    "shortfalls",
    [
      "Vehicle",
      "Delivered at event",
      "Required",
      "Unmet in plan",
      "Short at departure",
    ],
    replay.service.map((v) => [
      v.vehicle,
      num(v.delivered_so_far_kwh) + " kWh",
      num(v.required_kwh) + " kWh",
      num(v.shortfall_kwh) + " kWh",
      v.departed ? num(v.realized_shortfall_kwh) + " kWh" : "Not departed",
    ]),
  );
}
$("early-event").onclick = () => replan("early");
$("surge-event").onclick = () => replan("surge");
$("occupied-event").onclick = () => replan("occupied");
$("reset-event").onclick = () => {
  saved();
  $("event-status").textContent =
    "Original recorded plan restored; execution history reset.";
};
