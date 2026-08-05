let token = sessionStorage.getItem("dzmm-admin-token") || "";
let adminSession = sessionStorage.getItem("dzmm-admin-session") || "";
let identity = JSON.parse(sessionStorage.getItem("dzmm-admin-identity") || "null");
let loginLease = null;
let configurationVersion = null;
let currentState = "unknown";
let consoleLoading = false;
let refreshLoading = false;
let gameSettings = null;
let activitySettings = null;
let employeePage = 1;
let shopPage = 1;

const pageSize = 20;

const loginScreen = document.querySelector("#login-screen");
const dashboard = document.querySelector("#dashboard");
const loginForm = document.querySelector("#login-form");
const accountLoginForm = document.querySelector("#account-login-form");
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
const settingsModal = document.querySelector("#settings-modal");
const settingsCurrencyName = document.querySelector("#settings-currency-name");
const settingsOnboardingBonus = document.querySelector("#settings-onboarding-bonus");
const settingsCheckinReward = document.querySelector("#settings-checkin-reward");
const activitySettingsModal = document.querySelector("#activity-settings-modal");
const activityRuleInputs = document.querySelector("#activity-rule-inputs");
const incomeReportTimeInputs = document.querySelector("#income-report-time-inputs");

function headers() {
  return token ? {"X-Admin-Token": token} : {"X-Admin-Session": adminSession};
}

function setResult(message, type = "") {
  result.textContent = message;
  result.dataset.type = type;
}

function setAuthenticated(authenticated) {
  loginScreen.hidden = authenticated;
  dashboard.hidden = !authenticated;
  document.querySelector(".topbar-meta").hidden = !authenticated;
  document.querySelector("#nav-admins").hidden = !authenticated || identity?.role !== "super_admin";
  document.querySelector("#current-identity").textContent = authenticated ? `${identity?.username || "管理员"} · ${identity?.role === "super_admin" ? "超级管理员" : "管理员"}` : "";
}

function actorId() {
  return identity?.role === "super_admin" ? "super_admin" : identity?.account_id || "";
}

function configurationHeaders() {
  return configurationVersion === null ? {} : {"If-Match": String(configurationVersion)};
}

function idempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

function ownsLoginLease() {
  return Boolean(loginLease && loginLease.operator_id === actorId());
}

function clearAuthentication() {
  token = "";
  adminSession = "";
  identity = null;
  loginLease = null;
  sessionStorage.removeItem("dzmm-admin-token");
  sessionStorage.removeItem("dzmm-admin-session");
  sessionStorage.removeItem("dzmm-admin-identity");
  setAuthenticated(false);
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

function closeSettingsModal() {
  settingsModal.hidden = true;
}

function closeActivitySettingsModal() {
  activitySettingsModal.hidden = true;
}

function renderSettings(settings) {
  document.querySelector("#settings-card").innerHTML = `
    <article><span>货币名称</span><strong>${escapeHtml(settings.currency_name)}</strong><small>余额、打卡和商店的计价单位</small></article>
    <article><span>入职初始余额</span><strong>${settings.onboarding_bonus}</strong><small>仅影响之后新入职的员工</small></article>
    <article><span>每日打卡奖励</span><strong>${settings.checkin_reward}</strong><small>${escapeHtml(settings.reset_time_label)} 重置</small></article>`;
}

function renderActivitySettings(settings) {
  document.querySelector("#activity-settings-card").innerHTML = `
    <article><span>活跃等级</span><strong>LV1–LV10</strong><small>按累计有效字数结算</small></article>
    <article><span>最高每日奖励</span><strong>${settings.rules.at(-1).reward}</strong><small>达到最高等级后自动入账</small></article>
    <article><span>收益榜推送</span><strong>${settings.report_times.length} 个时段</strong><small>${escapeHtml(settings.report_times.join(" · "))}（北京时间）</small></article>`;
}

async function loadSettings() {
  gameSettings = await requestGame("/api/game/settings");
  configurationVersion = gameSettings.version;
  renderSettings(gameSettings);
  return gameSettings;
}

async function loadActivitySettings() {
  activitySettings = await requestGame("/api/game/activity-settings");
  configurationVersion = activitySettings.version;
  renderActivitySettings(activitySettings);
  return activitySettings;
}

async function openSettingsModal() {
  const settings = gameSettings || await loadSettings();
  settingsCurrencyName.value = settings.currency_name;
  settingsOnboardingBonus.value = settings.onboarding_bonus;
  settingsCheckinReward.value = settings.checkin_reward;
  settingsModal.hidden = false;
  settingsCurrencyName.focus();
}

function renderActivitySettingsInputs() {
  activityRuleInputs.innerHTML = activitySettings.rules.map((rule) => `
    <div class="activity-rule-row"><b>LV${rule.level}</b><label>累计字数<input data-activity-threshold type="number" min="0" value="${rule.character_threshold}"></label><label>奖励<input data-activity-reward type="number" min="0" max="999" value="${rule.reward}"></label></div>`).join("");
  incomeReportTimeInputs.innerHTML = activitySettings.report_times.map((reportTime) => `
    <div class="income-report-time-row"><input data-income-report-time type="time" value="${escapeHtml(reportTime)}"><button class="text-button" data-remove-income-report-time type="button">删除</button></div>`).join("");
}

async function openActivitySettingsModal() {
  const settings = activitySettings || await loadActivitySettings();
  activitySettings = settings;
  renderActivitySettingsInputs();
  activitySettingsModal.hidden = false;
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
  const method = (options.method || "GET").toUpperCase();
  const mutationHeaders = method === "GET" || method === "HEAD"
    ? {}
    : {"Idempotency-Key": idempotencyKey()};
  const response = await fetch(path, {
    ...options,
    headers: {...headers(), ...mutationHeaders, ...(options.headers || {})},
  });
  if (!response.ok) throw new Error(await responseError(response));
  return response.json();
}

async function responseError(response) {
  const body = await response.text();
  try {
    const detail = JSON.parse(body).detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg).filter(Boolean).join("；") || String(response.status);
    }
    if (detail && typeof detail === "object") return String(detail.message || response.status);
    return String(detail || response.status);
  } catch (_) {
    return body.trim() || String(response.status);
  }
}

async function runMutation(button, busyLabel, operation) {
  if (button.dataset.busy === "true") return;
  const label = button.textContent;
  button.dataset.busy = "true";
  button.disabled = true;
  button.textContent = busyLabel;
  try {
    return await operation();
  } finally {
    delete button.dataset.busy;
    button.disabled = false;
    button.textContent = label;
  }
}

function renderPagination(container, pageData, unit, onPageChange) {
  if (!pageData.total) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }
  const start = (pageData.page - 1) * pageData.page_size + 1;
  const end = Math.min(pageData.page * pageData.page_size, pageData.total);
  container.hidden = false;
  container.innerHTML = `<small>显示 ${start}–${end} 条，共 ${pageData.total} ${unit}</small>
    <button class="secondary" data-page="${pageData.page - 1}" type="button" ${pageData.page <= 1 ? "disabled" : ""}>上一页</button>
    <button class="secondary" data-page="${pageData.page + 1}" type="button" ${pageData.page >= pageData.pages ? "disabled" : ""}>下一页</button>`;
  for (const button of container.querySelectorAll("button[data-page]")) {
    button.addEventListener("click", () => void onPageChange(Number(button.dataset.page)));
  }
}

async function loadEmployees(page = employeePage) {
  const settings = gameSettings || await loadSettings();
  const employees = await requestGame(`/api/game/users?page=${page}&page_size=${pageSize}`);
  employeePage = employees.page;
  document.querySelector("#employee-list").innerHTML = employees.items.map((employee) => `
    <article class="data-row"><div><b>${escapeHtml(employee.display_name)}</b><small>入职：${formatHeartbeat(employee.joined_at)}</small></div><strong>${employee.balance} ${escapeHtml(settings.currency_name)}</strong></article>`).join("") || "<p class=\"muted\">还没有员工入职。</p>";
  renderPagination(document.querySelector("#employee-pagination"), employees, "位员工", loadEmployees);
}

async function loadShop(page = shopPage) {
  const settings = gameSettings || await loadSettings();
  const items = await requestGame(`/api/game/items?page=${page}&page_size=${pageSize}`);
  shopPage = items.page;
  document.querySelector("#shop-list").innerHTML = items.items.map((item) => `
    <article class="data-row"><div><b>${escapeHtml(item.name)}</b><small>${escapeHtml(item.description)}</small></div><strong>${item.price} ${escapeHtml(settings.currency_name)} · 库存 ${item.stock}</strong></article>`).join("") || "<p class=\"muted\">尚未上架商品。</p>";
  renderPagination(document.querySelector("#shop-pagination"), items, "件物品", loadShop);
}

async function loadAdministrators() {
  const accounts = await requestGame("/api/admins");
  document.querySelector("#admin-account-list").innerHTML = accounts.map((account) => `
    <article class="data-row"><div><b>${escapeHtml(account.username)}</b><small>${account.active ? "可登录，可运营" : "已停用，所有会话已失效"}</small></div>
    <div class="command-actions"><button class="secondary" data-admin-action="toggle" data-admin-id="${account.id}" data-admin-active="${account.active}" type="button">${account.active ? "停用" : "启用"}</button><button class="secondary" data-admin-action="password" data-admin-id="${account.id}" type="button">重置密码</button><button class="danger-button" data-admin-action="delete" data-admin-id="${account.id}" type="button">删除</button></div></article>`).join("") || "<p class=\"muted\">还没有普通管理员账号。</p>";
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
    if (view === "settings") {
      await Promise.all([loadSettings(), loadActivitySettings()]);
      return;
    }
    if (view === "commands") {
      const commands = await requestGame("/api/game/commands");
      configurationVersion = commands[0]?.version ?? configurationVersion;
      document.querySelector("#command-list").innerHTML = commands.map((command) => `
        <article class="command-card">
          <div class="command-heading"><div><b>${escapeHtml(command.command)}</b><small>${escapeHtml(command.description)}</small></div>
          <div class="command-actions"><button class="secondary" data-command-templates="${escapeHtml(JSON.stringify(command.templates))}" data-command="${escapeHtml(command.command)}" data-command-description="${escapeHtml(command.description)}" type="button">配置回复</button>
          <button class="${command.enabled ? "secondary" : "primary"}" data-command="${escapeHtml(command.command)}" data-enabled="${!command.enabled}" type="button">${command.enabled ? "停用" : "启用"}</button></div></div>
        </article>`).join("") || "<p class=\"muted\">暂无指令。</p>";
      return;
    }
    if (view === "employees") {
      return loadEmployees();
    }
    if (view === "shop") return loadShop();
    if (identity?.role !== "super_admin") throw new Error("仅超级管理员可管理账号");
    return loadAdministrators();
  } catch (error) {
    setResult(`数据读取失败（${error.message}）`, "error");
  }
}

function updateControls(state) {
  const isRequired = state === "auth_required";
  const isProgress = state === "auth_in_progress";
  const hasLease = Boolean(loginLease);
  document.querySelector("#start-login").disabled = !isRequired || hasLease;
  document.querySelector("#open-login-console").disabled = !isProgress || !ownsLoginLease();
  document.querySelector("#finish-login").disabled = !isProgress || !ownsLoginLease();
  document.querySelector("#cancel-login").disabled = !hasLease;
  document.querySelector("#restart-browser").disabled = isProgress;
  document.querySelector("#step-required").classList.toggle("active", isRequired);
  document.querySelector("#step-console").classList.toggle("active", isProgress);
  document.querySelector("#step-finish").classList.toggle("active", state === "ready");
  loginStep.textContent = isProgress ? "验证进行中" : isRequired ? "需要登录" : state === "ready" ? "已登录" : "等待开始";
  if (!isProgress || !ownsLoginLease()) {
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
}

function renderLoginLease() {
  const leaseElement = document.querySelector("#login-lease");
  if (!loginLease) {
    leaseElement.textContent = "当前没有人工登录操作。";
  } else {
    const seconds = Math.max(0, Math.ceil((new Date(loginLease.expires_at).getTime() - Date.now()) / 1000));
    leaseElement.textContent = `当前由 ${loginLease.operator_name} 操作，剩余 ${seconds} 秒。${ownsLoginLease() ? " 你可完成或终止本次登录。" : " 任何管理员均可终止本次登录。"}`;
  }
  updateControls(currentState);
  if (currentState === "auth_in_progress" && ownsLoginLease() && !consoleFrame.getAttribute("src")) void openConsole();
}

async function refreshLoginLease() {
  loginLease = await requestGame("/api/login/lease");
  renderLoginLease();
}

async function refresh() {
  if ((!token && !adminSession) || refreshLoading) return;
  refreshLoading = true;
  try {
    const response = await fetch("/api/status", {headers: headers()});
    if (response.status === 401) {
      clearAuthentication();
      loginError.textContent = "登录已失效，请重新登录。";
      return;
    }
    if (!response.ok) {
      setResult(`状态读取失败（${await responseError(response)}）`, "error");
      return;
    }
    renderStatus(await response.json());
    await refreshLoginLease();
    setResult("状态已更新", "success");
  } catch (error) {
    setResult(`状态读取失败（${error.message}）`, "error");
  } finally {
    refreshLoading = false;
  }
}

async function submitAction(button) {
  const busyLabel = button.id === "start-login" ? "启动中…" : button.id === "restart-browser" ? "重启中…" : "提交中…";
  try {
    await runMutation(button, busyLabel, async () => {
      await requestGame(button.dataset.action, {method: "POST"});
      if (button.id === "start-login") {
        setResult("正在启动安全登录桌面…", "success");
        if (await waitForLoginDesktop()) await openConsole();
      } else {
        setResult("操作指令已发送，正在等待 Worker 响应。", "success");
        window.setTimeout(refresh, 800);
      }
    });
  } catch (error) {
    setResult(`操作失败（${error.message}）`, "error");
  } finally {
    updateControls(currentState);
  }
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
  const button = document.querySelector("#open-login-console");
  try {
    await runMutation(button, "加载中…", async () => {
      const response = await fetch("/api/session", {method: "POST", headers: headers()});
      if (!response.ok) throw new Error(await responseError(response));
      consoleFrame.src = "/login-console";
      consolePanel.hidden = false;
      consolePanel.scrollIntoView({behavior: "smooth", block: "start"});
      setResult("登录桌面已就绪，请在下方完成验证。", "success");
    });
  } catch (error) {
    setResult(`登录控制台授权失败（${error.message}）`, "error");
  } finally {
    consoleLoading = false;
    updateControls(currentState);
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  token = document.querySelector("#admin-token").value.trim();
  if (!token) return;
  adminSession = "";
  identity = {account_id: null, username: "超级管理员", role: "super_admin"};
  sessionStorage.setItem("dzmm-admin-token", token);
  sessionStorage.removeItem("dzmm-admin-session");
  sessionStorage.setItem("dzmm-admin-identity", JSON.stringify(identity));
  loginError.textContent = "";
  setAuthenticated(true);
  await refresh();
});

accountLoginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  const values = Object.fromEntries(new FormData(event.currentTarget));
  try {
    await runMutation(button, "登录中…", async () => {
      const response = await fetch("/api/auth/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(values)});
      if (!response.ok) throw new Error(await responseError(response));
      const login = await response.json();
      token = "";
      adminSession = login.session_token;
      identity = {account_id: login.account_id, username: login.username, role: login.role};
      sessionStorage.removeItem("dzmm-admin-token");
      sessionStorage.setItem("dzmm-admin-session", adminSession);
      sessionStorage.setItem("dzmm-admin-identity", JSON.stringify(identity));
      loginError.textContent = "";
      setAuthenticated(true);
      await refresh();
    });
  } catch (error) {
    loginError.textContent = `登录失败：${error.message}`;
  }
});

document.querySelector("#logout").addEventListener("click", async () => {
  if (adminSession) await fetch("/api/auth/logout", {method: "POST", headers: headers()});
  clearAuthentication();
  loginForm.reset();
  accountLoginForm.reset();
});
document.querySelector("#refresh").addEventListener("click", async (event) => {
  await runMutation(event.currentTarget, "刷新中…", refresh);
});
document.querySelector("#open-login-console").addEventListener("click", openConsole);
document.querySelector("#cancel-login").addEventListener("click", async (event) => {
  try {
    await runMutation(event.currentTarget, "终止中…", async () => {
      await requestGame("/api/login/cancel", {method: "POST"});
      consolePanel.hidden = true;
      consoleFrame.removeAttribute("src");
      await refresh();
    });
    setResult("人工登录已终止，浏览器将恢复常驻 Worker。", "success");
  } catch (error) {
    setResult(`终止失败（${error.message}）`, "error");
  }
});
document.querySelector("#edit-settings").addEventListener("click", () => void openSettingsModal());
document.querySelector("#edit-activity-settings").addEventListener("click", () => void openActivitySettingsModal());
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
      await runMutation(button, button.dataset.enabled === "true" ? "启用中…" : "停用中…", async () => {
        const updated = await requestGame("/api/game/commands", {
          method: "PATCH",
          headers: {"Content-Type": "application/json", ...configurationHeaders()},
          body: JSON.stringify({command: button.dataset.command, enabled: button.dataset.enabled === "true"}),
        });
        configurationVersion = updated.version;
        await loadGameView("commands");
      });
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
  const button = event.target;
  try {
    await runMutation(button, "保存中…", async () => {
      const updated = await requestGame("/api/game/command-templates", {
        method: "PATCH",
        headers: {"Content-Type": "application/json", ...configurationHeaders()},
        body: JSON.stringify({
          command: templateModal.dataset.command,
          scenario: templateModalScenario.value,
          template: templateModalInput.value,
        }),
      });
      configurationVersion = updated.version;
      closeTemplateModal();
      await loadGameView("commands");
    });
    setResult("回复模板已保存", "success");
  } catch (error) {
    setResult(`保存失败（${error.message}）`, "error");
  }
});
settingsModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-settings-modal]")) {
    closeSettingsModal();
    return;
  }
  if (event.target.id !== "save-settings-modal") return;
  const button = event.target;
  try {
    await runMutation(button, "保存中…", async () => {
      gameSettings = await requestGame("/api/game/settings", {
        method: "PATCH",
        headers: {"Content-Type": "application/json", ...configurationHeaders()},
        body: JSON.stringify({
          currency_name: settingsCurrencyName.value.trim(),
          onboarding_bonus: Number(settingsOnboardingBonus.value),
          checkin_reward: Number(settingsCheckinReward.value),
        }),
      });
      configurationVersion = gameSettings.version;
      renderSettings(gameSettings);
      closeSettingsModal();
    });
    setResult("经济规则已保存", "success");
  } catch (error) {
    setResult(`保存失败（${error.message}）`, "error");
  }
});
activitySettingsModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-activity-settings-modal]")) {
    closeActivitySettingsModal();
    return;
  }
  if (event.target.closest("[data-remove-income-report-time]")) {
    activitySettings.report_times.splice([...incomeReportTimeInputs.querySelectorAll("[data-remove-income-report-time]")].indexOf(event.target.closest("[data-remove-income-report-time]")), 1);
    renderActivitySettingsInputs();
    return;
  }
  if (event.target.id === "add-income-report-time") {
    activitySettings.report_times.push("12:00");
    renderActivitySettingsInputs();
    return;
  }
  if (event.target.id !== "save-activity-settings-modal") return;
  const rules = [...activityRuleInputs.querySelectorAll(".activity-rule-row")].map((row, index) => ({
    level: index + 1,
    character_threshold: Number(row.querySelector("[data-activity-threshold]").value),
    reward: Number(row.querySelector("[data-activity-reward]").value),
  }));
  const report_times = [...incomeReportTimeInputs.querySelectorAll("[data-income-report-time]")].map((input) => input.value);
  if (!report_times.length || new Set(report_times).size !== report_times.length || report_times.some((value) => !value)) {
    setResult("请至少保留一个不重复的推送时段", "error");
    return;
  }
  const button = event.target;
  try {
    await runMutation(button, "保存中…", async () => {
      activitySettings = await requestGame("/api/game/activity-settings", {
        method: "PATCH",
        headers: {"Content-Type": "application/json", ...configurationHeaders()},
        body: JSON.stringify({rules, report_times}),
      });
      configurationVersion = activitySettings.version;
      renderActivitySettings(activitySettings);
      closeActivitySettingsModal();
    });
    setResult("日活跃度规则已保存", "success");
  } catch (error) {
    setResult(`保存失败（${error.message}）`, "error");
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !templateModal.hidden) closeTemplateModal();
  if (event.key === "Escape" && !settingsModal.hidden) closeSettingsModal();
  if (event.key === "Escape" && !activitySettingsModal.hidden) closeActivitySettingsModal();
});
document.querySelector("#item-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  const button = event.currentTarget.querySelector("button[type=submit]");
  try {
    await runMutation(button, "上架中…", async () => {
      await requestGame("/api/game/items", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({...values, price: Number(values.price), stock: Number(values.stock)}),
      });
      event.currentTarget.reset();
      await loadShop(shopPage);
    });
    setResult("物品已上架", "success");
  } catch (error) {
    setResult(`上架失败（${error.message}）`, "error");
  }
});

document.querySelector("#admin-account-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  const values = Object.fromEntries(new FormData(event.currentTarget));
  try {
    await runMutation(button, "创建中…", async () => {
      await requestGame("/api/admins", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(values),
      });
      event.currentTarget.reset();
      await loadAdministrators();
    });
    setResult("管理员账号已创建", "success");
  } catch (error) {
    setResult(`创建失败（${error.message}）`, "error");
  }
});

document.querySelector("#admin-account-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-admin-action]");
  if (!button) return;
  const {adminAction, adminId, adminActive} = button.dataset;
  let body;
  let method = "PATCH";
  if (adminAction === "toggle") body = {active: adminActive !== "true"};
  if (adminAction === "password") {
    const password = window.prompt("输入新密码（至少 8 位）");
    if (password === null) return;
    body = {password};
  }
  if (adminAction === "delete") {
    if (!window.confirm("确定删除该管理员账号？该操作会使其所有会话立即失效。")) return;
    method = "DELETE";
  }
  try {
    await runMutation(button, adminAction === "delete" ? "删除中…" : "保存中…", async () => {
      await requestGame(`/api/admins/${adminId}`, {
        method,
        ...(body ? {headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {}),
      });
      await loadAdministrators();
    });
    setResult("管理员账号已更新", "success");
  } catch (error) {
    setResult(`更新失败（${error.message}）`, "error");
  }
});

async function restoreIdentity() {
  if (identity || (!token && !adminSession)) return;
  const response = await fetch("/api/auth/me", {headers: headers()});
  if (!response.ok) return;
  identity = await response.json();
  sessionStorage.setItem("dzmm-admin-identity", JSON.stringify(identity));
  setAuthenticated(true);
}

setAuthenticated(Boolean(token || adminSession));
if (token || adminSession) {
  void restoreIdentity().then(refresh);
  window.setInterval(refresh, 10000);
}
window.setInterval(renderLoginLease, 1000);
