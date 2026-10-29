const $ = (id) => document.getElementById(id);
const el = (tag, text, cls) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
};
const number = (x) => (Number.isFinite(x) ? x.toFixed(1) : "—");
const rupees = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const money = (x) => (Number.isFinite(x) ? rupees.format(x) : "—");
function demoScenario(input) {
  const copy = structuredClone(input);
  copy.currency = "INR";
  copy.assumptions = {
    ...copy.assumptions,
    currency:
      "Synthetic INR demo rates; numeric rates unchanged, no foreign-exchange conversion.",
  };
  return copy;
}
let report,
  scenario,
  result,
  selected,
  timer,
  busy = false,
  version = 1,
  spatialLoaded = false;
const chart = echarts.init($("power-chart"));
new ResizeObserver(() => chart.resize()).observe($("power-chart"));
function time(slot) {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }).format(
    new Date(
      new Date(scenario.start).getTime() + slot * scenario.slot_minutes * 60000,
    ),
  );
}
const horizon = () => scenario.tariffs.length;
const now = () => Number($("slot").value);
function rowFor(v) {
  return result.schedule?.find((r) => r.vehicle === v.id);
}
function energyAt(v, slot) {
  return (
    (((rowFor(v)?.grid_kw_by_slot || [])
      .slice(0, slot)
      .reduce((a, b) => a + b, 0) *
      scenario.slot_minutes) /
      60) *
    scenario.efficiency
  );
}
function stateAt(v, slot) {
  const delivered = energyAt(v, slot),
    departure = v.actual_departure ?? v.deadline;
  if (slot < v.arrival) return "Not arrived";
  if (slot >= departure)
    return delivered + 1e-5 >= v.kwh
      ? "Departed · target met"
      : "Departed short";
  if (delivered + 1e-5 >= v.kwh) return "Target met";
  if (rowFor(v)?.grid_kw_by_slot?.[slot] > 1e-5) return "Charging";
  return rowFor(v)?.battery_kwh + 1e-5 >= v.kwh
    ? "Waiting · scheduled"
    : "Awaiting allocation";
}
function stop() {
  clearInterval(timer);
  timer = null;
  window.depotMotionPaused = true;
  $("play").textContent = "▶";
  $("spatial-play").textContent = "▶ Play";
}
function reset() {
  stop();
  const saved = report.four_way.find(
    (r) => r.forecast === "qcloud" && r.optimizer === "qpiai_qubo",
  );
  if (!saved) throw Error("Recorded hybrid execution is unavailable.");
  scenario = demoScenario(saved.scenario);
  result = structuredClone(saved.result);
  selected = scenario.vehicles[0].id;
  version = 1;
  $("slot").value = 0;
  $("source").textContent = "Recorded run · Plan 1";
  $("source").title =
    "Saved SDK execution. Generate plan executes a new run; each accepted event creates the next plan version.";
  $("status").textContent = "";
  $("event-status").textContent = "";
  render();
}
function outcome(value, label, cls) {
  const n = el("div", undefined, "outcome");
  n.append(el("strong", value, cls), el("span", label));
  return n;
}
function render() {
  $("slot").max = horizon();
  $("slot").min = 0;
  $("shift-context").textContent =
    `${time(0)}–${time(horizon())} · ${scenario.vehicles.length} vehicles · ${scenario.chargers.length} chargers`;
  $("cursor-label").textContent = `${scenario.slot_minutes} min / step`;
  renderEvidence();
  renderCursor();
}
function renderCursor(animate = false) {
  const slot = now(),
    audit = result.validation_report;
  const ready = scenario.vehicles.filter(
    (v) => (rowFor(v)?.battery_kwh ?? 0) + 1e-5 >= v.kwh,
  ).length;
  const departed = scenario.vehicles.filter(
    (v) => slot >= (v.actual_departure ?? v.deadline),
  );
  const short = departed.filter((v) => energyAt(v, slot) + 1e-5 < v.kwh);
  const violations = audit?.capacity_violations ?? result.capacity_violations;
  const verified =
    result.independent_validation === true || audit?.passed === true;
  $("clock").textContent = $("spatial-clock").textContent = time(slot);
  $("outcomes").replaceChildren(
    outcome(
      `${ready}/${scenario.vehicles.length}`,
      "projected ready",
      ready === scenario.vehicles.length ? "good" : "warn",
    ),
    ...(departed.length
      ? [
          outcome(
            String(short.length),
            short.length === 1 ? "departure shortfall" : "departure shortfalls",
            short.length ? "warn" : "",
          ),
        ]
      : []),
    outcome(
      Number.isFinite(violations) ? String(violations) : "—",
      verified ? "capacity violations" : "capacity violations · check required",
      verified && !violations ? "good" : "warn",
    ),
    outcome(
      `${number(result.peak_kw)} / ${scenario.capacity_kw} kW`,
      "peak / limit",
    ),
  );
  const unmet = scenario.vehicles.filter(
    (v) => (rowFor(v)?.battery_kwh ?? 0) + 1e-5 < v.kwh,
  );
  const exception = $("exception");
  exception.replaceChildren();
  exception.hidden = !unmet.length && !short.length && verified;
  if (!exception.hidden) {
    exception.append(
      el(
        "strong",
        result.status === "safe_hold"
          ? "Future charging held"
          : "Service exception",
      ),
    );
    const list = short.map(
      (v) => `${v.id} departed ${number(v.kwh - energyAt(v, slot))} kWh short`,
    );
    const projected = unmet
      .filter((v) => !short.includes(v))
      .map(
        (v) =>
          `${v.id}: ${number(v.kwh - (rowFor(v)?.battery_kwh ?? 0))} kWh projected unmet`,
      );
    exception.append(
      el(
        "span",
        [
          ...list,
          ...projected,
          ...(!verified ? ["Physical validation needs attention"] : []),
        ].join(" · "),
      ),
    );
  }
  renderPlan(slot);
  renderDetail(slot);
  renderChart(slot);
  renderBill(slot);
  const roster = $("depot-status");
  roster.replaceChildren();
  for (const v of scenario.vehicles) {
    const b = el("button", undefined, "depot-status-item");
    b.dataset.state = stateAt(v, slot);
    const absence =
      slot < v.arrival ? `Arrives ${time(v.arrival)}` : stateAt(v, slot);
    b.append(
      el("strong", v.id),
      el("span", absence),
      el("small", `${number(energyAt(v, slot))}/${number(v.kwh)} kWh`),
    );
    b.onclick = () => {
      selected = v.id;
      renderCursor();
      window.selectDepotVehicle?.(v.id);
    };
    roster.append(b);
  }
  if (spatialLoaded && $("spatial-dialog").open)
    window.renderDepot3D?.(
      scenario,
      result,
      slot,
      time,
      animate && !matchMedia("(prefers-reduced-motion: reduce)").matches,
    );
}
function bar(track, start, end, label, cls) {
  if (end <= start) return;
  const b = el("span", label, cls);
  b.style.left = `${(100 * start) / horizon()}%`;
  b.style.width = `${(100 * (end - start)) / horizon()}%`;
  track.append(b);
  return b;
}
function renderPlan(slot) {
  const plan = $("plan");
  plan.replaceChildren();
  const axis = el("div", undefined, "plan-axis"),
    labels = el("div", undefined, "time-labels");
  axis.append(el("span", "Delivered / required kWh"));
  [0, 0.25, 0.5, 0.75, 1].forEach((p) =>
    labels.append(el("span", time(horizon() * p))),
  );
  axis.append(labels);
  plan.append(axis);
  for (const v of scenario.vehicles) {
    const row = el(
      "button",
      undefined,
      "plan-row" + (v.id === selected ? " selected" : ""),
    );
    row.dataset.vehicle = v.id;
    row.setAttribute("aria-pressed", String(v.id === selected));
    row.setAttribute(
      "aria-label",
      `${v.id}, ${stateAt(v, slot)}, ${number(energyAt(v, slot))} of ${number(v.kwh)} kWh delivered, confirmed departure ${time(v.deadline)}`,
    );
    const label = el("span", undefined, "vehicle-label"),
      progress = el("progress");
    progress.max = v.kwh;
    progress.value = energyAt(v, slot);
    progress.setAttribute("aria-label", `${v.id} delivered energy`);
    label.append(
      el("b", v.id),
      el("small", `${number(energyAt(v, slot))} / ${number(v.kwh)}`),
      progress,
    );
    const track = el("span", undefined, "track"),
      p = rowFor(v);
    for (const segment of p?.segments || (p ? [p] : [])) {
      const visit = bar(
        track,
        segment.start_slot,
        segment.end_slot,
        undefined,
        "visit" + (slot >= segment.end_slot ? " executed" : ""),
      );
      if (!visit) continue;
      const slack = v.deadline - segment.end_slot;
      visit.classList.toggle("tight-window", slack <= 1);
      visit.title = `${v.id} · ${segment.charger} · ${time(segment.start_slot)}–${time(segment.end_slot)} · ${slack * scenario.slot_minutes} min before confirmed departure`;
      const fraction = Math.max(
        0,
        Math.min(
          1,
          (slot - segment.start_slot) / (segment.end_slot - segment.start_slot),
        ),
      );
      const fill = el("span", undefined, "visit-fill");
      fill.style.width = `${fraction * 100}%`;
      const name = el("span", segment.charger, "visit-name");
      name.classList.toggle("on-executed", fraction >= 0.5);
      visit.append(fill, name);
    }
    const deadline = el("i", undefined, "deadline");
    deadline.style.left = `${(100 * v.deadline) / horizon()}%`;
    deadline.title = `Confirmed departure ${time(v.deadline)}`;
    track.append(deadline);
    if (v.actual_departure !== undefined) {
      const d = el("i", undefined, "deadline departure-actual");
      d.style.left = `${(100 * v.actual_departure) / horizon()}%`;
      d.title = `Actual simulated departure ${time(v.actual_departure)}`;
      track.append(d);
    }
    const cursor = el("i", undefined, "cursor");
    cursor.style.left = `${(100 * slot) / horizon()}%`;
    track.append(cursor);
    row.append(label, track);
    row.onclick = () => {
      selected = v.id;
      renderCursor();
      window.selectDepotVehicle?.(selected);
    };
    plan.append(row);
  }
  const blocks = scenario.charger_blocks || [];
  if (blocks.length) {
    const holds = el("div", undefined, "holds");
    for (const c of scenario.chargers) {
      const active = blocks.filter((b) => b.charger === c.id);
      if (!active.length) continue;
      const r = el("div", undefined, "hold-row"),
        t = el("div", undefined, "hold-track");
      r.append(el("span", `${c.id} · unavailable`), t);
      active.forEach((b) => bar(t, b.start, b.end, "", "hold"));
      holds.append(r);
    }
    plan.append(holds);
  }
  const tariffs = $("tariffs");
  tariffs.replaceChildren();
  const max = Math.max(...scenario.tariffs),
    min = Math.min(...scenario.tariffs);
  scenario.tariffs.forEach((p, i) => {
    const n = el(
      "span",
      i === 0 || p !== scenario.tariffs[i - 1] ? p.toFixed(2) : "",
      "tariff-cell",
    );
    const band =
      max === min
        ? "mid"
        : (p - min) / (max - min) < 0.34
          ? "low"
          : (p - min) / (max - min) > 0.67
            ? "high"
            : "mid";
    n.classList.add(`rate-${band}`);
    n.title = `${time(i)} · ₹${p.toFixed(3)}/kWh · ${band === "low" ? "Low" : band === "high" ? "High" : "Standard"} rate`;
    tariffs.append(n);
  });
  const cursor = el("i", undefined, "cursor");
  cursor.style.left = `${(100 * slot) / horizon()}%`;
  tariffs.append(cursor);
}
function renderDetail(slot) {
  const v =
      scenario.vehicles.find((v) => v.id === selected) || scenario.vehicles[0],
    p = rowFor(v),
    forecast = result.forecasts?.find((f) => f.vehicle === v.id),
    delivered = energyAt(v, slot);
  $("vehicle-title").textContent = v.id;
  $("vehicle-state").textContent = stateAt(v, slot);
  const detail = $("vehicle-detail");
  detail.replaceChildren();
  const total = el("div", undefined, "energy-total");
  total.append(
    el("strong", number(delivered)),
    el("small", ` / ${number(v.kwh)} kWh`),
  );
  const progress = el("progress", undefined, "energy-progress");
  progress.value = delivered;
  progress.max = v.kwh;
  progress.setAttribute("aria-label", "Delivered / required energy");
  detail.append(total, progress);
  const list = el("dl", undefined, "detail-list");
  const intervals = (p?.segments || (p ? [p] : [])).map(
    (s) => `${s.charger} ${time(s.start_slot)}–${time(s.end_slot)}`,
  );
  const predicted = forecast?.predicted_disconnect
    ? new Date(forecast.predicted_disconnect).toLocaleTimeString("en-GB", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Unavailable";
  for (const [label, value] of [
    ["Confirmed departure", time(v.deadline)],
    ["Predicted unplug¹", predicted],
    [
      "Planned charging finish",
      p?.battery_kwh + 1e-5 >= v.kwh ? time(p.end_slot) : "Not fully allocated",
    ],
    [
      "Actual departure",
      v.actual_departure !== undefined
        ? time(v.actual_departure)
        : "Not observed",
    ],
    ["Charging allocation", intervals.join(" / ") || "No allocation"],
  ]) {
    const r = el("div");
    r.append(el("dt", label), el("dd", value));
    list.append(r);
  }
  detail.append(list);
  const deficit =
    v.kwh -
    (slot >= (v.actual_departure ?? v.deadline)
      ? delivered
      : (p?.battery_kwh ?? 0));
  if (deficit > 1e-5)
    detail.append(
      el(
        "p",
        `${slot >= (v.actual_departure ?? v.deadline) ? "Departure shortfall" : "Projected unmet energy"}: ${number(deficit)} kWh`,
        "vehicle-warning",
      ),
    );
  detail.append(
    el(
      "p",
      "¹ Model estimate / departure proxy. Energy shows a requested top-up, not battery state of charge.",
      "detail-note",
    ),
  );
}
function renderChart(slot) {
  const series = (a) =>
    (a || [])
      .map((v, i) => [i, v])
      .concat(a?.length ? [[horizon(), a.at(-1)]] : []);
  chart.setOption(
    {
      animation: false,
      grid: { left: 44, right: 108, top: 32, bottom: 28 },
      tooltip: { trigger: "axis", valueFormatter: (v) => `${number(v)} kW` },
      xAxis: {
        type: "value",
        min: 0,
        max: horizon(),
        interval: horizon() / 4,
        axisLabel: { formatter: time, fontSize: 13, fontWeight: 600 },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        name: "Power (kW)",
        nameGap: 14,
        nameTextStyle: { fontSize: 13, fontWeight: 600, color: "#46515f" },
        min: 0,
        max: Math.ceil(
          Math.max(scenario.capacity_kw, ...(result.aggregate_site_kw || [])) *
            1.15,
        ),
        axisLabel: { fontSize: 13, fontWeight: 600 },
        splitLine: { lineStyle: { color: "#e7ebef" } },
      },
      series: [
        {
          name: "Building",
          type: "line",
          step: "end",
          symbol: "none",
          data: series(scenario.base_load_kw),
          lineStyle: { color: "#7b8490", width: 2, type: "dashed" },
          endLabel: {
            show: true,
            formatter: "Building",
            color: "#566170",
            fontSize: 13,
            fontWeight: 600,
          },
          labelLayout: { moveOverlap: "shiftY" },
          areaStyle: { color: "#e5e9ee", opacity: 0.7 },
        },
        {
          name: "Site load",
          type: "line",
          step: "end",
          symbol: "none",
          data: series(result.aggregate_site_kw),
          lineStyle: { color: "#344f70", width: 3 },
          endLabel: {
            show: true,
            formatter: "Site total",
            color: "#344f70",
            fontSize: 13,
            fontWeight: 600,
          },
          labelLayout: { moveOverlap: "shiftY" },
          markLine: {
            symbol: "none",
            label: { show: false },
            data: [
              {
                yAxis: scenario.capacity_kw,
                label: {
                  show: true,
                  formatter: `Limit ${scenario.capacity_kw} kW`,
                  position: "insideEndTop",
                  color: "#875815",
                  fontSize: 13,
                  fontWeight: 600,
                },
                lineStyle: { color: "#b2813d", type: "dashed" },
              },
              { xAxis: slot, lineStyle: { color: "#394554", type: "solid" } },
            ],
          },
        },
      ],
    },
    true,
  );
  $("power-now").textContent =
    slot < horizon()
      ? `${number(result.aggregate_site_kw?.[slot])} / ${scenario.capacity_kw} kW`
      : "Shift ended";
}
function renderBill(slot) {
  $("bill-title").textContent = result.validated
    ? "Projected bill"
    : "Partial-service cost";
  $("bill").textContent = money(result.incremental_bill);
  const parts = $("bill-parts");
  parts.replaceChildren();
  for (const [label, value] of [
    ["Energy", result.energy_cost],
    ["Incremental demand", result.incremental_demand_charge],
  ]) {
    const r = el("div", undefined, "bill-part");
    r.append(el("span", label), el("strong", money(value)));
    parts.append(r);
  }
  const cost = (result.aggregate_ev_kw || [])
    .slice(0, slot)
    .reduce(
      (s, p, i) => s + (p * scenario.tariffs[i] * scenario.slot_minutes) / 60,
      0,
    );
  $("incurred").textContent =
    `Energy incurred through ${time(slot)}: ${money(cost)}. ${result.validated ? "Projected future charging included · INR demo rates." : "Partial service · unmet energy remains."}`;
}
function renderEvidence() {
  const f = result.forecast_evidence || {},
    e = result.execution_evidence || {},
    proof = $("proof");
  proof.replaceChildren();
  for (const [title, body] of [
    [
      "QCloud · prediction",
      `${f.qubits ?? 6} qubits / ${f.shots ?? 512} shots · ${f.backend || "backend unavailable"} · ${f.reused_at_event ? "arrival prediction reused" : "measured quantum features"} · local simulator`,
    ],
    [
      "QpiAI Opt · allocation",
      `${e.provider || "QpiAI Opt"} · QUBO · classical local solver · ${number(result.seconds)} s`,
    ],
    [
      "Independent validation",
      `${result.validation_report?.passed ? "Physical checks passed" : "Physical audit requires review"} · ${result.validated ? "All confirmed energy requirements allocated" : "Service exceptions present"}`,
    ],
  ]) {
    const r = el("div", undefined, "proof-step");
    r.append(el("b", title), el("span", body));
    proof.append(r);
  }
  $("model-evidence").textContent = JSON.stringify(
    {
      selected_model: e.attempts?.[e.selected_attempt]?.model,
      selected_bits: e.attempts?.[e.selected_attempt]?.bits,
      visits: e.profile_menu,
    },
    null,
    2,
  );
  $("raw-evidence").textContent = JSON.stringify(
    {
      qcloud: f,
      opt: e,
      validation: result.validation_report,
      events: result.replay?.events,
    },
    null,
    2,
  );
  $("scenario-evidence").textContent = JSON.stringify(scenario, null, 2);
  const table = el("table"),
    header = el("tr");
  ["Scenario", "Method", "Ready", "Bill"].forEach((t) =>
    header.append(el("th", t)),
  );
  table.append(header);
  report.cases
    .filter((c) => c.runs)
    .forEach((c) =>
      Object.entries(c.runs).forEach(([method, r]) => {
        const tr = el("tr");
        [
          c.id,
          method,
          `${r.validation_report?.confirmed_ready ?? r.schedule?.length ?? 0}/${c.scenario.vehicles.length}`,
          money(r.incremental_bill),
        ].forEach((t) => tr.append(el("td", t)));
        table.append(tr);
      }),
    );
  $("comparison").replaceChildren(table);
}
function setBusy(value) {
  busy = value;
  [
    "run",
    "reset",
    "apply-event",
    "play",
    "slot",
    "conditions-open",
    "departure-demo",
  ].forEach((id) => ($(id).disabled = value));
}
async function post(path, request) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const data = await response.json();
  if (!response.ok || data.error) throw Error(data.error || "Request failed");
  return data;
}
$("play").onclick = () => {
  if (timer) return stop();
  if (now() >= horizon()) $("slot").value = result.replay?.slot ?? 0;
  window.depotMotionPaused = false;
  $("play").textContent = "Ⅱ";
  $("spatial-play").textContent = "Ⅱ Pause";
  timer = setInterval(() => {
    $("slot").value = now() + 1;
    renderCursor(true);
    if (now() >= horizon()) stop();
  }, 2800);
};
$("spatial-play").onclick = () => $("play").click();
$("slot").oninput = () => {
  stop();
  renderCursor();
};
$("reset").onclick = () => {
  if (
    result.replay &&
    !confirm(
      "Replay reset discards the current branch. The exported run retains its events. Continue?",
    )
  )
    return;
  reset();
};
$("run").onclick = async () => {
  if (busy) return;
  stop();
  setBusy(true);
  $("status").textContent = "Executing QCloud measurements and Opt allocation…";
  try {
    const input = demoScenario(
      report.four_way.find(
        (r) => r.forecast === "qcloud" && r.optimizer === "qpiai_qubo",
      ).scenario,
    );
    Object.assign(input, {
      backend: "qpiai_qubo",
      profile_limit: 4,
      forecast_source: "qcloud",
      risk_weight: 0.25,
    });
    const output = await post("/solve", input);
    scenario = input;
    result = output;
    version++;
    $("slot").value = 0;
    $("source").textContent = `Live run · Plan ${version}`;
    $("status").textContent = "";
    render();
  } catch (e) {
    $("status").textContent =
      `Run failed. Current branch retained: ${e.message}`;
  } finally {
    setBusy(false);
  }
};
$("export").onclick = () => {
  const a = el("a");
  a.href = URL.createObjectURL(
    new Blob(
      [
        JSON.stringify(
          { currency: "INR", scenario, result, plan_version: version },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    ),
  );
  a.download = "qaunfleets-execution.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
document
  .querySelectorAll("[data-close]")
  .forEach((b) => (b.onclick = () => b.closest("dialog").close()));
$("evidence-open").onclick = () => $("evidence-dialog").showModal();
$("departure-demo").onclick = () => {
  if (
    result.replay &&
    !confirm("The example starts a new recorded playback branch. Continue?")
  )
    return;
  reset();
  selected = "V2";
  $("slot").value = 14;
  renderCursor();
  $("event-kind").value = "depart_now";
  populateEvent();
  $("event-status").textContent =
    "Example: V2 leaves at 01:00. The event records delivered energy and replans the remaining fleet.";
  $("conditions-dialog").showModal();
};
$("conditions-open").onclick = () => {
  stop();
  populateEvent();
  $("conditions-dialog").showModal();
};
function populateEvent() {
  $("event-time").textContent =
    `Effective ${time(now())} · Plan ${version} · past slots remain fixed`;
  for (const [id, items] of [
    ["event-vehicle", scenario.vehicles],
    ["event-charger", scenario.chargers],
  ]) {
    const current = $(id).value;
    $(id).replaceChildren();
    items.forEach((item) => {
      const o = el("option", item.id);
      o.value = item.id;
      $(id).append(o);
    });
    if (items.some((v) => v.id === current)) $(id).value = current;
  }
  $("event-vehicle").value = selected;
  $("event-until").replaceChildren();
  for (let i = now() + 1; i <= horizon(); i++) {
    const o = el("option", time(i));
    o.value = i;
    $("event-until").append(o);
  }
  $("event-until").value = Math.min(
    horizon(),
    now() + Math.ceil(60 / scenario.slot_minutes),
  );
  updateEventFields();
}
function updateEventFields() {
  const k = $("event-kind").value;
  $("vehicle-field").hidden = !["depart_now", "deadline"].includes(k);
  $("charger-field").hidden = !["occupied", "release"].includes(k);
  $("until-field").hidden = !["deadline", "occupied", "load"].includes(k);
  $("load-field").hidden = k !== "load";
}
$("event-kind").onchange = updateEventFields;
$("event-form").onsubmit = async (e) => {
  e.preventDefault();
  if (busy) return;
  stop();
  if (now() >= horizon() || now() < (result.replay?.slot ?? 0)) {
    $("event-status").textContent =
      "The event time must follow the last recorded event and precede shift end.";
    return;
  }
  const event = { type: $("event-kind").value };
  if (["depart_now", "deadline"].includes(event.type))
    event.vehicle = $("event-vehicle").value;
  if (["occupied", "release"].includes(event.type))
    event.charger = $("event-charger").value;
  if (["occupied", "load"].includes(event.type))
    event.until = Number($("event-until").value);
  if (event.type === "deadline")
    event.deadline = Number($("event-until").value);
  if (event.type === "load") event.delta_kw = Number($("event-load").value);
  setBusy(true);
  $("event-status").textContent =
    "Preserving delivered energy and replanning future slots…";
  try {
    const data = await post("/replan", {
      scenario,
      result,
      slot: now(),
      event,
    });
    scenario = data.scenario;
    result = data.result;
    version++;
    if (event.vehicle) selected = event.vehicle;
    $("source").textContent = `Execution replay · Plan ${version}`;
    $("status").textContent = result.replay.future_plan_found
      ? "Future plan updated; delivered energy preserved."
      : "No accepted future plan. Charging held; shortfalls shown.";
    render();
    $("event-status").textContent = $("status").textContent;
    $("conditions-dialog").close();
  } catch (error) {
    $("event-status").textContent =
      `Event not applied: ${error.message}. Current branch retained.`;
  } finally {
    setBusy(false);
  }
};
$("spatial-open").onclick = async () => {
  $("spatial-dialog").showModal();
  try {
    if (!spatialLoaded) {
      await import("./depot3d.js");
      spatialLoaded = true;
    }
    renderCursor();
    window.selectDepotVehicle?.(selected);
    window.dispatchEvent(new Event("resize"));
  } catch (e) {
    $("fleet").textContent =
      "3D unavailable. All allocations remain available in the charging plan.";
  }
};
window.addEventListener("depot-select", (e) => {
  selected = e.detail;
  renderCursor();
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") stop();
});
fetch("/evidence")
  .then((r) => {
    if (!r.ok) throw Error("Recorded evidence unavailable");
    return r.json();
  })
  .then((data) => {
    report = data;
    reset();
  })
  .catch((error) => ($("status").textContent = error.message));
