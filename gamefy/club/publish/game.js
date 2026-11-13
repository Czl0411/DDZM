import {ClubClient} from "./client.js";
import {CONFIG} from "./config.js";
import {createTileFace, tileLabel, tileSuit} from "./mahjong-faces.js";
import {tablePosition, sameMahjongHand, mahjongChanges, waitStatus, handHintStatus} from "./mahjong-presentation.js";
import {loadEconomy} from "./games/economy.js";

const $ = selector => document.querySelector(selector);
const sdk = window.dzmm;
const client = new ClubClient({sdk, apiBase: CONFIG.apiBase});
let rooms = [], room = null, stopFollow = null, selectedTile = null, receivedAt = 0, bootReady = false;
let chatOpen = false, unreadChat = 0, seenMessageCount = 0, messagesInitialized = false;
let dismissedResult = null, latestDiscard = null, mahjongCue = "";
let pendingWinDecline = null;
let meldChoice = null;
let tableChanges = [], drawnTile = null, calloutAnimation = null;
let seatActivity = [null, null, null, null];
let activeClubTab = "channel", activeDirectFriend = null;
let socialVersion = null, socialRefreshTimer = null, channelRenderVersion = 0, directRenderVersion = 0;
let actionBusy = false, handGesture = null, handHoldTimer = null, ignoreTileClickUntil = 0;
let presenceTimer = null, profileRenderVersion = 0, profileOrigin = null, drawerFocus = null, savedActiveRoom = null, resumeVersion = 0;
const directDrafts = new Map();
let activeClubModule = null, clubModuleVersion = 0, clubModuleRoom = null;
let mahjongEconomy = {coin_stakes: [5, 10, 20], rake_percent: 20};
const roomSharePrefix = "MoyuClubRoom:";
const gameNames = {mahjong: "摸鱼麻将", chess: "群聊象棋", doudizhu: "斗地主", drawguess: "你画我猜", texas: "德州扑克", zhajinhua: "炸金花", blackjack: "21 点", niuniu: "斗牛"};
const clubModules = {
  chess: {base: "./games/chess", title: "群聊象棋"},
  doudizhu: {base: "./games/doudizhu", title: "斗地主"},
  drawguess: {base: "./games/drawguess", title: "你画我猜"},
  texas: {base: "./games/card-table", title: "德州扑克"},
  zhajinhua: {base: "./games/card-table", title: "炸金花"},
  niuniu: {base: "./games/card-table", title: "斗牛"},
  blackjack: {base: "./games/card-table", title: "21 点"},
};

const winds = ["东", "南", "西", "北"];
const phaseNames = {waiting: "候场", playing: "对局中", reaction: "鸣牌响应", hand_finished: "本局结算", match_finished: "终局", cancelled: "已取消"};
const resultNames = {tsumo: "自摸", ron: "荣和", "荒牌流局": "荒牌流局", "流局满贯": "流局满贯", "途中流局": "途中流局", match: "终局"};

function feedback(text = "", kind = "info") {
  const node = $("#feedback"); node.textContent = text; node.dataset.kind = kind;
  const local = $("#create-dialog").open ? $("#create-feedback") : !$("#club-drawer").hidden ? $("#drawer-feedback") : chatOpen ? $("#room-chat-feedback") : null;
  if (local && text) { local.textContent = text; local.dataset.kind = kind; }
}
function show(selector, value = true) { $(selector).hidden = !value; }
function markReady() { if (!bootReady) { bootReady = true; sdk?.loading?.ready?.(); } }
function fullscreenElement() { return document.fullscreenElement || document.webkitFullscreenElement || null; }
function updateFullscreenButton() {
  const active = Boolean(fullscreenElement());
  $("#fullscreen").textContent = active ? "退出" : "全屏";
  $("#fullscreen").setAttribute("aria-label", active ? "退出全屏" : "进入全屏");
}
async function enterFullscreen(silent = false) {
  if (fullscreenElement()) return true;
  const root = document.documentElement;
  const request = root.requestFullscreen || root.webkitRequestFullscreen;
  if (!request) {
    if (!silent) feedback("当前浏览器不支持游戏内全屏，请使用平台顶部的全屏按钮");
    return false;
  }
  try {
    await request.call(root);
    return true;
  } catch (error) {
    if (!silent) feedback("浏览器未允许全屏，请使用平台顶部的全屏按钮");
    return false;
  }
}
async function toggleFullscreen() {
  if (!fullscreenElement()) return enterFullscreen();
  const exit = document.exitFullscreen || document.webkitExitFullscreen;
  if (exit) {
    try { await exit.call(document); } catch { feedback("无法退出全屏，请重试"); }
  }
}
async function returnToLobby() {
  if (["playing", "reaction"].includes(room?.phase) && !confirm("牌局尚未结束。返回后将由系统按倒计时自动摸切，重新进入 Club 会回到本桌。确定返回吗？")) return;
  if (["hand_finished", "match_finished"].includes(room?.phase) && room.seat !== null) {
    try {
      const value = await client.action(room.id, room.version, "leave", {});
      setRoom(value);
    } catch (error) { feedback(error.message); return; }
  }
  const exit = document.exitFullscreen || document.webkitExitFullscreen;
  if (fullscreenElement() && exit) {
    try { await exit.call(document); } catch {}
  }
  await openLobby();
}
function secondsLeft() {
  if (!room?.deadline) return null;
  const server = Date.parse(room.server_time) + (Date.now() - receivedAt);
  return Math.max(0, Math.ceil((Date.parse(room.deadline) - server) / 1000));
}
function tileNode(id, small = false) {
  const tile = document.createElement("button");
  tile.type = "button"; tile.className = `tile ${small ? "small" : ""}`; tile.dataset.id = String(id); tile.dataset.suit = tileSuit(id); tile.append(createTileFace(id)); tile.setAttribute("aria-label", tileLabel(id)); tile.title = tileLabel(id);
  return tile;
}
function avatarNode(player, className = "") {
  const avatar = document.createElement("span"); avatar.className = className; avatar.textContent = player?.name?.slice(0, 1) || "?";
  if (player?.avatar_url) {
    const image = document.createElement("img"); image.src = player.avatar_url; image.alt = ""; image.loading = "lazy"; image.referrerPolicy = "no-referrer";
    image.addEventListener("error", () => image.remove(), {once: true}); avatar.append(image);
  }
  return avatar;
}
function playerButton(player, className = "") {
  const button = document.createElement("button"); button.type = "button"; button.className = `player-link ${className}`.trim(); button.setAttribute("aria-label", `查看${player?.name || "玩家"}的主页`); button.append(avatarNode(player, className ? `${className}-avatar` : ""));
  if (player?.id) button.addEventListener("click", () => openPlayerProfile(player.id));
  return button;
}
function gameCard(game) {
  const button = document.createElement("button"); button.type = "button"; button.className = "game-card";
  button.dataset.game = game.id;
  const art = document.createElement("span"); art.className = `game-art ${game.id}`; art.textContent = game.icon; art.style.backgroundImage = `url("${game.image}")`; art.setAttribute("aria-hidden", "true");
  const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = game.name; const description = document.createElement("small"); description.textContent = game.description; copy.append(name, description);
  const arrow = document.createElement("b"); arrow.textContent = "›"; button.append(art, copy, arrow);
  if (game.path) button.addEventListener("click", () => void openClubGame(game.id));
  return button;
}
function renderGames() {
  const grid = $("#game-grid"); grid.replaceChildren();
  const mahjong = {id: "mahjong", name: "摸鱼麻将", icon: "雀", image: "./assets/game-mahjong.webp", description: "四人立直 · 休闲 / 摸鱼币"};
  const mahjongCard = gameCard(mahjong); mahjongCard.addEventListener("click", openLobby);
  grid.append(mahjongCard, ...CONFIG.games.map(gameCard));
}

function decodeRoomShare(text) {
  if (typeof text !== "string" || !text.startsWith(roomSharePrefix)) return null;
  try {
    const value = JSON.parse(text.slice(roomSharePrefix.length));
    if (!gameNames[value.game] || typeof value.roomId !== "string" || !/^[0-9a-f-]{36}$/i.test(value.roomId)) return null;
    return {game: value.game, roomId: value.roomId, host: String(value.host || "玩家").slice(0, 40)};
  } catch { return null; }
}
function roomShareText(value) { return `${roomSharePrefix}${JSON.stringify({game: value.game, roomId: value.roomId, host: value.host})}`; }
function joinSharedRoom(value) {
  closeClubDrawer();
  if (value.game === "mahjong") { void enterRoom(value.roomId, null, true); return; }
  const game = CONFIG.games.find(item => item.id === value.game); if (!game) return;
  void openClubGame(game.id, value.roomId);
}
async function hydrateRoomShare(row, share) {
  const meta = row.querySelector(".room-share-meta");
  const action = row.querySelector(".room-share-action");
  try {
    const status = await client.roomStatus(share.game, share.roomId);
    meta.textContent = `${status.label} · 人数 ${status.occupied}/${status.capacity}`;
    row.dataset.roomState = status.state;
    action.disabled = !status.enterable;
    action.textContent = status.state === "started" ? "进入观战" : status.state === "waiting" ? "进入房间" : status.label;
    if (status.enterable) action.addEventListener("click", () => joinSharedRoom({...share, game: status.game}), {once: true});
  } catch {
    meta.textContent = "状态暂不可用";
    action.textContent = "尝试进入";
    action.disabled = false;
    action.addEventListener("click", () => joinSharedRoom(share), {once: true});
  }
}
function messageRow(item, direct = false) {
  const row = document.createElement("article"); row.className = `club-message${(direct ? item.mine : item.player?.id === client.clubPlayer?.id) ? " mine" : ""}`; row.dataset.messageId = item.id || "";
  const player = direct ? (item.mine ? client.clubPlayer : activeDirectFriend) : item.player; const identity = document.createElement("span"); identity.className = "message-identity";
  if (player) identity.append(playerButton(player, "message")); const name = document.createElement("b"); name.textContent = direct ? (item.mine ? "我" : activeDirectFriend?.name || "好友") : item.player?.name || "玩家"; if (player) { name.role = "button"; name.tabIndex = 0; name.addEventListener("click", () => openPlayerProfile(player.id)); name.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); void openPlayerProfile(player.id); } }); } identity.append(name);
  if (item.at && Number.isFinite(Date.parse(item.at))) { const time = document.createElement("time"); time.dateTime = item.at; time.textContent = new Date(item.at).toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit"}); identity.append(time); }
  const share = direct ? null : decodeRoomShare(item.text);
  if (!share) { const text = document.createElement("p"); text.textContent = item.text; row.append(identity, text); return row; }
  row.classList.add("room-share-message"); const title = document.createElement("strong"); title.textContent = `${gameNames[share.game]} · ${share.host}的房间`;
  const meta = document.createElement("span"); meta.className = "room-share-meta"; meta.textContent = "正在读取房间状态…";
  const action = document.createElement("button"); action.type = "button"; action.className = "room-share-action"; action.textContent = "读取中"; action.disabled = true;
  row.append(identity, title, meta, action); row.roomShare = share; return row;
}
async function refreshChannelPreview() {
  try {
    const messages = await client.channel(); const latest = messages.at(-1);
    const share = latest && decodeRoomShare(latest.text);
    $("#channel-peek-text").textContent = latest ? (share ? `${latest.player.name} 分享了${gameNames[share.game]}房间` : `${latest.player.name}：${latest.text}`) : "还没有消息，来打个招呼吧";
    return messages;
  } catch (error) {
    $("#channel-peek-text").textContent = "公共频道暂时连接不上";
    return [];
  }
}
async function refreshPresence() {
  try {
    const presence = await client.presence();
    $("#club-online-count").textContent = String(presence.online);
    $("#club-playing-count").textContent = String(presence.playing);
    $("#club-presence").classList.remove("unavailable");
  } catch {
    $("#club-presence").classList.add("unavailable");
  }
}
function startPresenceHeartbeat() {
  clearInterval(presenceTimer);
  void refreshPresence();
  presenceTimer = setInterval(refreshPresence, 15000);
}
function startSocialFollowing() {
  client.followSocial(next => {
    const previous = socialVersion;
    socialVersion = next;
    const channelChanged = !previous || previous.channel !== next.channel;
    const directChanged = !previous || previous.direct !== next.direct;
    const friendsChanged = !previous || previous.friends !== next.friends;
    clearTimeout(socialRefreshTimer);
    socialRefreshTimer = setTimeout(async () => {
      const drawerOpen = !$("#club-drawer").hidden;
      try {
        if (channelChanged) {
          if (drawerOpen && activeClubTab === "channel") await renderChannel();
          else await refreshChannelPreview();
        }
        if (drawerOpen && activeClubTab === "friends") {
          if (directChanged && activeDirectFriend) await openDirect(activeDirectFriend);
          else if (friendsChanged) await renderFriends();
        }
      } catch {}
    }, 50);
  }, () => {});
}
async function renderChannel() {
  const version = ++channelRenderVersion;
  const messages = await refreshChannelPreview();
  if (version !== channelRenderVersion) return;
  const list = $("#club-channel-messages"); const reading = readingPosition(list); const previous = list.lastElementChild?.dataset.messageId; const rows = messages.map(item => messageRow(item)); list.replaceChildren(...rows);
  await Promise.allSettled(rows.filter(row => row.roomShare).map(row => hydrateRoomShare(row, row.roomShare)));
  if (version === channelRenderVersion) { restoreReading(list, reading); $("#channel-new").hidden = reading.bottom || previous === list.lastElementChild?.dataset.messageId; }
}
function friendCard(player, actionLabel, action) {
  const row = document.createElement("div"); row.className = "friend-card"; const avatar = avatarNode(player, "friend-avatar");
  const copy = document.createElement("div"); const name = document.createElement("b"); name.textContent = player.name; const id = document.createElement("small"); id.textContent = `ID ${player.id.slice(0, 8)}`; copy.append(name, id);
  const button = document.createElement("button"); button.type = "button"; button.className = "secondary compact"; button.textContent = actionLabel; button.disabled = actionLabel === "等待接受"; button.addEventListener("click", async () => { if (button.disabled) return; button.disabled = true; try { await action(); } catch (error) { feedback(error.message, "error"); } finally { button.disabled = false; } }); row.append(avatar, copy, button); return row;
}
async function openDirect(player) {
  const changed = activeDirectFriend?.id !== player.id;
  if (changed) { saveDirectDraft(); $("#direct-input").value = directDrafts.get(player.id) || ""; $("#direct-messages").replaceChildren(); }
  const version = ++directRenderVersion; activeDirectFriend = player; $("#direct-name").textContent = player.name; show("#direct-chat");
  const messages = await client.directMessages(player.id);
  if (version !== directRenderVersion || activeDirectFriend?.id !== player.id) return;
  const list = $("#direct-messages"); const reading = readingPosition(list); const previous = list.lastElementChild?.dataset.messageId; list.replaceChildren(...messages.map(item => messageRow(item, true))); restoreReading(list, reading); $("#direct-new").hidden = reading.bottom || previous === list.lastElementChild?.dataset.messageId;
}
async function renderFriends() {
  saveDirectDraft(); directRenderVersion += 1; show("#direct-chat", false); activeDirectFriend = null; const data = await client.friends(); const list = $("#friend-list"); list.replaceChildren();
  for (const item of data.incoming) list.append(friendCard(item, "接受", async () => { await client.acceptFriend(item.request_id); await renderFriends(); }));
  for (const item of data.friends) list.append(friendCard(item, "私聊", () => openDirect(item).catch(error => feedback(error.message, "error"))));
  for (const item of data.outgoing) list.append(friendCard(item, "等待接受", () => {}));
  if (!list.children.length) { const empty = document.createElement("p"); empty.className = "drawer-empty"; empty.textContent = "还没有好友，可输入玩家 ID 添加。"; list.append(empty); }
}
const taskNames = {employment: "加入公司", checkin: "完成一次打卡", random_event: "完成一次随机事件", five_rounds: "小游戏完成 5 轮", activity: "活跃彩蛋", dark_market: "上架一次暗网商品"};
async function renderTasks() {
  const tasks = await client.tasks(); const list = $("#task-list"); list.replaceChildren();
  const visible = tasks.filter(item => !item.hidden || item.eligible || item.claimed);
  for (const cadence of ["once", "daily"]) {
    const items = visible.filter(item => item.cadence === cadence);
    if (!items.length) continue;
    const section = document.createElement("section"); section.className = `task-group task-group-${cadence}`;
    const heading = document.createElement("header"); const title = document.createElement("b"); title.textContent = cadence === "once" ? "一次性任务" : "每日任务"; const note = document.createElement("small"); note.textContent = cadence === "once" ? "每个账号仅可领取一次" : "每日 00:00 刷新"; heading.append(title, note); section.append(heading);
    items.forEach(item => {
      const row = document.createElement("div"); row.className = "task-card"; const copy = document.createElement("div"); const line = document.createElement("span"); const name = document.createElement("b"); name.textContent = taskNames[item.key]; const cadenceBadge = document.createElement("em"); cadenceBadge.textContent = cadence === "once" ? "仅一次" : "每日"; line.append(name, cadenceBadge); const reward = document.createElement("small"); reward.textContent = `+${item.reward} 摸鱼币`; copy.append(line, reward);
      const button = document.createElement("button"); button.type = "button"; button.className = "primary compact"; button.textContent = item.claimed ? "已领取" : item.eligible ? "领取奖励" : "未完成"; button.disabled = item.claimed || !item.eligible;
      button.addEventListener("click", async () => { try { await client.claimTask(item.key); await renderTasks(); await renderProfile(); } catch (error) { feedback(error.message, "error"); } }); row.append(copy, button); section.append(row);
    });
    list.append(section);
  }
}
async function renderProfile(playerId = null) {
  const version = ++profileRenderVersion;
  const profile = playerId ? await client.playerProfile(playerId) : await client.profile(); if (version !== profileRenderVersion) return; const holder = $("#club-profile"); holder.replaceChildren(); const avatar = avatarNode(profile, "profile-avatar");
  const name = document.createElement("h2"); name.textContent = profile.name; const role = document.createElement("p"); role.textContent = profile.employee ? "已入职玩家" : "游客玩家";
  const id = document.createElement("code"); id.textContent = `玩家编号：${profile.id.slice(0, 8)}`;
  const balance = document.createElement("strong"); balance.className = "balance-chip"; balance.textContent = profile.employee ? `${profile.balance} 摸鱼币` : "入职后可参加摸鱼币场并领取任务";
  if (playerId && profile.relationship !== "self") {
    const actions = document.createElement("div"); actions.className = "profile-actions";
    const button = document.createElement("button"); button.type = "button"; button.className = "primary";
    if (profile.relationship === "friend") { button.textContent = "发起私聊"; button.addEventListener("click", async () => { await openClubDrawer("friends"); await openDirect(profile).catch(error => feedback(error.message, "error")); }); }
    else if (profile.relationship === "none") { button.textContent = "添加好友"; button.addEventListener("click", async () => { try { await client.requestFriend(profile.id); await renderProfile(profile.id); } catch (error) { feedback(error.message, "error"); } }); }
    else { button.textContent = profile.relationship === "incoming" ? "待你在好友页接受" : "好友申请已发送"; button.disabled = true; }
    actions.append(button); const header = document.createElement("div"); header.className = "profile-summary"; header.append(avatar, name, role); holder.append(header, actions, id); return;
  }
  const stats = document.createElement("section"); stats.className = "profile-stats";
  const total = profile.stats?.total || {played: 0, wins: 0, losses: 0, draws: 0};
  const summary = document.createElement("b"); summary.textContent = `对局 ${total.played} · 胜 ${total.wins} · 负 ${total.losses} · 平 ${total.draws}`; stats.append(summary);
  const labels = {mahjong: "摸鱼麻将", chess: "群聊象棋", doudizhu: "斗地主", drawguess: "你画我猜", texas: "德州扑克", zhajinhua: "炸金花", blackjack: "21 点", niuniu: "斗牛"};
  Object.entries(labels).forEach(([key, label]) => { const item = profile.stats?.games?.[key] || {played: 0, wins: 0, losses: 0, draws: 0}; const row = document.createElement("small"); row.textContent = `${label} · ${item.played} 局 · ${item.wins}胜 ${item.losses}负 ${item.draws}平`; stats.append(row); });
  const ledger = document.createElement("section"); ledger.className = "profile-ledger"; const ledgerTitle = document.createElement("header"); ledgerTitle.textContent = "最近摸鱼币记录"; ledger.append(ledgerTitle);
  for (const item of profile.recent_transactions || []) { const row = document.createElement("div"); const copy = document.createElement("span"); const label = document.createElement("b"); label.textContent = item.label; const at = document.createElement("small"); at.textContent = new Date(item.at).toLocaleString("zh-CN", {month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit"}); copy.append(label, at); const amount = document.createElement("strong"); amount.textContent = `${item.amount > 0 ? "+" : ""}${item.amount}`; amount.className = item.amount >= 0 ? "gain" : "loss"; row.append(copy, amount); ledger.append(row); }
  if (!(profile.recent_transactions || []).length) { const empty = document.createElement("p"); empty.textContent = "还没有摸鱼币记录"; ledger.append(empty); }
  const header = document.createElement("div"); header.className = "profile-summary"; header.append(avatar, name, role); holder.append(header, balance, stats, ledger, id);
}
async function openPlayerProfile(playerId) {
  profileOrigin = !$("#club-drawer").hidden && activeClubTab !== "profile" ? {tab: activeClubTab} : profileOrigin;
  await openClubDrawer("profile", playerId);
  $("#profile-back").hidden = !profileOrigin;
}
async function openClubDrawer(tab = "channel", playerId = null, restore = false) {
  const opening = $("#club-drawer").hidden;
  if (opening) drawerFocus = document.activeElement;
  $("#drawer-feedback").textContent = ""; $("#profile-back").hidden = true;
  activeClubTab = tab; show("#club-drawer"); show("#club-drawer-backdrop"); document.body.classList.add("drawer-open");
  setMainNavigation({channel:"channel-toggle",friends:"friends-toggle",tasks:"tasks-toggle",profile:"profile-toggle"}[tab]);
  if (opening) $("#club-drawer-close").focus();
  document.querySelectorAll("[data-club-tab]").forEach(button => button.classList.toggle("active", button.dataset.clubTab === tab));
  document.querySelectorAll(".club-panel").forEach(panel => { panel.hidden = panel.id !== `club-panel-${tab}`; });
  $("#club-drawer-title").textContent = {channel: "公共频道", friends: "好友与私聊", tasks: "任务中心", profile: "个人中心"}[tab];
  try { if (restore) return; if (tab === "channel") await renderChannel(); if (tab === "friends") await renderFriends(); if (tab === "tasks") await renderTasks(); if (tab === "profile") await renderProfile(playerId); } catch (error) { feedback(error.message, "error"); }
}
function closeClubDrawer() { show("#club-drawer", false); show("#club-drawer-backdrop", false); document.body.classList.remove("drawer-open"); profileOrigin = null; setMainNavigation("home-nav"); drawerFocus?.focus(); }

async function boot(refresh = false) {
  feedback("正在进入 Club…"); sdk?.loading?.progress?.({phase: "runtime_initializing", progress: 20, message: "正在进入摸鱼 Club"});
  try {
    await client.identity(refresh); $("#identity").textContent = "在线"; startPresenceHeartbeat(); startSocialFollowing();
    await refreshMahjongEconomy();
    renderGames();
    void refreshChannelPreview();
    const launch = await sdk?.getLaunchParams?.().catch?.(() => null);
    const roomId = launch?.roomId ?? launch?.params?.roomId;
    if (typeof roomId === "string" && roomId) await enterRoom(roomId);
    else {
      const activeRoom = await client.activeRoom().catch(() => null);
      if (activeRoom?.game === "mahjong" && activeRoom?.room_id) {
        await enterRoom(activeRoom.room_id);
      } else if (activeRoom?.game && activeRoom?.room_id && clubModules[activeRoom.game]) {
        await openClubGame(activeRoom.game, activeRoom.room_id);
      } else openHome();
    }
    feedback(); markReady();
  } catch (error) {
    feedback(error.message || "加载失败，请重试", "error"); sdk?.loading?.error?.("CLUB_BOOT_FAILED", error.message || "加载失败");
  }
}
function stopRoom() { clearMahjongAnimations(); $("#hand-hints-dialog").close(); $("#pass-win-dialog").close(); pendingWinDecline = null; stopFollow?.(); stopFollow = null; room = null; selectedTile = null; dismissedResult = null; chatOpen = false; unreadChat = 0; seenMessageCount = 0; messagesInitialized = false; show("#chat-drawer", false); $("#table").classList.remove("chat-open"); updateChatBadges(); }
function moduleCss(css, base) {
  return css
    .replaceAll(":root", ":host")
    .replace(/\bhtml\b/g, ":host")
    .replace(/url\((['"]?)\.\//g, `url($1${base}/`);
}
function stopClubModule() {
  activeClubModule?.module?.unmount?.();
  activeClubModule?.host?.remove();
  activeClubModule = null;
  clubModuleRoom = null;
  $("#club-module-share").hidden = true;
  window.MoyuClubRuntime?.clearRoomContext?.();
}
async function openClubGame(game, roomId = null) {
  const config = clubModules[game];
  if (!config) return;
  const version = ++clubModuleVersion;
  stopClubModule(); stopRoom(); show("#club-home", false); show("#mahjong-lobby", false); show("#table", false); show("#club-game"); document.body.dataset.view = "subgame";
  const mount = $("#club-game-mount"); mount.replaceChildren();
  const loading = document.createElement("div"); loading.className = "club-module-loading"; loading.textContent = `正在进入${config.title}…`; mount.append(loading);
  try {
    const [htmlResponse, cssResponse, sharedResponse] = await Promise.all([fetch(`${config.base}/index.html`), fetch(`${config.base}/style.css`), fetch("./games/ui-refresh.css")]);
    if (!htmlResponse.ok || !cssResponse.ok || !sharedResponse.ok) throw new Error("游戏资源加载失败");
    const source = await htmlResponse.text(); const css = `${await cssResponse.text()}\n${await sharedResponse.text()}`;
    if (version !== clubModuleVersion) return;
    const parsed = new DOMParser().parseFromString(source, "text/html"); parsed.querySelectorAll("script").forEach(node => node.remove());
    const host = document.createElement("div"); host.className = "club-module-host"; const root = host.attachShadow({mode: "open"});
    const style = document.createElement("style"); style.textContent = `:host{display:block;width:100%;height:100%;min-height:0}\n${moduleCss(css, config.base)}`;
    const body = document.createElement("body"); body.className = "club-module-body"; body.innerHTML = parsed.body.innerHTML;
    body.querySelectorAll("[src],[href]").forEach(node => {
      for (const attribute of ["src", "href"]) {
        const value = node.getAttribute(attribute); if (value?.startsWith("./")) node.setAttribute(attribute, `${config.base}/${value.slice(2)}`);
      }
    });
    root.append(style, body); mount.replaceChildren(host);
    root.querySelectorAll(".club-link").forEach(link => { link.hidden = true; link.addEventListener("click", event => { event.preventDefault(); closeClubGame(); }); });
    const duplicatePublicButton = root.querySelector("#public-channel"); if (duplicatePublicButton) duplicatePublicButton.hidden = true;
    window.CHESS_API_BASE = CONFIG.apiBase; window.DOUDIZHU_CONFIG = {apiBase: CONFIG.apiBase};
    window.MoyuClubModuleMount = {root, game, roomId, close: closeClubGame, reload: () => void openClubGame(game, roomId)};
    const module = await import(`${config.base}/game.js?mount=${version}`);
    delete window.MoyuClubModuleMount;
    if (version !== clubModuleVersion) { module.unmount?.(); host.remove(); return; }
    activeClubModule = {game, host, module};
  } catch (error) {
    delete window.MoyuClubModuleMount;
    if (version !== clubModuleVersion) return;
    mount.replaceChildren(loading); loading.replaceChildren(); loading.dataset.kind = "error";
    const message = document.createElement("p"); message.textContent = `${config.title}暂时未能载入，请检查连接后重试。`;
    const retry = document.createElement("button"); retry.className = "primary gold"; retry.textContent = "重新加载"; retry.onclick = () => void openClubGame(game, roomId);
    const back = document.createElement("button"); back.className = "secondary"; back.textContent = "返回大厅"; back.onclick = closeClubGame;
    loading.append(message, retry, back);
  }
}
function closeClubGame() { clubModuleVersion += 1; stopClubModule(); $("#club-game-mount").replaceChildren(); show("#club-game", false); openHome(); }
function setMainNavigation(active) { document.querySelectorAll(".club-bottom-nav button").forEach(button => button.classList.toggle("active", button.id === active)); }
function openHome() { stopRoom(); show("#club-home"); show("#mahjong-lobby", false); show("#table", false); show("#club-game", false); document.body.dataset.view = "home"; setMainNavigation("home-nav"); void refreshResumeRoom(); }
async function openLobby() {
  stopRoom(); show("#club-home", false); show("#mahjong-lobby"); show("#table", false); document.body.dataset.view = "lobby"; setMainNavigation("home-nav"); feedback("正在刷新牌桌…");
  try { rooms = await client.rooms(); renderRooms(); feedback(); } catch (error) { feedback(error.message, "error"); }
}
function renderRooms() {
  $("#room-count").textContent = `${rooms.length} 桌`; const list = $("#rooms"); list.replaceChildren();
  if (!rooms.length) {
    const empty = document.createElement("div"); empty.className = "empty room-empty";
    const art = document.createElement("span"); art.className = "room-empty-art"; art.textContent = "🀄";
    const title = document.createElement("b"); title.textContent = "今晚还没有牌桌";
    const copy = document.createElement("span"); copy.textContent = "开一桌，邀请群友直接入座";
    const button = document.createElement("button"); button.type = "button"; button.className = "primary gold compact"; button.textContent = "开第一桌"; button.addEventListener("click", () => void openMahjongCreateDialog());
    empty.append(art, title, copy, button); list.append(empty); return;
  }
  for (const item of rooms) {
    const button = document.createElement("button"); button.className = "room-card"; button.type = "button";
    const icon = document.createElement("span"); icon.className = "room-icon"; icon.textContent = "🀄";
    const copy = document.createElement("div"); const title = document.createElement("strong"); title.textContent = `${item.creator_name}的牌桌`; const meta = document.createElement("small"); meta.textContent = `${item.room_type === "coin" ? `${item.stake} 币场` : "休闲场"} · ${item.match_mode === "south" ? "半庄战" : "东风战"} · ${item.occupied}/4 人${item.mine ? " · 我已入座" : ""}`; copy.append(title, meta);
    const phase = document.createElement("b"); phase.textContent = phaseNames[item.phase] || item.phase; button.append(icon, copy, phase); button.addEventListener("click", () => enterRoom(item.id, null, true)); list.append(button);
  }
}
async function createRoom() {
  if ($("#confirm-create").disabled) return; $("#confirm-create").disabled = true;
  feedback("正在创建牌桌…");
  const roomType = $("#room-type").value;
  const stake = roomType === "coin" ? Number($("#stake").value) : 0;
  try { const next = await client.create(roomType, stake, $("#match-mode").value); $("#create-dialog").close(); await enterRoom(next.id, next); } catch (error) { feedback(error.message, "error"); } finally { $("#confirm-create").disabled = false; }
}
async function enterRoom(roomId, initial = null, immersive = false) {
  if (immersive) void enterFullscreen(true);
  stopFollow?.(); feedback("正在进入房间…");
  try {
    const next = initial || await client.snapshot(roomId);
    if (next.phase === "cancelled") { await openLobby(); return; }
    setRoom(next); show("#club-home", false); show("#mahjong-lobby", false); show("#table"); document.body.dataset.view = "table"; renderTable(); feedback();
    stopFollow = client.follow(roomId, next => { if (next.phase === "cancelled") { void openLobby(); return; } const changed = renderKey(next) !== renderKey(room); setRoom(next); if (changed) renderTable(); feedback(); }, error => feedback(`${error.message}，正在重连…`, "warning"));
  } catch (error) { feedback(error.message, "error"); }
}
function setRoom(next) {
  if (room?.id === next.id && next.version < room.version) return;
  const sameResponse = room?.id === next.id && room.phase === "reaction" && next.phase === "reaction" && next.game?.actions?.pass && next.game.reaction_version != null && room.game?.reaction_version === next.game.reaction_version;
  if (!sameResponse && (room?.id !== next.id || room?.version !== next.version)) { $("#pass-win-dialog").close(); pendingWinDecline = null; meldChoice = null; }
  tableChanges = mahjongChanges(room, next);
  if (!sameMahjongHand(room, next) || next.version > room.version + 1) { latestDiscard = null; mahjongCue = ""; drawnTile = null; seatActivity.fill(null); }
  for (const change of tableChanges) {
    const name = next.players[change.seat]?.name || "玩家";
    const position = tablePosition(change.seat, next.seat);
    const handTile = id => change.seat === next.seat ? $(`#hand .tile[data-id="${id}"]`) : $(`.concealed-${position} .tile:last-child`);
    let origin;
    if (change.kind === "discard") {
      origin = handTile(change.tile);
      seatActivity[change.seat] = `${change.riichi ? "立直 · " : "打出 "}${tileLabel(change.tile)}`;
      latestDiscard = {seat: change.seat, tile: change.tile};
      mahjongCue = `${name} · ${change.riichi ? "立直 · " : ""}打出 ${tileLabel(change.tile)}`;
    } else if (change.kind === "meld") {
      const meld = next.game.melds[change.seat][change.index];
      const label = {chi:"吃",pon:"碰",kan:"杠",ankan:"暗杠",minkan:"明杠",kakan:"加杠"}[change.meld] || "鸣牌";
      seatActivity[change.seat] = label;
      mahjongCue = `${name} · ${label}`;
      if (change.meld === "kakan") {
        change.movingTile = meld.tiles.find(id => !room.game.melds[change.seat][change.index].tiles.includes(id));
        origin = handTile(change.movingTile);
      } else if (meld.open && meld.from !== undefined && meld.called_tile !== undefined) {
        if (latestDiscard?.seat === meld.from && latestDiscard.tile === meld.called_tile) latestDiscard = null;
        seatActivity[change.seat] = `${label} ${tileLabel(meld.called_tile)}`;
        change.movingTile = meld.called_tile;
        change.originSeat = meld.from;
        origin = $(`.river[data-seat="${meld.from}"] .tile[data-id="${meld.called_tile}"]`);
        mahjongCue += ` ${next.players[meld.from]?.name || "玩家"}的${tileLabel(meld.called_tile)}`;
      }
    } else if (change.kind === "draw") {
      if (change.seat === next.seat) drawnTile = change.tile;
      seatActivity[change.seat] = "摸牌";
    }
    if (origin) { change.origin = origin.getBoundingClientRect(); change.originRotation = origin.classList.contains("riichi") ? 90 : 0; }
  }
  room = next; receivedAt = Date.now();
  if (!room.game?.hand?.includes(drawnTile)) drawnTile = null;
  if (selectedTile !== null && !room.game?.actions?.discard?.includes(selectedTile)) selectedTile = null;
}
function renderKey(value) { const messages = value?.messages || []; return JSON.stringify([value?.phase, value?.version, value?.settlement, messages.length, messages.at(-1)?.id]); }
function seatOrder() { const self = room.seat ?? 0; return {self, right: (self + 1) % 4, top: (self + 2) % 4, left: (self + 3) % 4}; }
function renderWaiting() {
  document.body.dataset.tablePhase = "waiting";
  show("#waiting"); show("#mahjong-table", false); show("#result", false);
  $("#room-kind").textContent = `${room.room_type === "coin" ? `${room.buy_in} 摸鱼币房` : "休闲房"} · ${room.match_mode === "south" ? "半庄战" : "东风战"}`; $("#room-code").textContent = `${room.creator_name || "玩家"}的牌桌`;
  const seats = $("#seats"); seats.replaceChildren();
  room.players.forEach((player, index) => {
    const item = document.createElement("div"); item.className = `waiting-seat seat-${index} ${player ? "occupied" : ""} ${player?.ready ? "ready" : ""} ${player && !player.online ? "offline" : ""} ${room.seat === index ? "mine" : ""}`;
    const avatar = player ? avatarNode(player, "waiting-avatar") : document.createElement("span"); if (!player) { avatar.className = "waiting-avatar"; avatar.textContent = "空"; }
    const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = player?.name || "等待入座";
    const status = document.createElement("small"); status.textContent = player ? `${index === room.creator_seat ? "房主 · " : ""}${player.ready ? "已准备" : "未准备"}${player.online ? "" : " · 离线"}` : ["东位", "南位", "西位", "北位"][index];
    copy.append(name, status); item.append(avatar, copy); seats.append(item);
  });
  const vacant = room.players.filter(player => !player).length;
  const pending = room.players.filter(player => player && !player.ready);
  $("#waiting-guidance").textContent = vacant ? `还差 ${vacant} 位玩家 · 可分享房间邀请群友` : pending.length ? `等待 ${pending.map(player => player.name).join("、")} 准备` : "四人已准备 · 等待房主开始";
  $("#claim").disabled = !vacant; $("#claim").textContent = vacant ? "立即入座" : "座位已满";
  $("#claim-controls b").textContent = vacant ? "你正在旁观 · 牌桌还有空位" : "你正在旁观 · 座位已满";
  show("#claim-controls", room.seat === null); show("#waiting-actions", room.seat !== null);
  if (room.seat !== null) { const mine = room.players[room.seat]; $("#ready").textContent = mine.ready ? "取消准备" : "准备"; $("#ready").dataset.action = mine.ready ? "unready" : "ready"; $("#start").hidden = room.seat !== 0; $("#start").disabled = room.players.some(player => !player?.ready); }
}
function isActiveMahjongSeat(seat) {
  return room.phase === "reaction" ? !!room.game.actions?.pass && room.seat === seat : room.phase === "playing" && room.game.turn === seat;
}
function renderPlayer(selector, seat) {
  const node = $(selector); const player = room.players[seat]; node.replaceChildren();
  node.dataset.seat = seat; node.classList.toggle("active", isActiveMahjongSeat(seat)); node.classList.toggle("offline", player?.online === false);
  node.classList.toggle("declared-riichi", room.game.riichi[seat]);
  const avatar = avatarNode(player, "player-avatar"); const copy = document.createElement("div");
  const name = document.createElement("strong"); name.textContent = player?.name || "玩家"; name.title = name.textContent;
  const points = document.createElement("b"); points.className = "player-points"; points.textContent = room.game.points[seat].toLocaleString();
  const position = {self:"你",left:"上家",top:"对家",right:"下家"}[tablePosition(seat, room.seat)];
  const count = document.createElement("small"); count.textContent = `${seat === room.game.dealer ? "庄家 · 东家" : `${winds[(seat - room.game.dealer + 4) % 4]}家`} · ${position}${player?.online === false ? " · 离线" : ""}`;
  copy.append(name, points, count); node.append(avatar, copy);
  if (seatActivity[seat]) {
    const action = document.createElement("span"); action.className = "player-action";
    action.textContent = seatActivity[seat]; action.title = `${player?.name || "玩家"}最近动作：${action.textContent}`;
    node.append(action);
  }
}
function tileBack() {
  const tile = document.createElement("span"); tile.className = "tile tile-back"; tile.setAttribute("aria-hidden", "true"); return tile;
}
function renderTableFurniture() {
  const hands = $("#concealed-hands"); hands.replaceChildren();
  const scores = $("#center-scores"); scores.replaceChildren();
  for (let seat = 0; seat < 4; seat++) {
    const position = tablePosition(seat, room.seat);
    const score = document.createElement("div"); score.className = `center-seat center-${position}`;
    score.classList.toggle("active", isActiveMahjongSeat(seat));
    const wind = document.createElement("b"); wind.textContent = winds[(seat - room.game.dealer + 4) % 4];
    const points = document.createElement("span"); points.textContent = room.game.points[seat].toLocaleString();
    score.append(wind, points); scores.append(score);
    if (position === "self") continue;
    const hand = document.createElement("div"); hand.className = `concealed concealed-${position}`;
    hand.dataset.seat = seat; hand.setAttribute("aria-label", `${room.players[seat]?.name || "玩家"}：${room.game.hand_counts[seat]}张暗牌`);
    for (let index = 0; index < room.game.hand_counts[seat]; index++) hand.append(tileBack());
    const rack = document.createElement("div"); rack.className = `seat-rack seat-rack-${position}`;
    rack.append(hand); hands.append(rack);
  }
  $("#table-sticks").textContent = `${room.game.honba} 本场 · ${room.game.riichi_sticks || 0} 根立直棒`;
}
function renderRivers() {
  const holder = $("#rivers"); holder.replaceChildren();
  room.game.discards.forEach((river, seat) => {
    const line = document.createElement("div"); line.className = `river river-${tablePosition(seat, room.seat)}`; line.dataset.seat = seat;
    line.setAttribute("aria-label", `${room.players[seat]?.name || "玩家"}的弃牌`);
    for (const item of river) {
      const slot = document.createElement("span"); slot.className = "river-slot";
      const tile = tileNode(item.tile, true); tile.classList.toggle("latest-discard", latestDiscard?.seat === seat && latestDiscard.tile === item.tile);
      tile.classList.toggle("called", item.called); tile.classList.toggle("riichi", item.riichi); tile.disabled = true; slot.append(tile); line.append(slot);
    }
    holder.append(line);
  });
}
function renderMelds() {
  const holder = $("#melds"); holder.replaceChildren();
  room.game.melds.forEach((melds, seat) => {
    if (!melds.length) return;
    const group = document.createElement("div"); group.className = `meld-group meld-${tablePosition(seat, room.seat)}`; group.dataset.seat = seat;
    group.setAttribute("aria-label", `${room.players[seat]?.name || "玩家"}的副露`);
    for (const [index, meld] of melds.entries()) {
      const row = document.createElement("span"); row.className = "meld"; row.dataset.index = index;
      meld.tiles.forEach((id, offset) => {
        const concealed = meld.kind === "ankan" && (offset === 0 || offset === meld.tiles.length - 1);
        const tile = concealed ? tileBack() : tileNode(id, true); tile.disabled = true;
        tile.classList.toggle("meld-called", id === meld.called_tile); row.append(tile);
      }); group.append(row);
    }
    const position = tablePosition(seat, room.seat);
    (position === "self" ? holder : $(`.seat-rack-${position}`)).append(group);
  });
}
function renderHand() {
  $("#mahjong-table").dataset.handRows = String(Math.max(1, Math.ceil(room.game.hand.length / 7)));
  const holder = $("#hand"); holder.replaceChildren();
  if (room.seat === null) { const spectator = document.createElement("div"); spectator.className = "spectator"; spectator.textContent = "观战模式 · 手牌已隐藏"; holder.append(spectator); return; }
  const discardable = new Set(room.game.actions.discard || []);
  const ordered = [...room.game.hand.filter(id => id !== drawnTile), ...room.game.hand.filter(id => id === drawnTile)];
  ordered.forEach(id => {
    const tile = tileNode(id); tile.classList.toggle("drawn", id === drawnTile);
    if (room.game.hints?.discards?.[id]) {
      const status = handHintStatus(room.game.hints.discards[id]);
      const badge = document.createElement("span"); badge.className = `tenpai-badge ${status.tone}`; badge.textContent = status.tone === "ready" ? "听" : status.label.includes("振听") ? "振听" : status.label === "无役" ? "无役" : "听!"; badge.setAttribute("aria-hidden", "true");
      tile.setAttribute("aria-description", `打出后${status.label}：${status.detail}，点选查看`); tile.append(badge);
    }
    tile.disabled = !discardable.has(id); tile.classList.toggle("selected", id === selectedTile); tile.setAttribute("aria-pressed", String(id === selectedTile));
    tile.addEventListener("click", () => {
      if (Date.now() < ignoreTileClickUntil || actionBusy) return;
      if (selectedTile === id) { void perform("discard", {tile: id}); return; }
      selectedTile = id;
      for (const item of holder.querySelectorAll(".tile")) { const selected = Number(item.dataset.id) === selectedTile; item.classList.toggle("selected", selected); item.setAttribute("aria-pressed", String(selected)); }
      renderActions();
    });
    holder.append(tile);
  });
}
function actionButton(label, action, payload = {}, className = "secondary") { const button = document.createElement("button"); button.type = "button"; button.className = className; button.textContent = label; button.addEventListener("click", () => requestMahjongAction(action, payload)); return button; }
function renderActions() {
  const bar = $("#action-bar"); const actions = room.game.actions || {};
  $("#hand-guidance").textContent = room.seat === null ? "观战中 · 其他玩家手牌不可见" : actions.discard?.length ? selectedTile === null ? "点选预览 · 再点同牌或「打出」 · 长按上拖出牌" : `已选 ${tileLabel(selectedTile)} · 再点同牌或「打出」确认` : room.phase === "reaction" ? actions.pass ? "请选择本次回应" : "等待其他玩家回应" : "等待其他玩家行动";
  const key = JSON.stringify([room.id, room.phase, room.game.reaction_version ?? room.version, actions, selectedTile, meldChoice]);
  if (bar.dataset.key !== key) {
    bar.dataset.key = key; bar.replaceChildren();
    if (actions.pass) bar.append(actionButton("过", "pass", {}, "secondary pass-action"));
    if (actions.chi?.length) {
      const button = document.createElement("button"); button.type = "button"; button.className = "primary action-call"; button.textContent = "吃";
      button.addEventListener("click", () => {
        if (actions.chi.length === 1) requestMahjongAction("chi", {tiles: actions.chi[0]});
        else { meldChoice = meldChoice === "chi" ? null : "chi"; renderActions(); }
      });
      button.setAttribute("aria-expanded", String(meldChoice === "chi")); bar.append(button);
    }
    for (const choice of actions.pon || []) bar.append(actionButton("碰", "pon", {tiles: choice}, "primary action-call"));
    for (const choice of actions.kan || []) bar.append(actionButton("杠", "kan", {tiles: choice}, "primary action-call"));
    for (const type of actions.ankan || []) bar.append(actionButton(`暗杠 ${tileLabel(type * 4)}`, "ankan", {tile_type: type}, "primary action-call"));
    for (const choice of actions.kakan || []) bar.append(actionButton(`加杠 ${tileLabel(choice.tile_type * 4)}`, "kakan", {meld_index: choice.meld_index}, "primary action-call"));
    if (actions.kyuushu) bar.append(actionButton("九种九牌", "kyuushu"));
    if (selectedTile !== null && (actions.discard || []).includes(selectedTile)) { if ((actions.riichi || []).includes(selectedTile)) bar.append(actionButton("立直打出", "riichi", {tile: selectedTile}, "primary gold")); bar.append(actionButton("打出", "discard", {tile: selectedTile}, "primary")); }
    if (actions.ron) bar.append(actionButton("荣和", "ron", {}, "primary gold win-action"));
    if (actions.tsumo) bar.append(actionButton("自摸", "tsumo", {}, "primary gold win-action"));
    renderMeldChoices();
  }
  renderHandHints();
  if (room.phase === "reaction" && room.game.reaction_action) {
    const label = {chi:"吃",pon:"碰",kan:"杠",ron:"荣和",pass:"过"}[room.game.reaction_action];
    $("#hand-guidance").textContent = `已选择${label} · 等待其他玩家回应`;
  }
}
function renderMeldChoices() {
  const panel = $("#meld-choices"); panel.replaceChildren(); panel.hidden = !meldChoice;
  if (!meldChoice) return;
  const caption = document.createElement("strong"); caption.textContent = "选择吃牌组合";
  const timer = document.createElement("span"); timer.id = "meld-choice-timer"; caption.append(timer); panel.append(caption);
  const last = room.game.discards[room.game.turn]?.at(-1)?.tile;
  for (const tiles of room.game.actions.chi || []) {
    const button = actionButton("", "chi", {tiles}, "meld-choice"); button.setAttribute("aria-label", `吃 ${tiles.map(tileLabel).join("、")}`);
    for (const id of [...tiles, ...(last === undefined ? [] : [last])].sort((a,b) => a-b)) {
      const art = document.createElement("span"); art.className = `choice-tile${id === last ? " taken" : ""}`; art.append(createTileFace(id)); button.append(art);
    }
    panel.append(button);
  }
  const cancel = document.createElement("button"); cancel.type = "button"; cancel.className = "cancel-choice"; cancel.textContent = "取消";
  cancel.addEventListener("click", () => { meldChoice = null; renderActions(); }); panel.append(cancel);
  updateTimer();
}
function requestMahjongAction(action, payload) {
  if (room?.game?.actions?.ron && action !== "ron") {
    pendingWinDecline = {action, payload};
    $("#pass-win-note").textContent = room.game.riichi[room.seat] ? "你已立直。放弃后本局不能再荣和，只能自摸。" : "放弃后会暂时振听，直到自己下一次摸牌前不能荣和，仍可自摸。";
    $("#pass-win-dialog").showModal(); updateTimer(); return;
  }
  void perform(action, payload);
}
function selectedHandHint() {
  const hints = room?.game?.hints;
  return selectedTile !== null ? hints?.discards?.[selectedTile] : hints?.current;
}
function renderHandHints() {
  const hints = room.game.hints, value = selectedHandHint(), entries = value?.waits || [];
  const status = handHintStatus(value), actions = room.game.actions;
  const winNow = selectedTile === null && (actions.ron ? "荣和" : actions.tsumo ? "自摸" : "");
  const statusLabel = winNow ? `可${winNow}` : status.label;
  const preview = $("#wait-preview"); preview.replaceChildren(); preview.hidden = !entries.length || room.seat === null;
  preview.dataset.tone = winNow ? "ready" : status.tone;
  if (!preview.hidden) {
    const heading = document.createElement("span"); heading.className = "wait-preview-heading";
    heading.textContent = `${selectedTile !== null ? "打出后 · " : ""}${statusLabel}${entries.length > 3 ? ` · 共${entries.length}种` : ""}`;
    const tiles = document.createElement("span"); tiles.className = "preview-wait-tiles";
    for (const item of entries.slice(0,3)) {
      const permission = waitStatus(item), holder = document.createElement("span"); holder.className = "preview-wait-entry"; holder.dataset.tone = permission.tone;
      const tile = document.createElement("span"); tile.className = "preview-wait-tile"; tile.append(createTileFace(item.type * 4 + 1));
      const count = document.createElement("small"); count.textContent = String(item.unseen); tile.append(count);
      const badge = document.createElement("span"); badge.className = "wait-permission"; badge.textContent = permission.label;
      holder.append(tile, badge); tiles.append(holder);
    }
    const detail = document.createElement("span"); detail.className = "wait-preview-detail";
    detail.textContent = `${winNow ? `本次可胡，请点${winNow}` : status.detail} ›`;
    preview.append(heading, tiles, detail);
    preview.setAttribute("aria-label", `${heading.textContent}，${detail.textContent}，${entries.map(item => `${tileLabel(item.type*4+1)}未见${item.unseen}张，${waitStatus(item).ron}，${waitStatus(item).tsumo}`).join("；")}，查看详情`);
  }
  const button = $("#hand-hints-button");
  const prefix = selectedTile !== null ? `打出${tileLabel(selectedTile)}后` : "当前";
  const count = Object.keys(hints?.discards || {}).length;
  button.textContent = winNow ? `可${winNow} ›` : entries.length ? `${statusLabel} · ${entries.length}种 ›` : count ? `${count}张可打听 ›` : "听牌与规则 ›";
  button.classList.toggle("ready", !!winNow || entries.length > 0 || count > 0);
  button.dataset.tone = winNow ? "ready" : entries.length ? status.tone : "";
  if (winNow) $("#hand-guidance").textContent = `本次可以${winNow}，请点${winNow}按钮`;
  else if (entries.length) $("#hand-guidance").textContent = `${status.detail} · 未见${entries.reduce((sum,item) => sum + item.unseen,0)}张`;
  $("#hand-hints-heading").textContent = winNow ? `现在可以${winNow}` : entries.length ? `${prefix}听 ${entries.length} 种牌 · ${status.label}` : room.seat === null ? "观战不展示私人听牌信息" : selectedTile !== null ? `${prefix}未听牌` : count ? "点选带标记的手牌，查看打出后的听牌条件" : hints?.current ? "当前未听牌" : "请先选一张要打出的牌";
  const reasons = {discard:"你曾打出过所听牌中的一种，因此所有待牌都不能荣和。自摸仍需满足役种条件。",temporary:"暂时不能荣和，等自己下一次摸牌后解除。自摸仍需满足役种条件。",riichi_pass:"立直后放过胡牌，本局不能再荣和，只能自摸。"};
  const note = $("#hand-hints-note");
  note.textContent = winNow ? `本次已满足和牌条件，请关闭说明后点“${winNow}”。下方逐张信息通常按普通条件计算。` : entries.length ? `${status.detail}。${reasons[value?.furiten] || "荣和＝胡别人打出的牌；自摸＝胡自己摸到的牌。"}` : "听牌只表示差一张凑齐牌型，能否胡还要满足役种与振听规则。";
  const list = $("#hand-hints-list"); list.replaceChildren();
  for (const item of entries) {
    const permission = waitStatus(item), row = document.createElement("div"); row.className = "wait-tile"; row.dataset.tone = permission.tone;
    const art = document.createElement("span"); art.className = "wait-tile-art"; art.append(createTileFace(item.type * 4 + 1));
    const copy = document.createElement("div"), title = document.createElement("strong"), description = document.createElement("small");
    title.textContent = `${tileLabel(item.type * 4 + 1)} · 未见 ${item.unseen} 张`;
    description.textContent = `${permission.ron} · ${permission.tsumo}${item.ron_now ? " · 本次可荣和" : ""}`;
    copy.append(title, description); row.append(art, copy); list.append(row);
  }
  if (!winNow && value?.closed && entries.some(item => item.ron_reason === "no_yaku")) note.textContent += " 门前清可通过立直取得役；满足条件时会出现“立直打出”。";
  if (!winNow && entries.some(item => item.ron_reason === "no_yaku" || item.tsumo_reason === "no_yaku")) note.textContent += " 无役＝缺少有效胡牌条件；宝牌不能单独作为役。海底、抢杠等特殊情况以实际和牌按钮为准。";
}

function resultCopy(result) {
  if (!result) return "结算中"; if (result.kind === "match") return `终局 · ${result.reason}`; if (result.kind === "途中流局") return result.reason; return resultNames[result.kind] || result.kind;
}
function renderResult() {
  const holder = $("#result"); holder.replaceChildren(); const resultKey = JSON.stringify([room.phase, room.version, room.game?.result, room.settlement]);
  if (!room.game?.result || !["hand_finished", "match_finished"].includes(room.phase) || dismissedResult === resultKey) { show("#result", false); return; }
  show("#result"); const heading = document.createElement("header"); const headingCopy = document.createElement("div"); const eyebrow = document.createElement("span"); eyebrow.textContent = room.phase === "match_finished" ? "MATCH RESULT" : "ROUND RESULT"; const title = document.createElement("h2"); title.textContent = resultCopy(room.game.result); const subtitle = document.createElement("small"); const rakeCopy = room.room_type === "coin" && room.settlement ? ` · 抽水 ${room.settlement.rake_amount || 0} 币（${room.settlement.rake_percent || 0}%）` : ""; subtitle.textContent = `本局已结算${rakeCopy} · 四人重新准备，房主开始后才发牌`; headingCopy.append(eyebrow, title, subtitle); const mark = document.createElement("b"); mark.textContent = room.phase === "match_finished" ? "终" : "局"; heading.append(headingCopy, mark);
  const rows = document.createElement("div"); rows.className = "result-rows";
  const lastHand = room.game.last_hand_result;
  if (lastHand?.winners?.length) {
    const evidence = document.createElement("div"); evidence.className = "winning-evidence";
    for (const seat of lastHand.winners) {
      const block = document.createElement("article"); const label = document.createElement("div"); const name = document.createElement("strong"); name.textContent = `${room.players[seat]?.name || "玩家"} · ${resultNames[lastHand.kind] || lastHand.kind}`;
      const detail = lastHand.details?.find(item => item.seat === seat); const yaku = document.createElement("small"); yaku.textContent = detail ? `${detail.yaku.join(" · ")} · ${detail.han}番${detail.fu ? ` ${detail.fu}符` : ""}${detail.limit ? ` · ${detail.limit}` : ""}` : "和牌"; label.append(name, yaku);
      const tiles = document.createElement("div"); tiles.className = "winning-tiles"; (room.game.winning_hands?.[String(seat)] || []).forEach(id => { const tile = tileNode(id, true); tile.disabled = true; tiles.append(tile); }); if (!lastHand.tiles_unavailable && lastHand.kind === "ron" && lastHand.tile !== undefined) { const separator = document.createElement("i"); separator.textContent = "+"; tiles.append(separator); const tile = tileNode(lastHand.tile, true); tile.disabled = true; tiles.append(tile); }
      block.append(label, tiles); evidence.append(block);
    }
    holder.append(heading, evidence);
  } else holder.append(heading);
  const order = room.settlement?.order || room.game.result.order || [0, 1, 2, 3].sort((a, b) => room.game.points[b] - room.game.points[a]);
  order.forEach((seat, index) => {
    const player = room.players[seat]; const row = document.createElement("div"); row.className = lastHand?.winners?.includes(seat) ? "winner" : "";
    const rank = document.createElement("b"); rank.textContent = String(index + 1); const avatar = avatarNode(player, "result-avatar"); const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = player?.name || "玩家"; const note = document.createElement("small");
    if (room.room_type === "coin" && room.settlement?.net) { const net = room.settlement.net[seat] || 0; note.textContent = `本局摸鱼币 ${net >= 0 ? "+" : ""}${net} · 托管退回 ${room.settlement.refunds?.[seat] || 0}`; } else note.textContent = winds[(seat - room.game.dealer + 4) % 4] + "家";
    copy.append(name, note);
    const score = document.createElement("span"); const points = document.createElement("strong"); points.textContent = room.game.points[seat].toLocaleString(); const delta = lastHand?.starting_points ? room.game.points[seat] - lastHand.starting_points[seat] : lastHand?.deltas?.[seat]; const change = document.createElement("small"); change.textContent = delta === undefined ? "" : `${delta >= 0 ? "+" : ""}${delta}`; score.append(points, change); row.append(rank, avatar, copy, score); rows.append(row);
  });
  const actions = document.createElement("div"); actions.className = "result-actions";
  if (room.seat !== null) {
    const ready = room.players[room.seat]?.ready; const readyButton = document.createElement("button"); readyButton.type = "button"; readyButton.className = ready ? "secondary" : "primary gold"; readyButton.textContent = ready ? "取消准备" : "准备下一局"; readyButton.addEventListener("click", () => perform(ready ? "unready" : "ready")); actions.append(readyButton);
    const exit = document.createElement("button"); exit.type = "button"; exit.className = "secondary"; exit.textContent = "退出房间"; exit.addEventListener("click", returnToLobby); actions.append(exit);
    if (room.seat === room.creator_seat) { const readyCount = room.players.filter(player => player?.ready).length; const start = document.createElement("button"); start.type = "button"; start.className = "primary gold"; start.disabled = readyCount !== 4 || room.players.some(player => player?.online === false); start.textContent = readyCount !== 4 ? `等待准备 ${readyCount}/4` : start.disabled ? "等待玩家上线" : "开始下一局"; start.addEventListener("click", () => perform("start")); actions.append(start); }
  } else { const close = document.createElement("button"); close.type = "button"; close.className = "primary gold"; close.textContent = "返回大厅"; close.addEventListener("click", () => { dismissedResult = resultKey; show("#result", false); void returnToLobby(); }); actions.append(close); }
  const body = document.createElement("div"); body.className = "result-body";
  const evidence = holder.querySelector(".winning-evidence"); if (evidence) body.append(evidence);
  body.append(rows);
  if (room.room_type === "coin" && room.settlement?.transfers) {
    const details = document.createElement("section"); details.className = "coin-breakdown";
    const rate = document.createElement("strong"); rate.textContent = `每2000点＝${room.buy_in}币 · 每笔向上取整`; details.append(rate);
    for (const entry of room.settlement.transfers) {
      const line = document.createElement("p"); line.textContent = `${room.players[entry.from]?.name || "玩家"} → ${room.players[entry.to]?.name || "玩家"}：${entry.points}点 ÷ 2000 × ${room.buy_in} ＝ ${entry.coins}币（向上取整）`; details.append(line);
    }
    const sticks = document.createElement("p");
    const paid = room.settlement.riichi_paid || [];
    sticks.textContent = paid.map((coins, seat) => coins ? `${room.players[seat]?.name}立直已付${coins}币` : "").filter(Boolean).join("；");
    if (room.settlement.riichi_award) sticks.textContent += `；${room.players[room.settlement.riichi_recipient]?.name}领取立直棒${room.settlement.riichi_award}币（已扣款，不重复收取）`;
    if (room.settlement.riichi_carried) sticks.textContent += `；桌面立直棒${room.settlement.riichi_carried}币留待下局`;
    if (sticks.textContent) details.append(sticks);
    if (!room.settlement.transfers.length && !room.settlement.riichi_award) { const line = document.createElement("p"); line.textContent = "本局无玩家间付款"; details.append(line); }
    body.append(details);
  }
  const status = document.createElement("p"); status.className = "result-ready-status";
  status.textContent = room.players.map(player => `${player?.name || "玩家"}：${player?.online === false ? "离线" : player?.ready ? "已准备" : "未准备"}`).join(" · ");
  holder.append(body, status, actions);
}
function renderGame() {
  document.body.dataset.tablePhase = "game";
  show("#waiting", false); show("#mahjong-table"); const order = seatOrder(); renderPlayer("#opponent-left", order.left); renderPlayer("#opponent-top", order.top); renderPlayer("#opponent-right", order.right); renderPlayer("#self-player", order.self);
  const round = `${winds[room.game.round_wind - 27] || "东"}${room.game.hand_number}局`;
  const rakeCopy = room.room_type === "coin" ? ` · 抽水 ${room.rake_percent || 0}%` : ""; $("#round-label").textContent = `${round} · ${room.game.honba}本场${rakeCopy}`; $("#center-round").textContent = round; $("#remaining-count").textContent = `余 ${room.game.remaining} 张`; $("#turn-status").textContent = ["hand_finished", "match_finished"].includes(room.phase) ? "本局结束 · 等待重新准备" : room.phase === "reaction" ? room.game.actions?.pass ? "等待你的回应" : "等待其他玩家回应" : room.game.turn === room.seat ? "轮到你出牌" : `${room.players[room.game.turn]?.name || "玩家"} 思考中`;
  const dora = $("#dora"); dora.replaceChildren(); room.game.dora_indicators.forEach(id => { const node = tileNode(id, true); node.disabled = true; dora.append(node); });
  $("#mahjong-cue").textContent = mahjongCue; renderTableFurniture(); renderRivers(); renderMelds(); renderHand(); renderActions(); renderResult(); animateMahjongChanges();
}
function clearMahjongAnimations() {
  for (const ghost of document.querySelectorAll(".tile-flight")) { ghost.getAnimations().forEach(animation => animation.cancel()); ghost.remove(); }
  calloutAnimation?.cancel(); $("#table-callout").hidden = true;
}
function flyMahjongTile(tile, origin, fromSeat, toSeat, originRotation = 0) {
  if (!tile || !origin) return;
  const end = tile.getBoundingClientRect(), width = tile.offsetWidth, height = tile.offsetHeight;
  const angle = seat => ({self:0,right:-90,top:180,left:90}[tablePosition(seat, room.seat)]);
  const endScale = tile.classList.contains("meld-called") ? .88 : tile.classList.contains("riichi") ? .84 : 1;
  const endAngle = angle(toSeat) + (tile.classList.contains("meld-called") || tile.classList.contains("riichi") ? 90 : 0);
  const dx = origin.x + origin.width / 2 - end.x - end.width / 2, dy = origin.y + origin.height / 2 - end.y - end.height / 2;
  const ghost = tile.cloneNode(true); ghost.className = "tile-flight"; ghost.removeAttribute("data-id"); ghost.setAttribute("aria-hidden", "true"); ghost.tabIndex = -1;
  Object.assign(ghost.style, {left:`${end.x + (end.width - width) / 2}px`,top:`${end.y + (end.height - height) / 2}px`,width:`${width}px`,height:`${height}px`});
  document.body.append(ghost);
  const animation = ghost.animate([
    {transform:`translate(${dx}px,${dy}px) rotate(${angle(fromSeat) + originRotation}deg) scale(1.15)`,opacity:.85},
    {transform:`translate(0,0) rotate(${endAngle}deg) scale(${endScale})`,opacity:1,offset:.88},
    {transform:`translate(0,0) rotate(${endAngle}deg) scale(${endScale})`,opacity:0}
  ], {duration:340,easing:"cubic-bezier(.2,.7,.25,1)"});
  tile.animate([{opacity:0},{opacity:0,offset:.8},{opacity:1}],{duration:340});
  animation.onfinish = () => ghost.remove(); animation.oncancel = () => ghost.remove();
}
function animateMahjongChanges() {
  const changes = tableChanges; tableChanges = []; clearMahjongAnimations();
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  for (const change of changes) {
    const position = tablePosition(change.seat, room.seat);
    $(`.player[data-seat="${change.seat}"] .player-action`)?.animate([{opacity:.3,transform:"translateY(5px)"},{opacity:1,transform:"translateY(0)"}],{duration:240});
    if (change.kind === "draw") {
      const tile = change.seat === room.seat ? $("#hand .drawn") : $(`.concealed-${position} .tile:last-child`);
      tile?.animate([{opacity:0,transform:"translate(16px,-18px)"},{opacity:1,transform:"translate(0,0)"}],{duration:280,easing:"ease-out"});
    }
    if (change.kind === "discard") {
      const tile = $(`.river[data-seat="${change.seat}"] .tile[data-id="${change.tile}"]`);
      flyMahjongTile(tile, change.origin, change.seat, change.seat, change.originRotation);
    }
    if (change.kind === "meld") {
      const meld = $(`.meld-group[data-seat="${change.seat}"] .meld[data-index="${change.index}"]`);
      flyMahjongTile(meld?.querySelector(`[data-id="${change.movingTile}"]`), change.origin, change.originSeat ?? change.seat, change.seat, change.originRotation);
      meld?.animate([{filter:"brightness(1.65)"},{filter:"brightness(1)"}],{duration:600});
    }
    if (change.kind === "meld" || change.riichi) {
      const label = change.riichi ? "立直" : {chi:"吃",pon:"碰",kan:"杠",ankan:"暗杠",minkan:"杠",kakan:"加杠"}[change.meld] || "鸣牌";
      const callout = $("#table-callout"); calloutAnimation?.cancel(); callout.replaceChildren();
      const name = document.createElement("small"); name.textContent = room.players[change.seat]?.name || "玩家";
      const mark = document.createElement("strong"); mark.textContent = label; callout.append(name, mark); callout.hidden = false;
      calloutAnimation = callout.animate([{opacity:0,transform:"translate(-50%,-50%) scale(.9)"},{opacity:1,transform:"translate(-50%,-50%) scale(1)",offset:.2},{opacity:1,offset:.7},{opacity:0,transform:"translate(-50%,-58%) scale(1)"}],{duration:750,easing:"ease-out"});
      calloutAnimation.onfinish = () => callout.hidden = true;
    }
  }
}
function updateChatBadges() {
  for (const selector of ["#chat-unread", "#chat-preview-unread"]) { const badge = $(selector); badge.textContent = String(unreadChat); badge.hidden = unreadChat === 0; }
}
function openChat() { chatOpen = true; unreadChat = 0; $("#table").classList.add("chat-open"); show("#chat-drawer"); show("#chat-preview", false); updateChatBadges(); $("#chat-input").focus(); }
function closeChat() { chatOpen = false; $("#table").classList.remove("chat-open"); show("#chat-drawer", false); show("#chat-preview"); }
function renderMessages() {
  const entries = room.messages || [];
  if (messagesInitialized && entries.length > seenMessageCount && !chatOpen) unreadChat += entries.length - seenMessageCount;
  messagesInitialized = true; seenMessageCount = entries.length;
  const list = $("#messages"); const reading = readingPosition(list); list.replaceChildren();
  for (const item of entries) { const row = document.createElement("div"); const avatar = item.player ? playerButton(item.player, "message") : document.createElement("i"); if (!item.player) avatar.textContent = item.name?.slice(0, 1) || "?"; const copy = document.createElement("span"); const name = document.createElement("strong"); name.textContent = item.name; if (item.player) { name.role = "button"; name.tabIndex = 0; name.addEventListener("click", () => openPlayerProfile(item.player.id)); } const text = document.createElement("b"); text.textContent = item.text; copy.append(name, text); row.append(avatar, copy); list.append(row); }
  restoreReading(list, reading);
  const preview = $("#chat-preview-lines"); preview.replaceChildren();
  for (const item of entries.slice(-3)) { const line = document.createElement("span"); const name = document.createElement("b"); name.textContent = item.name; const text = document.createElement("i"); text.textContent = item.text; line.append(name, text); preview.append(line); }
  if (!entries.length) preview.textContent = "还没有聊天消息";
  updateChatBadges();
}
function renderTable() {
  $("#table-title").textContent = `${room.players[0]?.name || "玩家"}的牌桌`; $("#round-label").textContent = phaseNames[room.phase] || room.phase;
  if (room.phase === "waiting") renderWaiting(); else renderGame(); renderMessages(); updateTimer();
}
async function perform(action, payload = {}) {
  if (!room || actionBusy) return; feedback(); actionBusy = true; document.body.classList.add("action-busy");
  try {
    if (room.phase === "reaction" && room.game.reaction_version != null) payload = {...payload, reaction_version: room.game.reaction_version};
    const next = await client.action(room.id, room.version, action, payload);
    if (action === "leave") { await returnToLobby(); return; }
    setRoom(next); selectedTile = null; renderTable();
  } catch (error) { feedback(error.message, "error"); } finally { actionBusy = false; document.body.classList.remove("action-busy"); }
}
async function sendChatText(text) {
  if (!room || !text || $("#chat-send").disabled) return false;
  $("#chat-send").disabled = true; $("#room-chat-feedback").textContent = ""; const id = room.id;
  try { await client.chat(id, text); if (room?.id === id) { setRoom(await client.snapshot(id)); renderMessages(); } return true; }
  catch (error) { feedback(error.message, "error"); return false; }
  finally { $("#chat-send").disabled = false; }
}
async function sendChat() { const input = $("#chat-input"); const text = input.value.trim(); if (!text) return; if (await sendChatText(text) && input.value.trim() === text) input.value = ""; }
async function shareRoom() {
  if (!room) return;
  try {
    await sdk?.share?.({title: "摸鱼麻将", description: `${room.players[0]?.name || "玩家"}的牌桌 · 点击即可入座或观战`, params: JSON.stringify({roomId: room.id})});
  } catch (error) { feedback(error.message || "分享失败，请重试", "error"); }
}
async function shareRoomToChannel(value = null) {
  const share = value || (room && {game: "mahjong", roomId: room.id, host: room.players[0]?.name || room.creator_name || "玩家"});
  if (!share) throw new Error("请先进入房间");
  await client.sendChannel(roomShareText(share));
  await openClubDrawer("channel");
}
function updateTimer() {
  const seconds = secondsLeft(); $("#timer").textContent = seconds === null ? "--" : `${seconds}s`;
  const timer = $("#decision-timer"); timer.textContent = seconds === null ? "—" : String(seconds);
  timer.classList.toggle("urgent", seconds !== null && seconds <= 8);
  const choiceTimer = $("#meld-choice-timer");
  if (choiceTimer) choiceTimer.textContent = `剩余 ${seconds ?? "—"} 秒`;
  if ($("#pass-win-dialog").open) {
    $("#pass-win-timer").textContent = `回应剩余 ${Math.max(0, seconds ?? 0)} 秒 · 计时不会暂停`;
    if (seconds !== null && seconds <= 0) { $("#pass-win-dialog").close(); pendingWinDecline = null; }
  }
}

const customSelects = [...document.querySelectorAll(".custom-select")];
function closeCustomSelect(root, returnFocus = false) {
  const menu = root.querySelector(".custom-select-menu");
  root.classList.remove("open"); menu.hidden = true; root.querySelector(".custom-select-trigger").setAttribute("aria-expanded", "false");
  if (returnFocus) root.querySelector(".custom-select-trigger").focus();
}
function closeCustomSelects(except = null) { customSelects.forEach(root => { if (root !== except) closeCustomSelect(root); }); }
function syncCustomSelect(root) {
  const select = $(`#${root.dataset.selectFor}`); const selected = select.options[select.selectedIndex];
  root.querySelector(".custom-select-trigger>span").textContent = selected.textContent;
  root.querySelectorAll("[role=option]").forEach(option => option.setAttribute("aria-selected", String(option.dataset.value === select.value)));
}
function syncCreateEconomy() {
  const coin = $("#room-type").value === "coin"; show("#stake-field", coin); show(".prize-panel", coin);
  if (coin) { const stake = Number($("#stake").value); $("#prize-copy").textContent = `每2000点＝${stake}币，每笔向上取整。荣和由放炮者支付，自摸三家分别支付；每局托管${stake}币，结算全退后按得点收付；赢家收益抽水${mahjongEconomy.rake_percent}%，余额可为负。`; }
}
function openCustomSelect(root, focusOption = false) {
  closeCustomSelects(root); const menu = root.querySelector(".custom-select-menu");
  root.classList.add("open"); menu.hidden = false; root.querySelector(".custom-select-trigger").setAttribute("aria-expanded", "true");
  if (focusOption) (menu.querySelector('[aria-selected="true"]') || menu.querySelector("[role=option]"))?.focus();
}
function bindCustomSelectOption(root, option) {
  const select = $(`#${root.dataset.selectFor}`);
  option.addEventListener("click", () => { select.value = option.dataset.value; select.dispatchEvent(new Event("change", {bubbles: true})); closeCustomSelect(root, true); });
  option.addEventListener("keydown", event => {
    const options = [...root.querySelectorAll("[role=option]")]; const index = options.indexOf(event.currentTarget);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); options[(index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length].focus(); }
    if (event.key === "Escape") { event.preventDefault(); closeCustomSelect(root, true); }
  });
}
customSelects.forEach(root => {
  const select = $(`#${root.dataset.selectFor}`); const trigger = root.querySelector(".custom-select-trigger");
  syncCustomSelect(root); select.addEventListener("change", () => syncCustomSelect(root));
  trigger.addEventListener("click", () => root.classList.contains("open") ? closeCustomSelect(root) : openCustomSelect(root));
  trigger.addEventListener("keydown", event => { if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); openCustomSelect(root, true); } });
  root.querySelectorAll("[role=option]").forEach(option => bindCustomSelectOption(root, option));
});
function applyMahjongEconomy() {
  const select = $("#stake"); const root = document.querySelector('[data-select-for="stake"]'); const menu = root.querySelector(".custom-select-menu");
  const preferred = mahjongEconomy.coin_stakes.includes(10) ? 10 : mahjongEconomy.coin_stakes[0];
  select.replaceChildren(...mahjongEconomy.coin_stakes.map(stake => {
    const option = document.createElement("option"); option.value = String(stake); option.textContent = `${stake} 摸鱼币`; option.selected = stake === preferred; return option;
  }));
  menu.replaceChildren(...mahjongEconomy.coin_stakes.map(stake => {
    const option = document.createElement("button"); option.type = "button"; option.setAttribute("role", "option"); option.dataset.value = String(stake);
    const copy = document.createElement("span"); const title = document.createElement("b"); title.textContent = `${stake} 摸鱼币`; const note = document.createElement("small"); note.textContent = `每2000点＝${stake}币`; copy.append(title, note); option.append(copy);
    if (stake === preferred) { const mark = document.createElement("em"); mark.textContent = "推荐"; option.append(mark); }
    bindCustomSelectOption(root, option); return option;
  }));
  syncCustomSelect(root); syncCreateEconomy();
}
async function refreshMahjongEconomy() {
  mahjongEconomy = await loadEconomy(CONFIG.apiBase, "mahjong");
  applyMahjongEconomy();
}
async function openMahjongCreateDialog() {
  await refreshMahjongEconomy();
  $("#create-dialog").showModal();
}
document.addEventListener("pointerdown", event => { if (!event.target.closest(".custom-select")) closeCustomSelects(); });
$("#create-dialog").addEventListener("close", () => closeCustomSelects());
$("#room-type").addEventListener("change", syncCreateEconomy); $("#stake").addEventListener("change", syncCreateEconomy); syncCreateEconomy();

function clearHandGesture() { clearTimeout(handHoldTimer); handHoldTimer = null; handGesture = null; $("#hand").classList.remove("drag-armed", "drag-ready"); }
$("#hand").addEventListener("pointerdown", event => {
  const tile = event.target.closest(".tile:not(:disabled)"); if (!tile || !room?.game) return;
  handGesture = {pointerId: event.pointerId, tile: Number(tile.dataset.id), startY: event.clientY, currentY: event.clientY, armed: false};
  handHoldTimer = setTimeout(() => { if (!handGesture || handGesture.pointerId !== event.pointerId) return; handGesture.armed = true; $("#hand").classList.add("drag-armed"); }, 280);
  tile.setPointerCapture?.(event.pointerId);
});
document.addEventListener("pointermove", event => { if (!handGesture || handGesture.pointerId !== event.pointerId) return; handGesture.currentY = event.clientY; $("#hand").classList.toggle("drag-ready", handGesture.armed && handGesture.startY - event.clientY >= 44); });
document.addEventListener("pointerup", event => {
  if (!handGesture || handGesture.pointerId !== event.pointerId) return;
  const gesture = {...handGesture, currentY: event.clientY}; const play = gesture.armed && gesture.startY - gesture.currentY >= 44; clearHandGesture();
  if (play && (room?.game?.actions?.discard || []).includes(gesture.tile)) { ignoreTileClickUntil = Date.now() + 500; selectedTile = gesture.tile; event.preventDefault(); void perform("discard", {tile: gesture.tile}); }
});
document.addEventListener("pointercancel", event => { if (handGesture?.pointerId === event.pointerId) clearHandGesture(); });

$("#refresh").addEventListener("click", () => boot(true)); $("#home").addEventListener("click", openHome); $("#home-nav").addEventListener("click", openHome); $("#club-back").addEventListener("click", openHome); $("#lobby-back").addEventListener("click", returnToLobby);
$("#create-room").addEventListener("click", () => void openMahjongCreateDialog()); $("#cancel-create").addEventListener("click", () => $("#create-dialog").close()); $("#confirm-create").addEventListener("click", event => { event.preventDefault(); void enterFullscreen(true); createRoom(); });
$("#claim").addEventListener("click", () => perform("claim")); $("#ready").addEventListener("click", () => perform($("#ready").dataset.action || "ready")); $("#start").addEventListener("click", () => perform("start")); $("#leave").addEventListener("click", () => perform("leave"));
$("#share-room").addEventListener("click", shareRoom);
$("#share-room-channel").addEventListener("click", () => shareRoomToChannel().catch(error => feedback(error.message || "分享失败，请重试", "error")));
$("#fullscreen").addEventListener("click", toggleFullscreen); document.addEventListener("fullscreenchange", updateFullscreenButton); document.addEventListener("webkitfullscreenchange", updateFullscreenButton);
$("#table-channel").addEventListener("click", () => openClubDrawer("channel"));
$("#chat-channel").addEventListener("click", () => openClubDrawer("channel"));
$("#chat-toggle").addEventListener("click", openChat); $("#chat-preview").addEventListener("click", openChat); $("#chat-close").addEventListener("click", closeChat); $("#chat-send").addEventListener("click", sendChat); $("#chat-input").addEventListener("keydown", event => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); sendChat(); } });
document.querySelectorAll("[data-quick-chat]").forEach(button => button.addEventListener("click", () => sendChatText(button.dataset.quickChat)));
$("#channel-toggle").addEventListener("click", () => openClubDrawer("channel")); $("#channel-peek").addEventListener("click", () => openClubDrawer("channel")); $("#tasks-toggle").addEventListener("click", () => openClubDrawer("tasks")); $("#profile-toggle").addEventListener("click", () => openClubDrawer("profile"));
$("#club-drawer-close").addEventListener("click", closeClubDrawer); $("#club-drawer-backdrop").addEventListener("click", closeClubDrawer); document.querySelectorAll("[data-club-tab]").forEach(button => button.addEventListener("click", () => openClubDrawer(button.dataset.clubTab)));
$("#club-channel-send").addEventListener("click", async () => { const button = $("#club-channel-send"); const input = $("#club-channel-input"); const text = input.value.trim(); if (!text || button.disabled) return; button.disabled = true; $("#drawer-feedback").textContent = ""; feedback(); try { await client.sendChannel(text); if (input.value.trim() === text) input.value = ""; await renderChannel(); } catch (error) { feedback(error.message, "error"); } finally { button.disabled = false; } });
$("#club-channel-input").addEventListener("keydown", event => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); $("#club-channel-send").click(); } });
$("#friend-add").addEventListener("click", async () => { const input = $("#friend-player-id"); try { await client.requestFriend(input.value.trim()); input.value = ""; await renderFriends(); } catch (error) { feedback(error.message, "error"); } });
$("#direct-back").addEventListener("click", () => renderFriends().catch(error => feedback(error.message, "error")));
$("#direct-send").addEventListener("click", async () => { const button = $("#direct-send"); const input = $("#direct-input"); const text = input.value.trim(); const friend = activeDirectFriend; if (!friend || !text || button.disabled) return; button.disabled = true; $("#drawer-feedback").textContent = ""; feedback(); try { await client.sendDirectMessage(friend.id, text); if (activeDirectFriend?.id === friend.id) { if (input.value.trim() === text) input.value = ""; await openDirect(friend); } else if (directDrafts.get(friend.id)?.trim() === text) directDrafts.delete(friend.id); } catch (error) { feedback(error.message, "error"); } finally { button.disabled = false; } });
window.MoyuClubRuntime = {
  embedded: true,
  sdk,
  openGameLobby: game => openClubGame(game),
  openChannel: () => openClubDrawer("channel"),
  openProfile: player => openPlayerProfile(player.id),
  shareRoom: shareRoomToChannel,
  setRoomContext(value) { clubModuleRoom = value; $("#club-module-share").hidden = !value; },
  clearRoomContext() { clubModuleRoom = null; $("#club-module-share").hidden = true; },
  close: closeClubGame,
};
window.MoyuClub = {closeGame: closeClubGame};
$("#club-module-home").addEventListener("click", () => { if (["playing", "bidding", "drawing", "selecting", "revealing"].includes(clubModuleRoom?.phase) && !confirm("返回大厅不会退出房间。进行中的牌局倒计时仍会继续，可在大厅返回牌局。确定暂离吗？")) return; closeClubGame(); });
$("#club-module-public").addEventListener("click", () => openClubDrawer("channel"));
$("#club-module-share").addEventListener("click", () => { if (clubModuleRoom) void shareRoomToChannel(clubModuleRoom); });
window.addEventListener("resize", clearMahjongAnimations);
setInterval(updateTimer, 500); window.addEventListener("visibilitychange", () => { if (!document.hidden) void refreshPresence(); }); window.addEventListener("pagehide", () => { clearInterval(presenceTimer); clearTimeout(socialRefreshTimer); client.dispose(); }); updateFullscreenButton(); boot();

function readingPosition(list) { return {top: list.scrollTop, bottom: !list.children.length || list.scrollHeight - list.scrollTop - list.clientHeight < 48}; }
function restoreReading(list, position) { list.scrollTop = position.bottom ? list.scrollHeight : position.top; }
function saveDirectDraft() { if (activeDirectFriend) directDrafts.set(activeDirectFriend.id, $("#direct-input").value); }
async function refreshResumeRoom() {
  const version = ++resumeVersion;
  const current = await client.activeRoom().catch(() => null);
  if (version !== resumeVersion) return;
  savedActiveRoom = current;
  $("#resume-room").hidden = !current?.room_id;
  if (current) $("#resume-room-label").textContent = `${gameNames[current.game] || "游戏"} · 座位保留，进行中的倒计时仍会继续`;
}
$("#resume-room").addEventListener("click", () => { if (savedActiveRoom) joinSharedRoom({game: savedActiveRoom.game, roomId: savedActiveRoom.room_id}); });
$("#friends-toggle").addEventListener("click", () => openClubDrawer("friends"));
$("#profile-back").addEventListener("click", () => { const origin = profileOrigin; profileOrigin = null; if (origin) void openClubDrawer(origin.tab, null, true); });
for (const [button, list] of [["#channel-new", "#club-channel-messages"], ["#direct-new", "#direct-messages"]]) {
  $(button).addEventListener("click", () => { $(list).scrollTop = $(list).scrollHeight; $(button).hidden = true; });
}
$("#direct-input").addEventListener("keydown", event => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); $("#direct-send").click(); } });
document.addEventListener("keydown", event => {
  if ($("#club-drawer").hidden) return;
  if (event.key === "Escape") closeClubDrawer();
  if (event.key !== "Tab") return;
  const focusable = [...$("#club-drawer").querySelectorAll("button:not(:disabled), input:not(:disabled), [tabindex='0']")].filter(node => node.getClientRects().length);
  const first = focusable[0], last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
});

const navigationIcons = {"home-nav": "M3 10l9-7 9 7v11H3z M9 21v-8h6v8", "channel-toggle": "M3 4h18v13H9l-6 4z M7 8h10 M7 12h7", "friends-toggle": "M16 21v-2a5 5 0 0 0-10 0v2 M11 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M18 5a4 4 0 0 1 0 7 M20 16a5 5 0 0 1 2 4", "tasks-toggle": "M5 3h14v18H5z M8 8l2 2 5-5 M8 15h8", "profile-toggle": "M4 21v-2a8 8 0 0 1 16 0v2 M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8"};
for (const [id, path] of Object.entries(navigationIcons)) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true");
  const line = document.createElementNS(svg.namespaceURI, "path"); line.setAttribute("d", path); svg.append(line); $(`#${id} b`).replaceChildren(svg);
}

$("#wait-preview").addEventListener("click", () => $("#hand-hints-dialog").showModal());
$("#hand-hints-button").addEventListener("click", () => { renderHandHints(); $("#hand-hints-dialog").showModal(); });
$("#close-hand-hints").addEventListener("click", () => $("#hand-hints-dialog").close());
$("#cancel-pass-win").addEventListener("click", () => { $("#pass-win-dialog").close(); pendingWinDecline = null; });
$("#confirm-pass-win").addEventListener("click", () => { const pending = pendingWinDecline; pendingWinDecline = null; $("#pass-win-dialog").close(); if (pending && room?.game?.actions?.ron) void perform(pending.action, pending.payload); });
