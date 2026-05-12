"use strict";

const MODE_LABEL = {
  copy: "Backup",
  sync: "Espejo",
  bisync: "Sincronizar",
};
const MODE_ARROW = { copy: "↑", sync: "⇒", bisync: "⇄" };
const POLL_INTERVAL_MS = 10000;

const state = {
  jobs: [],
  remotes: [],
  remotesDetailed: [],
  agent: { available: false, active: false, enabled: false },
  picker: { remoteName: "", path: "", remoteLabel: "" },
};

const els = {};
const api = () => window.pywebview && window.pywebview.api;

function $(sel, root = document) {
  return root.querySelector(sel);
}

document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  bindEvents();
  waitForApi(boot);
});

function waitForApi(cb) {
  if (api()) return cb();
  setTimeout(() => waitForApi(cb), 50);
}

function cacheElements() {
  els.jobList = $("#job-list");
  els.emptyNoRemote = $("#empty-no-remote");
  els.emptyNoJobs = $("#empty-no-jobs");
  els.newJobBtn = $("#new-job-btn");
  els.jobModal = $("#job-modal");
  els.jobForm = $("#job-form");
  els.detailModal = $("#detail-modal");
  els.toast = $("#toast");
  els.cardTpl = $("#job-card-template");
  els.detailRunsList = $("#detail-runs");
  els.detailConfigList = $("#detail-config");
  els.detailResyncBtn = $("#detail-resync-btn");
  els.agentPill = $("#agent-pill");
  els.agentWarning = $("#agent-warning");
  els.agentWarningDetail = $("#agent-warning-detail");
  els.agentWarningAction = $("#agent-warning-action");
  els.sharedModal = $("#shared-drive-modal");
  els.sharedOptions = $("#shared-drive-options");
  els.sharedConfirm = $("#shared-confirm");
  els.overflowMenu = $("#overflow-menu");
  els.overflowAgentToggle = $("#overflow-agent-toggle");
  els.overflowRemotes = $("#overflow-remotes");
  els.folderPickerModal = $("#folder-picker-modal");
  els.folderPickerList = $("#folder-picker-list");
  els.folderPickerCrumbs = $("#folder-picker-breadcrumbs");
  els.folderPickerConfirm = $("#folder-picker-confirm");
  els.folderPickerNew = $("#folder-picker-new");
}

function bindEvents() {
  els.newJobBtn.addEventListener("click", () => openJobModal());
  els.jobForm.addEventListener("submit", handleSaveJob);
  els.agentPill.addEventListener("click", () => toggleAgent());
  els.agentWarningAction.addEventListener("click", () => toggleAgent(true));
  els.folderPickerConfirm.addEventListener("click", confirmFolderPicker);
  els.folderPickerNew.addEventListener("click", newFolderInPicker);
  els.folderPickerList.addEventListener("click", handlePickerClick);
  els.folderPickerCrumbs.addEventListener("click", handlePickerClick);
  document.body.addEventListener("click", handleAction);
}

function handleAction(e) {
  const target = e.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  switch (action) {
    case "close-job": els.jobModal.close(); break;
    case "close-detail": els.detailModal.close(); break;
    case "close-shared": els.sharedModal.close(); break;
    case "new-job": openJobModal(); break;
    case "connect-drive": startConnectDrive(); break;
    case "toggle-agent": toggleAgent(); break;
    case "pick-folder": pickFolder(); break;
    case "pick-remote": openFolderPicker(); break;
    case "close-folder-picker": els.folderPickerModal.close(); break;
    case "detail-sync": runFromDetail(false, false); break;
    case "detail-dry": runFromDetail(true, false); break;
    case "detail-resync": runFromDetail(false, true); break;
    case "detail-edit": editFromDetail(); break;
    case "detail-delete": deleteFromDetail(); break;
  }
  if (target.classList.contains("overflow-item")) closeOverflow();
}

function closeOverflow() {
  if (els.overflowMenu) els.overflowMenu.open = false;
}

async function boot() {
  await refreshAll();
  startPolling();
}

function startPolling() {
  setInterval(pollTick, POLL_INTERVAL_MS);
}

async function pollTick() {
  if (anyModalOpen()) return;
  try {
    await refreshJobs();
    await refreshAgent();
  } catch (_) {}
}

function anyModalOpen() {
  return els.jobModal.open || els.detailModal.open || els.sharedModal.open || els.folderPickerModal.open;
}

async function refreshAll() {
  await refreshRemotes();
  await refreshJobs();
  await refreshAgent();
}

async function refreshRemotes() {
  state.remotesDetailed = await api().list_remotes_detailed();
  state.remotes = state.remotesDetailed.map((r) => r.name);
  populateRemoteSelect();
  renderOverflowRemotes();
}

function populateRemoteSelect() {
  const select = $("#job-remote");
  if (state.remotesDetailed.length === 0) {
    select.innerHTML = "";
    return;
  }
  select.innerHTML = state.remotesDetailed
    .map((r) => `<option value="${escapeHtml(r.name)}">${escapeHtml(r.label)} (${escapeHtml(r.name)})</option>`)
    .join("");
}

function renderOverflowRemotes() {
  if (!els.overflowRemotes) return;
  if (state.remotesDetailed.length === 0) {
    els.overflowRemotes.textContent = "Sin cuentas conectadas";
  } else {
    els.overflowRemotes.innerHTML = state.remotesDetailed
      .map((r) => `<div>${escapeHtml(r.label)} <span class="muted">(${escapeHtml(r.name)})</span></div>`)
      .join("");
  }
}

async function refreshJobs() {
  state.jobs = await api().list_jobs();
  els.jobList.innerHTML = "";
  if (state.remotes.length === 0) {
    els.emptyNoRemote.classList.remove("hidden");
    els.emptyNoJobs.classList.add("hidden");
    els.newJobBtn.hidden = true;
    return;
  }
  els.emptyNoRemote.classList.add("hidden");
  els.newJobBtn.hidden = false;
  if (state.jobs.length === 0) {
    els.emptyNoJobs.classList.remove("hidden");
    return;
  }
  els.emptyNoJobs.classList.add("hidden");
  state.jobs.forEach((job) => els.jobList.appendChild(renderJobCard(job)));
  renderAgentWarning();
}

function renderJobCard(job) {
  const node = els.cardTpl.content.firstElementChild.cloneNode(true);
  node.dataset.id = job.id;
  $(".job-name", node).textContent = job.name;
  $(".job-arrow", node).textContent = MODE_ARROW[job.mode] || "→";
  $(".job-dest", node).textContent = describeTarget(job);
  $(".job-status", node).className = "job-status " + jobStatusClass(job);
  $(".job-status", node).textContent = jobStatusText(job);
  const syncBtn = $(".action-sync", node);
  if (job.needs_baseline) {
    syncBtn.textContent = "Inicializar";
    syncBtn.addEventListener("click", () => runJob(job, false, true));
  } else {
    syncBtn.addEventListener("click", () => runJob(job, false, false));
  }
  $(".action-dry", node).addEventListener("click", () => runJob(job, true, false));
  $(".action-more", node).addEventListener("click", () => openDetailModal(job));
  return node;
}

function describeTarget(job) {
  const remote = state.remotesDetailed.find((r) => r.name === job.remote_name);
  const accountLabel = remote ? remote.label : job.remote_name;
  return `${accountLabel} · ${job.remote_path}`;
}

function jobStatusClass(job) {
  if (job._running) return "running";
  if (job.needs_baseline) return "warn";
  if (job.last_status === "ok") return "ok";
  if (job.last_status === "error") return "danger";
  return "";
}

function jobStatusText(job) {
  if (job._running) return "Corriendo…";
  if (job.needs_baseline) return "Falta inicializar baseline";
  if (!job.last_status) return "Sin corridas todavía";
  const verb = job.last_status === "ok" ? "OK" : "Error";
  return `${verb} · ${formatTime(job.last_run_at)}`;
}

function formatTime(ts) {
  if (!ts) return "nunca";
  const d = new Date(ts.replace(" ", "T") + "Z");
  if (isNaN(d.getTime())) return ts;
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diff < 60) return "hace un momento";
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  return d.toLocaleDateString();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function openJobModal(job = null) {
  if (state.remotes.length === 0) {
    showToast("Conectá una cuenta de Drive primero", "info");
    startConnectDrive();
    return;
  }
  $("#job-modal-title").textContent = job ? `Editar ${job.name}` : "Nueva sincronización";
  els.jobForm.reset();
  els.jobForm.dataset.id = job ? job.id : "";
  els.jobForm.elements.mode.value = "copy";
  if (job) {
    els.jobForm.elements.name.value = job.name;
    els.jobForm.elements.local_path.value = job.local_path;
    els.jobForm.elements.remote_name.value = job.remote_name;
    els.jobForm.elements.remote_path.value = job.remote_path;
    Array.from(els.jobForm.elements.mode).forEach((r) => (r.checked = r.value === job.mode));
    els.jobForm.elements.interval_minutes.value = job.interval_minutes;
    els.jobForm.elements.auto_sync.checked = !!job.auto_sync;
    els.jobForm.elements.excludes.value = job.excludes || "";
  }
  els.jobModal.showModal();
}

function autoSuggestFromLocal(local) {
  if (!local) return;
  const base = local.replace(/\/+$/, "").split("/").pop() || "";
  if (!base) return;
  if (!els.jobForm.elements.name.value.trim()) {
    els.jobForm.elements.name.value = base;
  }
}

async function openFolderPicker() {
  const remoteName = els.jobForm.elements.remote_name.value;
  if (!remoteName) {
    showToast("Elegí una cuenta primero", "warn");
    return;
  }
  const detailed = state.remotesDetailed.find((r) => r.name === remoteName);
  state.picker.remoteName = remoteName;
  state.picker.remoteLabel = detailed ? detailed.label : remoteName;
  state.picker.path = els.jobForm.elements.remote_path.value.trim();
  await loadPickerPath();
  els.folderPickerModal.showModal();
}

async function loadPickerPath() {
  renderPickerBreadcrumbs();
  els.folderPickerList.innerHTML = '<div class="muted">Cargando…</div>';
  try {
    const folders = await api().list_remote_folders(state.picker.remoteName, state.picker.path);
    renderFolderList(folders);
  } catch (err) {
    els.folderPickerList.innerHTML = `<div class="muted">Error: ${escapeHtml(toMessage(err))}</div>`;
  }
}

function renderPickerBreadcrumbs() {
  const parts = state.picker.path ? state.picker.path.split("/").filter(Boolean) : [];
  const crumbs = [`<a data-picker-nav="">${escapeHtml(state.picker.remoteLabel)}</a>`];
  parts.forEach((p, i) => {
    const path = parts.slice(0, i + 1).join("/");
    crumbs.push(`<a data-picker-nav="${escapeHtml(path)}">${escapeHtml(p)}</a>`);
  });
  els.folderPickerCrumbs.innerHTML = crumbs.join(' <span class="muted">/</span> ');
}

function renderFolderList(folders) {
  if (folders.length === 0) {
    els.folderPickerList.innerHTML = '<div class="muted">(sin subcarpetas)</div>';
    return;
  }
  els.folderPickerList.innerHTML = folders
    .map((f) => `<button type="button" class="folder-item" data-picker-nav-rel="${escapeHtml(f)}"><span>📁</span><span>${escapeHtml(f)}</span></button>`)
    .join("");
}

function handlePickerClick(e) {
  const navAbs = e.target.closest("[data-picker-nav]");
  if (navAbs) {
    e.preventDefault();
    state.picker.path = navAbs.dataset.pickerNav || "";
    loadPickerPath();
    return;
  }
  const navRel = e.target.closest("[data-picker-nav-rel]");
  if (navRel) {
    e.preventDefault();
    const sub = navRel.dataset.pickerNavRel;
    state.picker.path = state.picker.path ? `${state.picker.path}/${sub}` : sub;
    loadPickerPath();
  }
}

function confirmFolderPicker() {
  els.jobForm.elements.remote_path.value = state.picker.path;
  els.folderPickerModal.close();
}

async function newFolderInPicker() {
  const name = prompt("Nombre de la carpeta nueva:");
  if (!name || !name.trim()) return;
  const clean = name.trim();
  const target = state.picker.path ? `${state.picker.path}/${clean}` : clean;
  try {
    await api().make_remote_folder(state.picker.remoteName, target);
    state.picker.path = target;
    await loadPickerPath();
    showToast(`Carpeta "${clean}" creada`, "ok");
  } catch (err) {
    showToast(toMessage(err), "error");
  }
}

async function pickFolder() {
  try {
    const path = await api().pick_local_path();
    if (path) {
      els.jobForm.elements.local_path.value = path;
      autoSuggestFromLocal(path);
    }
  } catch (err) {
    showToast(toMessage(err), "error");
  }
}

async function handleSaveJob(e) {
  e.preventDefault();
  const data = formToJobPayload(els.jobForm);
  try {
    const newId = await api().save_job(data);
    els.jobModal.close();
    showToast(data.id ? "Cambios guardados" : "Sincronización creada", "ok");
    await refreshJobs();
    await autoInitIfNeeded(newId, data);
  } catch (err) {
    showToast(toMessage(err), "error");
  }
}

async function autoInitIfNeeded(jobId, data) {
  if (data.mode !== "bisync") return;
  await refreshJobs();
  const job = state.jobs.find((j) => j.id === jobId);
  if (!job || !job.needs_baseline) return;
  showToast("Inicializando sincronización bidireccional…", "info");
  await runJob(job, false, true, { auto: true });
}

function formToJobPayload(form) {
  return {
    id: form.dataset.id ? Number(form.dataset.id) : null,
    name: form.elements.name.value,
    local_path: form.elements.local_path.value,
    remote_name: form.elements.remote_name.value,
    remote_path: form.elements.remote_path.value,
    mode: form.elements.mode.value,
    interval_minutes: Number(form.elements.interval_minutes.value || 15),
    auto_sync: form.elements.auto_sync.checked,
    excludes: form.elements.excludes.value,
  };
}

async function runJob(job, dryRun, resync, opts = {}) {
  const auto = !!opts.auto;
  if (!auto && !dryRun && !resync && job.mode === "sync") {
    if (!confirm(`"${job.name}" está en modo Espejo y puede borrar archivos en Drive. ¿Continuar?`)) return;
  }
  setJobRunning(job.id, true);
  const label = dryRun ? "Dry run en progreso…" : resync ? "Inicializando…" : "Sincronizando…";
  showToast(label, "info");
  try {
    const result = await api().run(job.id, dryRun, resync);
    if (result.needs_resync && !auto) {
      const job2 = state.jobs.find((j) => j.id === job.id);
      if (job2) await runJob(job2, false, true, { auto: true });
      return;
    }
    if (result.needs_resync && auto) {
      showToast(result.summary, "warn");
    } else {
      const okLabel = dryRun ? "Dry run OK" : resync ? "Inicializado" : "Sync OK";
      const text = result.ok ? okLabel : `Error: ${truncate(result.summary, 200)}`;
      showToast(text, result.ok ? "ok" : "error");
    }
  } catch (err) {
    showToast(toMessage(err), "error");
  } finally {
    setJobRunning(job.id, false);
    await refreshJobs();
  }
}

function setJobRunning(jobId, running) {
  const job = state.jobs.find((j) => j.id === jobId);
  if (job) job._running = running;
  const card = els.jobList.querySelector(`[data-id="${jobId}"]`);
  if (!card) return;
  const status = card.querySelector(".job-status");
  if (running) {
    status.className = "job-status running";
    status.textContent = "Corriendo…";
  }
}

async function openDetailModal(job) {
  els.detailModal.dataset.id = job.id;
  $("#detail-name").textContent = job.name;
  $("#detail-subtitle").textContent = `${job.local_path} ${MODE_ARROW[job.mode]} ${describeTarget(job)}`;
  els.detailResyncBtn.hidden = job.mode !== "bisync";
  await renderRuns(job.id);
  renderConfig(job);
  els.detailModal.showModal();
}

async function renderRuns(jobId) {
  const runs = await api().list_runs(jobId);
  if (runs.length === 0) {
    els.detailRunsList.innerHTML = '<p class="muted" style="padding:8px 0">Sin corridas todavía.</p>';
    return;
  }
  els.detailRunsList.innerHTML = runs.map((r) => `
    <div class="run-item">
      <span class="run-icon ${r.status}">${r.status === "ok" ? "●" : "⚠"}</span>
      <div>
        <div>${formatTime(r.started_at)}</div>
        <div class="run-meta">${escapeHtml(truncate(r.summary || "", 120))}</div>
      </div>
      <span class="run-tag">${r.run_type}</span>
    </div>
  `).join("");
}

function renderConfig(job) {
  const remote = state.remotesDetailed.find((r) => r.name === job.remote_name);
  const accountLabel = remote ? `${remote.label} (${remote.name})` : job.remote_name;
  const rows = [
    ["Carpeta local", job.local_path],
    ["Cuenta", accountLabel],
    ["Destino", job.remote_path],
    ["Tipo", MODE_LABEL[job.mode]],
    ["Automático", job.auto_sync ? `cada ${job.interval_minutes} min` : "no"],
    ["Excludes", job.excludes ? job.excludes.split("\n").join(", ") : "—"],
  ];
  els.detailConfigList.innerHTML = rows
    .map(([k, v]) => `<div class="config-row"><span class="config-key">${escapeHtml(k)}</span><span class="config-value">${escapeHtml(v)}</span></div>`)
    .join("");
}

async function runFromDetail(dryRun, resync) {
  const job = currentDetailJob();
  if (!job) return;
  els.detailModal.close();
  await runJob(job, dryRun, resync);
}

async function editFromDetail() {
  const job = currentDetailJob();
  if (!job) return;
  els.detailModal.close();
  openJobModal(job);
}

async function deleteFromDetail() {
  const job = currentDetailJob();
  if (!job) return;
  if (!confirm(`¿Eliminar "${job.name}"? Esto no toca tus archivos.`)) return;
  await api().delete_job(job.id);
  els.detailModal.close();
  showToast("Eliminado", "ok");
  await refreshJobs();
}

function currentDetailJob() {
  const id = Number(els.detailModal.dataset.id);
  return state.jobs.find((j) => j.id === id);
}

async function startConnectDrive() {
  showToast("Abriendo navegador para autorizar…", "info");
  try {
    const result = await api().connect_drive();
    showToast(`Cuenta conectada: ${result.name}`, "ok");
    await refreshAll();
    if (result && Array.isArray(result.shared_drives) && result.shared_drives.length > 0) {
      openSharedDriveModal(result.name, result.shared_drives);
    }
  } catch (err) {
    showToast(toMessage(err), "error");
  }
}

function openSharedDriveModal(remoteName, drives) {
  els.sharedOptions.innerHTML = drives.map((d) => `
    <label class="checkbox option-row">
      <input type="radio" name="shared-target" value="${escapeHtml(d.id)}">
      <span><strong>${escapeHtml(d.name)}</strong><br><span class="muted">Shared Drive</span></span>
    </label>
  `).join("");
  els.sharedConfirm.onclick = async () => {
    const choice = els.sharedModal.querySelector('input[name="shared-target"]:checked');
    const driveId = choice ? choice.value : "";
    els.sharedModal.close();
    if (!driveId) {
      showToast("Apuntando a Mi Drive", "ok");
      return;
    }
    try {
      await api().select_shared_drive(remoteName, driveId);
      showToast("Shared Drive vinculado", "ok");
      await refreshRemotes();
    } catch (err) {
      showToast(toMessage(err), "error");
    }
  };
  els.sharedModal.showModal();
}

async function refreshAgent() {
  try {
    state.agent = await api().agent_status();
  } catch (_) {
    state.agent = { available: false, active: false, enabled: false };
  }
  renderAgentPill();
  renderAgentWarning();
  renderOverflowAgentToggle();
}

function renderAgentPill() {
  const { available, active } = state.agent;
  if (!available) {
    els.agentPill.hidden = true;
    return;
  }
  els.agentPill.hidden = false;
  els.agentPill.className = "pill agent-pill " + (active ? "on" : "muted");
  els.agentPill.textContent = active ? "Agente activo" : "Agente apagado";
  els.agentPill.title = active ? "Click para desactivar" : "Click para activar";
}

function renderAgentWarning() {
  const autoJobs = state.jobs.filter((j) => j.auto_sync);
  const shouldWarn = autoJobs.length > 0 && state.agent.available && !state.agent.active;
  if (!shouldWarn) {
    els.agentWarning.classList.add("hidden");
    return;
  }
  const noun = autoJobs.length === 1 ? "sincronización automática" : "sincronizaciones automáticas";
  els.agentWarningDetail.textContent = `Tenés ${autoJobs.length} ${noun} pero no se van a disparar.`;
  els.agentWarning.classList.remove("hidden");
}

function renderOverflowAgentToggle() {
  if (!els.overflowAgentToggle) return;
  if (!state.agent.available) {
    els.overflowAgentToggle.textContent = "Agente no disponible";
    els.overflowAgentToggle.disabled = true;
    return;
  }
  els.overflowAgentToggle.disabled = false;
  els.overflowAgentToggle.textContent = state.agent.active ? "Desactivar agente" : "Activar agente";
}

async function toggleAgent(forceEnable = false) {
  if (!state.agent.available) {
    showToast("El servicio del agente no está disponible", "warn");
    return;
  }
  const turnOn = forceEnable || !state.agent.active;
  showToast(turnOn ? "Activando agente…" : "Desactivando agente…", "info");
  try {
    state.agent = turnOn ? await api().agent_enable() : await api().agent_disable();
    renderAgentPill();
    renderAgentWarning();
    renderOverflowAgentToggle();
    showToast(turnOn ? "Agente activo" : "Agente apagado", "ok");
  } catch (err) {
    showToast(toMessage(err), "error");
  }
}

let toastTimeout = null;
function showToast(msg, kind = "info") {
  els.toast.textContent = msg;
  els.toast.className = "toast " + kind;
  if (toastTimeout) clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => els.toast.classList.add("hidden"), 4500);
}

function toMessage(err) {
  if (!err) return "Error desconocido";
  if (typeof err === "string") return err;
  return err.message || err.toString();
}

function truncate(s, max) {
  if (!s) return "";
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
