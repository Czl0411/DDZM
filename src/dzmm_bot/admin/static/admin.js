let token = sessionStorage.getItem("dzmm-admin-token") || "";
let currentState = "unknown";
let consoleLoading = false;

const loginScreen = document.querySelector("#login-screen");
const dashboard = document.querySelector("#dashboard");
const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const result = document.querySelector("#result");
const stateElement = document.querySelector("#state");
const stateHelp = document.querySelector("#state-help");
const loginStep = document.querySelector("#login-step");
const consolePanel = document.querySelector("#login-console-panel");
const consoleFrame = document.querySelector("#login-console-frame");

function headers() {
  return {"X-Admin-Token": token};
}

function setResult(message, type = "") {
  result.textContent = message;
  result.dataset.type = type;
}

function setAuthenticated(authenticated) {
  loginScreen.hidden = authenticated;
  dashboard.hidden = !authenticated;
  document.querySelector(".topbar-meta").hidden = !authenticated;
}

function formatHeartbeat(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "short", timeStyle: "medium",
  }).format(new Date(value));
}

function updateControls(state) {
  const isRequired = state === "auth_required";
  const isProgress = state === "auth_in_progress";
  document.querySelector("#start-login").disabled = !isRequired;
  document.querySelector("#open-login-console").disabled = !isProgress;
  document.querySelector("#finish-login").disabled = !isProgress;
  document.querySelector("#restart-browser").disabled = isProgress;
  document.querySelector("#step-required").classList.toggle("active", isRequired);
  document.querySelector("#step-console").classList.toggle("active", isProgress);
  document.querySelector("#step-finish").classList.toggle("active", state === "ready");
  loginStep.textContent = isProgress ? "验证进行中" : isRequired ? "需要登录" : state === "ready" ? "已登录" : "等待开始";
  if (!isProgress) {
    consolePanel.hidden = true;
    consoleFrame.removeAttribute("src");
  }
}

function renderStatus(status) {
  currentState = status.state || "unknown";
  stateElement.textContent = currentState.replaceAll("_", " ");
  stateElement.dataset.state = currentState;
  stateHelp.textContent = currentState === "auth_required" ? "登录已失效，请启动人工登录" : currentState === "auth_in_progress" ? "请在登录控制台完成验证" : currentState === "ready" ? "浏览器已就绪" : "等待 Worker 心跳";
  document.querySelector("#last-heartbeat").textContent = formatHeartbeat(status.last_heartbeat);
  const queue = status.queue_counts || {};
  document.querySelector("#queue-total").textContent = String(queue.inbound_accepted || 0);
  document.querySelector("#queue-counts").textContent = Object.entries(queue).map(([key, value]) => `${key}: ${value}`).join(" · ") || "队列为空";
  updateControls(currentState);
  if (currentState === "auth_in_progress" && !consoleFrame.getAttribute("src")) {
    void openConsole();
  }
}

async function refresh() {
  if (!token) return;
  const response = await fetch("/api/status", {headers: headers()});
  if (response.status === 401) {
    token = "";
    sessionStorage.removeItem("dzmm-admin-token");
    setAuthenticated(false);
    loginError.textContent = "管理员 Token 无效，请重新输入。";
    return;
  }
  if (!response.ok) {
    setResult(`状态读取失败（${response.status}）`, "error");
    return;
  }
  renderStatus(await response.json());
  setResult("状态已更新", "success");
}

async function submitAction(button) {
  button.disabled = true;
  const response = await fetch(button.dataset.action, {method: "POST", headers: headers()});
  if (response.ok) {
    if (button.id === "start-login") {
      setResult("正在启动安全登录桌面…", "success");
      if (await waitForLoginDesktop()) {
        await openConsole();
      }
    } else {
      setResult("操作指令已发送，正在等待 Worker 响应。", "success");
      window.setTimeout(refresh, 800);
    }
  } else {
    setResult(`操作被拒绝（${response.status}）`, "error");
  }
  window.setTimeout(() => updateControls(currentState), 200);
}

async function waitForLoginDesktop() {
  for (let attempt = 0; attempt < 24; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    await refresh();
    if (currentState === "auth_in_progress") return true;
    if (currentState !== "auth_required") break;
  }
  setResult("登录桌面启动超时，请刷新状态后重试。", "error");
  return false;
}

async function openConsole() {
  if (consoleLoading || consoleFrame.getAttribute("src")) return;
  consoleLoading = true;
  const response = await fetch("/api/session", {method: "POST", headers: headers()});
  if (!response.ok) {
    setResult(`登录控制台授权失败（${response.status}）`, "error");
    consoleLoading = false;
    return;
  }
  consoleFrame.src = "/login-console";
  consolePanel.hidden = false;
  consoleLoading = false;
  consolePanel.scrollIntoView({behavior: "smooth", block: "start"});
  setResult("登录桌面已就绪，请在下方完成验证。", "success");
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  token = document.querySelector("#admin-token").value.trim();
  if (!token) return;
  sessionStorage.setItem("dzmm-admin-token", token);
  loginError.textContent = "";
  setAuthenticated(true);
  await refresh();
});

document.querySelector("#logout").addEventListener("click", () => {
  token = "";
  sessionStorage.removeItem("dzmm-admin-token");
  loginForm.reset();
  setAuthenticated(false);
});
document.querySelector("#refresh").addEventListener("click", refresh);
document.querySelector("#open-login-console").addEventListener("click", openConsole);
for (const button of document.querySelectorAll("button[data-action]")) {
  button.addEventListener("click", () => submitAction(button));
}

setAuthenticated(Boolean(token));
if (token) {
  refresh();
  window.setInterval(refresh, 10000);
}
