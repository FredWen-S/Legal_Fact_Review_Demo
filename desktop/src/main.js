import { invoke } from "@tauri-apps/api/core";

const statusText = document.getElementById("status-text");
const urlText = document.getElementById("url-text");
const pidText = document.getElementById("pid-text");
const resultText = document.getElementById("result-text");
const errorText = document.getElementById("error-text");
const logText = document.getElementById("log-text");

const buttons = {
  status: document.getElementById("btn-status"),
  start: document.getElementById("btn-start"),
  stop: document.getElementById("btn-stop"),
  openReview: document.getElementById("btn-open-review"),
  openData: document.getElementById("btn-open-data"),
  openExports: document.getElementById("btn-open-exports"),
  openLogs: document.getElementById("btn-open-logs"),
  refreshLogs: document.getElementById("btn-refresh-logs"),
};

let currentStatus = "stopped";
let currentUrl = null;
let pendingAction = null;

const statusLabels = {
  stopped: "未启动",
  starting: "启动中",
  running: "已启动",
  error: "错误",
  ok: "已完成",
};

function setResult(message) {
  resultText.textContent = message || "";
}

function setError(error) {
  errorText.textContent = error ? normalizeError(error) : "";
}

function normalizeError(error) {
  if (!error) return "";
  if (typeof error === "string") return error;
  if (error.message) return error.message;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function renderStatus(payload = {}) {
  currentStatus = payload.status || currentStatus || "stopped";
  currentUrl = payload.url || currentUrl || null;

  statusText.textContent = statusLabels[currentStatus] || currentStatus;
  statusText.dataset.status = currentStatus;
  urlText.textContent = currentUrl || "-";
  pidText.textContent = payload.pid || "-";
  updateButtons();
}

function updateButtons() {
  const busy = Boolean(pendingAction);
  const running = currentStatus === "running";
  const starting = currentStatus === "starting";

  Object.values(buttons).forEach((button) => {
    button.disabled = busy;
  });

  if (!busy) {
    buttons.start.disabled = running || starting;
    buttons.stop.disabled = !running && !starting;
  }
}

function setLoading(actionName) {
  pendingAction = actionName;
  setResult(`正在执行：${actionName}……`);
  setError("");
  updateButtons();
}

function clearLoading() {
  pendingAction = null;
  updateButtons();
}

async function runAction(actionName, command, payload = {}, options = {}) {
  setLoading(actionName);
  try {
    const result = await invoke(command, payload);
    if (options.renderStatus !== false) {
      renderStatus(result);
    }
    if (options.renderLogs) {
      renderLogs(result);
    }
    setResult(result?.message || `${actionName}完成`);
    return result;
  } catch (error) {
    const message = normalizeError(error) || `${actionName}失败`;
    setError(message);
    setResult(`${actionName}失败`);
    if (options.statusOnError) {
      renderStatus({ status: "error", message });
    }
    return null;
  } finally {
    clearLoading();
  }
}

function renderLogs(result) {
  const lines = Array.isArray(result?.lines) ? result.lines : [];
  logText.textContent = lines.length ? lines.join("\n") : "暂无日志";
}

async function refreshStatus() {
  const result = await runAction("刷新状态", "service_status");
  if (result) {
    setResult(result.message || `刷新状态完成：${statusLabels[result.status] || result.status}`);
  }
}

async function startService() {
  renderStatus({ status: "starting" });
  await runAction("启动服务", "service_start", {}, { statusOnError: true });
}

async function stopService() {
  await runAction("停止服务", "service_stop");
}

async function openReviewUi() {
  setLoading("打开复核界面");
  try {
    const status = await invoke("service_status");
    renderStatus(status);
    if (status.status !== "running" || !status.url) {
      throw new Error("请先启动服务");
    }
    const result = await invoke("open_review_ui");
    setResult(result?.message || "打开复核界面完成");
  } catch (error) {
    setError(normalizeError(error) || "打开复核界面失败");
    setResult("打开复核界面失败");
  } finally {
    clearLoading();
  }
}

async function openDataDir() {
  await runAction("打开 data 目录", "open_data_dir", {}, { renderStatus: false });
}

async function openExportsDir() {
  await runAction("打开 exports 目录", "open_exports_dir", {}, { renderStatus: false });
}

async function openLogsDir() {
  await runAction("打开 logs 目录", "open_logs_dir", {}, { renderStatus: false });
}

async function refreshLogs() {
  await runAction("查看日志", "service_logs", { lines: 120 }, { renderStatus: false, renderLogs: true });
}

window.addEventListener("error", (event) => {
  setError(`前端 JS 错误：${event.message}`);
});

window.addEventListener("unhandledrejection", (event) => {
  setError(`前端 Promise 错误：${normalizeError(event.reason)}`);
});

document.getElementById("btn-status").addEventListener("click", refreshStatus);
document.getElementById("btn-start").addEventListener("click", startService);
document.getElementById("btn-stop").addEventListener("click", stopService);
document.getElementById("btn-open-review").addEventListener("click", openReviewUi);
document.getElementById("btn-open-data").addEventListener("click", openDataDir);
document.getElementById("btn-open-exports").addEventListener("click", openExportsDir);
document.getElementById("btn-open-logs").addEventListener("click", openLogsDir);
document.getElementById("btn-refresh-logs").addEventListener("click", refreshLogs);

renderStatus({ status: "stopped" });
refreshStatus().then(refreshLogs);
