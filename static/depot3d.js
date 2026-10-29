import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";

const host = document.getElementById("fleet");
let renderer,
  scene,
  camera,
  controls,
  world,
  template,
  latest,
  signature,
  selected = null,
  vehicles = [],
  chargers = [],
  labels = [],
  cables = [],
  raf;
const ray = new THREE.Raycaster(),
  mouse = new THREE.Vector2();
const mat = (color, extra = {}) =>
  new THREE.MeshStandardMaterial({ color, roughness: 0.85, ...extra });
const palettes = {
  ground: mat("#dce5db"),
  road: mat("#536561"),
  cream: mat("#e6e4d9"),
  roof: mat("#587d76"),
  glass: mat("#385463"),
  green: mat("#6fa37c"),
  yellow: mat("#f7d679"),
  dark: mat("#263e37"),
  light: mat("#e9f3d6", { emissive: "#dae6a4", emissiveIntensity: 0.5 }),
};
function box(w, h, d, x, y, z, material, parent = world) {
  let m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  m.position.set(x, y, z);
  m.castShadow = true;
  m.receiveShadow = true;
  parent.add(m);
  return m;
}
function cylinder(r, h, x, y, z, material, parent = world) {
  let m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 8), material);
  m.position.set(x, y, z);
  m.castShadow = true;
  m.receiveShadow = true;
  parent.add(m);
  return m;
}
function label(text, cls) {
  let e = document.createElement("div");
  e.className = cls;
  e.textContent = text;
  host.append(e);
  return e;
}
let hud, detail, hint, loading;
function setup() {
  host.replaceChildren();
  host.className = "depot-webgl";
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.35;
  host.append(renderer.domElement);
  renderer.domElement.setAttribute(
    "aria-label",
    "3D depot: drag to orbit, right-drag to pan, scroll to zoom",
  );
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(37, 1, 0.1, 250);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 16;
  controls.maxDistance = 85;
  controls.maxPolarAngle = Math.PI * 0.47;
  controls.target.set(0, 0, 2);
  reset();
  scene.add(new THREE.HemisphereLight("#e8f5ff", "#59704e", 2.4));
  let sun = new THREE.DirectionalLight("#fff4d5", 4);
  sun.position.set(-16, 28, 12);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, {
    left: -32,
    right: 32,
    top: 32,
    bottom: -32,
    near: 0.5,
    far: 100,
  });
  sun.shadow.bias = -0.0003;
  sun.shadow.normalBias = 0.04;
  scene.add(sun);
  hud = label("", "three-hud");
  detail = label("", "three-detail hidden");
  hint = label(
    "Drag to orbit Â· Right-drag to pan Â· Scroll to zoom",
    "three-hint",
  );
  loading = label("Loading delivery vehicles…", "three-loading");
  const buttons = document.createElement("div");
  buttons.className = "three-tools";
  host.append(buttons);
  for (let [text, action] of [
    ["+", () => zoom(0.8)],
    ["âˆ’", () => zoom(1.25)],
    ["Reset", reset],
  ]) {
    let b = document.createElement("button");
    b.textContent = text;
    b.setAttribute(
      "aria-label",
      text === "+" ? "Zoom in" : text === "âˆ’" ? "Zoom out" : "Reset camera",
    );
    b.onclick = action;
    buttons.append(b);
  }
  let start;
  renderer.domElement.addEventListener(
    "pointerdown",
    (e) => (start = [e.clientX, e.clientY]),
  );
  renderer.domElement.addEventListener("pointerup", (e) => {
    if (!start || Math.hypot(e.clientX - start[0], e.clientY - start[1]) > 5)
      return;
    let rect = renderer.domElement.getBoundingClientRect();
    mouse.set(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      (-(e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    ray.setFromCamera(mouse, camera);
    let hit = ray.intersectObjects(
      vehicles.map((v) => v.model),
      true,
    )[0];
    if (hit) {
      let o = hit.object;
      while (o && !o.userData.vehicle) o = o.parent;
      if (o) {
        selected = o.userData.vehicle;
        updateDetail();
      }
    }
  });
  new ResizeObserver(() => {
    let w = host.clientWidth,
      h = host.clientHeight;
    if (w < 1 || h < 1) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.fov = w < h ? Math.min(65, (37 * h) / w) : 37;
    camera.updateProjectionMatrix();
  }).observe(host);
  function animate() {
    raf = requestAnimationFrame(animate);
    controls.update();
    vehicles.forEach((v) => {
      advanceMotion(v);
      let p = v.model.position.clone();
      p.y += 3.7;
      p.project(camera);
      v.label.style.left = (p.x * 0.5 + 0.5) * host.clientWidth + "px";
      v.label.style.top = (-p.y * 0.5 + 0.5) * host.clientHeight + "px";
      v.label.style.display = p.z > 1 || p.z < -1 ? "none" : "";
    });
    renderer.render(scene, camera);
  }
  animate();
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) cancelAnimationFrame(raf);
    else animate();
  });
}
function spawnOpacity(v, alpha) {
  v.model.traverse((o) => {
    if (!o.isMesh) return;
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
      if (!m.userData.spawnBase)
        m.userData.spawnBase = {
          opacity: m.opacity,
          transparent: m.transparent,
        };
      m.opacity = m.userData.spawnBase.opacity * alpha;
      m.transparent = alpha < 1 || m.userData.spawnBase.transparent;
    }
  });
  v.label.style.opacity = alpha;
}
function advanceMotion(v) {
  if (!v.motion) return;
  const m = v.motion,
    now = performance.now();
  if (!window.depotMotionPaused) m.elapsed += now - m.last;
  m.last = now;
  const t = Math.min(1, m.elapsed / m.duration),
    u = t * t * (3 - 2 * t);
  if (m.kind === "depart") {
    spawnOpacity(v, 1 - u);
    if (t >= 1) {
      v.model.visible = false;
      v.label.style.visibility = "hidden";
      v.motion = null;
      spawnOpacity(v, 1);
    }
    return;
  }
  if (m.kind === "spawn") {
    v.model.position.copy(m.target);
    v.model.position.y += (1 - u) * 0.7;
    spawnOpacity(v, u);
    if (t >= 1) {
      spawnOpacity(v, 1);
      v.motion = null;
      if (v.cable) v.cable.visible = true;
    }
    return;
  }
  v.model.position.copy(m.curve.getPointAt(u));
  const direction = m.curve.getTangentAt(Math.min(0.999, u));
  let angle = Math.atan2(direction.x, direction.z);
  const desired = new THREE.Quaternion().setFromAxisAngle(
    new THREE.Vector3(0, 1, 0),
    angle,
  );
  v.model.quaternion.slerp(desired, 0.22);
  if (t > 0.8)
    v.model.quaternion.slerp(new THREE.Quaternion(), (t - 0.8) / 0.2);
  if (t >= 1) {
    v.model.rotation.y = 0;
    v.model.visible = !m.hide;
    v.label.style.visibility = m.hide ? "hidden" : "visible";
    v.motion = null;
    if (v.cable) v.cable.visible = true;
  }
}
function reset() {
  if (!camera) return;
  camera.position.set(31, 29, 34);
  controls.target.set(0, 0, 2);
  controls.update();
}
function zoom(f) {
  let p = camera.position.clone().sub(controls.target).multiplyScalar(f);
  p.clampLength(16, 85);
  camera.position.copy(controls.target).add(p);
  controls.update();
}
function build(data) {
  if (world) {
    scene.remove(world);
    world.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
    });
  }
  labels.forEach((e) => e.remove());
  labels = [];
  vehicles = [];
  chargers = [];
  cables = [];
  world = new THREE.Group();
  scene.add(world);
  const columns = Math.max(3, data.chargers.length),
    width = Math.max(29, columns * 6 + 8),
    rows = Math.ceil(data.vehicles.length / 3),
    depth = Math.max(32, rows * 7 + 17);
  box(width, 0.7, depth, 0, -0.4, 3, palettes.ground);
  box(width - 2, 0.05, depth - 2, 0, -0.02, 3, palettes.road);
  box(width - 2, 0.2, 3, 0, 0.05, -10, palettes.cream);
  box(width - 3, 3.8, 4, 0, 1.9, -12, palettes.cream);
  box(width - 2, 0.3, 4.7, 0, 3.9, -12, palettes.roof);
  for (let x = -width / 2 + 3; x < width / 2 - 2; x += 4.5) {
    box(3, 2.4, 0.08, x, 1.3, -9.96, palettes.dark);
    box(3.1, 0.16, 0.24, x, 2.65, -9.9, palettes.roof);
  }
  for (let x = -width / 2 + 2; x < width / 2 - 1; x += 3)
    box(1.3, 0.025, 0.11, x, 0.03, 2, palettes.yellow);
  // Charging pedestals and painted bays, sized from the actual charger list.
  data.chargers.forEach((c, i) => {
    let x = (i - (data.chargers.length - 1) / 2) * 6,
      z = -4.6;
    for (let dx of [-2.3, 2.3])
      box(0.08, 0.03, 6.5, x + dx, 0.04, z, palettes.cream);
    box(4.7, 0.03, 0.08, x, 0.04, z - 3.25, palettes.cream);
    box(0.75, 1.8, 0.65, x + 1.8, 0.9, z - 3, palettes.cream);
    box(0.55, 0.55, 0.04, x + 1.8, 1.4, z - 2.65, palettes.glass);
    const lamp = box(
      0.55,
      0.1,
      0.05,
      x + 1.8,
      1.8,
      z - 2.63,
      mat("#688e76", { emissive: "#6fb86d", emissiveIntensity: 0 }),
    );
    chargers.push({ id: c.id, x, z, lamp });
  });
  for (let i = 0; i < data.vehicles.length; i++) {
    let x = ((i % 3) - 1) * 7,
      z = 7 + Math.floor(i / 3) * 7;
    for (let dx of [-2.6, 2.6])
      box(0.08, 0.03, 5.7, x + dx, 0.04, z, palettes.cream);
  }
  // Transformer, curbside trees, bollards and lamps provide scale without UI labels.
  box(2, 2.5, 1.6, -width / 2 + 2, 1.25, -6, palettes.roof);
  for (let y = 0.5; y < 2; y += 0.25)
    box(1.5, 0.08, 0.04, -width / 2 + 2, y, -5.18, palettes.dark);
  for (let z of [-7, 7, depth / 2]) {
    for (let x of [-width / 2 + 0.8, width / 2 - 0.8]) {
      cylinder(0.18, 1.1, x, 0.55, z, palettes.dark);
      let crown = new THREE.Mesh(
        new THREE.IcosahedronGeometry(1.15, 0),
        palettes.green,
      );
      crown.position.set(x, 2.1, z);
      crown.castShadow = true;
      world.add(crown);
    }
  }
  for (let x of [-width / 2 + 1, width / 2 - 1]) {
    cylinder(0.07, 6, x, 3, 1, palettes.cream);
    box(1.1, 0.18, 0.45, x, 6, 1, palettes.light);
  }
  data.vehicles.forEach((v, i) => {
    let model = template.clone(true);
    model.traverse((o) => {
      if (o.isMesh) {
        o.geometry = o.geometry.clone();
        o.material = Array.isArray(o.material)
          ? o.material.map((m) => m.clone())
          : o.material.clone();
        o.castShadow = true;
        o.receiveShadow = true;
      }
    });
    let bounds = new THREE.Box3().setFromObject(model),
      size = bounds.getSize(new THREE.Vector3());
    model.scale.setScalar(4.6 / Math.max(size.x, size.z));
    bounds.setFromObject(model);
    let center = bounds.getCenter(new THREE.Vector3());
    let group = new THREE.Group();
    model.position.sub(new THREE.Vector3(center.x, bounds.min.y, center.z));
    group.add(model);
    group.userData.vehicle = v.id;
    world.add(group);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(2.35, 2.48, 48),
      mat("#b9ef71", {
        side: THREE.DoubleSide,
        emissive: "#77ad43",
        emissiveIntensity: 0.5,
      }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.04;
    group.add(ring);
    let tag = document.createElement("button");
    tag.className = "three-vehicle";
    tag.dataset.vehicle = v.id;
    let name = document.createElement("span");
    name.textContent = v.id;
    let bar = document.createElement("progress");
    bar.max = v.kwh;
    tag.append(name, bar);
    tag.onclick = () => {
      selected = v.id;
      updateDetail();
    };
    host.append(tag);
    labels.push(tag);
    vehicles.push({
      id: v.id,
      model: group,
      label: tag,
      bar,
      ring,
      park: new THREE.Vector3(((i % 3) - 1) * 7, 0, 7 + Math.floor(i / 3) * 7),
    });
  });
  selected = null;
  reset();
}
function updateDetail() {
  if (!latest) return;
  let { data, plan, slot, formatTime } = latest;
  const v = data.vehicles.find((v) => v.id === selected),
    s = vehicles.find((v) => v.id === selected);
  detail.replaceChildren();
  detail.classList.toggle("hidden", !v);
  vehicles.forEach((v) => (v.ring.visible = v.charging || v.id === selected));
  if (!v) return;
  let close = document.createElement("button");
  close.className = "depot-close";
  close.textContent = "×";
  close.setAttribute("aria-label", "Close vehicle details");
  close.onclick = () => {
    selected = null;
    updateDetail();
  };
  detail.append(close);
  let h = document.createElement("h3");
  h.textContent = v.id + " / " + s.state;
  detail.append(h);
  let a =
      plan.execution_evidence?.attempts?.[
        plan.execution_evidence.selected_attempt
      ],
    bit = plan.execution_evidence?.profile_menu?.find(
      (b) =>
        b.vehicle === v.id &&
        b.charger === s.p?.charger &&
        b.start_slot === s.p?.start_slot &&
        a?.bits[b.bit] > 0.5,
    );
  for (let [k, value] of [
    ["Delivered", s.energy.toFixed(1) + " / " + v.kwh.toFixed(1) + " kWh"],
    ["Power now", (s.p?.grid_kw_by_slot[slot] || 0).toFixed(1) + " kW"],
    ["Departure", formatTime(v.deadline)],
    ["Charger", s.p?.charger || "No accepted allocation"],
    ["QUBO choice", bit ? "x" + bit.bit + " = 1" : "Not used"],
  ]) {
    let row = document.createElement("div");
    row.className = "iso-field";
    let t = document.createElement("span");
    t.textContent = k;
    let valueEl = document.createElement("strong");
    valueEl.textContent = value;
    row.append(t, valueEl);
    detail.append(row);
  }
}
function update(data, plan, slot, formatTime, animateMotion = false) {
  latest = { data, plan, slot, formatTime };
  if (!template) return;
  let key = JSON.stringify([data.vehicles, data.chargers]);
  if (key !== signature) {
    build(data);
    signature = key;
  }
  cables.forEach((c) => {
    world.remove(c);
    c.geometry.dispose();
    c.material.dispose();
  });
  cables = [];
  vehicles.forEach((v) => {
    let spec = data.vehicles.find((s) => s.id === v.id),
      p = plan.schedule?.find((p) => p.vehicle === v.id);
    v.p = p;
    v.cable = null;
    v.energy = p
      ? ((p.grid_kw_by_slot.slice(0, slot).reduce((a, b) => a + b, 0) *
          data.slot_minutes) /
          60) *
        data.efficiency
      : 0;
    v.charging = !!p && slot >= p.start_slot && slot < p.end_slot;
    let ready = !!p && v.energy >= spec.kwh - 1e-6,
      offsite = slot < spec.arrival || slot >= spec.deadline;
    v.state = !p
      ? "No plan"
      : slot < spec.arrival
        ? "Not arrived"
        : slot >= spec.deadline
          ? "Dispatched"
          : v.charging
            ? "Charging"
            : ready
              ? "Ready"
              : "Waiting";
    let bay = chargers.find((c) => c.id === p?.charger);
    const target =
      v.charging && bay ? new THREE.Vector3(bay.x, 0, bay.z) : v.park.clone();
    const departure = slot >= spec.deadline,
      entered = !offsite && !v.wasOnsite;
    const canAnimate =
      animateMotion && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    spawnOpacity(v, 1);
    if (canAnimate && entered) {
      v.motion = {
        kind: "spawn",
        target: target.clone(),
        elapsed: 0,
        last: performance.now(),
        duration: 650,
      };
      v.model.position.copy(target);
      v.model.position.y += 0.7;
      v.model.rotation.y = 0;
      v.model.visible = true;
      v.label.style.visibility = "visible";
      spawnOpacity(v, 0);
    } else if (canAnimate && departure && v.wasOnsite) {
      v.motion = {
        kind: "depart",
        elapsed: 0,
        last: performance.now(),
        duration: 650,
      };
      v.model.visible = true;
    } else if (
      canAnimate &&
      ((departure && v.wasOnsite) ||
        (!offsite && (entered || v.model.position.distanceTo(target) > 0.01)))
    ) {
      const from = v.model.position.clone();
      const to = target;
      const points = [from];
      if (Math.abs(from.z - to.z) > 1) {
        points.push(
          new THREE.Vector3(from.x, 0, 2.3),
          new THREE.Vector3(to.x, 0, 2.3),
        );
      }
      points.push(to);
      const clean = points.filter(
        (p, i) => !i || p.distanceTo(points[i - 1]) > 0.01,
      );
      v.motion = {
        curve: new THREE.CatmullRomCurve3(clean, false, "centripetal"),
        elapsed: 0,
        last: performance.now(),
        duration: 1000,
        hide: departure,
      };
      v.model.position.copy(from);
      v.model.visible = true;
      v.label.style.visibility = "visible";
    } else {
      v.motion = null;
      v.model.position.copy(target);
      v.model.rotation.y = 0;
      v.model.visible = !offsite;
      v.label.style.visibility = offsite ? "hidden" : "visible";
    }
    v.wasOnsite = !offsite;
    v.label.dataset.state = v.state;
    v.label.dataset.energy = v.energy;
    v.label.setAttribute("aria-label", v.id + ": " + v.state);
    v.label.classList.toggle("charging", v.charging);
    v.label.classList.toggle("ready", ready);
    v.bar.value = v.energy;
    v.ring.visible = v.charging || v.id === selected;
    if (v.charging && bay) {
      let points = [
        new THREE.Vector3(bay.x + 1.8, 1.1, bay.z - 2.7),
        new THREE.Vector3(bay.x + 2.5, 0.35, bay.z - 1.5),
        new THREE.Vector3(bay.x + 1, 0.9, bay.z - 0.5),
      ];
      let mesh = new THREE.Mesh(
        new THREE.TubeGeometry(
          new THREE.CatmullRomCurve3(points),
          12,
          0.045,
          6,
          false,
        ),
        mat("#b9ef71", { emissive: "#5ca348", emissiveIntensity: 0.5 }),
      );
      mesh.visible = !v.motion;
      v.cable = mesh;
      world.add(mesh);
      cables.push(mesh);
    }
  });
  chargers.forEach((c) => {
    let active = vehicles.some((v) => v.charging && v.p.charger === c.id);
    c.lamp.material.emissiveIntensity = active ? 2 : 0;
  });
  let load = plan.aggregate_site_kw?.[slot];
  hud.textContent =
    load === undefined
      ? "End of planning horizon"
      : load.toFixed(1) + " / " + data.capacity_kw + " kW";
  updateDetail();
  loading.classList.add("hidden");
  host.dataset.ready = "true";
  host.dataset.vehicleCount = vehicles.length;
}
function createDeliveryVan() {
  const van = new THREE.Group();
  const body = mat("#f1f0e5"),
    windowMaterial = mat("#385463"),
    rubber = mat("#25302d"),
    trim = mat("#47866c");
  box(1.8, 1.8, 2.8, 0, 1.35, -0.65, body, van);
  box(1.8, 1.35, 1.4, 0, 1.12, 1.4, body, van);
  box(1.55, 0.65, 0.04, 0, 1.5, 2.12, windowMaterial, van);
  box(0.04, 0.55, 0.9, -0.91, 1.6, 1.35, windowMaterial, van);
  box(0.04, 0.55, 0.9, 0.91, 1.6, 1.35, windowMaterial, van);
  box(1.85, 0.2, 4.3, 0, 0.65, 0, trim, van);
  for (const x of [-0.85, 0.85])
    for (const z of [-1.35, 1.25]) {
      const wheel = new THREE.Mesh(
        new THREE.CylinderGeometry(0.4, 0.4, 0.25, 12),
        rubber,
      );
      wheel.rotation.z = Math.PI / 2;
      wheel.position.set(x, 0.4, z);
      van.add(wheel);
    }
  return van;
}
try {
  setup();
  template = createDeliveryVan();
  window.renderDepot3D = update;
  if (window.pendingDepot) update(...window.pendingDepot);
} catch (e) {
  host.textContent =
    "3D requires WebGL support. The schedule and charts remain available.";
  console.error(e);
}
window.depot3DDebug = () => ({
  camera: camera?.position.toArray(),
  target: controls?.target.toArray(),
  vehicles: vehicles.map((v) => ({
    id: v.id,
    energy: v.energy,
    state: v.state,
    visible: v.model.visible,
    moving: !!v.motion,
    position: v.model.position.toArray(),
  })),
  assetLoaded: !!template,
});

window.selectDepotVehicle = (id) => {
  selected = id;
  updateDetail();
};
