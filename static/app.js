import { FtmsTrainer } from "./ftms-trainer.js";

const app = document.querySelector("#app");
const navButtons = document.querySelectorAll("[data-view]");
const MESSAGE_DURATION_MS = 4600;
const SESSION_STORAGE_KEY = "cycling-app-supabase-session";
let messageTimer = null;
let trainerClient = null;
let gradeCommandPending = false;

const state = {
  config: null,
  session: null,
  authMode: "login",
  authMessage: "",
  passwordRecovery: false,
  view: "routes",
  routes: [],
  activities: [],
  settings: null,
  selectedRoute: null,
  selectedActivity: null,
  draft: emptyDraft(),
  message: "",
  training: null,
  trainer: {
    connected: false,
    connecting: false,
    status: "Rodillo no conectado",
    metrics: emptyTrainerMetrics(),
    lastDataAt: null,
    features: null
  },
  calibration: emptyCalibrationState(),
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

await initialize();
render();

async function initialize() {
  state.config = await fetch("/api/config").then((response) => response.json());
  if (state.config.config_error) {
    state.authMessage = "El despliegue no tiene configuradas las variables de Supabase.";
    return;
  }
  if (!state.config.auth_enabled) {
    await refresh();
    return;
  }
  state.session = loadSession();
  if (state.session && tokenExpiresSoon(state.session)) {
    await refreshSession();
  }
  if (state.session) {
    try {
      await refresh();
    } catch (error) {
      clearSession();
    }
  }
}

async function api(path, options = {}) {
  const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  if (state.session?.access_token) headers.Authorization = `Bearer ${state.session.access_token}`;
  const response = await fetch(path, {
    headers,
    ...options
  });
  if (response.status === 401 && state.session?.refresh_token && await refreshSession()) {
    return api(path, options);
  }
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
  clearMessage();
  navButtons.forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  render();
}

function render() {
  if (state.config?.config_error) {
    document.body.classList.add("auth-screen");
    app.innerHTML = `
      <section class="auth-card">
        <span class="eyebrow">Configuración incompleta</span>
        <h2>Aplicación no disponible</h2>
        <p>${escapeHtml(state.authMessage)}</p>
      </section>
    `;
    return;
  }
  document.body.classList.toggle("auth-screen", Boolean(state.config?.auth_enabled && !state.session));
  const account = document.querySelector("[data-user-account]");
  if (account) {
    account.hidden = !state.session;
    account.querySelector("[data-user-email]").textContent = state.session?.user?.email || "";
  }
  if (state.config?.auth_enabled && !state.session) {
    app.innerHTML = renderAuth();
    bindAuthEvents();
    return;
  }

  if (state.view !== "training" && state.training?.timer) {
    clearInterval(state.training.timer);
    state.training = null;
  }

  if (state.view === "routes") app.innerHTML = renderRoutes();
  if (state.view === "import") app.innerHTML = renderImport();
  if (state.view === "route-detail") app.innerHTML = renderRouteDetail();
  if (state.view === "training") app.innerHTML = renderTraining();
  if (state.view === "activities") app.innerHTML = renderActivities();
  if (state.view === "settings") app.innerHTML = renderSettings();

  if (state.routeModalOpen && state.selectedRoute) app.insertAdjacentHTML("beforeend", renderRouteModal());
  if (state.activityModalOpen && state.selectedActivity) app.insertAdjacentHTML("beforeend", renderActivityModal());
  if (state.calibration.open) app.insertAdjacentHTML("beforeend", renderCalibrationModal());
  if (state.busyText) app.insertAdjacentHTML("beforeend", renderBusyOverlay());
  if (state.message) app.insertAdjacentHTML("beforeend", renderToast());

  bindEvents();
  drawCharts();
}

function renderAuth() {
  const signingUp = state.authMode === "signup";
  const recovering = state.authMode === "recovery";
  return `
    <section class="auth-card">
      <div>
        <span class="eyebrow">Tacx Flux Climber</span>
        <h2>${recovering ? "Recuperar contraseña" : signingUp ? "Crear cuenta" : "Iniciar sesión"}</h2>
        <p>${recovering ? "Te enviaremos un enlace para elegir una nueva contraseña." : signingUp ? "Tus rutas, actividades, ajustes y clave de OpenAI serán privados." : "Accede a tus rutas y entrenamientos."}</p>
      </div>
      <form data-auth-form>
        <label>Correo electrónico<input type="email" name="email" autocomplete="email" required /></label>
        ${recovering ? "" : `<label>Contraseña<input type="password" name="password" autocomplete="${signingUp ? "new-password" : "current-password"}" minlength="8" required /></label>`}
        <button class="primary" type="submit">${recovering ? "Enviar enlace" : signingUp ? "Crear cuenta" : "Entrar"}</button>
      </form>
      ${state.authMessage ? `<p class="auth-message">${escapeHtml(state.authMessage)}</p>` : ""}
      <div class="auth-links">
        <button data-action="toggle-auth">${signingUp || recovering ? "Volver a iniciar sesión" : "Crear una cuenta"}</button>
        ${!signingUp && !recovering ? `<button data-action="recover-password">He olvidado mi contraseña</button>` : ""}
      </div>
    </section>
  `;
}

function bindAuthEvents() {
  document.querySelector("[data-auth-form]")?.addEventListener("submit", submitAuth);
  document.querySelector("[data-action='toggle-auth']")?.addEventListener("click", () => {
    state.authMode = state.authMode === "login" ? "signup" : "login";
    state.authMessage = "";
    render();
  });
  document.querySelector("[data-action='recover-password']")?.addEventListener("click", () => {
    state.authMode = "recovery";
    state.authMessage = "";
    render();
  });
}

async function submitAuth(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const email = String(form.get("email") || "").trim();
  const password = String(form.get("password") || "");
  if (state.authMode === "recovery") {
    const response = await fetch(`${state.config.supabase_url}/auth/v1/recover`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: state.config.supabase_publishable_key
      },
      body: JSON.stringify({ email, redirect_to: window.location.origin })
    });
    state.authMessage = response.ok
      ? "Revisa tu correo para continuar."
      : "No se ha podido enviar el enlace de recuperación.";
    render();
    return;
  }
  const signup = state.authMode === "signup";
  const path = signup ? "/auth/v1/signup" : "/auth/v1/token?grant_type=password";
  const response = await fetch(`${state.config.supabase_url}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: state.config.supabase_publishable_key
    },
    body: JSON.stringify({ email, password })
  });
  const result = await response.json();
  if (!response.ok) {
    state.authMessage = result.msg || result.error_description || "No se ha podido completar la autenticación.";
    render();
    return;
  }
  const session = result.access_token ? result : result.session;
  if (!session?.access_token) {
    state.authMode = "login";
    state.authMessage = "Cuenta creada. Confirma el correo recibido y después inicia sesión.";
    render();
    return;
  }
  saveSession(session);
  state.authMessage = "";
  await refresh();
  render();
}

function loadSession() {
  const hash = new URLSearchParams(window.location.hash.slice(1));
  if (hash.get("access_token")) {
    const session = {
      access_token: hash.get("access_token"),
      refresh_token: hash.get("refresh_token"),
      expires_at: Math.floor(Date.now() / 1000) + Number(hash.get("expires_in") || 3600),
      token_type: hash.get("token_type") || "bearer",
      user: null
    };
    state.passwordRecovery = hash.get("type") === "recovery";
    history.replaceState(null, "", window.location.pathname);
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    return session;
  }
  try {
    return JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY));
  } catch {
    return null;
  }
}

function saveSession(session) {
  state.session = session;
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
}

function clearSession() {
  state.session = null;
  localStorage.removeItem(SESSION_STORAGE_KEY);
}

function tokenExpiresSoon(session) {
  return !session.expires_at || session.expires_at * 1000 < Date.now() + 30000;
}

async function refreshSession() {
  if (!state.session?.refresh_token) return false;
  const response = await fetch(`${state.config.supabase_url}/auth/v1/token?grant_type=refresh_token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: state.config.supabase_publishable_key
    },
    body: JSON.stringify({ refresh_token: state.session.refresh_token })
  });
  if (!response.ok) {
    clearSession();
    return false;
  }
  saveSession(await response.json());
  return true;
}

async function logout() {
  if (state.session?.access_token) {
    await fetch(`${state.config.supabase_url}/auth/v1/logout`, {
      method: "POST",
      headers: {
        apikey: state.config.supabase_publishable_key,
        Authorization: `Bearer ${state.session.access_token}`
      }
    }).catch(() => {});
  }
  clearSession();
  state.routes = [];
  state.activities = [];
  state.settings = null;
  state.selectedRoute = null;
  state.selectedActivity = null;
  state.authMode = "login";
  render();
}

function showMessage(message) {
  state.message = message;
  if (messageTimer) clearTimeout(messageTimer);
  messageTimer = setTimeout(() => {
    state.message = "";
    messageTimer = null;
    render();
  }, MESSAGE_DURATION_MS);
}

function clearMessage() {
  state.message = "";
  if (messageTimer) clearTimeout(messageTimer);
  messageTimer = null;
}

function renderToast() {
  return `
    <div class="toast" role="status" aria-live="polite">
      <span>${escapeHtml(state.message)}</span>
      <div class="toast-progress" style="--toast-duration: ${MESSAGE_DURATION_MS}ms"></div>
    </div>
  `;
}

function renderRoutes() {
  const cards = state.routes.map((route) => `
    <article class="card route-card" data-open-route="${route.id}" role="button" tabindex="0">
      <div class="card-top">
        <div>
          <span class="eyebrow">Ruta</span>
          <h3>${escapeHtml(route.name)}</h3>
          <p>${new Date(route.created_at).toLocaleDateString("es-ES")}</p>
        </div>
        <span class="route-ribbon">${route.max_grade_percent.toFixed(1)}% max</span>
      </div>
      <div class="route-stats">
        ${statPill("Distancia", `${route.distance_km.toFixed(2)} km`)}
        ${statPill("Desnivel", `${Math.round(route.elevation_gain_m)} m+`)}
        ${statPill("Media", `${route.avg_grade_percent.toFixed(1)}%`)}
        ${statPill("Final", `${Math.round(route.end_altitude_m)} m`)}
      </div>
    </article>
  `).join("");
  return `
    <section>
      <header class="page-header">
        <div><span class="eyebrow">Biblioteca</span><h2>Rutas</h2><p>${state.routes.length} rutas guardadas</p></div>
        <button class="primary" data-view-action="import">Crear ruta</button>
      </header>
      <div class="grid-list">${cards}</div>
      ${state.routes.length ? "" : `<div class="empty-state"><strong>No hay rutas guardadas</strong><button class="primary" data-view-action="import">Crear ruta</button></div>`}
    </section>
  `;
}

function renderImport() {
  return `
    <section>
      <header class="page-header">
        <div><span class="eyebrow">Editor</span><h2>Crear ruta</h2><p>${state.draft.name ? escapeHtml(state.draft.name) : "Nueva ruta"}</p></div>
      </header>
      <div class="upload-panel">
        <label class="dropzone" data-dropzone for="image-file">
          <input type="file" id="image-file" accept="image/png,image/jpeg,image/webp" />
          <span class="upload-icon">+</span>
          <strong data-upload-name>Arrastra una imagen aquí</strong>
          <span>o haz click para seleccionar un perfil de altimetría</span>
          <small>PNG, JPG o WebP</small>
        </label>
        <button data-action="analyze-image" ${state.busyText ? "disabled" : ""}>Analizar imagen</button>
      </div>
      ${renderRouteForm(state.draft)}
      <div class="chart-shell"><canvas class="chart" data-chart="draft"></canvas></div>
      <div class="bottom-actions">
        <button class="primary large-action" data-action="save-draft" ${state.busyText ? "disabled" : ""}>Guardar ruta</button>
      </div>
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
            <span class="eyebrow">Detalle de ruta</span>
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
        <div class="chart-shell"><canvas class="chart" data-chart="selected"></canvas></div>
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
        <div><span class="eyebrow">Detalle de ruta</span><h2>${escapeHtml(route.name)}</h2><p>${route.distance_km.toFixed(2)} km · ${Math.round(route.elevation_gain_m)} m+</p></div>
        <div class="actions">
          <button data-action="duplicate-route">Duplicar</button>
          <button data-action="delete-route">Eliminar</button>
          <button data-action="update-route">Guardar cambios</button>
          <button class="primary" data-action="start-training">Entrenar</button>
        </div>
      </header>
      ${renderRouteForm(routeToDraft(route))}
      <div class="chart-shell"><canvas class="chart" data-chart="selected"></canvas></div>
    </section>
  `;
}

function renderTraining() {
  const route = state.selectedRoute;
  if (!route) return `<div class="empty-state">Selecciona una ruta.</div>`;
  if (!state.training) resetTraining();
  const t = state.training;
  syncTrainingFromTrainer();
  const segment = getSegmentAtKm(route.segments, t.km);
  const realGrade = segment?.grade_percent ?? 0;
  const trainerGrade = applyTrainerGradeLimit(realGrade);
  const altitude = interpolateAltitude(segment, t.km, route.start_altitude_m);
  const paused = !hasLiveTrainerData() || t.speed <= 0.2;
  const progress = route.distance_km > 0 ? Math.min(100, (t.km / route.distance_km) * 100) : 0;
  const cadence = paused ? 0 : Math.round(state.trainer.metrics.cadence_rpm);
  const power = paused ? 0 : Math.round(state.trainer.metrics.power_w);
  const connectDisabled = state.trainer.connecting || state.trainer.connected;
  const rideStatus = t.activityId ? "Continuando actividad parcial" : t.running ? (paused ? "Pausada" : "En marcha") : "Preparada";
  return `
    <section>
      <header class="page-header">
        <div><span class="eyebrow">Entrenamiento</span><h2>${escapeHtml(route.name)}</h2><p>${rideStatus} · real ${realGrade.toFixed(1)}% · rodillo ${trainerGrade.toFixed(1)}%</p></div>
        <div class="actions">
          <button data-action="connect-trainer" ${connectDisabled ? "disabled" : ""}>${state.trainer.connecting ? "Conectando..." : state.trainer.connected ? "Tacx conectado" : "Conectar Tacx"}</button>
          <button data-action="toggle-training" ${state.trainer.connected ? "" : "disabled"}>${t.running ? "Pausar manual" : "Iniciar"}</button>
          <button data-action="save-partial">Guardar parcial</button>
          <button class="primary" data-action="save-completed">Terminar</button>
        </div>
      </header>
      <div class="training-layout">
        <div class="training-main">
          <div class="training-status">
            <div class="progress-header"><span>${t.km.toFixed(2)} / ${route.distance_km.toFixed(2)} km</span><strong>${progress.toFixed(0)}%</strong></div>
            <div class="progress-track"><div class="progress-fill" style="--progress: ${progress}%"></div></div>
          </div>
          <div class="chart-shell"><canvas class="chart" data-chart="training"></canvas></div>
          <div class="metrics">
            ${metric("Tiempo activo", formatSeconds(t.activeSeconds))}
            ${metric("Tiempo total", formatSeconds(t.elapsed))}
            ${metric("Altitud virtual", `${Math.round(altitude)} m`)}
            ${metric("Desnivel", `${Math.max(0, Math.round(altitude - route.start_altitude_m))} m`)}
          </div>
        </div>
        <aside class="training-side">
          <div class="panel trainer-panel">
            <span class="eyebrow">Conexion FTMS</span>
            <strong>${escapeHtml(state.trainer.status)}</strong>
            <p>${state.trainer.connected ? "Leyendo datos reales del Tacx y enviando la pendiente de la ruta." : "Usa Chrome o Edge y conecta el rodillo por Bluetooth."}</p>
            ${state.trainer.connected ? `<button data-action="disconnect-trainer">Desconectar</button>` : ""}
          </div>
          <div class="metrics">
            ${metric("Velocidad", `${t.speed.toFixed(1)} km/h`)}
            ${metric("Cadencia", `${cadence} rpm`)}
            ${metric("Potencia", `${power} W`)}
            ${metric("Pendiente", `${trainerGrade.toFixed(1)}%`)}
          </div>
        </aside>
      </div>
    </section>
  `;
}

function renderActivities() {
  const totalKm = state.activities.reduce((sum, activity) => sum + activity.distance_km, 0);
  const totalElevation = state.activities.reduce((sum, activity) => sum + activity.completed_elevation_m, 0);
  const maxPower = state.activities.reduce((max, activity) => Math.max(max, activity.max_power_w), 0);
  const cards = state.activities.map((activity) => `
    <article class="card activity-card" data-open-activity="${activity.id}" role="button" tabindex="0">
      <div class="card-top">
        <div>
          <span class="eyebrow">${new Date(activity.started_at).toLocaleDateString("es-ES")}</span>
          <h3>${escapeHtml(activity.route_name)}</h3>
          <p>${formatSeconds(activity.active_seconds)} activo · ${formatSeconds(activity.total_seconds)} total</p>
        </div>
        <span class="status-chip ${activity.status === "partial" ? "partial" : ""}">${activity.status === "completed" ? "Completada" : "Parcial"}</span>
      </div>
      <div class="activity-stats">
        ${statPill("Distancia", `${activity.distance_km.toFixed(2)} km`)}
        ${statPill("Potencia", `${activity.avg_power_w} W`)}
        ${statPill("Cadencia", `${activity.avg_cadence_rpm} rpm`)}
        ${statPill("Velocidad", `${activity.avg_speed_kph.toFixed(1)} km/h`)}
      </div>
    </article>
  `).join("");
  return `
    <section>
      <header class="page-header"><div><span class="eyebrow">Historial</span><h2>Actividades</h2><p>${state.activities.length} entrenamientos guardados</p></div></header>
      <div class="dashboard-strip">
        ${metric("Actividades", state.activities.length)}
        ${metric("Kilometros", `${totalKm.toFixed(1)} km`)}
        ${metric("Desnivel", `${Math.round(totalElevation)} m+`)}
        ${metric("Mayor potencia", `${maxPower} W`)}
      </div>
      <div class="grid-list">${cards}</div>
      ${state.activities.length ? "" : `<div class="empty-state"><strong>No hay actividades guardadas</strong><button class="primary" data-view-action="routes">Ver rutas</button></div>`}
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
        <div><span class="eyebrow">Detalle de actividad</span><h2>${escapeHtml(activity.route_name)}</h2><p>${activity.status === "completed" ? "Completada" : "Parcial"} · ${activity.distance_km.toFixed(2)} km · ${formatSeconds(activity.active_seconds)}</p></div>
        <div class="actions">
          ${activity.status === "partial" ? `<button class="primary" data-action="resume-activity">Continuar</button>` : ""}
          <button class="danger" data-action="delete-current-activity">Eliminar</button>
          <button data-action="close-activity-modal">Cerrar</button>
        </div>
      </header>
      <div class="chart-shell"><canvas class="chart" data-chart="activity"></canvas></div>
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
  const keyStatus = s.openai_api_key_configured ? "Hay una clave guardada. Escribe otra solo para reemplazarla." : "No hay ninguna clave guardada.";
  return `
    <section>
      <header class="page-header">
        <div><span class="eyebrow">Preferencias</span><h2>Ajustes</h2><p>OpenAI, rodillo y simulación</p></div>
        <button class="primary" data-action="save-settings">Guardar ajustes</button>
      </header>
      ${renderTrainerSettingsPanel()}
      <div class="panel form-grid settings-panel">
        <label class="wide">API key de OpenAI<input type="password" name="openai_api_key" value="" autocomplete="off" placeholder="${s.openai_api_key_configured ? "Clave guardada" : "sk-..."}" /><small>${keyStatus}</small></label>
        <label class="check wide"><input type="checkbox" name="clear_openai_api_key" /> Eliminar la clave de OpenAI guardada</label>
        <label>Pendiente máxima rodillo<input type="number" step="0.1" name="max_trainer_grade_percent" value="${s.max_trainer_grade_percent}" /></label>
        <label>Peso ciclista<input type="number" step="0.1" name="rider_weight_kg" value="${s.rider_weight_kg}" /></label>
        <label>Peso bici<input type="number" step="0.1" name="bike_weight_kg" value="${s.bike_weight_kg}" /></label>
        <label class="check"><input type="checkbox" name="enable_negative_grades" ${s.enable_negative_grades ? "checked" : ""} /> Pendientes negativas</label>
        <label class="check"><input type="checkbox" name="smooth_grade_changes" ${s.smooth_grade_changes ? "checked" : ""} /> Suavizar cambios</label>
      </div>
      ${state.config.auth_enabled ? `
        <div class="panel form-grid password-panel">
          <label class="wide">${state.passwordRecovery ? "Elige tu nueva contraseña" : "Nueva contraseña"}<input type="password" name="new_password" minlength="8" autocomplete="new-password" /></label>
          <button data-action="change-password">Cambiar contraseña</button>
        </div>
      ` : ""}
    </section>
  `;
}

function renderTrainerSettingsPanel() {
  const metrics = state.trainer.metrics;
  const calibrationDisabled = !state.trainer.connected || state.trainer.features?.spinDownControl === false;
  return `
    <div class="panel trainer-settings-panel">
      <div>
        <span class="eyebrow">Rodillo</span>
        <h3>Tacx FLUX 2 Smart</h3>
        <p>${escapeHtml(state.trainer.status)}</p>
      </div>
      <div class="trainer-settings-actions">
        <button data-action="connect-trainer" ${state.trainer.connecting || state.trainer.connected ? "disabled" : ""}>${state.trainer.connecting ? "Conectando..." : state.trainer.connected ? "Conectado" : "Conectar rodillo"}</button>
        <button data-action="disconnect-trainer" ${state.trainer.connected ? "" : "disabled"}>Desconectar</button>
        <button class="primary" data-action="start-calibration" ${calibrationDisabled ? "disabled" : ""}>Calibrar ahora</button>
      </div>
      <div class="metrics">
        ${metric("Velocidad", `${Number(metrics.speed_kph || 0).toFixed(1)} km/h`)}
        ${metric("Cadencia", `${Math.round(metrics.cadence_rpm || 0)} rpm`)}
        ${metric("Potencia", `${Math.round(metrics.power_w || 0)} W`)}
      </div>
    </div>
  `;
}

function renderCalibrationModal() {
  const c = state.calibration;
  const targetSpeedLabel = formatCalibrationSpeedTarget(c);
  const currentSpeed = Number(state.trainer.metrics.speed_kph || 0).toFixed(1);
  return `
    <div class="modal-backdrop" data-action="close-calibration">
      <section class="modal calibration-modal" role="dialog" aria-modal="true" aria-label="Calibrar rodillo" data-modal-panel>
        <header class="page-header">
          <div>
            <span class="eyebrow">Calibracion</span>
            <h2>Tacx FLUX 2 Smart</h2>
            <p>${escapeHtml(c.message)}</p>
          </div>
          <button data-action="close-calibration">Cerrar</button>
        </header>
        <div class="calibration-steps">
          ${calibrationStep("1", "Acelera progresivamente", `Lleva la bici hasta ${targetSpeedLabel}.`, c.step === "accelerate")}
          ${calibrationStep("2", "Deja de pedalear", "Cuando la app lo indique, deja que el rodillo se pare solo.", c.step === "coast")}
          ${calibrationStep("3", "Espera el resultado", "No toques el freno ni vuelvas a pedalear hasta que termine.", c.step === "waiting")}
        </div>
        <div class="metrics">
          ${metric("Velocidad actual", `${currentSpeed} km/h`)}
          ${metric("Velocidad objetivo", targetSpeedLabel)}
          ${metric("Estado", escapeHtml(c.status))}
          ${metric("Resultado", escapeHtml(c.result || "Pendiente"))}
        </div>
        <div class="bottom-actions">
          <button class="primary" data-action="start-calibration-command" ${c.running ? "disabled" : ""}>${c.running ? "Calibrando..." : "Iniciar secuencia"}</button>
        </div>
      </section>
    </div>
  `;
}

function calibrationStep(number, title, description, active) {
  return `
    <div class="calibration-step ${active ? "active" : ""}">
      <span>${number}</span>
      <div><strong>${title}</strong><p>${description}</p></div>
    </div>
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
    <div class="panel route-editor" id="route-form">
      <div class="form-grid">
        <label class="wide">Nombre<input name="name" value="${escapeAttr(draft.name)}" /></label>
      </div>
      <div class="summary-grid">
        ${readonlyNumber("Distancia total", `${calculated.distance_km.toFixed(2)} km`)}
        ${readonlyNumber("Desnivel positivo", `${Math.round(calculated.elevation_gain_m)} m`)}
        ${readonlyNumber("Altitud inicial", `${Math.round(calculated.start_altitude_m)} m`)}
        ${readonlyNumber("Altitud final", `${Math.round(calculated.end_altitude_m)} m`)}
        ${readonlyNumber("Pendiente media", `${calculated.avg_grade_percent.toFixed(1)}%`)}
        ${readonlyNumber("Pendiente máxima", `${calculated.max_grade_percent.toFixed(1)}%`)}
      </div>
      <div class="segments-header">
        <div>
          <h3>Segmentos</h3>
          <p>${draft.segments.length} tramos</p>
        </div>
        <button data-action="add-segment" type="button">Añadir segmento</button>
      </div>
      <div class="segments-table">${rows}</div>
    </div>
  `;
}

function bindEvents() {
  document.querySelector("[data-action='logout']")?.addEventListener("click", logout);
  document.querySelectorAll("[data-view-action]").forEach((el) => el.addEventListener("click", () => setView(el.dataset.viewAction)));
  document.querySelectorAll("[data-open-route]").forEach((el) => el.addEventListener("click", async () => {
    state.selectedRoute = await api(`/api/routes/${el.dataset.openRoute}`);
    state.draft = routeToDraft(state.selectedRoute);
    state.routeDirty = false;
    state.routeModalOpen = true;
    render();
  }));
  document.querySelectorAll("[data-open-route]").forEach((el) => el.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    el.click();
  }));
  document.querySelectorAll("[data-open-activity]").forEach((el) => el.addEventListener("click", async () => {
    state.selectedActivity = await api(`/api/activities/${el.dataset.openActivity}`);
    state.selectedRoute = await api(`/api/routes/${state.selectedActivity.activity.route_id}`);
    state.activityModalOpen = true;
    render();
  }));
  document.querySelectorAll("[data-open-activity]").forEach((el) => el.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    el.click();
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
  bindDropzone();
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
  document.querySelector("[data-action='connect-trainer']")?.addEventListener("click", connectTrainer);
  document.querySelector("[data-action='disconnect-trainer']")?.addEventListener("click", disconnectTrainer);
  document.querySelector("[data-action='start-calibration']")?.addEventListener("click", openCalibrationModal);
  document.querySelector("[data-action='start-calibration-command']")?.addEventListener("click", startCalibrationCommand);
  document.querySelectorAll("[data-action='close-calibration']").forEach((el) => el.addEventListener("click", (event) => {
    if (event.currentTarget.classList.contains("modal-backdrop") && event.target.closest("[data-modal-panel]")) return;
    state.calibration.open = false;
    render();
  }));
  document.querySelector("[data-action='save-partial']")?.addEventListener("click", () => saveActivity("partial"));
  document.querySelector("[data-action='save-completed']")?.addEventListener("click", () => saveActivity("completed"));
  document.querySelector("[data-action='resume-activity']")?.addEventListener("click", resumeActivity);
  document.querySelector("[data-action='delete-current-activity']")?.addEventListener("click", async () => {
    if (state.selectedActivity) await deleteActivity(state.selectedActivity.activity.id);
  });
  document.querySelector("[data-action='save-settings']")?.addEventListener("click", saveSettings);
  document.querySelector("[data-action='change-password']")?.addEventListener("click", changePassword);
}

function bindDropzone() {
  const dropzone = document.querySelector("[data-dropzone]");
  const fileInput = document.querySelector("#image-file");
  const fileName = document.querySelector("[data-upload-name]");
  if (!dropzone || !fileInput || !fileName) return;

  const updateFileName = () => {
    const file = fileInput.files?.[0];
    fileName.textContent = file ? file.name : "Arrastra una imagen aquí";
    dropzone.classList.toggle("has-file", Boolean(file));
  };

  fileInput.addEventListener("change", updateFileName);

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragging");
    });
  });

  ["dragleave", "dragend"].forEach((eventName) => {
    dropzone.addEventListener(eventName, () => {
      dropzone.classList.remove("dragging");
    });
  });

  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
    if (!event.dataTransfer?.files?.length) return;
    fileInput.files = event.dataTransfer.files;
    updateFileName();
  });
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
    showMessage("La ruta necesita al menos un segmento.");
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
    showMessage("Pon un nombre a la ruta antes de guardar.");
    render();
    return false;
  }
  const invalidSegment = draft.segments.find((segment) => segment.end_km <= segment.start_km);
  if (invalidSegment || draft.distance_km <= 0) {
    showMessage("Cada segmento debe tener un km final mayor que el km inicial.");
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
    showMessage("Selecciona primero una imagen.");
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
    showMessage("Imagen analizada. Revisa los datos antes de guardar.");
  } catch (error) {
    showMessage(error.message);
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
      speed: currentTrainerSpeed(),
      samples: state.resumeActivity.samples.map(({ id, activity_id, ...sample }) => sample),
      activityId: activity.id,
      startedAt: activity.started_at
    };
    return;
  }
  state.training = { running: false, timer: null, elapsed: 0, activeSeconds: 0, km: 0, speed: currentTrainerSpeed(), samples: [], activityId: null, startedAt: null };
}

function resumeActivity() {
  if (!state.selectedActivity || state.selectedActivity.activity.status !== "partial") return;
  state.resumeActivity = state.selectedActivity;
  state.activityModalOpen = false;
  state.training = null;
  setView("training");
}

async function connectTrainer() {
  if (state.trainer.connecting || state.trainer.connected) return;
  state.trainer.connecting = true;
  state.trainer.status = "Preparando Bluetooth...";
  render();
  try {
    trainerClient = new FtmsTrainer({
      onData: handleTrainerData,
      onStatus: (status) => {
        state.trainer.status = status;
        render();
      },
      onMachineStatus: handleTrainerMachineStatus,
      onDisconnect: () => {
        state.trainer.connected = false;
        state.trainer.connecting = false;
        state.trainer.metrics = emptyTrainerMetrics();
        state.trainer.lastDataAt = null;
        state.trainer.features = null;
        state.calibration = emptyCalibrationState();
        if (state.training?.running) {
          state.training.running = false;
          clearInterval(state.training.timer);
          state.training.timer = null;
        }
        render();
      }
    });
    await trainerClient.connect();
    state.trainer.connected = true;
    state.trainer.connecting = false;
    state.trainer.features = trainerClient.features;
    await sendCurrentGradeToTrainer(true);
    showMessage("Tacx conectado. Ya puedes iniciar el entrenamiento.");
  } catch (error) {
    state.trainer.connected = false;
    state.trainer.connecting = false;
    state.trainer.status = "Rodillo no conectado";
    showMessage(error.message);
  }
  render();
}

async function disconnectTrainer() {
  if (!trainerClient) return;
  await trainerClient.disconnect();
  trainerClient = null;
  state.trainer.connected = false;
  state.trainer.connecting = false;
  state.trainer.status = "Rodillo no conectado";
  state.trainer.metrics = emptyTrainerMetrics();
  state.trainer.lastDataAt = null;
  state.trainer.features = null;
  state.calibration = emptyCalibrationState();
  render();
}

function handleTrainerData(metrics) {
  state.trainer.metrics = {
    ...state.trainer.metrics,
    ...metrics
  };
  state.trainer.lastDataAt = Date.now();
  updateCalibrationFromSpeed();
  if (state.training) syncTrainingFromTrainer();
  if ((state.calibration.open || state.view === "settings") && !state.message) render();
}

function handleTrainerMachineStatus(status) {
  if (status.type !== "spin_down") return;
  state.calibration.status = status.label;
  if (status.spinDownStatus === 0x02) {
    state.calibration.step = "done";
    state.calibration.running = false;
    state.calibration.result = "Completada";
    state.calibration.message = "Calibracion completada correctamente.";
  } else if (status.spinDownStatus === 0x03) {
    state.calibration.step = "error";
    state.calibration.running = false;
    state.calibration.result = "Fallida";
    state.calibration.message = "El rodillo ha rechazado o fallado el calibrado. Prueba de nuevo con el rodillo caliente.";
  } else if (status.spinDownStatus === 0x04) {
    state.calibration.step = "coast";
    state.calibration.message = "Deja de pedalear y espera a que el rodillo se detenga.";
  }
  if (state.calibration.open) render();
}

function openCalibrationModal() {
  if (!state.trainer.connected) {
    showMessage("Conecta el rodillo antes de calibrar.");
    return;
  }
  if (state.trainer.features?.spinDownControl === false) {
    showMessage("Este rodillo no anuncia calibracion por FTMS.");
    return;
  }
  state.calibration = {
    ...emptyCalibrationState(),
    open: true,
    status: state.trainer.features?.spinDownControl === false ? "No anunciado por FTMS" : "Listo",
    message: "La secuencia FTMS pide acelerar hasta la velocidad objetivo y dejar de pedalear."
  };
  render();
}

async function startCalibrationCommand() {
  if (!trainerClient?.connected) {
    showMessage("Conecta el rodillo antes de calibrar.");
    return;
  }
  state.calibration.running = true;
  state.calibration.step = "accelerate";
  state.calibration.status = "Solicitando calibracion";
  state.calibration.message = "Acelera suavemente hasta la velocidad objetivo.";
  state.calibration.result = "";
  render();
  try {
    const result = await trainerClient.startSpinDownCalibration();
    state.calibration.targetSpeedKph = result.targetSpeedKph || 30;
    state.calibration.lowSpeedKph = result.lowSpeedKph;
    state.calibration.highSpeedKph = result.highSpeedKph;
    state.calibration.status = "Acelerando";
    state.calibration.message = `Acelera hasta entrar en ${formatCalibrationSpeedTarget(state.calibration)} y despues deja de pedalear cuando se indique.`;
  } catch (error) {
    state.calibration.running = false;
    state.calibration.step = "error";
    state.calibration.status = "No disponible";
    state.calibration.result = "No iniciada";
    state.calibration.message = error.message;
  }
  render();
}

function updateCalibrationFromSpeed() {
  const c = state.calibration;
  if (!c.open || !c.running || c.step !== "accelerate") return;
  const currentSpeed = Number(state.trainer.metrics.speed_kph || 0);
  const minimumTargetSpeed = c.lowSpeedKph || c.targetSpeedKph;
  if (currentSpeed >= minimumTargetSpeed) {
    c.step = "waiting";
    c.status = "Velocidad alcanzada";
    c.message = "Mantente atento: el rodillo debe indicar cuando dejar de pedalear.";
  }
}

function formatCalibrationSpeedTarget(calibration) {
  const low = calibration.lowSpeedKph;
  const high = calibration.highSpeedKph;
  if (low && high && Math.abs(high - low) >= 0.1) return `${low.toFixed(1)}-${high.toFixed(1)} km/h`;
  return `${Number(calibration.targetSpeedKph || 30).toFixed(1)} km/h`;
}

async function toggleTraining() {
  if (!state.trainer.connected) {
    showMessage("Conecta el Tacx FLUX 2 Smart antes de iniciar.");
    return;
  }
  if (!state.training.running) {
    try {
      await trainerClient?.start();
      await sendCurrentGradeToTrainer(true);
    } catch (error) {
      showMessage(error.message);
      render();
      return;
    }
    state.training.running = true;
    state.training.timer = setInterval(() => {
      tickTraining();
    }, 1000);
  } else {
    state.training.running = false;
    clearInterval(state.training.timer);
    state.training.timer = null;
    neutralizeTrainer().catch((error) => showMessage(error.message));
  }
  render();
}

async function tickTraining() {
  const route = state.selectedRoute;
  const t = state.training;
  syncTrainingFromTrainer();
  const paused = !hasLiveTrainerData() || t.speed <= 0.2;
  const segment = getSegmentAtKm(route.segments, t.km);
  const grade = applyTrainerGradeLimit(segment?.grade_percent ?? 0);
  const altitude = interpolateAltitude(segment, t.km, route.start_altitude_m);
  await sendCurrentGradeToTrainer();
  const sample = {
    timestamp_ms: Date.now(),
    elapsed_seconds: t.elapsed + 1,
    km: t.km,
    speed_kph: paused ? 0 : t.speed,
    cadence_rpm: paused ? 0 : Math.round(state.trainer.metrics.cadence_rpm),
    power_w: paused ? 0 : Math.round(state.trainer.metrics.power_w),
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

function syncTrainingFromTrainer() {
  if (!state.training) return;
  state.training.speed = currentTrainerSpeed();
}

function currentTrainerSpeed() {
  return hasLiveTrainerData() ? Number(state.trainer.metrics.speed_kph || 0) : 0;
}

function hasLiveTrainerData() {
  return Boolean(state.trainer.connected && state.trainer.lastDataAt && Date.now() - state.trainer.lastDataAt < 4000);
}

async function sendCurrentGradeToTrainer(force = false) {
  if (!trainerClient?.connected || !state.selectedRoute || !state.training) return;
  if (gradeCommandPending) return;
  const segment = getSegmentAtKm(state.selectedRoute.segments, state.training.km);
  const grade = applyTrainerGradeLimit(segment?.grade_percent ?? 0);
  gradeCommandPending = true;
  try {
    await trainerClient.setGrade(grade, { force });
  } catch (error) {
    showMessage(error.message);
  } finally {
    gradeCommandPending = false;
  }
}

async function saveActivity(status) {
  const route = state.selectedRoute;
  const t = state.training;
  if (!t || state.savingActivity) return;
  if (t.timer) clearInterval(t.timer);
  t.running = false;
  await neutralizeTrainer();
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
    showMessage(error.message);
    render();
  }
}

async function neutralizeTrainer() {
  if (!trainerClient?.connected) return;
  try {
    await trainerClient.neutralize();
  } catch (error) {
    showMessage(error.message);
  }
}

async function saveSettings() {
  const root = document.querySelector(".settings-panel");
  state.settings = {
    openai_api_key: root.querySelector("[name='openai_api_key']").value,
    clear_openai_api_key: root.querySelector("[name='clear_openai_api_key']").checked,
    max_trainer_grade_percent: Number(root.querySelector("[name='max_trainer_grade_percent']").value),
    enable_negative_grades: root.querySelector("[name='enable_negative_grades']").checked,
    smooth_grade_changes: root.querySelector("[name='smooth_grade_changes']").checked,
    rider_weight_kg: Number(root.querySelector("[name='rider_weight_kg']").value),
    bike_weight_kg: Number(root.querySelector("[name='bike_weight_kg']").value)
  };
  state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(state.settings) });
  showMessage("Ajustes guardados.");
  render();
}

async function changePassword() {
  const password = document.querySelector("[name='new_password']")?.value || "";
  if (password.length < 8) {
    showMessage("La nueva contraseña debe tener al menos 8 caracteres.");
    render();
    return;
  }
  const response = await fetch(`${state.config.supabase_url}/auth/v1/user`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      apikey: state.config.supabase_publishable_key,
      Authorization: `Bearer ${state.session.access_token}`
    },
    body: JSON.stringify({ password })
  });
  const result = await response.json();
  if (!response.ok) {
    showMessage(result.msg || result.error_description || "No se ha podido cambiar la contraseña.");
    render();
    return;
  }
  showMessage("Contraseña actualizada.");
  state.passwordRecovery = false;
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

  ctx.strokeStyle = "#e2e7ea";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const gy = padding.top + i * ((height - padding.top - padding.bottom) / 5);
    const altitudeLabel = maxAlt - (i * altitudeSpan) / 5;
    ctx.beginPath();
    ctx.moveTo(padding.left, gy);
    ctx.lineTo(width - padding.right, gy);
    ctx.stroke();
    ctx.fillStyle = "#687178";
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
    ctx.strokeStyle = "#eef2f3";
    ctx.stroke();
    ctx.fillStyle = "#687178";
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
  ctx.fillStyle = "rgba(15, 118, 110, 0.13)";
  ctx.fill();

  ctx.beginPath();
  points.forEach((point, index) => {
    const px = x(point.km);
    const py = y(point.altitude);
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.strokeStyle = "#0f766e";
  ctx.lineWidth = 3;
  ctx.stroke();

  segments.forEach((segment) => {
    if (segment.end_km <= segment.start_km) return;
    const startX = x(segment.start_km);
    const endX = x(segment.end_km);
    const labelX = startX + (endX - startX) / 2;
    const grade = Number(segment.grade_percent ?? calculateSegmentGrade(segment));
    ctx.fillStyle = grade >= 8 ? "#b42318" : grade >= 5 ? "#c56b17" : "#0f766e";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(`${grade.toFixed(1)}%`, labelX, 18);
    ctx.beginPath();
    ctx.moveTo(startX, padding.top - 8);
    ctx.lineTo(endX, padding.top - 8);
    ctx.strokeStyle = "rgba(15, 118, 110, 0.28)";
    ctx.lineWidth = 2;
    ctx.stroke();
  });

  if (completedKm !== null) drawMarker(ctx, x(completedKm), padding.top, height - padding.bottom, "#0f766e");
  if (currentKm !== null) drawMarker(ctx, x(currentKm), padding.top, height - padding.bottom, "#ef8a23");

  ctx.fillStyle = "#687178";
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

function emptyTrainerMetrics() {
  return {
    speed_kph: 0,
    cadence_rpm: 0,
    power_w: 0,
    heart_rate_bpm: null
  };
}

function emptyCalibrationState() {
  return {
    open: false,
    running: false,
    step: "accelerate",
    status: "Pendiente",
    message: "Conecta el rodillo para iniciar la calibracion.",
    targetSpeedKph: 30,
    lowSpeedKph: null,
    highSpeedKph: null,
    result: ""
  };
}

function metric(label, value) {
  return `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`;
}

function statPill(label, value) {
  return `<div class="stat-pill"><span>${label}</span><strong>${value}</strong></div>`;
}

function numberInput(label, name, value) {
  return `<label>${label}<input type="number" step="0.1" inputmode="decimal" name="${name}" value="${value}" /></label>`;
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
