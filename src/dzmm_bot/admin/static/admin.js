let token = sessionStorage.getItem("dzmm-admin-token") || "";
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
  renderSettings(gameSettings);
  return gameSettings;
}

async function loadActivitySettings() {
  activitySettings = await requestGame("/api/game/activity-settings");
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
  const response = await fetch(path, {
    ...options,
    headers: {...headers(), ...(options.headers || {})},
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
    return loadShop();
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
  if (!token || refreshLoading) return;
  refreshLoading = true;
  try {
    const response = await fetch("/api/status", {headers: headers()});
    if (response.status === 401) {
      token = "";
      sessionStorage.removeItem("dzmm-admin-token");
      setAuthenticated(false);
      loginError.textContent = "管理员 Token 无效，请重新输入。";
      return;
    }
    if (!response.ok) {
      setResult(`状态读取失败（${await responseError(response)}）`, "error");
      return;
    }
    renderStatus(await response.json());
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
      const response = await fetch(button.dataset.action, {method: "POST", headers: headers()});
      if (!response.ok) throw new Error(await responseError(response));
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
document.querySelector("#refresh").addEventListener("click", async (event) => {
  await runMutation(event.currentTarget, "刷新中…", refresh);
});
document.querySelector("#open-login-console").addEventListener("click", openConsole);
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
        await requestGame("/api/game/commands", {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({command: button.dataset.command, enabled: button.dataset.enabled === "true"}),
        });
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
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          currency_name: settingsCurrencyName.value.trim(),
          onboarding_bonus: Number(settingsOnboardingBonus.value),
          checkin_reward: Number(settingsCheckinReward.value),
        }),
      });
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
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({rules, report_times}),
      });
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

setAuthenticated(Boolean(token));
if (token) {
  refresh();
  window.setInterval(refresh, 10000);
}
