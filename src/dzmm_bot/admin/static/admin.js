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
let randomEventSettings = null;
let employeePage = 1;
let shopPage = 1;
let randomEventScenePage = 1;
let randomEventSceneOpeningTarget = null;
let randomEventAddScenes = [];
let hideAndSeekSettings = null;
let hideAndSeekScenePage = 1;
let memoryAssessmentSettings = null;

const pageSize = 20;
const randomEventCommandOptions = [
  ["/入职", "/入职"], ["/我的物品", "/我的物品"], ["/打卡", "/打卡"],
  ["/余额", "/余额"], ["/我", "/我（含 /me）"], ["/商店", "/商店"],
  ["/帮助", "/帮助"], ["/加入", "/加入"], ["/退出", "/退出"],
  ["/摸鱼躲猫猫", "/开始摸鱼躲藏、/躲"], ["/记忆考核", "/记忆考核"],
  ["/继续", "/继续"], ["/收手", "/收手"], ["/投降", "/投降"],
];

const loginScreen = document.querySelector("#login-screen");
const dashboard = document.querySelector("#dashboard");
const loginForm = document.querySelector("#login-form");
const accountLoginForm = document.querySelector("#account-login-form");
const loginError = document.querySelector("#login-error");
const result = document.querySelector("#result");
const notificationRegion = document.querySelector("#notification-region");
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
const settingsWeeklyAttendanceReward = document.querySelector("#settings-weekly-attendance-reward");
const activitySettingsModal = document.querySelector("#activity-settings-modal");
const activityRuleInputs = document.querySelector("#activity-rule-inputs");
const incomeReportTimeInputs = document.querySelector("#income-report-time-inputs");
const randomEventSettingsModal = document.querySelector("#random-event-settings-modal");
const randomEventSceneModal = document.querySelector("#random-event-scene-modal");
const randomEventTimeModal = document.querySelector("#random-event-time-modal");
const randomEventAddModal = document.querySelector("#random-event-add-modal");
const randomEventDetailsModal = document.querySelector("#random-event-details-modal");
const randomEventSceneSeats = document.querySelector("#random-event-scene-seats");
const randomEventSceneOpenings = document.querySelector("#random-event-scene-openings");
const randomEventTimeInputs = document.querySelector("#random-event-time-inputs");
const hideAndSeekSettingsModal = document.querySelector("#hide-and-seek-settings-modal");
const hideAndSeekSceneModal = document.querySelector("#hide-and-seek-scene-modal");
const memoryAssessmentSettingsModal = document.querySelector("#memory-assessment-settings-modal");

function headers() {
  return token ? {"X-Admin-Token": token} : {"X-Admin-Session": adminSession};
}

function setResult(message, type = "") {
  result.textContent = message;
  result.dataset.type = type;
  if (message) showNotification(message, type);
}

function showNotification(message, type = "") {
  const level = type || "info";
  const title = ({success: "操作成功", error: "操作未完成", info: "提示"})[level] || "提示";
  const notification = document.createElement("section");
  notification.className = "notification";
  notification.dataset.type = level;
  notification.innerHTML = '<span class="notification-mark" aria-hidden="true"></span><div class="notification-copy"><b></b><p></p></div><button class="notification-close" type="button" aria-label="关闭提示">×</button>';
  notification.querySelector("b").textContent = title;
  notification.querySelector("p").textContent = message;
  notification.querySelector("button").addEventListener("click", () => notification.remove());
  notificationRegion.replaceChildren(notification);
  window.setTimeout(() => notification.remove(), level === "error" ? 6500 : 3600);
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

function commandLabel(command) {
  return command === "/摸鱼躲猫猫" ? "/开始摸鱼躲藏" : command;
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

function closeRandomEventSettingsModal() { randomEventSettingsModal.hidden = true; }
function closeRandomEventSceneModal() { randomEventSceneModal.hidden = true; }
function closeRandomEventTimeModal() {
  randomEventTimeModal.hidden = true;
  delete randomEventTimeModal.dataset.scheduleId;
}
function closeRandomEventAddModal() { randomEventAddModal.hidden = true; }
function closeHideAndSeekSettingsModal() { hideAndSeekSettingsModal.hidden = true; }
function closeHideAndSeekSceneModal() {
  hideAndSeekSceneModal.hidden = true;
  delete hideAndSeekSceneModal.dataset.sceneId;
  delete hideAndSeekSceneModal.dataset.enabled;
}

function renderSettings(settings) {
  document.querySelector("#settings-card").innerHTML = `
    <article><span>货币名称</span><strong>${escapeHtml(settings.currency_name)}</strong><small>余额、打卡和商店的计价单位</small></article>
    <article><span>入职初始余额</span><strong>${settings.onboarding_bonus}</strong><small>仅影响之后新入职的员工</small></article>
    <article><span>每日打卡奖励</span><strong>${settings.checkin_reward}</strong><small>${escapeHtml(settings.reset_time_label)} 重置</small></article>
    <article><span>每周全勤奖</span><strong>${settings.weekly_attendance_reward}</strong><small>上周全勤于周一自动入账</small></article>`;
}

function renderActivitySettings(settings) {
  document.querySelector("#activity-settings-card").innerHTML = `
    <article><span>活跃等级</span><strong>LV1–LV10</strong><small>按累计有效字数结算</small></article>
    <article><span>最高每日奖励</span><strong>${settings.rules.at(-1).reward}</strong><small>达到最高等级后自动入账</small></article>
    <article><span>收益榜推送</span><strong>${settings.report_times.length} 个时段</strong><small>${escapeHtml(settings.report_times.join(" · "))}（北京时间）</small></article>`;
}

function eventStatusLabel(status) {
  return ({pending: "待开始", signup: "报名中", in_progress: "进行中", ended: "已结束", dissolved: "已解散", skipped: "已跳过"})[status] || status;
}

function formatBeijingInput(value) {
  const formatter = new Intl.DateTimeFormat("sv-SE", {timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23"});
  const parts = Object.fromEntries(formatter.formatToParts(new Date(value)).filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function renderRandomEventSettings(settings) {
  document.querySelector("#random-event-settings-card").innerHTML = `
    <article><span>每日固定场次</span><strong>${settings.schedule_times.length} 场</strong><small>${escapeHtml(settings.schedule_times.join(" · "))}（北京时间）</small></article>
    <article><span>报名补充说明</span><strong>已配置</strong><small>${escapeHtml(settings.signup_notice_template)}</small></article>
    <article><span>报名与提醒</span><strong>${settings.signup_timeout_minutes} / ${settings.reminder_interval_minutes} 分钟</strong><small>报名超时 / 未满员提醒</small></article>
    <article><span>期间指令放行</span><strong>${settings.signup_allowed_commands.length} / ${settings.in_progress_allowed_commands.length}</strong><small>报名中 / 进行中</small></article>`;
}

function renderRandomEventScenes(scenes) {
  document.querySelector("#random-event-scene-list").innerHTML = scenes.map((scene) => `
    <article class="data-row"><div><b>${escapeHtml(scene.name)}${scene.enabled ? "" : "（已停用）"}</b><small>报名公告：${escapeHtml(scene.signup_text)}</small><small>事件模板：${scene.events.length} 条</small><small>席位：${scene.seats.map((seat) => `${escapeHtml(seat.role)} × ${seat.capacity}`).join(" · ")}</small></div><div class="command-actions"><strong>${scene.target_rounds} 轮 · ${scene.reward} 奖励</strong><button class="secondary" data-random-event-scene="${escapeHtml(JSON.stringify(scene))}" data-scene-action="edit" type="button">编辑</button><button class="secondary" data-random-event-scene="${escapeHtml(JSON.stringify(scene))}" data-scene-action="toggle" type="button">${scene.enabled ? "停用" : "启用"}</button><button class="danger-button" data-random-event-scene="${escapeHtml(JSON.stringify(scene))}" data-scene-action="delete" type="button">删除</button></div></article>`).join("") || "<p class=\"muted\">还没有场景。新增一个场景后，系统才会在计划时刻发起事件。</p>";
}

function renderHideAndSeekSettings(settings) {
  document.querySelector("#hide-and-seek-settings-card").innerHTML = `
    <article><span>游戏状态</span><strong>${settings.enabled ? "已启用" : "已停用"}</strong><small>停用后玩家无法发起新游戏</small></article>
    <article><span>每局经济</span><strong>${settings.entry_fee} / ${settings.win_reward}</strong><small>被发现扣除 / 胜利奖励</small></article>
    <article><span>每日限制</span><strong>${settings.daily_limit} 次</strong><small>选择超时 ${settings.selection_timeout_minutes} 分钟</small></article>`;
}

function renderHideAndSeekScenes(scenes) {
  document.querySelector("#hide-and-seek-scene-list").innerHTML = scenes.map((scene) => `
    <article class="data-row"><div><b>${escapeHtml(scene.name)}${scene.enabled ? "" : "（已停用）"}</b><small>${scene.enabled ? "可被随机抽取为躲藏地点" : "不会进入新的躲猫猫游戏"}</small></div>
    <div class="command-actions"><button class="secondary" data-hide-and-seek-scene="${escapeHtml(JSON.stringify(scene))}" data-hide-and-seek-scene-action="edit" type="button">编辑</button><button class="secondary" data-hide-and-seek-scene="${escapeHtml(JSON.stringify(scene))}" data-hide-and-seek-scene-action="toggle" type="button">${scene.enabled ? "停用" : "启用"}</button><button class="danger-button" data-hide-and-seek-scene="${escapeHtml(JSON.stringify(scene))}" data-hide-and-seek-scene-action="delete" type="button">删除</button></div></article>`).join("") || "<p class=\"muted\">还没有地点。至少新增并启用 7 个地点后，玩家才能开始游戏。</p>";
}

function renderMemoryAssessmentSettings(settings) {
  document.querySelector("#memory-assessment-settings-card").innerHTML = `
    <article><span>游戏状态</span><strong>${settings.enabled ? "已启用" : "已停用"}</strong><small>考题展示后自动撤回</small></article>
    <article><span>单人挑战</span><strong>每日 ${settings.single_daily_limit} 次 / ${settings.single_recall_seconds} 秒</strong><small>${settings.levels.map((rule) => `LV${rule.level}: ${rule.answer_length} 字符 / ${rule.reward} 奖励`).join(" · ")}</small></article>
    <article><span>双人对战</span><strong>基础奖池 ${settings.duel_base_pool} / 答错冻结 ${settings.duel_wrong_freeze}</strong><small>难度 LV${settings.duel_difficulty_level}，${settings.duel_answer_timeout_minutes} 分钟超时，答错上限 ${settings.duel_wrong_limit} 次</small></article>`;
}

async function loadMemoryAssessment() {
  memoryAssessmentSettings = await requestGame("/api/game/memory-assessment/settings");
  configurationVersion = memoryAssessmentSettings.version;
  renderMemoryAssessmentSettings(memoryAssessmentSettings);
}

async function openMemoryAssessmentSettingsModal() {
  const settings = memoryAssessmentSettings || await requestGame("/api/game/memory-assessment/settings");
  memoryAssessmentSettings = settings;
  document.querySelector("#memory-assessment-enabled").checked = settings.enabled;
  document.querySelector("#memory-assessment-daily-limit").value = settings.single_daily_limit;
  document.querySelector("#memory-assessment-single-seconds").value = settings.single_recall_seconds;
  document.querySelector("#memory-assessment-duel-seconds").value = settings.duel_recall_seconds;
  document.querySelector("#memory-assessment-duel-level").value = settings.duel_difficulty_level;
  document.querySelector("#memory-assessment-base-pool").value = settings.duel_base_pool;
  document.querySelector("#memory-assessment-wrong-freeze").value = settings.duel_wrong_freeze;
  document.querySelector("#memory-assessment-wrong-limit").value = settings.duel_wrong_limit;
  document.querySelector("#memory-assessment-timeout").value = settings.duel_answer_timeout_minutes;
  document.querySelector("#memory-assessment-character-set").value = settings.character_set;
  document.querySelector("#memory-assessment-levels").value = settings.levels.map((rule) => `${rule.answer_length},${rule.reward}`).join("\n");
  memoryAssessmentSettingsModal.hidden = false;
}

function closeMemoryAssessmentSettingsModal() { memoryAssessmentSettingsModal.hidden = true; }

async function loadHideAndSeek(page = hideAndSeekScenePage) {
  const [settings, scenes] = await Promise.all([
    requestGame("/api/game/hide-and-seek/settings"),
    requestGame(`/api/game/hide-and-seek/scenes?page=${page}&page_size=${pageSize}`),
  ]);
  hideAndSeekSettings = settings;
  hideAndSeekScenePage = scenes.page;
  configurationVersion = settings.version;
  renderHideAndSeekSettings(settings);
  renderHideAndSeekScenes(scenes.items);
  renderPagination(document.querySelector("#hide-and-seek-scene-pagination"), scenes, "个地点", loadHideAndSeek);
}

async function openHideAndSeekSettingsModal() {
  const settings = hideAndSeekSettings || await requestGame("/api/game/hide-and-seek/settings");
  hideAndSeekSettings = settings;
  document.querySelector("#hide-and-seek-enabled").checked = settings.enabled;
  document.querySelector("#hide-and-seek-entry-fee").value = settings.entry_fee;
  document.querySelector("#hide-and-seek-win-reward").value = settings.win_reward;
  document.querySelector("#hide-and-seek-daily-limit").value = settings.daily_limit;
  document.querySelector("#hide-and-seek-timeout").value = settings.selection_timeout_minutes;
  hideAndSeekSettingsModal.hidden = false;
}

function openHideAndSeekSceneModal(scene = null) {
  hideAndSeekSceneModal.dataset.sceneId = scene?.id || "";
  hideAndSeekSceneModal.dataset.enabled = String(scene?.enabled ?? true);
  document.querySelector("#hide-and-seek-scene-modal-title").textContent = scene ? `编辑地点：${scene.name}` : "新增地点";
  document.querySelector("#save-hide-and-seek-scene").textContent = scene ? "保存地点" : "创建地点";
  document.querySelector("#hide-and-seek-scene-name").value = scene?.name || "";
  hideAndSeekSceneModal.hidden = false;
  document.querySelector("#hide-and-seek-scene-name").focus();
}

function renderTodayRandomEvents(events) {
  document.querySelector("#today-random-event-list").innerHTML = events.map((event) => `
    <article class="data-row"><div><b>${escapeHtml(event.scene_name || "未安排场景")}－${escapeHtml(event.event_name || "未安排事件")}－${eventStatusLabel(event.status)}${event.is_cross_day ? "（跨日）" : ""}</b><small>${formatHeartbeat(event.scheduled_at)}</small></div>${event.status === "pending" ? `<div class="command-actions"><button class="secondary" data-trigger-random-event="${event.id}" type="button">立即触发</button><button class="secondary" data-adjust-random-event="${event.id}" data-scheduled-at="${event.scheduled_at}" type="button">调整时间</button><button class="danger-button" data-delete-random-event="${event.id}" type="button">移除</button></div>` : event.status === "skipped" ? "" : `<button class="secondary" data-view-random-event-details="${event.id}" type="button">查看详情</button>`}</article>`).join("") || "<p class=\"muted\">今日计划将在每天北京时间 00:00 自动生成。</p>";
}

async function loadRandomEvents(page = randomEventScenePage) {
  const [settings, scenes, today] = await Promise.all([
    requestGame("/api/game/random-events/settings"),
    requestGame(`/api/game/random-events/scenes?page=${page}&page_size=${pageSize}`),
    requestGame("/api/game/random-events/today"),
  ]);
  randomEventSettings = settings;
  randomEventScenePage = scenes.page;
  configurationVersion = settings.version;
  renderRandomEventSettings(settings);
  renderRandomEventScenes(scenes.items);
  renderPagination(document.querySelector("#random-event-scene-pagination"), scenes, "个场景", loadRandomEvents);
  renderTodayRandomEvents(today.items);
}

function renderRandomEventSceneSeat(role = "", capacity = 1) {
  const row = document.createElement("div");
  row.className = "scene-seat-row";
  row.innerHTML = `<input data-random-event-role maxlength="32" placeholder="角色，例如：主持" value="${escapeHtml(role)}"><input data-random-event-capacity type="number" min="1" max="99" value="${capacity}"><button class="text-button" data-remove-random-event-seat type="button">删除</button>`;
  randomEventSceneSeats.append(row);
  renderRandomEventSceneOpeningVariables();
}

function renderRandomEventSceneOpening(event = {}) {
  const row = document.createElement("div");
  row.className = "scene-opening-row";
  row.innerHTML = '<div class="scene-opening-editor"><input data-random-event-name maxlength="64" placeholder="事件名称，例如：咖啡事故"><textarea data-random-event-formal-opening rows="4" maxlength="2000" placeholder="例如：咖啡洒了一桌，主持人正在组织抢救。"></textarea><div class="scene-opening-variable-buttons"></div></div><button class="text-button" data-remove-random-event-opening type="button">删除</button>';
  row.querySelector("[data-random-event-name]").value = event.name || "";
  row.querySelector("textarea").value = event.opening_text || "";
  randomEventSceneOpenings.append(row);
  renderRandomEventSceneOpeningVariables();
}

function renderRandomEventSceneOpeningVariables() {
  const roles = [...new Set([...randomEventSceneSeats.querySelectorAll("[data-random-event-role]")]
    .map((input) => input.value.trim())
    .filter(Boolean))];
  randomEventSceneOpenings.querySelectorAll(".scene-opening-variable-buttons").forEach((container) => {
    container.innerHTML = roles.map((role) => `<button class="variable-chip" data-random-event-role-variable="${escapeHtml(role)}" type="button">{${escapeHtml(role)}}</button>`).join("");
  });
}

function insertRandomEventRoleVariable(role) {
  const hasTarget = randomEventSceneOpenings.contains(randomEventSceneOpeningTarget);
  const opening = hasTarget
    ? randomEventSceneOpeningTarget
    : randomEventSceneOpenings.querySelector("[data-random-event-formal-opening]");
  if (!opening) return;
  const token = `{${role}}`;
  if (hasTarget) {
    opening.setRangeText(token, opening.selectionStart, opening.selectionEnd, "end");
  } else {
    opening.value += token;
  }
  randomEventSceneOpeningTarget = opening;
  opening.focus();
}

async function openRandomEventSettingsModal() {
  const settings = randomEventSettings || await requestGame("/api/game/random-events/settings");
  randomEventSettings = settings;
  randomEventTimeInputs.innerHTML = "";
  settings.schedule_times.forEach((value) => renderRandomEventTime(value));
  document.querySelector("#random-event-signup-notice").value = settings.signup_notice_template;
  document.querySelector("#random-event-signup-timeout").value = settings.signup_timeout_minutes;
  document.querySelector("#random-event-reminder-interval").value = settings.reminder_interval_minutes;
  document.querySelector("#random-event-blocked-message").value = settings.blocked_message;
  renderRandomEventCommandPermissions("#random-event-signup-command-permissions", "signup", settings.signup_allowed_commands);
  renderRandomEventCommandPermissions("#random-event-progress-command-permissions", "progress", settings.in_progress_allowed_commands);
  randomEventSettingsModal.hidden = false;
}

function renderRandomEventCommandPermissions(selector, phase, allowed) {
  document.querySelector(selector).innerHTML = randomEventCommandOptions.map(([value, label]) =>
    `<label><input data-random-event-${phase}-command type="checkbox" value="${value}"${allowed.includes(value) ? " checked" : ""}>${label}</label>`
  ).join("");
}

function renderRandomEventTime(value = "") {
  const row = document.createElement("div");
  row.className = "income-report-time-row";
  row.innerHTML = `<input data-random-event-time type="time" value="${escapeHtml(value)}"><button class="text-button" data-remove-random-event-time type="button">删除</button>`;
  randomEventTimeInputs.append(row);
}

function renderRandomEventAddTemplates() {
  const scene = randomEventAddScenes.find((item) => item.id === document.querySelector("#random-event-add-scene").value);
  document.querySelector("#random-event-add-template").innerHTML = (scene?.events || []).map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`).join("");
}

async function openRandomEventAddModal() {
  const scenes = await requestGame("/api/game/random-events/scenes?page=1&page_size=100");
  randomEventAddScenes = scenes.items.filter((scene) => scene.enabled && scene.events.length);
  const sceneInput = document.querySelector("#random-event-add-scene");
  sceneInput.innerHTML = randomEventAddScenes.map((scene) => `<option value="${scene.id}">${escapeHtml(scene.name)}</option>`).join("");
  renderRandomEventAddTemplates();
  document.querySelector("#random-event-add-scheduled-at").value = "";
  randomEventAddModal.hidden = false;
}

function openRandomEventSceneModal(scene = null) {
  randomEventSceneModal.dataset.sceneId = scene?.id || "";
  randomEventSceneModal.dataset.enabled = String(scene?.enabled ?? true);
  document.querySelector("#random-event-scene-modal-title").textContent = scene ? `编辑场景：${scene.name}` : "新增场景";
  document.querySelector("#save-random-event-scene").textContent = scene ? "保存场景" : "创建场景";
  document.querySelector("#random-event-scene-name").value = scene?.name || "";
  document.querySelector("#random-event-scene-signup").value = scene?.signup_text || "";
  document.querySelector("#random-event-scene-rounds").value = scene?.target_rounds || 10;
  document.querySelector("#random-event-scene-reward").value = scene?.reward ?? 1;
  randomEventSceneSeats.innerHTML = "";
  (scene?.seats || [{role: "", capacity: 1}]).forEach((seat) => renderRandomEventSceneSeat(seat.role, seat.capacity));
  randomEventSceneOpenings.innerHTML = "";
  randomEventSceneOpeningTarget = null;
  (scene?.events || scene?.openings?.map((opening) => ({name: "未命名事件", opening_text: opening})) || [{}]).forEach((event) => renderRandomEventSceneOpening(event));
  randomEventSceneModal.hidden = false;
}

function openRandomEventTimeModal(button) {
  randomEventTimeModal.dataset.scheduleId = button.dataset.adjustRandomEvent;
  document.querySelector("#random-event-scheduled-at").value = formatBeijingInput(button.dataset.scheduledAt);
  randomEventTimeModal.hidden = false;
}

async function openRandomEventDetailsModal(scheduleId) {
  const details = await requestGame(`/api/game/random-events/today/${scheduleId}/details`);
  document.querySelector("#random-event-details-list").innerHTML = details.items.map((detail) => `<article class="data-row"><div><b>${escapeHtml(detail.display_name)}：${escapeHtml(detail.content)}</b><small>${formatHeartbeat(detail.occurred_at)}</small></div></article>`).join("") || '<p class="muted">暂无参与者发言记录。</p>';
  randomEventDetailsModal.hidden = false;
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
  settingsWeeklyAttendanceReward.value = settings.weekly_attendance_reward;
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
  templateModalTitle.textContent = `配置 ${commandLabel(button.dataset.command)} 回复`;
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
  const accounts = await requestGame("/api/admins", {cache: "no-store"});
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
    if (view === "events") return loadRandomEvents();
    if (view === "hide-and-seek") return loadHideAndSeek();
    if (view === "memory-assessment") return loadMemoryAssessment();
    if (view === "commands") {
      const commands = await requestGame("/api/game/commands");
      configurationVersion = commands[0]?.version ?? configurationVersion;
      document.querySelector("#command-list").innerHTML = commands.map((command) => `
        <article class="command-card">
          <div class="command-heading"><div><b>${escapeHtml(commandLabel(command.command))}</b><small>${escapeHtml(command.description)}</small></div>
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
document.querySelector("#edit-random-event-settings").addEventListener("click", () => void openRandomEventSettingsModal());
document.querySelector("#create-random-event-scene").addEventListener("click", () => openRandomEventSceneModal());
document.querySelector("#edit-hide-and-seek-settings").addEventListener("click", () => void openHideAndSeekSettingsModal());
document.querySelector("#create-hide-and-seek-scene").addEventListener("click", () => openHideAndSeekSceneModal());
document.querySelector("#edit-memory-assessment-settings").addEventListener("click", () => void openMemoryAssessmentSettingsModal());
document.querySelector("#add-today-random-event").addEventListener("click", async (event) => {
  try {
    await runMutation(event.currentTarget, "加载中…", openRandomEventAddModal);
  } catch (error) {
    setResult(`加载场景失败（${error.message}）`, "error");
  }
});
document.querySelector("#refresh-random-events").addEventListener("click", async (event) => {
  try {
    await runMutation(event.currentTarget, "刷新中…", loadRandomEvents);
  } catch (error) {
    setResult(`刷新失败（${error.message}）`, "error");
  }
});
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
          weekly_attendance_reward: Number(settingsWeeklyAttendanceReward.value),
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
randomEventSettingsModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-random-event-settings-modal]")) {
    closeRandomEventSettingsModal();
    return;
  }
  if (event.target.id === "add-random-event-time") {
    renderRandomEventTime();
    return;
  }
  if (event.target.closest("[data-remove-random-event-time]")) {
    event.target.closest(".income-report-time-row").remove();
    return;
  }
  const signupVariable = event.target.closest("[data-random-event-signup-variable]");
  if (signupVariable) {
    const input = document.querySelector("#random-event-signup-notice");
    input.setRangeText(signupVariable.dataset.randomEventSignupVariable, input.selectionStart, input.selectionEnd, "end");
    input.focus();
    return;
  }
  if (event.target.id !== "save-random-event-settings") return;
  const button = event.target;
  const settings = {
    schedule_times: [...randomEventTimeInputs.querySelectorAll("[data-random-event-time]")].map((input) => input.value).filter(Boolean),
    signup_notice_template: document.querySelector("#random-event-signup-notice").value.trim(),
    signup_timeout_minutes: Number(document.querySelector("#random-event-signup-timeout").value),
    reminder_interval_minutes: Number(document.querySelector("#random-event-reminder-interval").value),
    signup_allowed_commands: [...randomEventSettingsModal.querySelectorAll("[data-random-event-signup-command]:checked")].map((input) => input.value),
    in_progress_allowed_commands: [...randomEventSettingsModal.querySelectorAll("[data-random-event-progress-command]:checked")].map((input) => input.value),
    blocked_message: document.querySelector("#random-event-blocked-message").value.trim(),
  };
  if (!settings.schedule_times.length || !settings.signup_notice_template || !settings.blocked_message) {
    setResult("请至少设置一个触发时刻、报名补充说明和拦截提示", "error");
    return;
  }
  try {
    await runMutation(button, "保存中…", async () => {
      randomEventSettings = await requestGame("/api/game/random-events/settings", {
        method: "PATCH", headers: {"Content-Type": "application/json", ...configurationHeaders()}, body: JSON.stringify(settings),
      });
      configurationVersion = randomEventSettings.version;
      renderRandomEventSettings(randomEventSettings);
      closeRandomEventSettingsModal();
    });
    setResult("随机事件规则已保存", "success");
  } catch (error) {
    setResult(`保存失败（${error.message}）`, "error");
  }
});
randomEventSceneModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-random-event-scene-modal]")) {
    closeRandomEventSceneModal();
    return;
  }
  if (event.target.id === "add-random-event-scene-seat") {
    renderRandomEventSceneSeat();
    return;
  }
  if (event.target.id === "add-random-event-scene-opening") {
    renderRandomEventSceneOpening();
    return;
  }
  if (event.target.closest("[data-remove-random-event-seat]")) {
    event.target.closest(".scene-seat-row").remove();
    renderRandomEventSceneOpeningVariables();
    return;
  }
  if (event.target.closest("[data-remove-random-event-opening]")) {
    event.target.closest(".scene-opening-row").remove();
    return;
  }
  const roleVariable = event.target.closest("[data-random-event-role-variable]");
  if (roleVariable) {
    insertRandomEventRoleVariable(roleVariable.dataset.randomEventRoleVariable);
    return;
  }
  if (event.target.id !== "save-random-event-scene") return;
  const name = document.querySelector("#random-event-scene-name").value.trim();
  const signupText = document.querySelector("#random-event-scene-signup").value.trim();
  const events = [...randomEventSceneOpenings.querySelectorAll(".scene-opening-row")].map((row) => ({
    name: row.querySelector("[data-random-event-name]").value.trim(),
    opening_text: row.querySelector("[data-random-event-formal-opening]").value.trim(),
  }));
  if (!name || !signupText || !events.length || events.some((item) => !item.name || !item.opening_text)) {
    setResult("请填写场景名称、报名公告和每个事件的名称、开场白", "error");
    return;
  }
  const seats = [...randomEventSceneSeats.querySelectorAll(".scene-seat-row")].map((row) => ({
    role: row.querySelector("[data-random-event-role]").value.trim(),
    capacity: Number(row.querySelector("[data-random-event-capacity]").value),
  }));
  if (!seats.length || seats.some((seat) => !seat.role || !seat.capacity)) {
    setResult("请至少设置一个有效角色席位", "error");
    return;
  }
  const button = event.target;
  try {
    const sceneId = randomEventSceneModal.dataset.sceneId;
    await runMutation(button, sceneId ? "保存中…" : "创建中…", async () => {
      const created = await requestGame(
        sceneId ? `/api/game/random-events/scenes/${sceneId}` : "/api/game/random-events/scenes",
        {
        method: sceneId ? "PUT" : "POST", headers: {"Content-Type": "application/json", ...configurationHeaders()},
        body: JSON.stringify({
          name,
          signup_text: signupText,
          events,
          target_rounds: Number(document.querySelector("#random-event-scene-rounds").value),
          reward: Number(document.querySelector("#random-event-scene-reward").value), seats,
          ...(sceneId ? {enabled: randomEventSceneModal.dataset.enabled === "true"} : {}),
        }),
      });
      configurationVersion = created.version;
      closeRandomEventSceneModal();
      await loadRandomEvents();
    });
    setResult(sceneId ? "随机事件场景已保存" : "随机事件场景已创建", "success");
  } catch (error) {
    setResult(
      error.message === "场景名称已存在"
        ? "场景已存在，请直接编辑现有场景。"
        : `创建失败（${error.message}）`,
      "error",
    );
  }
});
randomEventSceneModal.addEventListener("input", (event) => {
  if (event.target.matches("[data-random-event-role]")) {
    renderRandomEventSceneOpeningVariables();
  }
});
randomEventSceneModal.addEventListener("focusin", (event) => {
  if (event.target.matches("[data-random-event-formal-opening]")) {
    randomEventSceneOpeningTarget = event.target;
  }
});
document.querySelector("#random-event-scene-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-scene-action]");
  if (!button) return;
  const scene = JSON.parse(button.dataset.randomEventScene);
  if (button.dataset.sceneAction === "edit") {
    openRandomEventSceneModal(scene);
    return;
  }
  if (button.dataset.sceneAction === "delete" && !window.confirm(`确定删除场景“${scene.name}”？`)) return;
  const deletion = button.dataset.sceneAction === "delete";
  const payload = {...scene, enabled: deletion ? scene.enabled : !scene.enabled};
  try {
    await runMutation(button, deletion ? "删除中…" : "保存中…", async () => {
      const updated = await requestGame(`/api/game/random-events/scenes/${scene.id}`, {
        method: deletion ? "DELETE" : "PUT",
        headers: configurationHeaders(),
        ...(deletion ? {} : {headers: {"Content-Type": "application/json", ...configurationHeaders()}, body: JSON.stringify(payload)}),
      });
      configurationVersion = updated.version;
      await loadRandomEvents();
    });
    setResult(deletion ? "场景已删除" : `场景已${scene.enabled ? "停用" : "启用"}`, "success");
  } catch (error) {
    setResult(`更新失败（${error.message}）`, "error");
  }
});
document.querySelector("#random-event-add-scene").addEventListener("change", renderRandomEventAddTemplates);
randomEventAddModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-random-event-add-modal]")) {
    closeRandomEventAddModal();
    return;
  }
  if (event.target.id !== "save-random-event-add") return;
  const scheduledAt = document.querySelector("#random-event-add-scheduled-at").value;
  if (!scheduledAt) {
    setResult("请选择今日未来的开始时间", "error");
    return;
  }
  const button = event.target;
  try {
    await runMutation(button, "补充中…", async () => {
      const created = await requestGame("/api/game/random-events/today", {
        method: "POST", headers: {"Content-Type": "application/json", ...configurationHeaders()},
        body: JSON.stringify({
          scene_id: document.querySelector("#random-event-add-scene").value,
          event_name: document.querySelector("#random-event-add-template").value,
          scheduled_at: `${scheduledAt}:00+08:00`,
        }),
      });
      configurationVersion = created.version;
      closeRandomEventAddModal();
      await loadRandomEvents();
    });
    setResult("今日随机事件已补充", "success");
  } catch (error) {
    setResult(`补充失败（${error.message}）`, "error");
  }
});
document.querySelector("#today-random-event-list").addEventListener("click", async (event) => {
  const adjustButton = event.target.closest("button[data-adjust-random-event]");
  if (adjustButton) {
    openRandomEventTimeModal(adjustButton);
    return;
  }
  const detailButton = event.target.closest("button[data-view-random-event-details]");
  if (detailButton) {
    try {
      await openRandomEventDetailsModal(detailButton.dataset.viewRandomEventDetails);
    } catch (error) {
      setResult(`获取详情失败（${error.message}）`, "error");
    }
    return;
  }
  const triggerButton = event.target.closest("button[data-trigger-random-event]");
  const deleteButton = event.target.closest("button[data-delete-random-event]");
  if (deleteButton) {
    if (!window.confirm("确定移除这个待开始事件吗？")) return;
    try {
      await runMutation(deleteButton, "移除中…", async () => {
        const removed = await requestGame(`/api/game/random-events/today/${deleteButton.dataset.deleteRandomEvent}`, {
          method: "DELETE", headers: configurationHeaders(),
        });
        configurationVersion = removed.version;
        await loadRandomEvents();
      });
      setResult("今日随机事件已移除", "success");
    } catch (error) {
      setResult(`移除失败（${error.message}）`, "error");
    }
    return;
  }
  if (!triggerButton) return;
  try {
    await runMutation(triggerButton, "触发中…", async () => {
      const updated = await requestGame(`/api/game/random-events/today/${triggerButton.dataset.triggerRandomEvent}/trigger`, {
        method: "POST", headers: configurationHeaders(),
      });
      configurationVersion = updated.version;
      await loadRandomEvents();
    });
    setResult("随机事件已开始报名", "success");
  } catch (error) {
    setResult(`立即触发失败（${error.message}）`, "error");
  }
});
randomEventDetailsModal.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-random-event-details-modal]")) randomEventDetailsModal.hidden = true;
});
randomEventTimeModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-random-event-time-modal]")) {
    closeRandomEventTimeModal();
    return;
  }
  if (event.target.id !== "save-random-event-time") return;
  const scheduledAt = document.querySelector("#random-event-scheduled-at").value;
  if (!scheduledAt) return;
  const button = event.target;
  try {
    await runMutation(button, "保存中…", async () => {
      const updated = await requestGame(`/api/game/random-events/today/${randomEventTimeModal.dataset.scheduleId}`, {
        method: "PATCH", headers: {"Content-Type": "application/json", ...configurationHeaders()},
        body: JSON.stringify({scheduled_at: `${scheduledAt}:00+08:00`}),
      });
      configurationVersion = updated.version;
      closeRandomEventTimeModal();
      await loadRandomEvents();
    });
    setResult("今日事件时间已调整", "success");
  } catch (error) {
    setResult(`调整失败（${error.message}）`, "error");
  }
});
hideAndSeekSettingsModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-hide-and-seek-settings-modal]")) {
    closeHideAndSeekSettingsModal();
    return;
  }
  if (event.target.id !== "save-hide-and-seek-settings") return;
  const button = event.target;
  const settings = {
    enabled: document.querySelector("#hide-and-seek-enabled").checked,
    entry_fee: Number(document.querySelector("#hide-and-seek-entry-fee").value),
    win_reward: Number(document.querySelector("#hide-and-seek-win-reward").value),
    daily_limit: Number(document.querySelector("#hide-and-seek-daily-limit").value),
    selection_timeout_minutes: Number(document.querySelector("#hide-and-seek-timeout").value),
  };
  try {
    await runMutation(button, "保存中…", async () => {
      hideAndSeekSettings = await requestGame("/api/game/hide-and-seek/settings", {
        method: "PATCH", headers: {"Content-Type": "application/json", ...configurationHeaders()}, body: JSON.stringify(settings),
      });
      configurationVersion = hideAndSeekSettings.version;
      renderHideAndSeekSettings(hideAndSeekSettings);
      closeHideAndSeekSettingsModal();
    });
    setResult("躲猫猫规则已保存", "success");
  } catch (error) {
    setResult(`保存失败（${error.message}）`, "error");
  }
});
memoryAssessmentSettingsModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-memory-assessment-settings-modal]")) {
    closeMemoryAssessmentSettingsModal();
    return;
  }
  if (event.target.id !== "save-memory-assessment-settings") return;
  const levels = document.querySelector("#memory-assessment-levels").value.trim().split("\n").filter(Boolean).map((line, index) => {
    const [answerLength, reward] = line.split(",").map((value) => Number(value.trim()));
    return {level: index + 1, answer_length: answerLength, reward};
  });
  const settings = {
    enabled: document.querySelector("#memory-assessment-enabled").checked,
    single_daily_limit: Number(document.querySelector("#memory-assessment-daily-limit").value),
    single_recall_seconds: Number(document.querySelector("#memory-assessment-single-seconds").value),
    duel_recall_seconds: Number(document.querySelector("#memory-assessment-duel-seconds").value),
    duel_difficulty_level: Number(document.querySelector("#memory-assessment-duel-level").value),
    duel_base_pool: Number(document.querySelector("#memory-assessment-base-pool").value),
    duel_wrong_freeze: Number(document.querySelector("#memory-assessment-wrong-freeze").value),
    duel_wrong_limit: Number(document.querySelector("#memory-assessment-wrong-limit").value),
    duel_answer_timeout_minutes: Number(document.querySelector("#memory-assessment-timeout").value),
    character_set: document.querySelector("#memory-assessment-character-set").value,
    levels,
  };
  try {
    await runMutation(event.target, "保存中…", async () => {
      memoryAssessmentSettings = await requestGame("/api/game/memory-assessment/settings", {
        method: "PATCH", headers: {"Content-Type": "application/json", ...configurationHeaders()}, body: JSON.stringify(settings),
      });
      configurationVersion = memoryAssessmentSettings.version;
      renderMemoryAssessmentSettings(memoryAssessmentSettings);
      closeMemoryAssessmentSettingsModal();
    });
    setResult("记忆考核规则已保存", "success");
  } catch (error) {
    setResult(`保存失败（${error.message}）`, "error");
  }
});
hideAndSeekSceneModal.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close-hide-and-seek-scene-modal]")) {
    closeHideAndSeekSceneModal();
    return;
  }
  if (event.target.id !== "save-hide-and-seek-scene") return;
  const name = document.querySelector("#hide-and-seek-scene-name").value.trim();
  if (!name) {
    setResult("请填写地点名称", "error");
    return;
  }
  const button = event.target;
  const sceneId = hideAndSeekSceneModal.dataset.sceneId;
  try {
    await runMutation(button, sceneId ? "保存中…" : "创建中…", async () => {
      const scene = await requestGame(
        sceneId ? `/api/game/hide-and-seek/scenes/${sceneId}` : "/api/game/hide-and-seek/scenes",
        {
          method: sceneId ? "PUT" : "POST",
          headers: {"Content-Type": "application/json", ...configurationHeaders()},
          body: JSON.stringify({name, ...(sceneId ? {enabled: hideAndSeekSceneModal.dataset.enabled === "true"} : {})}),
        },
      );
      configurationVersion = scene.version;
      closeHideAndSeekSceneModal();
      await loadHideAndSeek();
    });
    setResult(sceneId ? "躲猫猫地点已保存" : "躲猫猫地点已创建", "success");
  } catch (error) {
    setResult(error.message === "躲猫猫地点名称已存在" ? "地点已存在，请直接编辑现有地点。" : `保存失败（${error.message}）`, "error");
  }
});
document.querySelector("#hide-and-seek-scene-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-hide-and-seek-scene-action]");
  if (!button) return;
  const scene = JSON.parse(button.dataset.hideAndSeekScene);
  if (button.dataset.hideAndSeekSceneAction === "edit") {
    openHideAndSeekSceneModal(scene);
    return;
  }
  const deletion = button.dataset.hideAndSeekSceneAction === "delete";
  if (deletion && !window.confirm(`确定删除地点“${scene.name}”？`)) return;
  try {
    await runMutation(button, deletion ? "删除中…" : "保存中…", async () => {
      const updated = await requestGame(`/api/game/hide-and-seek/scenes/${scene.id}`, {
        method: deletion ? "DELETE" : "PUT",
        ...(deletion
          ? {headers: configurationHeaders()}
          : {headers: {"Content-Type": "application/json", ...configurationHeaders()}, body: JSON.stringify({...scene, enabled: !scene.enabled})}),
      });
      configurationVersion = updated.version;
      await loadHideAndSeek();
    });
    setResult(deletion ? "地点已删除" : `地点已${scene.enabled ? "停用" : "启用"}`, "success");
  } catch (error) {
    setResult(`更新失败（${error.message}）`, "error");
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !templateModal.hidden) closeTemplateModal();
  if (event.key === "Escape" && !settingsModal.hidden) closeSettingsModal();
  if (event.key === "Escape" && !randomEventDetailsModal.hidden) randomEventDetailsModal.hidden = true;
  if (event.key === "Escape" && !activitySettingsModal.hidden) closeActivitySettingsModal();
  if (event.key === "Escape" && !randomEventSettingsModal.hidden) closeRandomEventSettingsModal();
  if (event.key === "Escape" && !randomEventSceneModal.hidden) closeRandomEventSceneModal();
  if (event.key === "Escape" && !randomEventTimeModal.hidden) closeRandomEventTimeModal();
  if (event.key === "Escape" && !randomEventAddModal.hidden) closeRandomEventAddModal();
  if (event.key === "Escape" && !hideAndSeekSettingsModal.hidden) closeHideAndSeekSettingsModal();
  if (event.key === "Escape" && !hideAndSeekSceneModal.hidden) closeHideAndSeekSceneModal();
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
