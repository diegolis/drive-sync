"use strict";

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
  } catch (err) {
    console.error("pollTick failed:", err);
  }
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
    els.overflowRemotes.textContent = "No accounts connected";
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
  $(".job-arrow", node).textContent = "⇄";
  $(".job-dest", node).textContent = describeTarget(job);
  $(".job-status", node).className = "job-status " + jobStatusClass(job);
  $(".job-status", node).textContent = jobStatusText(job);
  const syncBtn = $(".action-sync", node);
  if (job.needs_baseline) syncBtn.textContent = "First sync";
  syncBtn.addEventListener("click", () => runJob(job, false, false));
  $(".action-dry", node).addEventListener("click", () => runJob(job, true, false));
  $(".action-more", node).addEventListener("click", () => openDetailModal(job));
  return node;
}

function describeTarget(job) {
  const remote = state.remotesDetailed.find((r) => r.name === job.remote_name);
  const accountLabel = remote ? remote.label : job.remote_name;
  return `${accountLabel} · ${job.remote_path || "(root)"}`;
}

function jobStatusClass(job) {
  if (job._running) return "running";
  if (job.needs_baseline) return "warn";
  if (job.last_status === "ok") return "ok";
  if (job.last_status === "error") return "danger";
  return "";
}

function jobStatusText(job) {
  if (job._running) return "Running…";
  if (job.needs_baseline) return "First sync pending";
  if (!job.last_status) return "No runs yet";
  const verb = job.last_status === "ok" ? "OK" : "Error";
  return `${verb} · ${formatTime(job.last_run_at)}`;
}

function formatTime(ts) {
  if (!ts) return "never";
  const d = new Date(ts.replace(" ", "T") + "Z");
  if (isNaN(d.getTime())) return ts;
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return d.toLocaleDateString();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function openJobModal(job = null) {
  if (state.remotes.length === 0) {
    showToast("Connect a Drive account first", "info");
    startConnectDrive();
    return;
  }
  $("#job-modal-title").textContent = job ? `Edit ${job.name}` : "New sync";
  els.jobForm.reset();
  els.jobForm.dataset.id = job ? job.id : "";
  if (job) {
    els.jobForm.elements.name.value = job.name;
    els.jobForm.elements.local_path.value = job.local_path;
    els.jobForm.elements.remote_name.value = job.remote_name;
    els.jobForm.elements.remote_path.value = job.remote_path;
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
    showToast("Pick an account first", "warn");
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
  els.folderPickerList.innerHTML = '<div class="muted">Loading…</div>';
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
    els.folderPickerList.innerHTML = '<div class="muted">(no subfolders)</div>';
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
  const name = prompt("Name for the new folder:");
  if (!name || !name.trim()) return;
  const clean = name.trim();
  const target = state.picker.path ? `${state.picker.path}/${clean}` : clean;
  try {
    await api().make_remote_folder(state.picker.remoteName, target);
    state.picker.path = target;
    await loadPickerPath();
    showToast(`Folder "${clean}" created`, "ok");
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
    showToast(data.id ? "Changes saved" : "Sync created", "ok");
    await refreshJobs();
    await autoInitIfNeeded(newId);
  } catch (err) {
    showToast(toMessage(err), "error");
  }
}

async function autoInitIfNeeded(jobId) {
  await refreshJobs();
  const job = state.jobs.find((j) => j.id === jobId);
  if (!job || !job.needs_baseline) return;
  showToast("Running first sync (merging both folders)…", "info");
  await runJob(job, false, false);
}

function formToJobPayload(form) {
  return {
    id: form.dataset.id ? Number(form.dataset.id) : null,
    name: form.elements.name.value,
    local_path: form.elements.local_path.value,
    remote_name: form.elements.remote_name.value,
    remote_path: form.elements.remote_path.value,
    interval_minutes: Number(form.elements.interval_minutes.value || 15),
    auto_sync: form.elements.auto_sync.checked,
    excludes: form.elements.excludes.value,
  };
}

async function runJob(job, dryRun, resync) {
  setJobRunning(job.id, true);
  const firstSync = job.needs_baseline;
  const label = dryRun ? "Dry run in progress…"
    : resync || firstSync ? "Merging both folders…"
    : "Syncing…";
  showToast(label, "info");
  try {
    const result = await api().run(job.id, dryRun, resync);
    const okLabel = dryRun ? "Dry run OK"
      : result.resync ? "Folders merged"
      : "Sync OK";
    const text = result.ok ? okLabel : `Error: ${truncate(result.summary, 200)}`;
    showToast(text, result.ok ? "ok" : "error");
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
    status.textContent = "Running…";
  }
}

async function openDetailModal(job) {
  els.detailModal.dataset.id = job.id;
  $("#detail-name").textContent = job.name;
  $("#detail-subtitle").textContent = `${job.local_path} ⇄ ${describeTarget(job)}`;
  await renderRuns(job.id);
  renderConfig(job);
  els.detailModal.showModal();
}

async function renderRuns(jobId) {
  const runs = await api().list_runs(jobId);
  if (runs.length === 0) {
    els.detailRunsList.innerHTML = '<p class="muted" style="padding:8px 0">No runs yet.</p>';
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
    ["Local folder", job.local_path],
    ["Account", accountLabel],
    ["Destination", job.remote_path || "(root)"],
    ["Auto", job.auto_sync ? `every ${job.interval_minutes} min` : "no"],
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
  if (!confirm(`Delete "${job.name}"? Your files are not touched.`)) return;
  await api().delete_job(job.id);
  els.detailModal.close();
  showToast("Deleted", "ok");
  await refreshJobs();
}

function currentDetailJob() {
  const id = Number(els.detailModal.dataset.id);
  return state.jobs.find((j) => j.id === id);
}

async function startConnectDrive() {
  showToast("Opening browser to authorize…", "info");
  try {
    const result = await api().connect_drive();
    showToast(`Account connected: ${result.name}`, "ok");
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
      showToast("Pointing to My Drive", "ok");
      return;
    }
    try {
      await api().select_shared_drive(remoteName, driveId);
      showToast("Shared Drive linked", "ok");
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
  els.agentPill.textContent = active ? "Agent on" : "Agent off";
  els.agentPill.title = active ? "Click to disable" : "Click to enable";
}

function renderAgentWarning() {
  const autoJobs = state.jobs.filter((j) => j.auto_sync);
  const shouldWarn = autoJobs.length > 0 && state.agent.available && !state.agent.active;
  if (!shouldWarn) {
    els.agentWarning.classList.add("hidden");
    return;
  }
  const noun = autoJobs.length === 1 ? "automatic sync" : "automatic syncs";
  els.agentWarningDetail.textContent = `You have ${autoJobs.length} ${noun} but they won't run.`;
  els.agentWarning.classList.remove("hidden");
}

function renderOverflowAgentToggle() {
  if (!els.overflowAgentToggle) return;
  if (!state.agent.available) {
    els.overflowAgentToggle.textContent = "Agent unavailable";
    els.overflowAgentToggle.disabled = true;
    return;
  }
  els.overflowAgentToggle.disabled = false;
  els.overflowAgentToggle.textContent = state.agent.active ? "Disable agent" : "Enable agent";
}

async function toggleAgent(forceEnable = false) {
  if (!state.agent.available) {
    showToast("Agent service unavailable", "warn");
    return;
  }
  const turnOn = forceEnable || !state.agent.active;
  showToast(turnOn ? "Enabling agent…" : "Disabling agent…", "info");
  try {
    state.agent = turnOn ? await api().agent_enable() : await api().agent_disable();
    renderAgentPill();
    renderAgentWarning();
    renderOverflowAgentToggle();
    showToast(turnOn ? "Agent on" : "Agent off", "ok");
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
  if (!err) return "Unknown error";
  if (typeof err === "string") return err;
  return err.message || err.toString();
}

function truncate(s, max) {
  if (!s) return "";
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
