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
const templateModal = document.querySelector("#template-modal");
const templateModalTitle = document.querySelector("#template-modal-title");
const templateModalContext = document.querySelector("#template-modal-context");
const templateModalScenario = document.querySelector("#template-modal-scenario");
const templateModalInput = document.querySelector("#template-modal-input");
const templateModalVariables = document.querySelector("#template-modal-variables");

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
    dateStyle: "short", timeStyle: "medium", timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;",
  })[character]);
}

function closeTemplateModal() {
  templateModal.hidden = true;
  delete templateModal.dataset.command;
  delete templateModal.dataset.templates;
}

function openTemplateModal(button) {
  const templates = JSON.parse(button.dataset.commandTemplates);
  templateModal.dataset.command = button.dataset.command;
  templateModal.dataset.templates = button.dataset.commandTemplates;
  templateModalTitle.textContent = `配置 ${button.dataset.command} 回复`;
  templateModalContext.textContent = button.dataset.commandDescription;
  templateModalScenario.innerHTML = templates
    .map((template) => `<option value="${escapeHtml(template.scenario)}">${escapeHtml(template.label)}</option>`)
    .join("");
  templateModalScenario.value = templates[0].scenario;
  loadTemplateScenario();
  templateModal.hidden = false;
  templateModalInput.focus();
}

function loadTemplateScenario() {
  const template = JSON.parse(templateModal.dataset.templates).find(
    (item) => item.scenario === templateModalScenario.value,
  );
  templateModalInput.value = template.template;
  templateModalVariables.innerHTML = template.variables
    .map((variable) => `<button class="variable-pill" data-variable="${escapeHtml(variable)}" type="button">${escapeHtml(variable)}</button>`)
    .join("");
}

async function requestGame(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {...headers(), ...(options.headers || {})},
  });
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}

function showView(view) {
  for (const element of document.querySelectorAll(".dashboard-view")) {
    element.hidden = element.id !== `${view}-view`;
  }
  for (const button of document.querySelectorAll(".nav-item")) {
    button.classList.toggle("active", button.dataset.view === view);
  }
}

async function loadGameView(view) {
  showView(view);
  try {
    if (view === "overview") return refresh();
    if (view === "commands") {
      const commands = await requestGame("/api/game/commands");
      document.querySelector("#command-list").innerHTML = commands.map((command) => `
        <article class="command-card">
          <div class="command-heading"><div><b>${escapeHtml(command.command)}</b><small>${escapeHtml(command.description)}</small></div>
          <div class="command-actions"><button class="secondary" data-command-templates="${escapeHtml(JSON.stringify(command.templates))}" data-command="${escapeHtml(command.command)}" data-command-description="${escapeHtml(command.description)}" type="button">配置回复</button>
          <button class="${command.enabled ? "secondary" : "primary"}" data-command="${escapeHtml(command.command)}" data-enabled="${!command.enabled}" type="button">${command.enabled ? "停用" : "启用"}</button></div></div>
        </article>`).join("") || "<p class=\"muted\">暂无指令。</p>";
      return;
    }
    if (view === "employees") {
      const employees = await requestGame("/api/game/users");
      document.querySelector("#employee-list").innerHTML = employees.map((employee) => `
        <article class="data-row"><div><b>${escapeHtml(employee.display_name)}</b><small>入职：${formatHeartbeat(employee.joined_at)}</small></div><strong>${employee.balance} 摸鱼币</strong></article>`).join("") || "<p class=\"muted\">还没有员工入职。</p>";
      return;
    }
    const items = await requestGame("/api/game/items");
    document.querySelector("#shop-list").innerHTML = items.map((item) => `
      <article class="data-row"><div><b>${escapeHtml(item.name)}</b><small>${escapeHtml(item.description)}</small></div><strong>${item.price} 币 · 库存 ${item.stock}</strong></article>`).join("") || "<p class=\"muted\">尚未上架商品。</p>";
  } catch (error) {
    setResult(`数据读取失败（${error.message}）`, "error");
  }
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
for (const button of document.querySelectorAll(".nav-item")) {
  button.addEventListener("click", () => void loadGameView(button.dataset.view));
}
document.querySelector("#command-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-command][data-enabled]");
  if (button) {
    try {
      await requestGame("/api/game/commands", {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({command: button.dataset.command, enabled: button.dataset.enabled === "true"}),
      });
      await loadGameView("commands");
      setResult("指令状态已更新", "success");
    } catch (error) {
      setResult(`更新失败（${error.message}）`, "error");
    }
    return;
  }
  const configure = event.target.closest("button[data-command-templates]");
  if (configure) openTemplateModal(configure);
});
templateModalScenario.addEventListener("change", loadTemplateScenario);
templateModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-template-modal]")) {
    closeTemplateModal();
    return;
  }
  const variable = event.target.closest("button[data-variable]");
  if (variable) {
    const start = templateModalInput.selectionStart;
    const end = templateModalInput.selectionEnd;
    templateModalInput.value = `${templateModalInput.value.slice(0, start)}${variable.dataset.variable}${templateModalInput.value.slice(end)}`;
    templateModalInput.focus();
    templateModalInput.selectionStart = templateModalInput.selectionEnd = start + variable.dataset.variable.length;
    return;
  }
  if (event.target.id !== "save-template-modal") return;
  try {
    await requestGame("/api/game/command-templates", {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        command: templateModal.dataset.command,
        scenario: templateModalScenario.value,
        template: templateModalInput.value,
      }),
    });
    closeTemplateModal();
    await loadGameView("commands");
    setResult("回复模板已保存", "success");
  } catch (error) {
    setResult(`保存失败（${error.message}）`, "error");
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !templateModal.hidden) closeTemplateModal();
});
document.querySelector("#item-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  try {
    await requestGame("/api/game/items", {
      method: "POST",
      body: JSON.stringify({...values, price: Number(values.price), stock: Number(values.stock)}),
    });
    event.currentTarget.reset();
    await loadGameView("shop");
    setResult("物品已上架", "success");
  } catch (error) {
    setResult(`上架失败（${error.message}）`, "error");
  }
});

setAuthenticated(Boolean(token));
if (token) {
  refresh();
  window.setInterval(refresh, 10000);
}
