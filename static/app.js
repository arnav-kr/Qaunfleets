const $ = (id) => document.getElementById(id);
let report, scenario, result, timer;
const money = (x) => (Number.isFinite(x) ? "$" + x.toFixed(2) : "—");
const num = (x) => (Number.isFinite(x) ? x.toFixed(1) : "—");
function node(tag, text, cls) {
  let e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
function table(id, head, rows) {
  let t = $(id);
  t.replaceChildren();
  let tr = node("tr");
  head.forEach((x) => tr.append(node("th", x)));
  t.append(tr);
  rows.forEach((row) => {
    let tr = node("tr");
    row.forEach((x) => tr.append(node("td", x)));
    t.append(tr);
  });
}
function time(slot) {
  let d = new Date(
    new Date(scenario.start).getTime() + slot * scenario.slot_minutes * 60000,
  );
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }).format(d);
}
function selected() {
  return report.cases.find((x) => x.id === $("scenario").value);
}
function saved() {
  stop();
  scenario = structuredClone(selected().scenario);
  $("solver").querySelector("[value=opt_qubo]").textContent =
    "QpiAI Opt · QUBO / " +
    (scenario.scenario_id === "quantum_circuit_demo" ? 2 : 4) +
    " choices per van";
  result = selected().runs[$("solver").value];
  if (!result) {
    $("solver").value = "opt_qubo";
    result = selected().runs.opt_qubo;
  }
  if (
    $("scenario").value === "tariff_and_peak" &&
    $("solver").value === "opt_qubo"
  ) {
    const final = report.four_way.find(
      (x) => x.forecast === "qcloud" && x.optimizer === "qpiai_qubo",
    );
    if (final) {
      scenario = structuredClone(final.scenario);
      result = final.result;
      $("forecast").value = "qcloud";
    }
  }
  $("input").value = JSON.stringify(scenario, null, 2);
  $("slot").value = 0;
  $("status").textContent =
    "Recorded execution · " +
    (result.solver || $("solver").selectedOptions[0].text) +
    " · " +
    result.status;
  render();
}
function render() {
  let ok = !!result.schedule?.length;
  $("slot").max = scenario.tariffs.length;
  $("play").disabled = !ok;
  $("slot").disabled = !ok;
  $("failure").classList.toggle("hidden", ok);
  $("failure").textContent = (result.reasons || ["No accepted schedule."]).join(
    " ",
  );
  $("metrics").replaceChildren();
  let energy = (result.schedule || []).reduce((s, x) => s + x.battery_kwh, 0);
  [
    [
      "Ready by departure",
      ok ? result.schedule.length + "/" + scenario.vehicles.length : "—",
      "Planned for the full shift",
    ],
    [
      "Site peak",
      ok ? num(result.peak_kw) + " kW" : "—",
      "Feeder limit " + scenario.capacity_kw + " kW",
    ],
    [
      "Charging cost",
      money(result.incremental_bill),
      "Energy " +
        money(result.energy_cost) +
        " · demand " +
        money(result.incremental_demand_charge),
    ],
    [
      "Energy to deliver",
      ok ? num(energy) + " kWh" : "—",
      ok ? "Planned top-up · not battery SOC" : "No accepted allocation",
    ],
  ].forEach(([label, value, sub]) => {
    let c = node("div", undefined, "metric");
    c.append(
      node("div", label, "small"),
      node("div", value, "value"),
      node("div", sub, "small"),
    );
    $("metrics").append(c);
  });
  table(
    "ledger",
    [
      "Vehicle",
      "Charger",
      "Charging",
      "Confirmed departure",
      "Predicted unplug",
      "Battery / grid kWh",
    ],
    (result.schedule || []).map((p) => {
      let v = scenario.vehicles.find((v) => v.id === p.vehicle),
        f = (result.forecasts || []).find((f) => f.vehicle === p.vehicle);
      return [
        p.vehicle,
        p.charger,
        time(p.start_slot) + "–" + time(p.end_slot),
        time(v.deadline),
        f?.predicted_disconnect
          ? new Date(f.predicted_disconnect).toLocaleTimeString("en-GB", {
              timeZone: "Asia/Kolkata",
              hour: "2-digit",
              minute: "2-digit",
            })
          : "Not used",
        num(p.battery_kwh) + " / " + num(p.grid_kwh),
      ];
    }),
  );
  algorithm();
  renderSummary();
  renderProof();
  playback();
}
function playback(animate = false) {
  let slot = +$("slot").value,
    n = scenario.tariffs.length;
  $("clock").textContent = time(slot);
  renderIsoDepot(scenario, result, slot, time, animate);
  $("gantt").replaceChildren();
  let axis = node("div", undefined, "gantt-axis");
  for (let t of [0, n / 4, n / 2, (3 * n) / 4, n])
    axis.append(node("span", time(t)));
  $("gantt").append(axis);
  for (let v of scenario.vehicles) {
    let row = node("div", undefined, "gantt-row");
    row.append(node("span", v.id));
    let track = node("div", undefined, "track"),
      p = result.schedule?.find((p) => p.vehicle === v.id);
    if (p) {
      let b = node("div", p.charger, "visit");
      b.style.left = (p.start_slot / n) * 100 + "%";
      b.style.width = ((p.end_slot - p.start_slot) / n) * 100 + "%";
      track.append(b);
    }
    let deadline = node("div", undefined, "deadline");
    deadline.style.left = (v.deadline / n) * 100 + "%";
    let cursor = node("div", undefined, "cursor");
    cursor.style.left = (slot / n) * 100 + "%";
    track.append(deadline, cursor);
    row.append(track);
    $("gantt").append(row);
  }
  drawChart(slot);
  renderRoster(slot);
  renderTariff(slot);
  renderEvents(slot);
}
let powerChart;
function drawChart(slot) {
  if (!powerChart) {
    powerChart = echarts.init($("chart"));
    new ResizeObserver(() => powerChart.resize()).observe($("chart"));
  }
  const n = scenario.tariffs.length,
    series = (values) =>
      values.map((v, i) => [i, v]).concat([[n, values.at(-1)]]);
  powerChart.setOption(
    {
      animation: false,
      aria: {
        enabled: true,
        description:
          "Planned site demand and background load in kilowatts, with a feeder capacity limit.",
      },
      grid: { left: 42, right: 24, top: 28, bottom: 32 },
      tooltip: {
        trigger: "axis",
        formatter: (items) =>
          time(items[0].value[0]) +
          "<br>" +
          items
            .map(
              (x) => x.marker + x.seriesName + ": " + num(x.value[1]) + " kW",
            )
            .join("<br>"),
        axisPointer: { type: "line" },
      },
      xAxis: {
        type: "value",
        min: 0,
        max: n,
        interval: Math.max(1, Math.ceil(n / 4)),
        axisLabel: { formatter: (v) => time(v), color: "#667571" },
        axisLine: { lineStyle: { color: "#dce3df" } },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: Math.ceil(
          Math.max(scenario.capacity_kw, ...(result.aggregate_site_kw || [])) *
            1.15,
        ),
        axisLabel: { color: "#667571" },
        splitLine: { lineStyle: { color: "#eef1ee" } },
      },
      series: [
        {
          name: "Background load",
          type: "line",
          step: "end",
          symbol: "none",
          data: series(scenario.base_load_kw),
          lineStyle: { color: "#9caea9", width: 1.5 },
          areaStyle: { color: "#e6eeeb", opacity: 0.8 },
        },
        {
          name: "Site demand",
          type: "line",
          step: "end",
          symbol: "none",
          data: result.aggregate_site_kw
            ? series(result.aggregate_site_kw)
            : [],
          lineStyle: { color: "#148267", width: 2.5 },
          markLine: {
            symbol: "none",
            silent: true,
            data: [
              {
                yAxis: scenario.capacity_kw,
                label: {
                  formatter: "Limit " + scenario.capacity_kw + " kW",
                  position: "insideEndTop",
                  color: "#95601b",
                },
                lineStyle: { color: "#b47d31", type: "dashed" },
              },
              {
                xAxis: slot,
                label: { show: false },
                lineStyle: { color: "#263f37", type: "solid", width: 1 },
              },
            ],
          },
        },
      ],
    },
    true,
  );
  $("power").textContent =
    slot < n && result.aggregate_site_kw
      ? num(result.aggregate_site_kw[slot]) + " kW at " + time(slot)
      : "End of shift";
}
function renderSummary() {
  const ok = !!result.schedule?.length;
  document.querySelectorAll(".metric").forEach((c, i) => {
    let bar = node("div", undefined, "metric-visual");
    if (i === 0) {
      for (let v of scenario.vehicles) {
        let segment = node("i");
        segment.classList.toggle(
          "filled",
          !!result.schedule?.some((p) => p.vehicle === v.id),
        );
        bar.append(segment);
      }
    } else {
      let fill = node("i", undefined, "filled");
      fill.style.width =
        (ok
          ? i === 1
            ? Math.min(100, (result.peak_kw / scenario.capacity_kw) * 100)
            : 100
          : 0) + "%";
      bar.append(fill);
    }
    if (i < 2) c.append(bar);
  });
  $("bill-total").textContent = ok ? money(result.incremental_bill) : "—";
  $("cost-bar").replaceChildren();
  $("cost-breakdown").replaceChildren();
  for (const [label, value, color] of [
    ["Energy", result.energy_cost, "#148267"],
    ["Demand", result.incremental_demand_charge, "#91a8de"],
  ]) {
    let part = node("span");
    part.style.background = color;
    part.style.width =
      (ok && result.incremental_bill > 0
        ? (value / result.incremental_bill) * 100
        : 0) + "%";
    $("cost-bar").append(part);
    let row = node("div", undefined, "cost-row");
    row.append(node("span", label), node("strong", ok ? money(value) : "—"));
    $("cost-breakdown").append(row);
  }
}
function renderRoster(slot) {
  $("roster").replaceChildren();
  let count = 0;
  for (const v of scenario.vehicles) {
    let p = result.schedule?.find((p) => p.vehicle === v.id),
      energy = p
        ? ((p.grid_kw_by_slot.slice(0, slot).reduce((a, b) => a + b, 0) *
            scenario.slot_minutes) /
            60) *
          scenario.efficiency
        : 0;
    let state = !p
      ? "No plan"
      : slot < v.arrival
        ? "Not arrived"
        : slot >= v.deadline
          ? "Departed"
          : slot >= p.start_slot && slot < p.end_slot
            ? "Charging"
            : energy >= v.kwh - 1e-6
              ? "Ready"
              : "Waiting";
    if (state === "Charging") count++;
    let row = node("button", undefined, "fleet-row");
    row.dataset.vehicle = v.id;
    row.dataset.state = state;
    row.setAttribute(
      "aria-label",
      v.id +
        ", " +
        state +
        ", " +
        num(energy) +
        " of " +
        v.kwh +
        " kWh delivered",
    );
    row.onclick = () => window.selectDepotVehicle?.(v.id);
    let top = node("div", undefined, "fleet-row-top");
    top.append(node("strong", v.id), node("span", state, "state"));
    let bar = node("progress");
    bar.max = v.kwh;
    bar.value = energy;
    let bottom = node("div", undefined, "fleet-row-bottom");
    bottom.append(
      node("span", num(energy) + " / " + num(v.kwh)),
      node("span", "Departs " + time(v.deadline)),
    );
    row.append(top, bar, bottom);
    $("roster").append(row);
  }
  $("scene-count").textContent = count + " charging";
}
function algorithm() {
  let e = result.execution_evidence || {},
    attempt = e.attempts?.[e.selected_attempt];
  $("evidence").textContent = JSON.stringify(e, null, 2);
  $("qcloud").textContent = JSON.stringify(
    result.forecast_evidence || {
      source: "none",
      note: "Choose QCloud and Run live to execute six-qubit feature circuits for these vehicles.",
    },
    null,
    2,
  );
  let ctx = $("matrix").getContext("2d");
  ctx.clearRect(0, 0, 480, 480);
  if (!attempt) {
    $("modelmeta").textContent =
      "No QUBO model in this run. Select the Opt QUBO result.";
    table("bits", ["Bit", "Visit", "Selected"], []);
    return;
  }
  let m = attempt.model;
  $("modelmeta").textContent =
    m.profile_count +
    " visit bits + " +
    (m.names.length - m.profile_count) +
    " slack bits · " +
    m.coefficients.length +
    " nonzero terms · penalty " +
    m.penalty.toFixed(3) +
    " · chosen peak ceiling " +
    num(attempt.ceiling_kw) +
    " kW · " +
    attempt.solver.method;
  if (attempt.samples_feasible_fraction !== undefined)
    $("modelmeta").textContent +=
      " · measured feasible samples " +
      (100 * attempt.samples_feasible_fraction).toFixed(2) +
      "% · uniform " +
      (100 * attempt.uniform_samples_feasible_fraction).toFixed(2) +
      "% (single run)";
  let sz = 480 / m.names.length,
    scale = Math.max(...m.coefficients.map((x) => Math.log1p(Math.abs(x[2]))));
  m.coefficients.forEach(([i, j, v]) => {
    ctx.fillStyle =
      v > 0
        ? "rgba(185,239,113," +
          (0.15 + (0.85 * Math.log1p(Math.abs(v))) / scale) +
          ")"
        : "rgba(174,138,255," +
          (0.15 + (0.85 * Math.log1p(Math.abs(v))) / scale) +
          ")";
    ctx.fillRect(j * sz, i * sz, Math.max(1, sz - 1), Math.max(1, sz - 1));
  });
  table(
    "bits",
    ["Bit", "Vehicle / charger / start", "Chosen"],
    (e.profile_menu || []).map((p) => [
      p.bit,
      p.vehicle + " / " + p.charger + " / " + time(p.start_slot),
      attempt.bits[p.bit] > 0.5 ? "1 ✓" : "0",
    ]),
  );
}
function stop(freeze = true) {
  window.depotMotionPaused = freeze;
  clearInterval(timer);
  timer = null;
  $("play").textContent = "▶";
}
$("play").onclick = () => {
  if (timer) return stop();
  if (+$("slot").value >= scenario.tariffs.length) {
    $("slot").value = 0;
    playback();
  }
  window.depotMotionPaused = false;
  $("play").textContent = "Ⅱ";
  timer = setInterval(() => {
    $("slot").value = +$("slot").value + 1;
    playback(true);
    if (+$("slot").value >= scenario.tariffs.length) stop(false);
  }, 2200);
};
$("slot").oninput = () => {
  stop();
  playback();
};
$("scenario").onchange = saved;
$("solver").onchange = saved;
document.querySelectorAll("[data-tab]").forEach(
  (b) =>
    (b.onclick = () => {
      document
        .querySelectorAll("[data-tab]")
        .forEach((x) => x.classList.toggle("active", x === b));
      document
        .querySelectorAll(".tab")
        .forEach((x) => x.classList.toggle("hidden", x.id !== b.dataset.tab));
      requestAnimationFrame(() => powerChart?.resize());
    }),
);
$("run").onclick = async () => {
  stop();
  $("run").disabled = true;
  $("status").textContent =
    "Executing locally; QCloud / Opt authentication may take a moment…";
  try {
    let d = JSON.parse($("input").value);
    d.backend =
      $("solver").value === "qcloud_qaoa"
        ? "qcloud_qaoa"
        : $("solver").value === "opt_qubo"
          ? "qpiai_qubo"
          : "highs";
    if ($("solver").value === "earliest_departure")
      throw Error(
        "Choose a solver for a live run; heuristic results are available as recorded evidence.",
      );
    if ($("solver").value === "full_classical") delete d.profile_limit;
    else
      d.profile_limit = scenario.scenario_id === "quantum_circuit_demo" ? 2 : 4;
    d.forecast_source = $("forecast").value;
    d.risk_weight = d.forecast_source === "none" ? 0 : 0.25;
    let response = await fetch("/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(d),
    });
    let r = await response.json();
    if (!response.ok || r.error) throw Error(r.error || "Solve failed");
    scenario = d;
    result = r;
    $("slot").value = 0;
    render();
    $("status").textContent =
      "Live execution · " +
      r.status +
      " · " +
      (r.independent_validation
        ? "independently verified"
        : "no accepted plan");
  } catch (e) {
    $("status").textContent =
      "Run failed; previous plan retained: " + e.message;
  } finally {
    $("run").disabled = false;
  }
};
$("download").onclick = () => {
  let a = node("a");
  a.href = URL.createObjectURL(
    new Blob([JSON.stringify({ scenario, result }, null, 2)], {
      type: "application/json",
    }),
  );
  a.download = "qaunfleets-evidence.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
window.addEventListener("load", () => {
  fetch("/evidence")
    .then((r) => {
      if (!r.ok) throw Error("Run shipping_benchmark.py first");
      return r.json();
    })
    .then((d) => {
      report = d;
      d.cases.forEach((c) => {
        let o = node("option", c.id.replaceAll("_", " "));
        o.value = c.id;
        $("scenario").append(o);
      });
      $("scenario").value = "tariff_and_peak";
      saved();
      table(
        "comparison",
        [
          "Scenario",
          "Method",
          "Status",
          "Ready",
          "Peak kW",
          "Energy",
          "Demand",
          "Bill",
        ],
        d.cases.flatMap((c) =>
          Object.entries(c.runs).map(([name, r]) => [
            c.id,
            name,
            r.status,
            (r.schedule?.length || 0) + "/" + c.scenario.vehicles.length,
            num(r.peak_kw),
            money(r.energy_cost),
            money(r.incremental_demand_charge),
            money(r.incremental_bill),
          ]),
        ),
      );
    })
    .catch((e) => ($("status").textContent = e.message));
});
