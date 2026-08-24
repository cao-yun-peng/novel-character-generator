"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  apiKey: "",
  capabilities: null,
  file: null,
  novel: null,
  run: null,
  pollTimer: null,
  characters: [],
  selectedCharacter: null,
  timelines: [],
  details: null,
};

const terminalRunStates = new Set(["succeeded", "failed", "cancelled"]);
const completedStepStates = new Set(["succeeded", "completed"]);
const runningStepStates = new Set(["claimed", "running"]);

class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortId(value) {
  if (!value) return "—";
  return `${String(value).slice(0, 8)}…`;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function humanStatus(value) {
  const labels = {
    queued: "排队中",
    claimed: "已领取",
    running: "执行中",
    retry_scheduled: "等待重试",
    waiting_approval: "等待审核",
    succeeded: "已完成",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    uploaded: "已上传",
    active: "有效",
    draft: "草稿",
    approved: "已批准",
  };
  return labels[value] || value || "未知";
}

function toast(message, type = "info") {
  const item = document.createElement("div");
  item.className = `toast${type === "error" ? " error" : ""}`;
  item.textContent = message;
  $("#toast-region").append(item);
  window.setTimeout(() => item.remove(), 4200);
}

function setBusy(button, busy, busyLabel) {
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? busyLabel : button.dataset.label;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.apiKey) headers.set("X-API-Key", state.apiKey);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const code = payload?.code || `http_${response.status}`;
    const message = payload?.message || payload || "请求失败";
    throw new ApiError(message, response.status, code);
  }
  return payload;
}

function apiErrorMessage(error) {
  if (error instanceof ApiError) {
    if (error.code === "invalid_api_key") return "API Key 无效，请在左侧重新连接。";
    if (error.code === "novel_not_chunked") return "小说尚未完成分块，请等待 Worker。";
    if (error.code === "appearance_conflicts_unresolved") return "角色档案仍有冲突，需要先审核。";
    return `${error.code}：${error.message}`;
  }
  return error?.message || "未知错误";
}

async function loadCapabilities() {
  const banner = $("#capability-banner");
  const connection = $("#connection-state");
  banner.className = "capability-banner loading";
  banner.querySelector("strong").textContent = "正在读取运行能力";
  banner.querySelector("p").textContent = "页面会按照 FastAPI 的能力声明开启或关闭操作。";
  try {
    const capabilities = await api("/api/v1/capabilities");
    state.capabilities = capabilities;
    banner.className = "capability-banner ready";
    banner.querySelector("strong").textContent = "FastAPI 已连接";
    banner.querySelector("p").textContent = capabilities.image_generation
      ? "文本分析与 2D 图像能力均已启用。"
      : "文本分析可用；2D 图像后端尚未启用，页面会保持只读提示。";
    $("#capability-chips").innerHTML = [
      ["TXT", capabilities.source_formats?.includes("txt")],
      ["角色提取", capabilities.extraction],
      ["外观聚合", capabilities.appearance_aggregation],
      ["任务恢复", capabilities.run_events_sse],
      ["人工审核", capabilities.human_approvals],
      ["2D 图像", capabilities.image_generation],
    ].map(([label, enabled]) => `<span class="capability-chip ${enabled ? "" : "off"}">${escapeHtml(label)} · ${enabled ? "ON" : "OFF"}</span>`).join("");
    connection.innerHTML = '<span class="status-dot online"></span><span>已连接，能力声明有效</span>';
    $("#footer-state").textContent = "API 在线";
    updateGenerationAvailability();
  } catch (error) {
    state.capabilities = null;
    banner.className = "capability-banner error";
    banner.querySelector("strong").textContent = "无法读取 API 能力";
    banner.querySelector("p").textContent = error.status === 401
      ? "当前服务需要 API Key，请在左侧填写后重试。"
      : apiErrorMessage(error);
    $("#capability-chips").innerHTML = "";
    connection.innerHTML = '<span class="status-dot error"></span><span>连接失败或需要认证</span>';
    $("#footer-state").textContent = "API 未连接";
    updateGenerationAvailability();
  }
}

function chooseFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".txt")) {
    toast("请选择 TXT 文件。", "error");
    return;
  }
  state.file = file;
  $("#file-name").textContent = file.name;
  $("#file-size").textContent = `${formatBytes(file.size)} · ${file.type || "text/plain"}`;
  $("#file-summary").classList.remove("hidden");
  $("#upload-button").disabled = false;
  $("#upload-feedback").textContent = "文件只会在点击上传后发送到 FastAPI";
  $("#upload-status").textContent = "文件已选择";
}

function removeFile() {
  state.file = null;
  $("#novel-file").value = "";
  $("#file-summary").classList.add("hidden");
  $("#upload-button").disabled = true;
  $("#upload-feedback").textContent = "请选择 UTF-8 TXT 文件";
  $("#upload-status").textContent = "等待文件";
}

async function uploadNovel() {
  if (!state.file) return;
  const button = $("#upload-button");
  setBusy(button, true, "正在上传…");
  const body = new FormData();
  body.append("file", state.file);
  try {
    state.novel = await api("/api/v1/novels", { method: "POST", body });
    renderNovelSummary();
    $("#upload-status").textContent = "上传完成";
    $("#upload-feedback").textContent = `项目 ${shortId(state.novel.id)} 已建立`;
    $("#analyse-button").disabled = false;
    setStage("analyse");
    toast("小说上传成功，可以开始分析角色。 ");
  } catch (error) {
    $("#upload-status").textContent = "上传失败";
    $("#upload-status").classList.add("error");
    toast(apiErrorMessage(error), "error");
  } finally {
    setBusy(button, false);
    button.disabled = state.novel !== null;
  }
}

function renderNovelSummary() {
  const summary = $("#novel-summary");
  if (!state.novel) return;
  summary.classList.remove("empty");
  summary.innerHTML = `
    <span class="summary-icon">书</span>
    <div>
      <strong>${escapeHtml(state.novel.title)}</strong>
      <p>状态：${escapeHtml(humanStatus(state.novel.status))}</p>
      <code>${escapeHtml(state.novel.id)}</code>
    </div>`;
}

async function startAnalysis() {
  if (!state.novel) return;
  const button = $("#analyse-button");
  setBusy(button, true, "正在创建任务…");
  try {
    state.run = await api(`/api/v1/novels/${state.novel.id}/runs`, {
      method: "POST",
      headers: { "Idempotency-Key": `ui-analysis-${state.novel.id}` },
    });
    $("#refresh-run-button").disabled = false;
    renderRun();
    beginPolling();
    toast("分析任务已创建，Worker 将异步处理。 ");
  } catch (error) {
    toast(apiErrorMessage(error), "error");
    setBusy(button, false);
  }
}

async function refreshRun() {
  if (!state.run) return;
  try {
    state.run = await api(`/api/v1/runs/${state.run.id}`);
    renderRun();
    if (terminalRunStates.has(state.run.status)) {
      stopPolling();
      if (state.run.status === "succeeded") await afterAnalysisSucceeded();
    }
  } catch (error) {
    stopPolling();
    toast(apiErrorMessage(error), "error");
  }
}

function beginPolling() {
  stopPolling();
  refreshRun();
  state.pollTimer = window.setInterval(refreshRun, 1200);
}

function stopPolling() {
  if (state.pollTimer) window.clearInterval(state.pollTimer);
  state.pollTimer = null;
}

function renderRun() {
  if (!state.run) return;
  const steps = state.run.steps || [];
  const completed = steps.filter((step) => completedStepStates.has(step.status)).length;
  const total = Math.max(steps.length, 2);
  const terminal = terminalRunStates.has(state.run.status);
  const percent = state.run.status === "succeeded" ? 100 : Math.round((completed / total) * 100);
  const status = $("#run-status");
  status.textContent = humanStatus(state.run.status);
  status.className = `panel-status${state.run.status === "failed" ? " error" : terminal ? "" : " muted"}`;
  $("#run-progress-label").textContent = terminal ? `任务${humanStatus(state.run.status)}` : "Worker 正在推进步骤";
  $("#run-progress-percent").textContent = `${percent}%`;
  $("#run-progress-bar").style.width = `${percent}%`;
  $("#step-list").innerHTML = steps.length
    ? steps.map((step, index) => {
        const className = completedStepStates.has(step.status) ? "complete" : runningStepStates.has(step.status) ? "running" : step.status === "failed" ? "failed" : "";
        const icon = className === "complete" ? "✓" : className === "failed" ? "!" : index + 1;
        return `<div class="run-step ${className}"><span class="step-state">${icon}</span><strong>${escapeHtml(step.step_key)}</strong><small>${escapeHtml(humanStatus(step.status))} · attempt ${escapeHtml(step.attempt)}</small></div>`;
      }).join("")
    : '<div class="empty-state compact">等待 Worker 创建和推进步骤</div>';
  $("#analyse-button").disabled = true;
  $("#analyse-button").textContent = terminal ? "分析任务已创建" : "分析进行中…";
}

async function afterAnalysisSucceeded() {
  if (state.characters.length) return;
  await Promise.all([loadCharacters(), loadTimelines()]);
  setStage("select");
  toast(`分析完成，识别到 ${state.characters.length} 个角色。`);
}

async function loadCharacters() {
  if (!state.novel) return;
  state.characters = await api(`/api/v1/novels/${state.novel.id}/characters`);
  $("#character-count").textContent = state.characters.length;
  renderCharacterList();
  renderGenerationCharacterOptions();
}

function renderCharacterList() {
  const list = $("#character-list");
  if (!state.characters.length) {
    list.innerHTML = '<div class="empty-state"><span class="empty-orbit"></span><strong>没有识别到角色</strong><p>检查提取步骤和 Provider 输出后重试。</p></div>';
    return;
  }
  list.innerHTML = state.characters.map((character) => `
    <button class="character-card" type="button" data-character-id="${escapeHtml(character.id)}">
      <span class="avatar">${escapeHtml(character.canonical_name.slice(0, 1))}</span>
      <span><strong>${escapeHtml(character.canonical_name)}</strong><small>${escapeHtml(humanStatus(character.status))} · revision ${escapeHtml(character.revision)}</small></span>
      <span class="arrow">›</span>
    </button>`).join("");
  $$(".character-card").forEach((button) => button.addEventListener("click", () => selectCharacter(button.dataset.characterId)));
}

async function selectCharacter(characterId) {
  const character = state.characters.find((item) => item.id === characterId);
  if (!character) return;
  state.selectedCharacter = character;
  $$(".character-card").forEach((button) => button.classList.toggle("active", button.dataset.characterId === characterId));
  $("#generation-character").value = characterId;
  $("#character-detail").innerHTML = '<div class="empty-state"><span class="portrait-placeholder">…</span><strong>正在加载角色证据</strong></div>';
  try {
    const [observations, expressions, states, conflicts] = await Promise.all([
      api(`/api/v1/characters/${characterId}/observations`),
      api(`/api/v1/characters/${characterId}/expressions`),
      api(`/api/v1/characters/${characterId}/appearance-states`),
      api(`/api/v1/characters/${characterId}/conflicts`),
    ]);
    state.details = { observations, expressions, states, conflicts };
    renderCharacterDetail();
    renderStageOptions();
    setStage("generate");
    updateGenerationAvailability();
  } catch (error) {
    toast(apiErrorMessage(error), "error");
  }
}

function renderCharacterDetail() {
  const character = state.selectedCharacter;
  const details = state.details;
  if (!character || !details) return;
  const facts = details.observations.slice(0, 8);
  const body = facts.length
    ? `<div class="facts-grid">${facts.map((fact) => `
        <div class="fact-card">
          <small>${escapeHtml(fact.field_path)}</small>
          <strong>${escapeHtml(typeof fact.value === "string" ? fact.value : JSON.stringify(fact.value))}</strong>
          <em title="${escapeHtml(fact.evidence_quote || "无引用")}">“${escapeHtml(fact.evidence_quote || "暂无原文引用")}”</em>
          <span class="confidence">置信度 ${Math.round(Number(fact.confidence || 0) * 100)}%</span>
        </div>`).join("")}</div>`
    : '<div class="empty-state compact">该角色还没有可展示的外观事实。</div>';
  $("#character-detail").innerHTML = `
    <div class="detail-head">
      <span class="avatar">${escapeHtml(character.canonical_name.slice(0, 1))}</span>
      <div><h3>${escapeHtml(character.canonical_name)}</h3><p>ID ${escapeHtml(shortId(character.id))} · revision ${escapeHtml(character.revision)}</p></div>
    </div>
    <div class="detail-badges">
      <span class="detail-badge">事实 ${details.observations.length}</span>
      <span class="detail-badge">神情 ${details.expressions.length}</span>
      <span class="detail-badge">阶段 ${details.states.length}</span>
      <span class="detail-badge">开放冲突 ${details.conflicts.filter((item) => item.status !== "resolved").length}</span>
    </div>
    ${body}`;
}

async function loadTimelines() {
  if (!state.novel) return;
  state.timelines = await api(`/api/v1/novels/${state.novel.id}/timelines`);
  const select = $("#timeline-select");
  select.innerHTML = state.timelines.length
    ? state.timelines.map((timeline) => `<option value="${escapeHtml(timeline.id)}">${escapeHtml(timeline.name)} · ${escapeHtml(timeline.canonicality)}</option>`).join("")
    : '<option value="">暂无可用时间线</option>';
  select.disabled = !state.timelines.length;
}

function renderGenerationCharacterOptions() {
  const select = $("#generation-character");
  select.innerHTML = state.characters.length
    ? `<option value="">选择角色</option>${state.characters.map((character) => `<option value="${escapeHtml(character.id)}">${escapeHtml(character.canonical_name)}</option>`).join("")}`
    : '<option value="">请先完成角色分析</option>';
  select.disabled = !state.characters.length;
}

function renderStageOptions() {
  const select = $("#stage-select");
  const states = state.details?.states || [];
  select.innerHTML = '<option value="">自动解析</option>' + states.map((item) => `<option value="${escapeHtml(item.label || item.id)}">${escapeHtml(item.label || item.age_stage || shortId(item.id))}</option>`).join("");
  select.disabled = !states.length;
}

function updateGenerationAvailability() {
  const available = Boolean(state.capabilities?.image_generation);
  const ready = available && state.selectedCharacter && state.timelines.length;
  const badge = $("#image-feature-badge");
  const lock = $("#generation-lock");
  badge.textContent = available ? "能力已启用" : "能力未启用";
  badge.className = `feature-badge ${available ? "available" : "unavailable"}`;
  lock.className = `generation-lock${available ? " ready" : ""}`;
  lock.innerHTML = available
    ? "<strong>图像后端已就绪</strong><p>选择角色和时间线后可以创建候选图任务；最终锁定仍需要人工审核。</p>"
    : "<strong>图像后端尚未接入</strong><p>页面已准备好请求结构；完成 Image Provider 与防漂移链路后，会由 capability 自动解锁。</p>";
  $("#generate-button").disabled = !ready;
}

async function generateImages(event) {
  event.preventDefault();
  if (!state.capabilities?.image_generation || !state.selectedCharacter) return;
  const button = $("#generate-button");
  setBusy(button, true, "正在创建图像任务…");
  const stage = $("#stage-select").value;
  const request = {
    timeline_id: $("#timeline-select").value,
    target_event_id: null,
    target_scene_id: null,
    target_chapter_ordinal: null,
    stage_keys: stage ? [stage] : [],
    candidate_count: Number($("#candidate-count").value),
    generate_character_sheet: $("#character-sheet").checked,
    render_overrides: {},
    budget_limit: Number($("#budget-limit").value).toFixed(2),
  };
  try {
    const imageRun = await api(`/api/v1/characters/${state.selectedCharacter.id}/image-runs`, {
      method: "POST",
      headers: { "Idempotency-Key": `ui-image-${crypto.randomUUID()}` },
      body: JSON.stringify(request),
    });
    renderImageRunPending(imageRun);
    toast("2D 图像任务已经创建。 ");
  } catch (error) {
    toast(apiErrorMessage(error), "error");
    setBusy(button, false);
    updateGenerationAvailability();
  }
}

function renderImageRunPending(imageRun) {
  $("#image-gallery").innerHTML = `
    <div class="gallery-placeholder">
      <div class="placeholder-grid"><span></span><span></span><span></span><span></span></div>
      <strong>图像任务已排队</strong>
      <p>Run ${escapeHtml(shortId(imageRun.run_id || imageRun.id))}。请通过任务接口查看生成、审计与人工选择进度。</p>
    </div>`;
}

function setStage(stage) {
  const order = ["upload", "analyse", "select", "generate"];
  const activeIndex = order.indexOf(stage);
  $$(".progress-rail li").forEach((item, index) => {
    item.classList.toggle("active", index === activeIndex);
    item.classList.toggle("complete", index < activeIndex);
  });
}

function resetPage() {
  stopPolling();
  state.file = null;
  state.novel = null;
  state.run = null;
  state.characters = [];
  state.selectedCharacter = null;
  state.details = null;
  state.timelines = [];
  window.location.reload();
}

function bindEvents() {
  $("#connect-button").addEventListener("click", () => {
    state.apiKey = $("#api-key").value.trim();
    loadCapabilities();
  });
  $("#toggle-key").addEventListener("click", () => {
    const input = $("#api-key");
    input.type = input.type === "password" ? "text" : "password";
    $("#toggle-key").textContent = input.type === "password" ? "显示" : "隐藏";
  });
  $("#novel-file").addEventListener("change", (event) => chooseFile(event.target.files?.[0]));
  $("#drop-zone").addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      $("#novel-file").click();
    }
  });
  for (const eventName of ["dragenter", "dragover"]) {
    $("#drop-zone").addEventListener(eventName, (event) => {
      event.preventDefault();
      $("#drop-zone").classList.add("dragover");
    });
  }
  for (const eventName of ["dragleave", "drop"]) {
    $("#drop-zone").addEventListener(eventName, (event) => {
      event.preventDefault();
      $("#drop-zone").classList.remove("dragover");
    });
  }
  $("#drop-zone").addEventListener("drop", (event) => chooseFile(event.dataTransfer?.files?.[0]));
  $("#remove-file").addEventListener("click", (event) => { event.preventDefault(); removeFile(); });
  $("#upload-button").addEventListener("click", uploadNovel);
  $("#analyse-button").addEventListener("click", startAnalysis);
  $("#refresh-run-button").addEventListener("click", refreshRun);
  $("#generation-character").addEventListener("change", (event) => selectCharacter(event.target.value));
  $("#generation-form").addEventListener("submit", generateImages);
  $("#reset-button").addEventListener("click", resetPage);
}

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  loadCapabilities();
});
