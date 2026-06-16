const { invoke } = window.__TAURI__.core;
const { openUrl } = window.__TAURI__.opener;

const statusText = document.querySelector("#statusText");
const urlText = document.querySelector("#urlText");
const pidText = document.querySelector("#pidText");
const messageBox = document.querySelector("#messageBox");
const logText = document.querySelector("#logText");
const startBtn = document.querySelector("#startBtn");
const openBtn = document.querySelector("#openBtn");
const stopBtn = document.querySelector("#stopBtn");
const viewLogsBtn = document.querySelector("#viewLogsBtn");

let currentUrl = null;

async function call(command, payload = {}) {
  try {
    const result = await invoke(command, payload);
    renderStatus(result);
    await refreshLogs();
    return result;
  } catch (error) {
    messageBox.textContent = String(error);
    messageBox.className = "message error";
    return null;
  }
}

function renderStatus(result) {
  if (!result) return;
  const status = result.status || "unknown";
  const labels = {
    stopped: "服务未启动",
    starting: "启动中",
    running: "服务已启动",
    error: "启动失败",
    ok: "正常"
  };
  statusText.textContent = labels[status] || status;
  statusText.dataset.status = status;
  currentUrl = result.url || currentUrl;
  urlText.textContent = result.url || currentUrl || "-";
  pidText.textContent = result.pid || "-";
  messageBox.textContent = result.message || "";
  messageBox.className = result.status === "error" ? "message error" : "message";
  renderButtons(status);
}

async function refreshLogs() {
  const result = await invoke("service_logs", { lines: 80 });
  const lines = result.lines || [];
  logText.textContent = lines.length ? lines.join("\n") : "暂无日志。";
}

function renderButtons(status) {
  startBtn.disabled = status === "starting" || status === "running";
  openBtn.disabled = status !== "running";
  stopBtn.disabled = status !== "running" && status !== "starting";
  viewLogsBtn.classList.toggle("primary", status === "error");
}

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  statusText.textContent = "启动中";
  statusText.dataset.status = "starting";
  await call("service_start");
});
stopBtn.addEventListener("click", () => call("service_stop"));
document.querySelector("#refreshBtn").addEventListener("click", () => call("service_status"));
openBtn.addEventListener("click", async () => {
  const result = await call("service_status");
  const url = result?.url || currentUrl;
  if (url) await openUrl(url);
});
document.querySelector("#dataBtn").addEventListener("click", () => invoke("open_project_dir", { name: "data" }));
document.querySelector("#exportsBtn").addEventListener("click", () => invoke("open_project_dir", { name: "exports" }));
document.querySelector("#logsBtn").addEventListener("click", () => invoke("open_project_dir", { name: "logs" }));
viewLogsBtn.addEventListener("click", refreshLogs);

call("service_status");
