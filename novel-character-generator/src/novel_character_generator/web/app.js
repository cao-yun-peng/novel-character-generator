"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  apiKey: "",
  capabilities: null,
  projects: [],
  file: null,
  novel: null,
  run: null,
  pollTimer: null,
  indexPollTimer: null,
  characters: [],
  selectedCharacter: null,
  timelines: [],
  details: null,
  approvals: [],
  approvalNextCursor: null,
  renderProfile: null,
  visualFieldGaps: null,
  enrichmentRuns: [],
  enrichmentRun: null,
  enrichmentEvidence: null,
  enrichmentPollTimer: null,
  loadedChunkOrdinal: -1,
  restartAfterCancel: false,
};

const terminalRunStates = new Set(["succeeded", "failed", "cancelled"]);
const completedStepStates = new Set(["succeeded", "completed"]);
const runningStepStates = new Set(["claimed", "running"]);
const groundingPriority = { exact: 0, manually_grounded: 0, fuzzy: 1, ungrounded: 2 };
const visualFieldGroupLabels = {
  hair: "头发",
  face: "面部",
  body: "身体与肤色",
  clothing: "服装",
  accessories: "配饰",
  marks_injuries: "标记与伤势",
  disguise_cleanliness: "伪装与整洁",
};

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

function formatTimestamp(value) {
  if (!value) return "未知时间";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
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
    building: "构建中",
    ready: "已就绪",
    degraded_lexical_only: "仅关键词索引",
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
    const detail = typeof payload?.detail === "string" ? payload.detail : null;
    const code = payload?.code || detail || `http_${response.status}`;
    const message = payload?.message || detail || payload || "请求失败";
    throw new ApiError(message, response.status, code);
  }
  return payload;
}

function apiErrorMessage(error) {
  if (error instanceof ApiError) {
    if (error.code === "invalid_api_key") return "API Key 无效，请在左侧重新连接。";
    if (error.code === "admin_api_key_required" || error.status === 403) return "该操作需要 ADMIN_API_KEY。";
    if (error.code === "novel_not_chunked") return "小说尚未完成分块，请等待 Worker。";
    if (error.code === "appearance_conflicts_unresolved") return "角色档案仍有冲突，需要先审核。";
    if (error.code === "retrieval_index_not_ready") return "当前源版本的混合检索索引尚未就绪。";
    if (error.code === "visual_field_gaps_empty") return "当前范围内没有需要补充的视觉字段组。";
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
      ["视觉精提取", capabilities.visual_enrichment],
      ["2D 图像", capabilities.image_generation],
    ].map(([label, enabled]) => `<span class="capability-chip ${enabled ? "" : "off"}">${escapeHtml(label)} · ${enabled ? "ON" : "OFF"}</span>`).join("");
    connection.innerHTML = '<span class="status-dot online"></span><span>已连接，能力声明有效</span>';
    $("#footer-state").textContent = "API 在线";
    updateGenerationAvailability();
    await loadProjects();
    await loadApprovals();
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

function renderProjectHistory(selectedId = state.novel?.id || "") {
  const select = $("#project-select");
  select.innerHTML = state.projects.length
    ? `<option value="">选择一本已上传小说</option>${state.projects.map((project) => `
        <option value="${escapeHtml(project.id)}"${project.id === selectedId ? " selected" : ""}>
          ${escapeHtml(project.title)} · ${escapeHtml(humanStatus(project.status))} · ${escapeHtml(formatTimestamp(project.updated_at))}
        </option>`).join("")}`
    : '<option value="">暂无历史项目</option>';
  select.disabled = !state.projects.length;
  $("#open-project-button").disabled = !select.value;
  $("#refresh-projects-button").disabled = false;
  $("#project-history-feedback").textContent = state.projects.length
    ? `找到 ${state.projects.length} 个项目；刷新页面后仍可从这里继续。`
    : "数据库中还没有小说，可以先上传 TXT。";
}

async function loadProjects(selectedId = state.novel?.id || "") {
  const refreshButton = $("#refresh-projects-button");
  setBusy(refreshButton, true, "正在读取…");
  try {
    state.projects = await api("/api/v1/novels?limit=50");
    renderProjectHistory(selectedId);
  } catch (error) {
    state.projects = [];
    renderProjectHistory();
    $("#project-history-feedback").textContent = apiErrorMessage(error);
  } finally {
    setBusy(refreshButton, false);
    refreshButton.disabled = state.capabilities === null;
  }
}

function resetProjectWorkspace() {
  stopPolling();
  stopIndexPolling();
  state.run = null;
  state.characters = [];
  state.selectedCharacter = null;
  state.details = null;
  state.timelines = [];
  state.renderProfile = null;
  state.visualFieldGaps = null;
  state.enrichmentRuns = [];
  state.enrichmentRun = null;
  state.enrichmentEvidence = null;
  stopEnrichmentPolling();
  state.loadedChunkOrdinal = -1;
  state.restartAfterCancel = false;
  $("#character-count").textContent = "0";
  renderCharacterList();
  renderGenerationCharacterOptions();
  $("#character-detail").innerHTML = '<div class="empty-state"><span class="portrait-placeholder" aria-hidden="true">?</span><strong>选择一个角色</strong><p>这里将展示外观事实、证据与阶段状态。</p></div>';
  renderCharacterReview();
}

function renderNoRun() {
  $("#run-status").textContent = "尚未创建";
  $("#run-status").className = "panel-status muted";
  $("#run-progress-label").textContent = "等待创建任务";
  $("#run-progress-percent").textContent = "0%";
  $("#run-progress-bar").style.width = "0%";
  $("#step-list").innerHTML = '<div class="empty-state compact">点击开始分析后显示 Worker 步骤</div>';
  $("#analyse-button").disabled = false;
  $("#analyse-button").textContent = "开始分析角色";
  $("#restart-run-button").disabled = true;
  $("#cancel-run-button").disabled = true;
  $("#cancel-run-button").textContent = "停止任务";
  $("#refresh-run-button").disabled = true;
}

async function openProject(novelId = $("#project-select").value) {
  if (!novelId) return;
  const button = $("#open-project-button");
  setBusy(button, true, "正在打开…");
  try {
    resetProjectWorkspace();
    const [novel, runs] = await Promise.all([
      api(`/api/v1/novels/${novelId}`),
      api(`/api/v1/novels/${novelId}/runs?limit=20`),
    ]);
    state.novel = novel;
    renderNovelSummary();
    renderProjectHistory(novelId);
    $("#upload-status").textContent = "已打开历史项目";
    $("#upload-feedback").textContent = "这里只恢复已有状态，不会自动启动任务；可继续查看或手动重启分析";
    setStage("analyse");
    const analysisRun = runs.find((run) => ["text_analysis", "character_extraction", "text_ingestion"].includes(run.run_type));
    if (!analysisRun) {
      renderNoRun();
      await loadCharacters();
      return;
    }
    state.run = await api(`/api/v1/runs/${analysisRun.id}`);
    $("#refresh-run-button").disabled = false;
    renderRun();
    await loadPartialAnalysis();
    if (state.run.status === "succeeded") {
      await afterAnalysisSucceeded();
    } else if (!terminalRunStates.has(state.run.status)) {
      beginPolling();
    }
    toast(`已打开项目：${state.novel.title}`);
  } catch (error) {
    toast(apiErrorMessage(error), "error");
  } finally {
    setBusy(button, false);
    button.disabled = !$("#project-select").value;
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
    const uploaded = await api("/api/v1/novels", { method: "POST", body });
    state.novel = await api(`/api/v1/novels/${uploaded.id}`);
    await loadProjects(state.novel.id);
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
  const indexStatus = state.novel.retrieval_index_status || "missing";
  const indexing = ["queued", "building"].includes(indexStatus);
  const indexReady = indexStatus === "ready";
  const indexLabel = indexStatus === "missing" ? "尚未构建" : humanStatus(indexStatus);
  summary.innerHTML = `
    <span class="summary-icon">书</span>
    <div class="summary-copy">
      <strong>${escapeHtml(state.novel.title)}</strong>
      <p>状态：${escapeHtml(humanStatus(state.novel.status))}</p>
      <p>精细索引：${escapeHtml(indexLabel)} · ${escapeHtml(state.novel.retrieval_passage_count || 0)} 个 passage</p>
      <code>${escapeHtml(state.novel.id)}</code>
    </div>
    <div class="summary-actions">
      <button class="button button-secondary" id="build-index-button" type="button"${indexing || indexReady ? " disabled" : ""}>
        ${indexing ? "正在构建…" : indexReady ? "精细索引已就绪" : indexStatus === "degraded_lexical_only" ? "需要配置 Embedding" : "构建精细索引"}
      </button>
      <small>${indexStatus === "degraded_lexical_only" ? "关键词切分已保存，但视觉精提取仍需向量索引" : indexReady ? "可以在角色页执行视觉精提取" : "复用原始文本，不重跑角色抽取"}</small>
    </div>`;
  const buildButton = $("#build-index-button");
  if (buildButton && !buildButton.disabled) {
    buildButton.addEventListener("click", () => ensureRetrievalIndex(buildButton));
  }
}

function stopIndexPolling() {
  if (state.indexPollTimer) window.clearTimeout(state.indexPollTimer);
  state.indexPollTimer = null;
}

async function ensureRetrievalIndex(button) {
  if (!state.novel) return;
  if (!state.capabilities?.retrieval_hybrid_index) {
    toast("当前未配置 Embedding。请先配置向量模型并重启 API/Worker，避免只生成不能用于视觉精提取的关键词索引。", "error");
    return;
  }
  setBusy(button, true, "正在创建…");
  try {
    await api(`/api/v1/novels/${state.novel.id}/retrieval-index-runs`, { method: "POST" });
    toast("精细索引任务已创建；不会重跑或覆盖已有角色事实。");
    stopIndexPolling();
    await pollRetrievalIndex();
  } catch (error) {
    toast(apiErrorMessage(error), "error");
    setBusy(button, false);
  }
}

async function pollRetrievalIndex() {
  if (!state.novel) return;
  try {
    state.novel = await api(`/api/v1/novels/${state.novel.id}`);
    renderNovelSummary();
    const status = state.novel.retrieval_index_status;
    if (["ready", "degraded_lexical_only", "failed"].includes(status)) {
      stopIndexPolling();
      if (status === "ready") {
        toast(`精细索引已就绪，共 ${state.novel.retrieval_passage_count} 个 passage。`);
      }
      return;
    }
    state.indexPollTimer = window.setTimeout(pollRetrievalIndex, 1400);
  } catch (error) {
    stopIndexPolling();
    toast(apiErrorMessage(error), "error");
  }
}

async function startAnalysis() {
  if (!state.novel) return;
  const button = $("#analyse-button");
  setBusy(button, true, "正在创建任务…");
  try {
    state.run = await api(`/api/v1/novels/${state.novel.id}/runs`, {
      method: "POST",
      headers: { "Idempotency-Key": `ui-analysis-${state.novel.id}-${crypto.randomUUID()}` },
    });
    state.characters = [];
    state.selectedCharacter = null;
    state.details = null;
    state.timelines = [];
    state.loadedChunkOrdinal = -1;
    state.restartAfterCancel = false;
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
    await loadPartialAnalysis();
    if (terminalRunStates.has(state.run.status)) {
      stopPolling();
      if (state.restartAfterCancel) {
        state.restartAfterCancel = false;
        await startAnalysis();
        return;
      }
      if (state.run.status === "succeeded") await afterAnalysisSucceeded();
    }
  } catch (error) {
    stopPolling();
    toast(apiErrorMessage(error), "error");
  }
}

async function cancelRun({ restart = false } = {}) {
  if (!state.run || terminalRunStates.has(state.run.status)) {
    if (restart) await startAnalysis();
    return;
  }
  const button = restart ? $("#restart-run-button") : $("#cancel-run-button");
  const confirmed = window.confirm(
    restart
      ? "将停止当前任务，并在安全停止后创建一个新的分析任务。是否继续？"
      : "将停止当前分析任务，已抽取的部分结果仍可查看。是否继续？",
  );
  if (!confirmed) return;

  setBusy(button, true, restart ? "正在重启…" : "正在停止…");
  state.restartAfterCancel = restart;
  try {
    state.run = await api(`/api/v1/runs/${state.run.id}/cancel`, { method: "POST" });
    renderRun();
    if (state.run.status === "cancelled") {
      if (restart) {
        state.restartAfterCancel = false;
        await startAnalysis();
      } else {
        stopPolling();
        toast("任务已停止，已抽取的部分结果仍可查看。 ");
      }
      return;
    }
    beginPolling();
    toast(restart ? "已请求停止；安全停止后会自动创建新任务。" : "已请求停止，正在等待当前调用结束。 ");
  } catch (error) {
    state.restartAfterCancel = false;
    toast(apiErrorMessage(error), "error");
  } finally {
    setBusy(button, false);
    renderRun();
  }
}

async function restartAnalysis() {
  await cancelRun({ restart: true });
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
  const expectedStepCount = 3;
  const extractionStep = steps.find((step) => step.step_key === "extract_characters");
  const extractedChunks = Number(extractionStep?.cursor?.current_chunk_ordinal || 0);
  const totalChunks = Number(state.novel?.chunk_count || 0);
  const chunkFraction = totalChunks > 0 ? Math.min(1, extractedChunks / totalChunks) : 0;
  const terminal = terminalRunStates.has(state.run.status);
  const extractionInProgress = extractionStep && !completedStepStates.has(extractionStep.status);
  const fractionalCompleted = completed + (extractionInProgress ? chunkFraction : 0);
  const percent = state.run.status === "succeeded" ? 100 : Math.round((fractionalCompleted / expectedStepCount) * 100);
  const status = $("#run-status");
  status.textContent = humanStatus(state.run.status);
  status.className = `panel-status${state.run.status === "failed" ? " error" : terminal ? "" : " muted"}`;
  $("#run-progress-label").textContent = extractionInProgress && totalChunks
    ? `角色抽取 ${extractedChunks} / ${totalChunks} 块 · 已完成部分可查看`
    : terminal ? `任务${humanStatus(state.run.status)}` : "Worker 正在推进步骤";
  $("#run-progress-percent").textContent = `${percent}%`;
  $("#run-progress-bar").style.width = `${percent}%`;
  $("#step-list").innerHTML = steps.length
    ? steps.map((step, index) => {
        const className = completedStepStates.has(step.status) ? "complete" : runningStepStates.has(step.status) ? "running" : step.status === "failed" ? "failed" : "";
        const icon = className === "complete" ? "✓" : className === "failed" ? "!" : index + 1;
        const chunkProgress = step.step_key === "extract_characters" && totalChunks
          ? ` · ${escapeHtml(step.cursor?.current_chunk_ordinal || 0)}/${escapeHtml(totalChunks)} 块`
          : "";
        return `<div class="run-step ${className}"><span class="step-state">${icon}</span><strong>${escapeHtml(step.step_key)}</strong><small>${escapeHtml(humanStatus(step.status))} · attempt ${escapeHtml(step.attempt)}${chunkProgress}</small></div>`;
      }).join("")
    : '<div class="empty-state compact">等待 Worker 创建和推进步骤</div>';
  $("#analyse-button").disabled = true;
  $("#analyse-button").textContent = terminal ? "分析任务已结束" : "分析进行中…";
  $("#restart-run-button").disabled = !terminal && state.run.cancel_requested;
  $("#restart-run-button").textContent = state.restartAfterCancel ? "停止后自动重启…" : "重启分析";
  $("#cancel-run-button").disabled = terminal || state.run.cancel_requested;
  $("#cancel-run-button").textContent = !terminal && state.run.cancel_requested ? "正在停止…" : "停止任务";
}

async function afterAnalysisSucceeded() {
  await Promise.all([loadCharacters(), loadTimelines(), loadApprovals()]);
  setStage("select");
  toast(`分析完成，识别到 ${state.characters.length} 个角色。`);
}

async function loadPartialAnalysis() {
  if (!state.run || !state.novel) return;
  const extractionStep = state.run.steps?.find((step) => step.step_key === "extract_characters");
  const completedOrdinal = Number(extractionStep?.cursor?.current_chunk_ordinal || 0);
  if (completedOrdinal <= 0 || completedOrdinal <= state.loadedChunkOrdinal) return;
  await Promise.all([loadCharacters(), loadTimelines()]);
  state.loadedChunkOrdinal = completedOrdinal;
  setStage("select");
  const terminalLabel = terminalRunStates.has(state.run.status) ? `（任务${humanStatus(state.run.status)}）` : "";
  $("#character-review-state").textContent = `已加载前 ${completedOrdinal} 块的部分结果${terminalLabel}`;
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

async function fetchRenderProfile(characterId) {
  try {
    return await api(`/api/v1/characters/${characterId}/render-profile`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

async function selectCharacter(characterId) {
  const character = state.characters.find((item) => item.id === characterId);
  if (!character) return;
  state.selectedCharacter = character;
  $$(".character-card").forEach((button) => button.classList.toggle("active", button.dataset.characterId === characterId));
  $("#generation-character").value = characterId;
  $("#character-detail").innerHTML = '<div class="empty-state"><span class="portrait-placeholder">…</span><strong>正在加载角色证据</strong></div>';
  try {
    const [observations, expressions, relations, states, conflicts, renderProfile] = await Promise.all([
      api(`/api/v1/characters/${characterId}/observations`),
      api(`/api/v1/characters/${characterId}/expressions`),
      api(`/api/v1/characters/${characterId}/relations`),
      api(`/api/v1/characters/${characterId}/appearance-states`),
      api(`/api/v1/characters/${characterId}/conflicts`),
      fetchRenderProfile(characterId),
    ]);
    state.details = { observations, expressions, relations, states, conflicts };
    state.renderProfile = renderProfile;
    renderCharacterDetail();
    await loadVisualEnrichmentState();
    renderCharacterReview();
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
  const orderedFacts = [...details.observations].sort((left, right) => {
    if (Boolean(left.is_visual) !== Boolean(right.is_visual)) return left.is_visual ? -1 : 1;
    const grounding = (groundingPriority[left.grounding_status] ?? 9) - (groundingPriority[right.grounding_status] ?? 9);
    if (grounding) return grounding;
    const chapter = Number(left.chapter_ordinal ?? Number.MAX_SAFE_INTEGER) - Number(right.chapter_ordinal ?? Number.MAX_SAFE_INTEGER);
    if (chapter) return chapter;
    return String(left.field_path).localeCompare(String(right.field_path), "zh-CN");
  });
  const visualFacts = orderedFacts.filter((fact) => fact.is_visual).slice(0, 24);
  const otherFacts = orderedFacts.filter((fact) => !fact.is_visual).slice(0, 8);
  const body = visualFacts.length || otherFacts.length
    ? `${renderFactSection("形象事实", visualFacts, "优先用于外观阶段与图像生成")}${renderFactSection("其他人物事实", otherFacts, "仅展示置信度最高、时间最早的部分记录")}`
    : '<div class="empty-state compact">该角色还没有可展示的事实。</div>';
  const aggregationStep = state.run?.steps?.find((step) => step.step_key === "aggregate_appearance");
  const aggregationEvaluated = Boolean(aggregationStep && completedStepStates.has(aggregationStep.status));
  const aggregationPending = !aggregationEvaluated;
  const conflictLabel = aggregationPending
    ? "冲突尚未评估"
    : details.states.length
      ? `开放冲突 ${details.conflicts.filter((item) => item.status !== "resolved").length}`
      : "已评估 · 无外观阶段";
  $("#character-detail").innerHTML = `
    <div class="detail-head">
      <span class="avatar">${escapeHtml(character.canonical_name.slice(0, 1))}</span>
      <div><h3>${escapeHtml(character.canonical_name)}</h3><p>ID ${escapeHtml(shortId(character.id))} · revision ${escapeHtml(character.revision)}</p></div>
    </div>
    <div class="detail-badges">
      <span class="detail-badge">事实 ${details.observations.length}</span>
      <span class="detail-badge">形象 ${details.observations.filter((item) => item.is_visual).length}</span>
      <span class="detail-badge">神情 ${details.expressions.length}</span>
      <span class="detail-badge">关系 ${details.relations.length}</span>
      <span class="detail-badge">阶段 ${details.states.length}</span>
      <span class="detail-badge${aggregationPending ? " warning" : ""}">${conflictLabel}</span>
    </div>
    ${body}
    ${renderRelationSection(details.relations)}
    <section class="visual-enrichment-panel" id="visual-enrichment-panel">
      <div class="empty-state compact">正在计算字段缺口…</div>
    </section>`;
}

function renderRelationSection(relations) {
  if (!relations?.length) return "";
  const labels = {
    father: "父亲",
    mother: "母亲",
    parent: "父母",
    son: "儿子",
    daughter: "女儿",
    child: "孩子",
    spouse: "配偶",
    husband: "丈夫",
    wife: "妻子",
    brother: "兄弟",
    sister: "姐妹",
  };
  return `
    <section class="fact-section relation-section">
      <div class="fact-section-head"><div><h4>人物关系</h4><p>关系两端均绑定到规范人物实体，并保留原文证据。</p></div><span>${relations.length} 条</span></div>
      <div class="facts-grid">${relations.map((relation) => {
        const relationLabel = labels[relation.relation_type] || relation.relation_type;
        const arrow = relation.direction === "outgoing"
          ? `${relation.source_character_name} → ${relationLabel} → ${relation.target_character_name}`
          : `${relation.source_character_name} → ${relationLabel} → ${relation.target_character_name}`;
        const chapter = relation.chapter_ordinal === null || relation.chapter_ordinal === undefined
          ? "章节未知"
          : `第 ${relation.chapter_ordinal} 章`;
        return `<article class="fact-card relation"><small>${escapeHtml(relation.relation_type)}</small><strong>${escapeHtml(arrow)}</strong><div class="fact-meta"><span>${escapeHtml(chapter)}</span><span>${escapeHtml(relation.grounding_status)}</span></div><em>“${escapeHtml(relation.evidence_quote)}”</em><span class="confidence">置信度 ${Math.round(Number(relation.confidence || 0) * 100)}%</span></article>`;
      }).join("")}</div>
    </section>`;
}

function stopEnrichmentPolling() {
  if (state.enrichmentPollTimer) window.clearTimeout(state.enrichmentPollTimer);
  state.enrichmentPollTimer = null;
}

async function loadVisualEnrichmentState(lifePhaseKey = "") {
  const character = state.selectedCharacter;
  if (!character) return;
  stopEnrichmentPolling();
  try {
    const phaseQuery = lifePhaseKey ? `?life_phase_key=${encodeURIComponent(lifePhaseKey)}` : "";
    const [gapPlan, runs] = await Promise.all([
      api(`/api/v1/characters/${character.id}/visual-field-gaps${phaseQuery}`),
      api(`/api/v1/characters/${character.id}/visual-enrichment-runs`),
    ]);
    if (state.selectedCharacter?.id !== character.id) return;
    state.visualFieldGaps = gapPlan;
    state.enrichmentRuns = runs;
    state.enrichmentRun = runs.length ? await api(`/api/v1/runs/${runs[0].id}`) : null;
    state.enrichmentEvidence = null;
    if (state.enrichmentRun) {
      try {
        state.enrichmentEvidence = await api(`/api/v1/visual-enrichment-runs/${state.enrichmentRun.id}/evidence`);
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 404) throw error;
      }
    }
    renderVisualEnrichmentPanel();
    if (state.enrichmentRun && !terminalRunStates.has(state.enrichmentRun.status)) {
      state.enrichmentPollTimer = window.setTimeout(pollVisualEnrichmentRun, 1400);
    }
  } catch (error) {
    renderVisualEnrichmentPanel(apiErrorMessage(error));
  }
}

function renderVisualEnrichmentPanel(errorMessage = "") {
  const host = $("#visual-enrichment-panel");
  if (!host) return;
  if (errorMessage) {
    host.innerHTML = `<div class="empty-state compact">${escapeHtml(errorMessage)}</div>`;
    return;
  }
  const plan = state.visualFieldGaps;
  if (!plan) {
    host.innerHTML = '<div class="empty-state compact">正在计算字段缺口…</div>';
    return;
  }
  const currentPhase = plan.life_phase_key || "";
  const ready = plan.retrieval_index_status === "ready" && state.capabilities?.visual_enrichment;
  const groups = plan.groups || [];
  const recommended = new Set(plan.recommended_field_groups || []);
  const run = state.enrichmentRun;
  const runSteps = run?.steps || [];
  const enrichmentOutcome = visualEnrichmentOutcome(run);
  const runStatusLabel = enrichmentOutcome.resultStatus === "no_valid_results"
    ? "完成但无有效结果"
    : enrichmentOutcome.resultStatus === "suggestions_pending"
      ? "完成，建议待审核"
      : humanStatus(run?.status);
  const availabilityMessage = plan.retrieval_index_status !== "ready"
    ? "需要当前源版本的混合索引达到 ready"
    : !state.capabilities?.visual_enrichment
      ? "部署尚未配置可用的 Embedding Provider"
      : recommended.size
        ? `推荐补齐 ${recommended.size} 组`
        : "当前范围没有字段缺口";
  host.innerHTML = `
    <div class="enrichment-head">
      <div><h4>检索增强视觉精提取</h4><p>服务端按当前事实自动规划缺失字段；可取消不需要的字段组。</p></div>
      <span class="index-status ${ready ? "ready" : "warning"}">索引 ${escapeHtml(plan.retrieval_index_status)}</span>
    </div>
    <div class="enrichment-controls">
      <label>人生阶段
        <select id="enrichment-phase-select">
          <option value="">全部/未限定</option>
          ${(plan.available_life_phases || []).map((phase) => `<option value="${escapeHtml(phase.key)}"${phase.key === currentPhase ? " selected" : ""}>${escapeHtml(phase.label)}</option>`).join("")}
        </select>
      </label>
      <div class="field-gap-grid">
        ${groups.map((group) => `
          <label class="field-gap ${group.covered ? "covered" : "missing"}">
            <input type="checkbox" value="${escapeHtml(group.field_group)}"${recommended.has(group.field_group) ? " checked" : ""}${group.covered ? " disabled" : ""} />
            <span><strong>${escapeHtml(visualFieldGroupLabels[group.field_group] || group.field_group)}</strong><small>${group.covered ? `已覆盖：${group.observed_field_paths.map((path) => escapeHtml(path)).join("、")}` : `${group.priority === "core" ? "核心缺口" : "可选缺口"}`}</small></span>
          </label>`).join("")}
      </div>
      <div class="enrichment-action-row">
        <button class="button button-primary" id="start-enrichment-button" type="button"${ready && recommended.size ? "" : " disabled"}>补齐所选字段</button>
        <span>${escapeHtml(availabilityMessage)}</span>
      </div>
    </div>
    ${run ? `
      <div class="enrichment-run">
        <div><strong>最近任务 · ${escapeHtml(runStatusLabel)}</strong><span>Run ${escapeHtml(shortId(run.id))}</span></div>
        <div class="enrichment-steps">${runSteps.map((step) => `<span class="${escapeHtml(step.status)}">${escapeHtml(step.step_key)} · ${escapeHtml(humanStatus(step.status))}</span>`).join("")}</div>
      </div>` : ""}
    ${renderEnrichmentEvidence(state.enrichmentEvidence)}`;
  $("#enrichment-phase-select").addEventListener("change", (event) => loadVisualEnrichmentState(event.target.value));
  const startButton = $("#start-enrichment-button");
  if (startButton) startButton.addEventListener("click", () => startVisualEnrichment(startButton));
  $$(".suggestion-decision").forEach((button) => button.addEventListener("click", () => resolveFeatureSuggestion(button.dataset.suggestionId, button.dataset.decision, button)));
}

function visualEnrichmentOutcome(run) {
  const persistStep = (run?.steps || []).find((step) => step.step_key === "persist_visual_evidence");
  const cursor = persistStep?.cursor || {};
  const observationCount = (cursor.observation_ids || []).length;
  const suggestionCount = (cursor.suggestion_ids || []).length;
  const rejectedCount = Number(cursor.rejected_count || 0);
  const inferredStatus = persistStep?.status === "succeeded" && !observationCount && !suggestionCount && rejectedCount
    ? "no_valid_results"
    : null;
  return {
    resultStatus: cursor.result_status || inferredStatus,
    observationCount,
    suggestionCount,
    rejectedCount,
  };
}

function renderEnrichmentEvidence(evidence) {
  if (!evidence) return "";
  const suggestions = evidence.suggestions || [];
  const observations = evidence.observations || [];
  const rejections = evidence.rejections || [];
  const visibleSuggestions = suggestions.slice(0, 12);
  const visibleObservations = observations.slice(0, 12);
  const visibleRejections = rejections.slice(0, 12);
  const passages = (evidence.passages || []).slice(0, 8);
  return `
    <div class="enrichment-evidence">
      <div class="fact-section-head"><div><h4>本次精提取结果</h4><p>命中、事实和建议均可回到同一 QueryPlan。</p></div><span>${evidence.hits?.length || 0} 个命中</span></div>
      <div class="enrichment-result-grid">
        ${visibleObservations.map((item) => `<article class="enrichment-result observation"><small>${escapeHtml(item.field_path)}</small><strong>${escapeHtml(typeof item.value === "string" ? item.value : JSON.stringify(item.value))}</strong><em>“${escapeHtml(item.evidence_quote || "无引用")}”</em></article>`).join("")}
        ${visibleSuggestions.map((item) => `<article class="enrichment-result suggestion"><small>${escapeHtml(item.field_path)} · ${escapeHtml(item.status)}</small><strong>${escapeHtml(typeof item.value === "string" ? item.value : JSON.stringify(item.value))}</strong><p>${escapeHtml(item.rationale)}</p>${item.status === "candidate" ? `<div><button class="button button-secondary suggestion-decision" data-suggestion-id="${escapeHtml(item.id)}" data-decision="accept" type="button">接受建议</button><button class="button button-ghost suggestion-decision" data-suggestion-id="${escapeHtml(item.id)}" data-decision="reject" type="button">拒绝</button></div>` : ""}</article>`).join("")}
        ${visibleRejections.map((item) => `<article class="enrichment-result rejection"><small>${escapeHtml(item.field_path)} · 已拒绝</small><strong>${escapeHtml(typeof item.value === "string" ? item.value : JSON.stringify(item.value))}</strong><em>“${escapeHtml(item.evidence_quote || "无引用")}”</em><p>${escapeHtml((item.reason_codes || []).join("、"))}</p></article>`).join("")}
      </div>
      ${observations.length > visibleObservations.length || suggestions.length > visibleSuggestions.length || rejections.length > visibleRejections.length ? `<p class="enrichment-truncation">当前展示 ${visibleObservations.length}/${observations.length} 条事实、${visibleSuggestions.length}/${suggestions.length} 条建议和 ${visibleRejections.length}/${rejections.length} 条拒绝；完整结果保留在 evidence API。</p>` : ""}
      <details><summary>查看证据包（${passages.length}/${evidence.passages?.length || 0} 段）</summary>${passages.map((passage) => `<blockquote><small>第 ${escapeHtml(passage.chapter_ordinal)} 章 · passage ${escapeHtml(shortId(passage.id))}</small>${escapeHtml(passage.content)}</blockquote>`).join("")}</details>
    </div>`;
}

async function startVisualEnrichment(button) {
  const character = state.selectedCharacter;
  if (!character || !state.visualFieldGaps) return;
  const groups = $$("#visual-enrichment-panel .field-gap input:checked").map((input) => input.value);
  if (!groups.length) {
    toast("请至少选择一个缺失字段组。", "error");
    return;
  }
  setBusy(button, true, "正在创建…");
  try {
    const phase = $("#enrichment-phase-select").value || null;
    const run = await api(`/api/v1/characters/${character.id}/visual-enrichment-runs`, {
      method: "POST",
      headers: { "Idempotency-Key": `visual-ui:${character.id}:${Date.now()}:${crypto.randomUUID()}` },
      body: JSON.stringify({ field_groups: groups, life_phase_key: phase, auto_plan: true }),
    });
    state.enrichmentRun = await api(`/api/v1/runs/${run.id}`);
    state.enrichmentEvidence = null;
    renderVisualEnrichmentPanel();
    toast(`视觉精提取任务已创建：${shortId(run.id)}`);
    stopEnrichmentPolling();
    state.enrichmentPollTimer = window.setTimeout(pollVisualEnrichmentRun, 800);
  } catch (error) {
    toast(apiErrorMessage(error), "error");
    setBusy(button, false);
  }
}

async function pollVisualEnrichmentRun() {
  const run = state.enrichmentRun;
  const characterId = state.selectedCharacter?.id;
  if (!run || !characterId) return;
  try {
    state.enrichmentRun = await api(`/api/v1/runs/${run.id}`);
    renderVisualEnrichmentPanel();
    if (terminalRunStates.has(state.enrichmentRun.status)) {
      stopEnrichmentPolling();
      if (state.enrichmentRun.status === "succeeded") {
        const outcome = visualEnrichmentOutcome(state.enrichmentRun);
        if (outcome.resultStatus === "no_valid_results") {
          toast(`视觉精提取完成，但没有候选通过校验；已记录 ${outcome.rejectedCount} 条拒绝原因。`, "error");
        } else if (outcome.resultStatus === "suggestions_pending") {
          toast(`视觉精提取完成，生成 ${outcome.suggestionCount} 条待审核建议，尚未改写角色事实。`);
        } else {
          toast(`视觉精提取完成，新增 ${outcome.observationCount} 条事实并已重新聚合。`);
        }
        await selectCharacter(characterId);
      }
      return;
    }
    state.enrichmentPollTimer = window.setTimeout(pollVisualEnrichmentRun, 1400);
  } catch (error) {
    stopEnrichmentPolling();
    toast(apiErrorMessage(error), "error");
  }
}

async function resolveFeatureSuggestion(suggestionId, decision, button) {
  const actorId = reviewerId();
  if (!actorId) return;
  setBusy(button, true, decision === "accept" ? "正在接受…" : "正在拒绝…");
  try {
    await api(`/api/v1/feature-suggestions/${suggestionId}/resolve`, {
      method: "POST",
      headers: { "X-Actor-ID": actorId },
      body: JSON.stringify({ decision }),
    });
    state.enrichmentEvidence = await api(`/api/v1/visual-enrichment-runs/${state.enrichmentRun.id}/evidence`);
    renderVisualEnrichmentPanel();
    toast(decision === "accept" ? "建议已接受。" : "建议已拒绝。");
  } catch (error) {
    toast(apiErrorMessage(error), "error");
    setBusy(button, false);
  }
}

function renderFactSection(title, facts, description) {
  if (!facts.length) return "";
  const phases = new Map();
  for (const fact of facts) {
    const phase = fact.life_phase_label || fact.life_phase_key || "未标记人生阶段";
    if (!phases.has(phase)) phases.set(phase, []);
    phases.get(phase).push(fact);
  }
  return `
    <section class="fact-section">
      <div class="fact-section-head"><div><h4>${escapeHtml(title)}</h4><p>${escapeHtml(description)}</p></div><span>${facts.length} 条</span></div>
      ${[...phases.entries()].map(([phase, phaseFacts]) => `
        <div class="fact-phase">
          <div class="fact-phase-title"><strong>${escapeHtml(phase)}</strong><span>${phaseFacts.length} 条证据</span></div>
          <div class="facts-grid">${phaseFacts.map((fact) => {
            const chapter = fact.chapter_ordinal === null || fact.chapter_ordinal === undefined ? "章节未知" : `第 ${fact.chapter_ordinal} 章`;
            const category = fact.visual_category || "人物设定";
            return `
              <article class="fact-card${fact.is_visual ? " visual" : ""}">
                <small>${escapeHtml(fact.field_path)}</small>
                <strong>${escapeHtml(typeof fact.value === "string" ? fact.value : JSON.stringify(fact.value))}</strong>
                <div class="fact-meta"><span>${escapeHtml(category)}</span><span>${escapeHtml(chapter)}</span><span>${escapeHtml(fact.grounding_status)}</span></div>
                <em title="${escapeHtml(fact.evidence_quote || "无引用")}">“${escapeHtml(fact.evidence_quote || "暂无原文引用")}”</em>
                <span class="confidence">置信度 ${Math.round(Number(fact.confidence || 0) * 100)}%</span>
              </article>`;
          }).join("")}</div>
        </div>`).join("")}
    </section>`;
}

function jsonText(value) {
  return JSON.stringify(value ?? {}, null, 2);
}

function reviewerId() {
  const value = $("#reviewer-id").value.trim();
  if (!value) {
    toast("请先填写审核人 ID。", "error");
    $("#reviewer-id").focus();
    return null;
  }
  return value;
}

function updateApprovalCount() {
  const openConflicts = state.details?.conflicts?.filter((item) => item.status !== "resolved").length || 0;
  $("#approval-count").textContent = state.approvals.length + openConflicts;
}

function renderApprovalQueue(message = "") {
  const list = $("#approval-list");
  $("#approval-queue-state").textContent = message || `${state.approvals.length} 项待处理`;
  if (!state.approvals.length) {
    list.innerHTML = `<div class="empty-state compact">${escapeHtml(message || "当前没有待审批动作。")}</div>`;
    updateApprovalCount();
    return;
  }
  list.innerHTML = state.approvals.map((approval) => `
    <article class="review-card" data-approval-id="${escapeHtml(approval.id)}">
      <div class="review-card-head">
        <strong>${escapeHtml(approval.approval_type)} · ${escapeHtml(approval.subject_type)}</strong>
        <span>revision ${escapeHtml(approval.revision)}</span>
      </div>
      <div class="review-meta">到期：${escapeHtml(formatTimestamp(approval.expires_at))} · ID ${escapeHtml(shortId(approval.id))}</div>
      <pre>${escapeHtml(jsonText(approval.action))}</pre>
      <div class="review-editor">
        <label for="modifications-${escapeHtml(approval.id)}">修改内容（JSON，仅“修改后通过”使用）</label>
        <textarea id="modifications-${escapeHtml(approval.id)}" rows="3">{}</textarea>
        <label for="defer-${escapeHtml(approval.id)}">延后至</label>
        <input id="defer-${escapeHtml(approval.id)}" type="datetime-local" />
      </div>
      <div class="review-actions">
        <button class="button button-primary approval-decision" type="button" data-decision="approve">批准</button>
        <button class="button button-secondary approval-decision" type="button" data-decision="modify">修改后通过</button>
        <button class="button button-secondary approval-decision" type="button" data-decision="defer">延后</button>
        <button class="button button-ghost approval-decision" type="button" data-decision="reject">拒绝</button>
      </div>
    </article>`).join("");
  $$(".approval-decision").forEach((button) => button.addEventListener("click", () => {
    const card = button.closest("[data-approval-id]");
    resolveApproval(card.dataset.approvalId, button.dataset.decision, button);
  }));
  updateApprovalCount();
}

async function loadApprovals() {
  const button = $("#refresh-approvals-button");
  setBusy(button, true, "正在读取…");
  try {
    const page = await api("/api/v1/approvals?status=pending&limit=50");
    state.approvals = page.items || [];
    state.approvalNextCursor = page.next_cursor || null;
    renderApprovalQueue(state.approvalNextCursor ? "显示前 50 项，仍有更多" : "");
    $("#review-auth-hint").textContent = "已连接管理员审核队列；所有决策使用 revision 并发保护。";
  } catch (error) {
    state.approvals = [];
    const message = error instanceof ApiError && error.status === 403
      ? "需要 ADMIN_API_KEY 才能读取审批队列。"
      : apiErrorMessage(error);
    renderApprovalQueue(message);
    $("#review-auth-hint").textContent = message;
  } finally {
    setBusy(button, false);
    button.disabled = state.capabilities === null;
  }
}

async function resolveApproval(approvalId, decision, button) {
  const actorId = reviewerId();
  if (!actorId) return;
  const approval = state.approvals.find((item) => item.id === approvalId);
  if (!approval) return;
  const body = { decision };
  try {
    if (decision === "modify") {
      body.modifications = JSON.parse($(`#modifications-${approvalId}`).value);
    }
    if (decision === "defer") {
      const deferValue = $(`#defer-${approvalId}`).value;
      if (!deferValue) {
        toast("请选择延后时间。", "error");
        return;
      }
      body.defer_until = new Date(deferValue).toISOString();
    }
  } catch (error) {
    toast(`修改内容不是有效 JSON：${error.message}`, "error");
    return;
  }
  setBusy(button, true, "正在提交…");
  try {
    await api(`/api/v1/approvals/${approval.id}/resolve`, {
      method: "POST",
      headers: {
        "If-Match": `"${approval.revision}"`,
        "X-Actor-ID": actorId,
      },
      body: JSON.stringify(body),
    });
    toast(`审批已${decision === "reject" ? "拒绝" : decision === "defer" ? "延后" : "提交"}。`);
    await loadApprovals();
    if (state.run) await refreshRun();
  } catch (error) {
    toast(apiErrorMessage(error), "error");
  } finally {
    setBusy(button, false);
  }
}

function renderCharacterReview() {
  const conflictList = $("#conflict-review-list");
  const profileContainer = $("#render-profile-review");
  if (!state.selectedCharacter || !state.details) {
    $("#character-review-state").textContent = "尚未选择角色";
    conflictList.innerHTML = '<div class="empty-state compact">先在“角色与原文证据”中选择一个角色。</div>';
    profileContainer.innerHTML = "";
    updateApprovalCount();
    return;
  }

  const conflicts = state.details.conflicts.filter((item) => item.status !== "resolved");
  $("#character-review-state").textContent = `${state.selectedCharacter.canonical_name} · ${conflicts.length} 个开放冲突`;
  conflictList.innerHTML = conflicts.length
    ? conflicts.map((conflict) => `
      <article class="review-card ${conflict.conflict_kind === "human_confirmation" ? "warning" : ""}" data-conflict-id="${escapeHtml(conflict.id)}">
        <div class="review-card-head">
          <strong>${escapeHtml(conflict.field_path)}</strong>
          <span>${escapeHtml(conflict.conflict_kind)} · revision ${escapeHtml(conflict.revision)}</span>
        </div>
        <div class="review-meta">${conflict.conflict_kind === "human_confirmation" ? "新自动事实与人工确认值冲突，必须人工选择。" : "请选择要保留的字段值。"}</div>
        <div class="candidate-actions">
          ${conflict.candidate_values.map((value, index) => `<button class="button button-secondary conflict-candidate" type="button" data-candidate-index="${index}">${escapeHtml(jsonText(value))}</button>`).join("")}
        </div>
      </article>`).join("")
    : '<div class="empty-state compact">该角色没有开放冲突。</div>';

  $$(".conflict-candidate").forEach((button) => button.addEventListener("click", () => {
    const card = button.closest("[data-conflict-id]");
    resolveCharacterConflict(card.dataset.conflictId, Number(button.dataset.candidateIndex), button);
  }));

  const profile = state.renderProfile;
  if (!profile) {
    profileContainer.innerHTML = '<div class="profile-review"><h4>Render Profile</h4><div class="empty-state compact">该角色尚未形成可审核档案。</div></div>';
    updateApprovalCount();
    return;
  }
  profileContainer.innerHTML = `
    <div class="profile-review">
      <h4>Render Profile <span class="profile-status">${escapeHtml(humanStatus(profile.status))} · revision ${escapeHtml(profile.revision)}</span></h4>
      <div class="review-editor">
        <label for="profile-style-preset">风格预设</label>
        <input id="profile-style-preset" value="${escapeHtml(profile.style_preset)}" />
        <label for="profile-default-stage">默认阶段</label>
        <input id="profile-default-stage" value="${escapeHtml(profile.default_stage_key || "")}" placeholder="可留空" />
        <label for="profile-identity-anchor">身份锚点（JSON）</label>
        <textarea id="profile-identity-anchor" rows="5">${escapeHtml(jsonText(profile.identity_anchor))}</textarea>
        <label for="profile-appearance-states">外观状态 ID（JSON 数组）</label>
        <textarea id="profile-appearance-states" rows="3">${escapeHtml(jsonText(profile.appearance_state_ids))}</textarea>
        <label for="profile-palette">色板（JSON）</label>
        <textarea id="profile-palette" rows="4">${escapeHtml(jsonText(profile.palette))}</textarea>
        <label for="profile-field-sources">字段来源（JSON）</label>
        <textarea id="profile-field-sources" rows="4">${escapeHtml(jsonText(profile.field_sources))}</textarea>
        <label for="profile-field-suggestions">字段建议（JSON）</label>
        <textarea id="profile-field-suggestions" rows="4">${escapeHtml(jsonText(profile.field_suggestions))}</textarea>
      </div>
      <div class="review-actions">
        <button class="button button-secondary" id="save-profile-button" type="button">保存档案修改</button>
        <button class="button button-primary" id="approve-profile-button" type="button"${conflicts.length || profile.status === "approved" ? " disabled" : ""}>${profile.status === "approved" ? "档案已批准" : conflicts.length ? "先解决冲突" : "批准档案"}</button>
      </div>
    </div>`;
  $("#save-profile-button").addEventListener("click", (event) => saveRenderProfile(event.currentTarget));
  $("#approve-profile-button").addEventListener("click", (event) => approveRenderProfile(event.currentTarget));
  updateApprovalCount();
}

async function resolveCharacterConflict(conflictId, candidateIndex, button) {
  const actorId = reviewerId();
  if (!actorId) return;
  const conflict = state.details?.conflicts.find((item) => item.id === conflictId);
  if (!conflict || candidateIndex < 0 || candidateIndex >= conflict.candidate_values.length) return;
  setBusy(button, true, "正在保存…");
  try {
    await api(`/api/v1/conflicts/${conflict.id}/resolve`, {
      method: "POST",
      headers: {
        "If-Match": `"${conflict.revision}"`,
        "X-Actor-ID": actorId,
      },
      body: JSON.stringify({ selected_value: conflict.candidate_values[candidateIndex] }),
    });
    toast(`已解决字段冲突：${conflict.field_path}`);
    await selectCharacter(state.selectedCharacter.id);
  } catch (error) {
    toast(apiErrorMessage(error), "error");
  } finally {
    setBusy(button, false);
  }
}

function parseProfileJson(selector, label) {
  try {
    return JSON.parse($(selector).value);
  } catch (error) {
    throw new Error(`${label}不是有效 JSON：${error.message}`);
  }
}

async function saveRenderProfile(button) {
  if (!state.renderProfile || !state.selectedCharacter) return;
  let body;
  try {
    const stylePreset = $("#profile-style-preset").value.trim();
    if (!stylePreset) throw new Error("风格预设不能为空");
    body = {
      identity_anchor: parseProfileJson("#profile-identity-anchor", "身份锚点"),
      default_stage_key: $("#profile-default-stage").value.trim() || null,
      appearance_state_ids: parseProfileJson("#profile-appearance-states", "外观状态 ID"),
      palette: parseProfileJson("#profile-palette", "色板"),
      field_sources: parseProfileJson("#profile-field-sources", "字段来源"),
      field_suggestions: parseProfileJson("#profile-field-suggestions", "字段建议"),
      style_preset: stylePreset,
    };
  } catch (error) {
    toast(error.message, "error");
    return;
  }
  setBusy(button, true, "正在保存…");
  try {
    state.renderProfile = await api(`/api/v1/characters/${state.selectedCharacter.id}/render-profile`, {
      method: "PUT",
      headers: { "If-Match": `"${state.renderProfile.revision}"` },
      body: JSON.stringify(body),
    });
    renderCharacterReview();
    toast("Render Profile 修改已保存。 ");
  } catch (error) {
    toast(apiErrorMessage(error), "error");
  } finally {
    setBusy(button, false);
  }
}

async function approveRenderProfile(button) {
  const actorId = reviewerId();
  if (!actorId || !state.renderProfile || !state.selectedCharacter) return;
  setBusy(button, true, "正在批准…");
  try {
    state.renderProfile = await api(`/api/v1/characters/${state.selectedCharacter.id}/approve`, {
      method: "POST",
      headers: {
        "If-Match": `"${state.renderProfile.revision}"`,
        "X-Actor-ID": actorId,
      },
    });
    renderCharacterReview();
    toast("角色 Render Profile 已批准。 ");
  } catch (error) {
    toast(apiErrorMessage(error), "error");
  } finally {
    setBusy(button, false);
  }
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
  stopIndexPolling();
  state.file = null;
  state.novel = null;
  state.run = null;
  state.characters = [];
  state.selectedCharacter = null;
  state.details = null;
  state.timelines = [];
  state.restartAfterCancel = false;
  stopEnrichmentPolling();
  window.location.reload();
}

function bindEvents() {
  $("#connect-button").addEventListener("click", () => {
    state.apiKey = $("#api-key").value.trim();
    loadCapabilities();
  });
  $("#project-select").addEventListener("change", (event) => {
    $("#open-project-button").disabled = !event.target.value;
  });
  $("#open-project-button").addEventListener("click", () => openProject());
  $("#refresh-projects-button").addEventListener("click", () => loadProjects());
  $("#refresh-approvals-button").addEventListener("click", () => loadApprovals());
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
  $("#restart-run-button").addEventListener("click", restartAnalysis);
  $("#cancel-run-button").addEventListener("click", () => cancelRun());
  $("#refresh-run-button").addEventListener("click", refreshRun);
  $("#generation-character").addEventListener("change", (event) => selectCharacter(event.target.value));
  $("#generation-form").addEventListener("submit", generateImages);
  $("#reset-button").addEventListener("click", resetPage);
}

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  loadCapabilities();
});
