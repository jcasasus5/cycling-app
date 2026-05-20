const app = document.querySelector("#app");
const navButtons = document.querySelectorAll("nav button");

const state = {
  view: "routes",
  routes: [],
  activities: [],
  settings: null,
  selectedRoute: null,
  selectedActivity: null,
  draft: emptyDraft(),
  message: "",
  training: null,
  resumeActivity: null,
  routeModalOpen: false,
  activityModalOpen: false,
  routeDirty: false,
  busyText: "",
  savingActivity: false
};

navButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setView(button.dataset.view);
  });
});

await refresh();
render();

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Error inesperado." }));
    throw new Error(error.detail || "Error inesperado.");
  }
  if (response.status === 204) return null;
  return response.json();
}

async function refresh() {
  const [routes, activities, settings] = await Promise.all([
    api("/api/routes"),
    api("/api/activities"),
    api("/api/settings")
  ]);
  state.routes = routes;
  state.activities = activities;
  state.settings = settings;
}

function setView(view) {
  const previousView = state.view;
  if (view === "import") {
    state.draft = emptyDraft();
    state.routeModalOpen = false;
    state.activityModalOpen = false;
    state.routeDirty = false;
  }
  if (view !== "training" && previousView === "training") state.resumeActivity = null;
  state.view = view;
  state.message = "";
  navButtons.forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  render();
}

function render() {
  if (state.view !== "training" && state.training?.timer) {
    clearInterval(state.training.timer);
    state.training = null;
  }

  const message = state.message ? `<div class="notice">${escapeHtml(state.message)}</div>` : "";
  if (state.view === "routes") app.innerHTML = message + renderRoutes();
  if (state.view === "import") app.innerHTML = message + renderImport();
  if (state.view === "route-detail") app.innerHTML = message + renderRouteDetail();
  if (state.view === "training") app.innerHTML = message + renderTraining();
  if (state.view === "activities") app.innerHTML = message + renderActivities();
  if (state.view === "settings") app.innerHTML = message + renderSettings();

  if (state.routeModalOpen && state.selectedRoute) app.insertAdjacentHTML("beforeend", renderRouteModal());
  if (state.activityModalOpen && state.selectedActivity) app.insertAdjacentHTML("beforeend", renderActivityModal());
  if (state.busyText) app.insertAdjacentHTML("beforeend", renderBusyOverlay());

  bindEvents();
  drawCharts();
}

function renderRoutes() {
  const cards = state.routes.map((route) => `
    <article class="card" data-open-route="${route.id}">
      <h3>${escapeHtml(route.name)}</h3>
      <p>${route.distance_km.toFixed(2)} km · ${Math.round(route.elevation_gain_m)} m+ · ${route.avg_grade_percent.toFixed(1)}% media · ${route.max_grade_percent.toFixed(1)}% máx.</p>
    </article>
  `).join("");
  return `
    <section>
      <header class="page-header">
        <div><h2>Biblioteca de rutas</h2><p>${state.routes.length} rutas guardadas</p></div>
        <button data-view-action="import">Crear Ruta</button>
      </header>
      <div class="grid-list">${cards}</div>
      ${state.routes.length ? "" : `<div class="empty-state">Crea una ruta manualmente o analiza una imagen con OpenAI.</div>`}
    </section>
  `;
}

function renderImport() {
  return `
    <section>
      <header class="page-header">
        <div><h2>Crear Ruta</h2><p>Sube una imagen con OpenAI o introduce los datos manualmente.</p></div>
        <div class="actions">
          <label><input type="file" id="image-file" accept="image/png,image/jpeg,image/webp" /></label>
          <button data-action="analyze-image" ${state.busyText ? "disabled" : ""}>Analizar imagen</button>
          <button class="primary" data-action="save-draft" ${state.busyText ? "disabled" : ""}>Guardar ruta</button>
        </div>
      </header>
      ${renderRouteForm(state.draft)}
      <canvas class="chart" data-chart="draft"></canvas>
    </section>
  `;
}

function renderRouteModal() {
  const route = state.selectedRoute;
  return `
    <div class="modal-backdrop" data-action="close-route-modal">
      <section class="modal" role="dialog" aria-modal="true" aria-label="Detalle de ruta" data-modal-panel>
        <header class="page-header">
          <div>
            <h2>${escapeHtml(route.name)}</h2>
            <p>${route.distance_km.toFixed(2)} km · ${Math.round(route.elevation_gain_m)} m+ · ${route.avg_grade_percent.toFixed(1)}% media · ${route.max_grade_percent.toFixed(1)}% máx.</p>
          </div>
          <div class="actions">
            <button data-action="duplicate-route">Duplicar</button>
            <button data-action="delete-route">Eliminar</button>
            <button class="${state.routeDirty ? "" : "hidden"}" data-action="update-route">Guardar cambios</button>
            <button class="primary" data-action="start-training">Entrenar</button>
            <button data-action="close-route-modal">Cerrar</button>
          </div>
        </header>
        ${renderRouteForm(state.draft)}
        <canvas class="chart" data-chart="selected"></canvas>
      </section>
    </div>
  `;
}

function renderBusyOverlay() {
  return `
    <div class="busy-overlay" role="status" aria-live="polite">
      <div class="busy-dialog">
        <div class="spinner"></div>
        <strong>${escapeHtml(state.busyText)}</strong>
        <span>No cierres esta pantalla hasta que termine.</span>
      </div>
    </div>
  `;
}

function renderRouteDetail() {
  const route = state.selectedRoute;
  if (!route) return `<div class="empty-state">Selecciona una ruta.</div>`;
  return `
    <section>
      <header class="page-header">
        <div><h2>${escapeHtml(route.name)}</h2><p>${route.distance_km.toFixed(2)} km · ${Math.round(route.elevation_gain_m)} m+</p></div>
        <div class="actions">
          <button data-action="duplicate-route">Duplicar</button>
          <button data-action="delete-route">Eliminar</button>
          <button data-action="update-route">Guardar cambios</button>
          <button class="primary" data-action="start-training">Entrenar</button>
        </div>
      </header>
      ${renderRouteForm(routeToDraft(route))}
      <canvas class="chart" data-chart="selected"></canvas>
    </section>
  `;
}

function renderTraining() {
  const route = state.selectedRoute;
  if (!route) return `<div class="empty-state">Selecciona una ruta.</div>`;
  if (!state.training) resetTraining();
  const t = state.training;
  const segment = getSegmentAtKm(route.segments, t.km);
  const realGrade = segment?.grade_percent ?? 0;
  const trainerGrade = applyTrainerGradeLimit(realGrade);
  const altitude = interpolateAltitude(segment, t.km, route.start_altitude_m);
  const paused = t.speed <= 0.2;
  return `
    <section>
      <header class="page-header">
        <div><h2>${escapeHtml(route.name)}</h2><p>${t.activityId ? "Continuando actividad parcial" : paused ? "Pausada" : t.running ? "En marcha" : "Preparada"} · pendiente real ${realGrade.toFixed(1)}% · rodillo ${trainerGrade.toFixed(1)}%</p></div>
        <div class="actions">
          <button data-action="toggle-training">${t.running ? "Pausar manual" : "Iniciar"}</button>
          <button data-action="save-partial">Guardar parcial</button>
          <button class="primary" data-action="save-completed">Terminar</button>
        </div>
      </header>
      <canvas class="chart" data-chart="training"></canvas>
      <div class="metrics">
        ${metric("Kilómetro", `${t.km.toFixed(2)} / ${route.distance_km.toFixed(2)}`)}
        ${metric("Tiempo activo", formatSeconds(t.activeSeconds))}
        ${metric("Tiempo total", formatSeconds(t.elapsed))}
        ${metric("Velocidad", `${t.speed.toFixed(1)} km/h`)}
        ${metric("Cadencia", `${paused ? 0 : Math.max(50, Math.round(92 - Math.max(0, trainerGrade) * 2))} rpm`)}
        ${metric("Potencia", `${paused ? 0 : Math.round(150 + Math.max(0, trainerGrade) * 18 + t.speed * 2)} W`)}
        ${metric("Altitud virtual", `${Math.round(altitude)} m`)}
        ${metric("Desnivel", `${Math.max(0, Math.round(altitude - route.start_altitude_m))} m`)}
      </div>
      <div class="panel">
        <label>Velocidad simulada
          <input type="range" min="0" max="45" value="${t.speed}" data-action="speed" />
          <span>${t.speed.toFixed(1)} km/h</span>
        </label>
      </div>
    </section>
  `;
}

function renderActivities() {
  const cards = state.activities.map((activity) => `
    <article class="card activity-card" data-open-activity="${activity.id}">
      <h3>${escapeHtml(activity.route_name)}</h3>
      <p>${new Date(activity.started_at).toLocaleDateString("es-ES")} · ${activity.distance_km.toFixed(2)} km · ${formatSeconds(activity.active_seconds)} · ${activity.avg_power_w} W media · ${activity.status === "completed" ? "Completada" : "Parcial"}</p>
    </article>
  `).join("");
  return `
    <section>
      <header class="page-header"><div><h2>Actividades realizadas</h2><p>${state.activities.length} entrenamientos guardados</p></div></header>
      <div class="grid-list">${cards}</div>
    </section>
  `;
}

function renderActivityModal() {
  const detail = state.selectedActivity;
  const activity = detail.activity;
  return `
    <div class="modal-backdrop" data-action="close-activity-modal">
      <section class="modal" role="dialog" aria-modal="true" aria-label="Detalle de actividad" data-modal-panel>
      <header class="page-header">
        <div><h2>${escapeHtml(activity.route_name)}</h2><p>${activity.status === "completed" ? "Completada" : "Parcial"} · ${activity.distance_km.toFixed(2)} km · ${formatSeconds(activity.active_seconds)}</p></div>
        <div class="actions">
          ${activity.status === "partial" ? `<button class="primary" data-action="resume-activity">Continuar</button>` : ""}
          <button class="danger" data-action="delete-current-activity">Eliminar</button>
          <button data-action="close-activity-modal">Cerrar</button>
        </div>
      </header>
      <canvas class="chart" data-chart="activity"></canvas>
      <div class="metrics">
        ${metric("Potencia media", `${activity.avg_power_w} W`)}
        ${metric("Potencia máxima", `${activity.max_power_w} W`)}
        ${metric("Cadencia media", `${activity.avg_cadence_rpm} rpm`)}
        ${metric("Velocidad media", `${activity.avg_speed_kph.toFixed(1)} km/h`)}
        ${metric("Tiempo total", formatSeconds(activity.total_seconds))}
        ${metric("Desnivel virtual", `${Math.round(activity.completed_elevation_m)} m`)}
      </div>
      </section>
    </div>
  `;
}

function renderSettings() {
  const s = state.settings;
  return `
    <section>
      <header class="page-header">
        <div><h2>Ajustes</h2><p>Configuración local de OpenAI y simulación.</p></div>
        <button class="primary" data-action="save-settings">Guardar ajustes</button>
      </header>
      <div class="panel form-grid">
        <label class="wide">API key de OpenAI<input type="password" name="openai_api_key" value="${escapeAttr(s.openai_api_key)}" /></label>
        <label>Pendiente máxima rodillo<input type="number" step="0.1" name="max_trainer_grade_percent" value="${s.max_trainer_grade_percent}" /></label>
        <label>Peso ciclista<input type="number" step="0.1" name="rider_weight_kg" value="${s.rider_weight_kg}" /></label>
        <label>Peso bici<input type="number" step="0.1" name="bike_weight_kg" value="${s.bike_weight_kg}" /></label>
        <label class="check"><input type="checkbox" name="enable_negative_grades" ${s.enable_negative_grades ? "checked" : ""} /> Pendientes negativas</label>
        <label class="check"><input type="checkbox" name="smooth_grade_changes" ${s.smooth_grade_changes ? "checked" : ""} /> Suavizar cambios</label>
      </div>
    </section>
  `;
}

function renderRouteForm(draft) {
  const calculated = calculateRouteFromSegments(draft);
  const rows = draft.segments.map((segment, index) => `
    <div class="segment-row" data-segment="${index}">
      ${numberInput("Del km", "start_km", segment.start_km)}
      ${numberInput("Al km", "end_km", segment.end_km)}
      ${numberInput("Altitud inicial (m)", "start_altitude_m", segment.start_altitude_m)}
      ${numberInput("Altitud final (m)", "end_altitude_m", segment.end_altitude_m)}
      <div class="readonly-field"><span>Pendiente</span><strong data-segment-grade="${index}">${calculateSegmentGrade(segment).toFixed(1)}%</strong></div>
      <button class="danger small" data-delete-segment="${index}" type="button">Eliminar</button>
    </div>
  `).join("");
  return `
    <div class="panel" id="route-form">
      <div class="form-grid">
        <label class="wide">Nombre<input name="name" value="${escapeAttr(draft.name)}" /></label>
        ${readonlyNumber("Distancia total", `${calculated.distance_km.toFixed(2)} km`)}
        ${readonlyNumber("Desnivel positivo", `${Math.round(calculated.elevation_gain_m)} m`)}
        ${readonlyNumber("Altitud inicial", `${Math.round(calculated.start_altitude_m)} m`)}
        ${readonlyNumber("Altitud final", `${Math.round(calculated.end_altitude_m)} m`)}
        ${readonlyNumber("Pendiente media", `${calculated.avg_grade_percent.toFixed(1)}%`)}
        ${readonlyNumber("Pendiente máxima", `${calculated.max_grade_percent.toFixed(1)}%`)}
      </div>
      <h3>Segmentos</h3>
      <div class="segments-table">${rows}</div>
      <button data-action="add-segment">Añadir segmento</button>
    </div>
  `;
}

function bindEvents() {
  document.querySelectorAll("[data-view-action]").forEach((el) => el.addEventListener("click", () => setView(el.dataset.viewAction)));
  document.querySelectorAll("[data-open-route]").forEach((el) => el.addEventListener("click", async () => {
    state.selectedRoute = await api(`/api/routes/${el.dataset.openRoute}`);
    state.draft = routeToDraft(state.selectedRoute);
    state.routeDirty = false;
    state.routeModalOpen = true;
    render();
  }));
  document.querySelectorAll("[data-open-activity]").forEach((el) => el.addEventListener("click", async () => {
    state.selectedActivity = await api(`/api/activities/${el.dataset.openActivity}`);
    state.selectedRoute = await api(`/api/routes/${state.selectedActivity.activity.route_id}`);
    state.activityModalOpen = true;
    render();
  }));
  document.querySelectorAll("#route-form input").forEach((input) => input.addEventListener("input", syncDraftFromForm));
  document.querySelectorAll("[data-delete-segment]").forEach((el) => el.addEventListener("click", () => {
    deleteSegment(Number(el.dataset.deleteSegment));
  }));
  document.querySelector("[data-action='add-segment']")?.addEventListener("click", () => {
    const draft = currentDraft();
    const last = draft.segments.at(-1);
    draft.segments.push({
      start_km: last?.end_km ?? 0,
      end_km: last?.end_km ?? 0,
      grade_percent: 0,
      start_altitude_m: last?.end_altitude_m ?? 0,
      end_altitude_m: last?.end_altitude_m ?? 0
    });
    if (state.routeModalOpen) state.routeDirty = true;
    render();
  });
  document.querySelector("[data-action='save-draft']")?.addEventListener("click", saveDraft);
  document.querySelector("[data-action='analyze-image']")?.addEventListener("click", analyzeImage);
  document.querySelector("[data-action='update-route']")?.addEventListener("click", updateRoute);
  document.querySelector("[data-action='duplicate-route']")?.addEventListener("click", duplicateRoute);
  document.querySelector("[data-action='delete-route']")?.addEventListener("click", deleteRoute);
  document.querySelector("[data-action='start-training']")?.addEventListener("click", () => {
    state.routeModalOpen = false;
    state.activityModalOpen = false;
    state.routeDirty = false;
    setView("training");
  });
  document.querySelectorAll("[data-action='close-route-modal']").forEach((el) => el.addEventListener("click", (event) => {
    if (event.currentTarget.classList.contains("modal-backdrop") && event.target.closest("[data-modal-panel]")) return;
    state.routeModalOpen = false;
    state.routeDirty = false;
    render();
  }));
  document.querySelectorAll("[data-action='close-activity-modal']").forEach((el) => el.addEventListener("click", (event) => {
    if (event.currentTarget.classList.contains("modal-backdrop") && event.target.closest("[data-modal-panel]")) return;
    state.activityModalOpen = false;
    render();
  }));
  document.querySelector("[data-action='toggle-training']")?.addEventListener("click", toggleTraining);
  document.querySelector("[data-action='save-partial']")?.addEventListener("click", () => saveActivity("partial"));
  document.querySelector("[data-action='save-completed']")?.addEventListener("click", () => saveActivity("completed"));
  document.querySelector("[data-action='resume-activity']")?.addEventListener("click", resumeActivity);
  document.querySelector("[data-action='delete-current-activity']")?.addEventListener("click", async () => {
    if (state.selectedActivity) await deleteActivity(state.selectedActivity.activity.id);
  });
  document.querySelector("[data-action='speed']")?.addEventListener("input", (event) => {
    state.training.speed = Number(event.target.value);
    render();
  });
  document.querySelector("[data-action='save-settings']")?.addEventListener("click", saveSettings);
}

function syncDraftFromForm() {
  const form = document.querySelector("#route-form");
  if (!form) return;
  const target = currentDraft();
  const nameInput = form.querySelector(`[name="name"]`);
  if (nameInput) target.name = nameInput.value;
  form.querySelectorAll("[data-segment]").forEach((row) => {
    const index = Number(row.dataset.segment);
    ["start_km", "end_km", "start_altitude_m", "end_altitude_m"].forEach((name) => {
      target.segments[index][name] = Number(row.querySelector(`[name="${name}"]`).value);
    });
    target.segments[index].grade_percent = calculateSegmentGrade(target.segments[index]);
  });
  applyRouteCalculations(target);
  if (state.routeModalOpen) {
    state.routeDirty = true;
    document.querySelector("[data-action='update-route']")?.classList.remove("hidden");
  }
  updateCalculatedFields(target);
  drawCharts();
}

function currentDraft() {
  return state.draft;
}

function deleteSegment(index) {
  const draft = currentDraft();
  if (draft.segments.length <= 1) {
    state.message = "La ruta necesita al menos un segmento.";
    render();
    return;
  }
  draft.segments.splice(index, 1);
  applyRouteCalculations(draft);
  if (state.routeModalOpen) state.routeDirty = true;
  render();
}

function calculateSegmentGrade(segment) {
  const distanceKm = segment.end_km - segment.start_km;
  if (distanceKm <= 0) return 0;
  return ((segment.end_altitude_m - segment.start_altitude_m) / (distanceKm * 1000)) * 100;
}

function calculateRouteFromSegments(draft) {
  const segments = draft.segments.map((segment) => ({
    ...segment,
    grade_percent: calculateSegmentGrade(segment)
  }));
  const ordered = [...segments].sort((a, b) => a.start_km - b.start_km);
  const valid = ordered.filter((segment) => segment.end_km > segment.start_km);
  const distanceKm = valid.length ? Math.max(...valid.map((segment) => segment.end_km)) : 0;
  const elevationGainM = valid.reduce((sum, segment) => sum + Math.max(0, segment.end_altitude_m - segment.start_altitude_m), 0);
  const startAltitudeM = ordered[0]?.start_altitude_m ?? 0;
  const endAltitudeM = ordered.length ? ordered[ordered.length - 1].end_altitude_m : 0;
  const avgGradePercent = distanceKm > 0 ? (elevationGainM / (distanceKm * 1000)) * 100 : 0;
  const maxGradePercent = valid.length ? Math.max(...valid.map((segment) => segment.grade_percent), 0) : 0;
  return {
    ...draft,
    distance_km: round(distanceKm, 2),
    elevation_gain_m: Math.round(elevationGainM),
    start_altitude_m: Math.round(startAltitudeM),
    end_altitude_m: Math.round(endAltitudeM),
    avg_grade_percent: round(avgGradePercent, 2),
    max_grade_percent: round(maxGradePercent, 1),
    segments
  };
}

function applyRouteCalculations(draft) {
  Object.assign(draft, calculateRouteFromSegments(draft));
}

function updateCalculatedFields(draft) {
  document.querySelector("[data-summary='distance_km']")?.replaceChildren(`${draft.distance_km.toFixed(2)} km`);
  document.querySelector("[data-summary='elevation_gain_m']")?.replaceChildren(`${Math.round(draft.elevation_gain_m)} m`);
  document.querySelector("[data-summary='start_altitude_m']")?.replaceChildren(`${Math.round(draft.start_altitude_m)} m`);
  document.querySelector("[data-summary='end_altitude_m']")?.replaceChildren(`${Math.round(draft.end_altitude_m)} m`);
  document.querySelector("[data-summary='avg_grade_percent']")?.replaceChildren(`${draft.avg_grade_percent.toFixed(1)}%`);
  document.querySelector("[data-summary='max_grade_percent']")?.replaceChildren(`${draft.max_grade_percent.toFixed(1)}%`);
  draft.segments.forEach((segment, index) => {
    document.querySelector(`[data-segment-grade="${index}"]`)?.replaceChildren(`${segment.grade_percent.toFixed(1)}%`);
  });
}

function validateRouteDraft(draft) {
  applyRouteCalculations(draft);
  if (!draft.name.trim()) {
    state.message = "Pon un nombre a la ruta antes de guardar.";
    render();
    return false;
  }
  const invalidSegment = draft.segments.find((segment) => segment.end_km <= segment.start_km);
  if (invalidSegment || draft.distance_km <= 0) {
    state.message = "Cada segmento debe tener un km final mayor que el km inicial.";
    render();
    return false;
  }
  return true;
}

async function saveDraft() {
  syncDraftFromForm();
  if (!validateRouteDraft(state.draft)) return;
  state.selectedRoute = await api("/api/routes", { method: "POST", body: JSON.stringify(state.draft) });
  state.draft = routeToDraft(state.selectedRoute);
  state.routeDirty = false;
  state.routeModalOpen = true;
  await refresh();
  setView("routes");
}

async function updateRoute() {
  syncDraftFromForm();
  if (!validateRouteDraft(state.draft)) return;
  state.selectedRoute = await api(`/api/routes/${state.selectedRoute.id}`, { method: "PUT", body: JSON.stringify(state.draft) });
  state.draft = routeToDraft(state.selectedRoute);
  state.routeDirty = false;
  await refresh();
  render();
}

async function duplicateRoute() {
  state.selectedRoute = await api(`/api/routes/${state.selectedRoute.id}/duplicate`, { method: "POST" });
  state.draft = routeToDraft(state.selectedRoute);
  state.routeDirty = false;
  state.routeModalOpen = true;
  await refresh();
  setView("routes");
}

async function deleteRoute() {
  await api(`/api/routes/${state.selectedRoute.id}`, { method: "DELETE" });
  state.selectedRoute = null;
  state.routeModalOpen = false;
  state.routeDirty = false;
  await refresh();
  setView("routes");
}

async function deleteActivity(activityId) {
  await api(`/api/activities/${activityId}`, { method: "DELETE" });
  if (state.selectedActivity?.activity.id === activityId) {
    state.selectedActivity = null;
    state.selectedRoute = null;
    state.activityModalOpen = false;
  }
  await refresh();
  setView("activities");
}

async function analyzeImage() {
  const file = document.querySelector("#image-file")?.files?.[0];
  if (!file) {
    state.message = "Selecciona primero una imagen.";
    render();
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  state.busyText = "Analizando imagen con OpenAI...";
  render();
  try {
    const result = await api("/api/import/image", { method: "POST", body: formData });
    state.draft = result.draft;
    state.message = "Imagen analizada. Revisa los datos antes de guardar.";
  } catch (error) {
    state.message = error.message;
  } finally {
    state.busyText = "";
  }
  render();
}

function resetTraining() {
  if (state.resumeActivity) {
    const activity = state.resumeActivity.activity;
    state.training = {
      running: false,
      timer: null,
      elapsed: activity.total_seconds,
      activeSeconds: activity.active_seconds,
      km: activity.distance_km,
      speed: 18,
      samples: state.resumeActivity.samples.map(({ id, activity_id, ...sample }) => sample),
      activityId: activity.id,
      startedAt: activity.started_at
    };
    return;
  }
  state.training = { running: false, timer: null, elapsed: 0, activeSeconds: 0, km: 0, speed: 18, samples: [], activityId: null, startedAt: null };
}

function resumeActivity() {
  if (!state.selectedActivity || state.selectedActivity.activity.status !== "partial") return;
  state.resumeActivity = state.selectedActivity;
  state.activityModalOpen = false;
  state.training = null;
  setView("training");
}

function toggleTraining() {
  if (!state.training.running) {
    state.training.running = true;
    state.training.timer = setInterval(tickTraining, 1000);
  } else {
    state.training.running = false;
    clearInterval(state.training.timer);
  }
  render();
}

function tickTraining() {
  const route = state.selectedRoute;
  const t = state.training;
  const paused = t.speed <= 0.2;
  const segment = getSegmentAtKm(route.segments, t.km);
  const grade = applyTrainerGradeLimit(segment?.grade_percent ?? 0);
  const altitude = interpolateAltitude(segment, t.km, route.start_altitude_m);
  const sample = {
    timestamp_ms: Date.now(),
    elapsed_seconds: t.elapsed + 1,
    km: t.km,
    speed_kph: paused ? 0 : t.speed,
    cadence_rpm: paused ? 0 : Math.max(50, Math.round(92 - Math.max(0, grade) * 2)),
    power_w: paused ? 0 : Math.round(150 + Math.max(0, grade) * 18 + t.speed * 2),
    grade_percent: grade,
    altitude_m: altitude,
    paused
  };
  t.samples.push(sample);
  t.elapsed += 1;
  if (!paused) {
    t.activeSeconds += 1;
    t.km = Math.min(route.distance_km, t.km + t.speed / 3600);
  }
  if (t.km >= route.distance_km) {
    saveActivity("completed");
  } else {
    render();
  }
}

async function saveActivity(status) {
  const route = state.selectedRoute;
  const t = state.training;
  if (!t || state.savingActivity) return;
  if (t.timer) clearInterval(t.timer);
  t.running = false;
  const activeSamples = t.samples.filter((sample) => !sample.paused);
  const averages = calculateAverages(activeSamples);
  const lastAltitude = t.samples.at(-1)?.altitude_m ?? route.start_altitude_m;
  const payload = {
    route_id: route.id,
    started_at: t.startedAt ?? new Date(Date.now() - t.elapsed * 1000).toISOString(),
    ended_at: new Date().toISOString(),
    status,
    active_seconds: t.activeSeconds,
    total_seconds: t.elapsed,
    distance_km: Number(t.km.toFixed(2)),
    completed_elevation_m: Math.max(0, lastAltitude - route.start_altitude_m),
    samples: t.samples,
    ...averages
  };
  const path = t.activityId ? `/api/activities/${t.activityId}` : "/api/activities";
  state.savingActivity = true;
  state.busyText = status === "completed" ? "Guardando actividad completada..." : "Guardando actividad parcial...";
  render();
  try {
    await api(path, { method: t.activityId ? "PUT" : "POST", body: JSON.stringify(payload) });
    state.training = null;
    state.resumeActivity = null;
    state.selectedActivity = null;
    state.savingActivity = false;
    state.busyText = "";
    await refresh();
    setView("activities");
  } catch (error) {
    state.savingActivity = false;
    state.busyText = "";
    state.message = error.message;
    render();
  }
}

async function saveSettings() {
  const root = document.querySelector(".panel");
  state.settings = {
    openai_api_key: root.querySelector("[name='openai_api_key']").value,
    max_trainer_grade_percent: Number(root.querySelector("[name='max_trainer_grade_percent']").value),
    enable_negative_grades: root.querySelector("[name='enable_negative_grades']").checked,
    smooth_grade_changes: root.querySelector("[name='smooth_grade_changes']").checked,
    rider_weight_kg: Number(root.querySelector("[name='rider_weight_kg']").value),
    bike_weight_kg: Number(root.querySelector("[name='bike_weight_kg']").value)
  };
  state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(state.settings) });
  state.message = "Ajustes guardados.";
  render();
}

function drawCharts() {
  document.querySelectorAll("canvas[data-chart]").forEach((canvas) => {
    const kind = canvas.dataset.chart;
    let route = null;
    let currentKm = null;
    let completedKm = null;
    if (kind === "draft") route = draftToRoute(state.draft);
    if (kind === "selected") route = draftToRoute(state.draft);
    if (kind === "training") {
      route = state.selectedRoute;
      currentKm = state.training?.km ?? 0;
    }
    if (kind === "activity") {
      route = state.selectedRoute;
      completedKm = state.selectedActivity?.activity.distance_km;
    }
    if (route) drawProfile(canvas, route.segments, currentKm, completedKm);
  });
}

function drawProfile(canvas, segments, currentKm = null, completedKm = null) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);
  const padding = { left: 58, right: 26, top: 48, bottom: 46 };
  const points = segments.flatMap((s) => [
    { km: s.start_km, altitude: s.start_altitude_m },
    { km: s.end_km, altitude: s.end_altitude_m }
  ]);
  const maxKm = Math.max(...points.map((p) => p.km), 1);
  const minAlt = Math.min(...points.map((p) => p.altitude));
  const maxAlt = Math.max(...points.map((p) => p.altitude));
  const altitudeSpan = Math.max(1, maxAlt - minAlt);
  const x = (km) => padding.left + (km / maxKm) * (width - padding.left - padding.right);
  const y = (alt) => height - padding.bottom - ((alt - minAlt) / altitudeSpan) * (height - padding.top - padding.bottom);

  ctx.strokeStyle = "#d9e2e1";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const gy = padding.top + i * ((height - padding.top - padding.bottom) / 5);
    const altitudeLabel = maxAlt - (i * altitudeSpan) / 5;
    ctx.beginPath();
    ctx.moveTo(padding.left, gy);
    ctx.lineTo(width - padding.right, gy);
    ctx.stroke();
    ctx.fillStyle = "#60726c";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.fillText(`${Math.round(altitudeLabel)} m`, padding.left - 8, gy);
  }

  for (let km = 0; km <= Math.ceil(maxKm); km += chooseKmTickStep(maxKm)) {
    const gx = x(Math.min(km, maxKm));
    ctx.beginPath();
    ctx.moveTo(gx, padding.top);
    ctx.lineTo(gx, height - padding.bottom);
    ctx.strokeStyle = "#edf2f1";
    ctx.stroke();
    ctx.fillStyle = "#60726c";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText(`${km}`, gx, height - padding.bottom + 10);
  }

  ctx.beginPath();
  points.forEach((point, index) => {
    const px = x(point.km);
    const py = y(point.altitude);
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.lineTo(x(maxKm), height - padding.bottom);
  ctx.lineTo(x(0), height - padding.bottom);
  ctx.closePath();
  ctx.fillStyle = "rgba(47, 133, 90, 0.16)";
  ctx.fill();

  ctx.beginPath();
  points.forEach((point, index) => {
    const px = x(point.km);
    const py = y(point.altitude);
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.strokeStyle = "#1f6f4a";
  ctx.lineWidth = 3;
  ctx.stroke();

  segments.forEach((segment) => {
    if (segment.end_km <= segment.start_km) return;
    const startX = x(segment.start_km);
    const endX = x(segment.end_km);
    const labelX = startX + (endX - startX) / 2;
    const grade = Number(segment.grade_percent ?? calculateSegmentGrade(segment));
    ctx.fillStyle = grade >= 8 ? "#8a1f1f" : grade >= 5 ? "#9a4d0f" : "#146c5f";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(`${grade.toFixed(1)}%`, labelX, 18);
    ctx.beginPath();
    ctx.moveTo(startX, padding.top - 8);
    ctx.lineTo(endX, padding.top - 8);
    ctx.strokeStyle = "rgba(20, 108, 95, 0.28)";
    ctx.lineWidth = 2;
    ctx.stroke();
  });

  if (completedKm !== null) drawMarker(ctx, x(completedKm), padding.top, height - padding.bottom, "#0f766e");
  if (currentKm !== null) drawMarker(ctx, x(currentKm), padding.top, height - padding.bottom, "#c2410c");

  ctx.fillStyle = "#60726c";
  ctx.font = "12px sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillText("km", width - padding.right - 14, height - 12);
  ctx.fillText("Altitud", 12, 16);
}

function chooseKmTickStep(maxKm) {
  if (maxKm <= 12) return 1;
  if (maxKm <= 30) return 2;
  if (maxKm <= 60) return 5;
  return 10;
}

function drawMarker(ctx, x, top, bottom, color) {
  ctx.beginPath();
  ctx.moveTo(x, top);
  ctx.lineTo(x, bottom);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();
}

function getSegmentAtKm(segments, km) {
  return segments.find((segment) => km >= segment.start_km && km < segment.end_km) ?? segments.find((segment) => km <= segment.end_km) ?? segments.at(-1);
}

function applyTrainerGradeLimit(grade) {
  const s = state.settings;
  const value = s.enable_negative_grades ? grade : Math.max(0, grade);
  return Math.min(s.max_trainer_grade_percent, value);
}

function interpolateAltitude(segment, km, fallback) {
  if (!segment) return fallback;
  const span = Math.max(0.001, segment.end_km - segment.start_km);
  const ratio = Math.min(1, Math.max(0, (km - segment.start_km) / span));
  return segment.start_altitude_m + (segment.end_altitude_m - segment.start_altitude_m) * ratio;
}

function calculateAverages(samples) {
  if (!samples.length) return { avg_power_w: 0, max_power_w: 0, avg_cadence_rpm: 0, avg_speed_kph: 0 };
  return {
    avg_power_w: Math.round(samples.reduce((sum, sample) => sum + sample.power_w, 0) / samples.length),
    max_power_w: Math.max(...samples.map((sample) => sample.power_w)),
    avg_cadence_rpm: Math.round(samples.reduce((sum, sample) => sum + sample.cadence_rpm, 0) / samples.length),
    avg_speed_kph: Number((samples.reduce((sum, sample) => sum + sample.speed_kph, 0) / samples.length).toFixed(1))
  };
}

function draftToRoute(draft) {
  const calculated = calculateRouteFromSegments(draft);
  return { ...calculated, id: 0, created_at: new Date().toISOString(), segments: calculated.segments.map((s, i) => ({ ...s, id: i + 1, route_id: 0 })) };
}

function routeToDraft(route) {
  return calculateRouteFromSegments({
    name: route.name,
    distance_km: route.distance_km,
    elevation_gain_m: route.elevation_gain_m,
    start_altitude_m: route.start_altitude_m,
    end_altitude_m: route.end_altitude_m,
    avg_grade_percent: route.avg_grade_percent,
    max_grade_percent: route.max_grade_percent,
    original_image_path: route.original_image_path,
    segments: route.segments.map(({ start_km, end_km, grade_percent, start_altitude_m, end_altitude_m }) => ({
      start_km,
      end_km,
      grade_percent,
      start_altitude_m,
      end_altitude_m
    }))
  });
}

function emptyDraft() {
  return {
    name: "",
    distance_km: 0,
    elevation_gain_m: 0,
    start_altitude_m: 0,
    end_altitude_m: 0,
    avg_grade_percent: 0,
    max_grade_percent: 0,
    original_image_path: null,
    segments: [
      { start_km: 0, end_km: 0, grade_percent: 0, start_altitude_m: 0, end_altitude_m: 0 }
    ]
  };
}

function metric(label, value) {
  return `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`;
}

function numberInput(label, name, value) {
  return `<label>${label}<input type="number" step="0.1" name="${name}" value="${value}" /></label>`;
}

function readonlyNumber(label, value) {
  const key = {
    "Distancia total": "distance_km",
    "Desnivel positivo": "elevation_gain_m",
    "Altitud inicial": "start_altitude_m",
    "Altitud final": "end_altitude_m",
    "Pendiente media": "avg_grade_percent",
    "Pendiente máxima": "max_grade_percent"
  }[label];
  return `<div class="readonly-field"><span>${label}</span><strong ${key ? `data-summary="${key}"` : ""}>${value}</strong></div>`;
}

function round(value, decimals) {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

function formatSeconds(total) {
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}` : `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#039;" })[char]);
}

function escapeAttr(value) {
  return escapeHtml(value ?? "");
}
