import {ClubClient} from "./client.js";
import {CONFIG} from "./config.js";

const $ = selector => document.querySelector(selector);
const sdk = window.dzmm;
const client = new ClubClient({sdk, apiBase: CONFIG.apiBase});
let rooms = [], room = null, stopFollow = null, selectedTile = null, receivedAt = 0, bootReady = false;
let chatOpen = false, unreadChat = 0, seenMessageCount = 0, messagesInitialized = false;
let dismissedResult = null;
let activeClubTab = "channel", activeDirectFriend = null;

const winds = ["东", "南", "西", "北"];
const phaseNames = {waiting: "候场", playing: "对局中", reaction: "鸣牌响应", hand_finished: "本局结算", match_finished: "终局", cancelled: "已取消"};
const resultNames = {tsumo: "自摸", ron: "荣和", "荒牌流局": "荒牌流局", "流局满贯": "流局满贯", "途中流局": "途中流局", match: "终局"};

function feedback(text = "", kind = "info") { const node = $("#feedback"); node.textContent = text; node.dataset.kind = kind; }
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
function tileType(id) { return Math.floor(id / 4); }
function tileLabel(id) {
  const type = tileType(id);
  if (type < 9) return `${type + 1}萬`;
  if (type < 18) return `${type - 8}筒`;
  if (type < 27) return `${type - 17}索`;
  return ["東", "南", "西", "北", "白", "發", "中"][type - 27];
}
function tileFace(id) {
  const type = tileType(id);
  const face = document.createElement("span"); face.className = "tile-face";
  if (type < 9) {
    face.classList.add("man-face");
    const rank = document.createElement("b"); rank.textContent = ["一", "二", "三", "四", "五", "六", "七", "八", "九"][type];
    const suit = document.createElement("i"); suit.textContent = "萬"; face.append(rank, suit); return face;
  }
  if (type < 18) {
    face.classList.add("pin-face"); face.dataset.rank = String(type - 8);
    for (let index = 0; index <= type - 9; index += 1) { const pip = document.createElement("i"); pip.className = `pip pip-${index % 3}`; face.append(pip); }
    return face;
  }
  if (type < 27) {
    face.classList.add("sou-face"); face.dataset.rank = String(type - 17);
    for (let index = 0; index <= type - 18; index += 1) { const bamboo = document.createElement("i"); bamboo.className = `bamboo bamboo-${index % 2}`; face.append(bamboo); }
    return face;
  }
  face.classList.add("honor-face", `honor-${type - 27}`); face.textContent = ["東", "南", "西", "北", "白", "發", "中"][type - 27]; return face;
}
function tileSuit(id) { const type = tileType(id); return type < 9 ? "man" : type < 18 ? "pin" : type < 27 ? "sou" : "honor"; }
function tileNode(id, small = false) {
  const tile = document.createElement("button");
  tile.type = "button"; tile.className = `tile ${small ? "small" : ""}`; tile.dataset.id = String(id); tile.dataset.suit = tileSuit(id); tile.append(tileFace(id)); tile.setAttribute("aria-label", tileLabel(id)); tile.title = tileLabel(id);
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
function gameCard(game) {
  const button = document.createElement("button"); button.type = "button"; button.className = "game-card";
  const art = document.createElement("span"); art.className = `game-art ${game.id}`; art.textContent = game.icon; art.style.backgroundImage = `url("${game.image}")`; art.setAttribute("aria-hidden", "true");
  const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = game.name; const description = document.createElement("small"); description.textContent = game.description; copy.append(name, description);
  const arrow = document.createElement("b"); arrow.textContent = "›"; button.append(art, copy, arrow);
  if (game.path) button.addEventListener("click", () => { window.location.href = game.path; });
  return button;
}
function renderGames() {
  const grid = $("#game-grid"); grid.replaceChildren();
  const mahjong = {id: "mahjong", name: "摸鱼麻将", icon: "雀", image: "./assets/game-mahjong.webp", description: "四人立直 · 休闲 / 摸鱼币"};
  const mahjongCard = gameCard(mahjong); mahjongCard.addEventListener("click", openLobby);
  grid.append(mahjongCard, ...CONFIG.games.map(gameCard));
}

function messageRow(item, direct = false) {
  const row = document.createElement("article"); row.className = `club-message${direct && item.mine ? " mine" : ""}`;
  const name = document.createElement("b"); name.textContent = direct ? (item.mine ? "我" : activeDirectFriend?.name || "好友") : item.player?.name || "玩家";
  const text = document.createElement("p"); text.textContent = item.text; row.append(name, text); return row;
}
async function refreshChannelPreview() {
  try {
    const messages = await client.channel(); const latest = messages.at(-1);
    $("#channel-peek-text").textContent = latest ? `${latest.player.name}：${latest.text}` : "还没有消息，来打个招呼吧";
    return messages;
  } catch (error) {
    $("#channel-peek-text").textContent = "公共频道暂时连接不上";
    return [];
  }
}
async function renderChannel() {
  const list = $("#club-channel-messages"); list.replaceChildren();
  const messages = await refreshChannelPreview(); messages.forEach(item => list.append(messageRow(item))); list.scrollTop = list.scrollHeight;
}
function friendCard(player, actionLabel, action) {
  const row = document.createElement("div"); row.className = "friend-card"; const avatar = avatarNode(player, "friend-avatar");
  const copy = document.createElement("div"); const name = document.createElement("b"); name.textContent = player.name; const id = document.createElement("small"); id.textContent = `ID ${player.id.slice(0, 8)}`; copy.append(name, id);
  const button = document.createElement("button"); button.type = "button"; button.className = "secondary compact"; button.textContent = actionLabel; button.addEventListener("click", action); row.append(avatar, copy, button); return row;
}
async function openDirect(player) {
  activeDirectFriend = player; $("#direct-name").textContent = player.name; show("#direct-chat");
  const list = $("#direct-messages"); list.replaceChildren(); const messages = await client.directMessages(player.id); messages.forEach(item => list.append(messageRow(item, true))); list.scrollTop = list.scrollHeight;
}
async function renderFriends() {
  show("#direct-chat", false); activeDirectFriend = null; const data = await client.friends(); const list = $("#friend-list"); list.replaceChildren();
  for (const item of data.incoming) list.append(friendCard(item, "接受", async () => { await client.acceptFriend(item.request_id); await renderFriends(); }));
  for (const item of data.friends) list.append(friendCard(item, "私聊", () => openDirect(item).catch(error => feedback(error.message, "error"))));
  for (const item of data.outgoing) list.append(friendCard(item, "等待接受", () => {}));
  if (!list.children.length) { const empty = document.createElement("p"); empty.className = "drawer-empty"; empty.textContent = "还没有好友，可输入玩家 ID 添加。"; list.append(empty); }
}
const taskNames = {employment: "加入公司", checkin: "完成一次打卡", random_event: "完成一次随机事件", five_rounds: "小游戏完成 5 轮", activity: "活跃彩蛋", dark_market: "上架一次暗网商品"};
async function renderTasks() {
  const tasks = await client.tasks(); const list = $("#task-list"); list.replaceChildren();
  tasks.filter(item => !item.hidden || item.eligible || item.claimed).forEach(item => {
    const row = document.createElement("div"); row.className = "task-card"; const copy = document.createElement("div"); const name = document.createElement("b"); name.textContent = taskNames[item.key]; const reward = document.createElement("small"); reward.textContent = `奖励 ${item.reward} 摸鱼币`; copy.append(name, reward);
    const button = document.createElement("button"); button.type = "button"; button.className = "primary compact"; button.textContent = item.claimed ? "已领取" : item.eligible ? "领取" : "未完成"; button.disabled = item.claimed || !item.eligible;
    button.addEventListener("click", async () => { try { await client.claimTask(item.key); await renderTasks(); await renderProfile(); } catch (error) { feedback(error.message, "error"); } }); row.append(copy, button); list.append(row);
  });
}
async function renderProfile() {
  const profile = await client.profile(); const holder = $("#club-profile"); holder.replaceChildren(); const avatar = avatarNode(profile, "profile-avatar");
  const name = document.createElement("h2"); name.textContent = profile.name; const role = document.createElement("p"); role.textContent = profile.employee ? "已入职玩家" : "游客玩家";
  const balance = document.createElement("strong"); balance.textContent = profile.employee ? `${profile.balance} 摸鱼币` : "入职后可参加摸鱼币场并领取任务";
  const stats = document.createElement("section"); stats.className = "profile-stats";
  const total = profile.stats?.total || {played: 0, wins: 0, losses: 0, draws: 0};
  const summary = document.createElement("b"); summary.textContent = `对局 ${total.played} · 胜 ${total.wins} · 负 ${total.losses} · 平 ${total.draws}`; stats.append(summary);
  const labels = {mahjong: "摸鱼麻将", chess: "群聊象棋", doudizhu: "斗地主", drawguess: "你画我猜"};
  Object.entries(labels).forEach(([key, label]) => { const item = profile.stats?.games?.[key] || {played: 0, wins: 0, losses: 0, draws: 0}; const row = document.createElement("small"); row.textContent = `${label} · ${item.played} 局 · ${item.wins}胜 ${item.losses}负 ${item.draws}平`; stats.append(row); });
  const id = document.createElement("code"); id.textContent = `玩家 ID：${profile.id}`; holder.append(avatar, name, role, balance, stats, id);
}
async function openClubDrawer(tab = "channel") {
  activeClubTab = tab; show("#club-drawer"); show("#club-drawer-backdrop"); document.body.classList.add("drawer-open");
  document.querySelectorAll("[data-club-tab]").forEach(button => button.classList.toggle("active", button.dataset.clubTab === tab));
  document.querySelectorAll(".club-panel").forEach(panel => { panel.hidden = panel.id !== `club-panel-${tab}`; });
  $("#club-drawer-title").textContent = {channel: "公共频道", friends: "好友与私聊", tasks: "任务中心", profile: "个人中心"}[tab];
  try { if (tab === "channel") await renderChannel(); if (tab === "friends") await renderFriends(); if (tab === "tasks") await renderTasks(); if (tab === "profile") await renderProfile(); } catch (error) { feedback(error.message, "error"); }
}
function closeClubDrawer() { show("#club-drawer", false); show("#club-drawer-backdrop", false); document.body.classList.remove("drawer-open"); }

async function boot(refresh = false) {
  feedback("正在进入 Club…"); sdk?.loading?.progress?.({phase: "runtime_initializing", progress: 20, message: "正在进入摸鱼 Club"});
  try {
    const uid = await client.identity(refresh); $("#identity").textContent = `ID · ${uid.slice(0, 6)}`;
    renderGames();
    await refreshChannelPreview();
    const launch = await sdk?.getLaunchParams?.().catch?.(() => null);
    const roomId = launch?.roomId ?? launch?.params?.roomId;
    if (typeof roomId === "string" && roomId) await enterRoom(roomId);
    else openHome();
    feedback(); markReady();
  } catch (error) {
    feedback(error.message || "加载失败，请重试", "error"); sdk?.loading?.error?.("CLUB_BOOT_FAILED", error.message || "加载失败");
  }
}
function stopRoom() { stopFollow?.(); stopFollow = null; room = null; selectedTile = null; dismissedResult = null; chatOpen = false; unreadChat = 0; seenMessageCount = 0; messagesInitialized = false; show("#chat-drawer", false); $("#table").classList.remove("chat-open"); updateChatBadges(); }
function openHome() { stopRoom(); show("#club-home"); show("#mahjong-lobby", false); show("#table", false); document.body.dataset.view = "home"; }
async function openLobby() {
  stopRoom(); show("#club-home", false); show("#mahjong-lobby"); show("#table", false); document.body.dataset.view = "lobby"; feedback("正在刷新牌桌…");
  try { rooms = await client.rooms(); renderRooms(); feedback(); } catch (error) { feedback(error.message, "error"); }
}
function renderRooms() {
  $("#room-count").textContent = `${rooms.length} 桌`; const list = $("#rooms"); list.replaceChildren();
  if (!rooms.length) {
    const empty = document.createElement("div"); empty.className = "empty room-empty";
    const art = document.createElement("span"); art.className = "room-empty-art"; art.textContent = "🀄";
    const title = document.createElement("b"); title.textContent = "今晚还没有牌桌";
    const copy = document.createElement("span"); copy.textContent = "开一桌，邀请群友直接入座";
    const button = document.createElement("button"); button.type = "button"; button.className = "primary gold compact"; button.textContent = "开第一桌"; button.addEventListener("click", () => $("#create-dialog").showModal());
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
  feedback("正在创建牌桌…");
  const roomType = $("#room-type").value;
  const stake = roomType === "coin" ? Number($("#stake").value) : 0;
  try { const next = await client.create(roomType, stake, $("#match-mode").value); $("#create-dialog").close(); await enterRoom(next.id, next); } catch (error) { feedback(error.message, "error"); }
}
async function enterRoom(roomId, initial = null, immersive = false) {
  if (immersive) void enterFullscreen(true);
  stopFollow?.(); feedback("正在落座…");
  try {
    setRoom(initial || await client.snapshot(roomId)); show("#club-home", false); show("#mahjong-lobby", false); show("#table"); document.body.dataset.view = "table"; renderTable(); feedback();
    stopFollow = client.follow(roomId, next => { const changed = renderKey(next) !== renderKey(room); setRoom(next); if (changed) renderTable(); feedback(); }, error => feedback(`${error.message}，正在重连…`, "warning"));
  } catch (error) { feedback(error.message, "error"); }
}
function setRoom(next) { room = next; receivedAt = Date.now(); if (selectedTile !== null && !room.game?.hand?.includes(selectedTile)) selectedTile = null; }
function renderKey(value) { const messages = value?.messages || []; return JSON.stringify([value?.phase, value?.version, value?.settlement, messages.length, messages.at(-1)?.id]); }
function seatOrder() { const self = room.seat ?? 0; return {self, right: (self + 1) % 4, top: (self + 2) % 4, left: (self + 3) % 4}; }
function playerText(seat) {
  const player = room.players[seat]; if (!player) return "空位";
  const points = room.game?.points?.[seat]; return `${player.name}${seat === room.creator_seat ? " · 房主" : ""}${points === undefined ? "" : ` · ${points.toLocaleString()}`}`;
}
function renderWaiting() {
  document.body.dataset.tablePhase = "waiting";
  show("#waiting"); show("#mahjong-table", false); show("#result", false);
  $("#room-kind").textContent = `${room.room_type === "coin" ? `${room.buy_in} 摸鱼币房` : "休闲房"} · ${room.match_mode === "south" ? "半庄战" : "东风战"}`; $("#room-code").textContent = `${room.creator_name || "玩家"}的牌桌`;
  const seats = $("#seats"); seats.replaceChildren();
  room.players.forEach((player, index) => {
    const item = document.createElement("div"); item.className = `waiting-seat seat-${index} ${player ? "occupied" : ""} ${player?.ready ? "ready" : ""} ${player && !player.online ? "offline" : ""} ${room.seat === index ? "mine" : ""}`;
    const avatar = player ? avatarNode(player, "waiting-avatar") : document.createElement("span"); if (!player) { avatar.className = "waiting-avatar"; avatar.textContent = "+"; }
    const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = player?.name || "等待入座";
    const status = document.createElement("small"); status.textContent = player ? `${index === room.creator_seat ? "房主 · " : ""}${player.ready ? "已准备" : "未准备"}${player.online ? "" : " · 离线"}` : ["东位", "南位", "西位", "北位"][index];
    copy.append(name, status); item.append(avatar, copy); seats.append(item);
  });
  show("#claim-controls", room.seat === null); show("#waiting-actions", room.seat !== null);
  if (room.seat !== null) { const mine = room.players[room.seat]; $("#ready").textContent = mine.ready ? "取消准备" : "准备"; $("#ready").dataset.action = mine.ready ? "unready" : "ready"; $("#start").hidden = room.seat !== 0; $("#start").disabled = room.players.some(player => !player?.ready); }
}
function renderPlayer(selector, seat) {
  const node = $(selector); const player = room.players[seat]; node.replaceChildren(); node.classList.toggle("active", room.game.turn === seat);
  const avatar = avatarNode(player); const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = playerText(seat); const count = document.createElement("small"); count.textContent = `${winds[(seat - room.game.dealer + 4) % 4]}风 · ${room.game.hand_counts[seat]} 张${room.game.riichi[seat] ? " · 立直" : ""}`; copy.append(name, count); node.append(avatar, copy);
}
function renderRivers() {
  const holder = $("#rivers"); holder.replaceChildren();
  room.game.discards.forEach((river, seat) => { const line = document.createElement("div"); line.className = `river river-${seat}`; for (const item of river) { const tile = tileNode(item.tile, true); tile.classList.toggle("called", item.called); tile.classList.toggle("riichi", item.riichi); tile.disabled = true; line.append(tile); } holder.append(line); });
}
function renderMelds() {
  const holder = $("#melds"); holder.replaceChildren();
  room.game.melds.forEach((melds, seat) => { if (!melds.length) return; const group = document.createElement("div"); group.className = "meld-group"; const name = document.createElement("small"); name.textContent = room.players[seat]?.name || `玩家${seat + 1}`; group.append(name); for (const meld of melds) { const row = document.createElement("span"); row.className = "meld"; meld.tiles.forEach(id => { const tile = tileNode(id, true); tile.disabled = true; row.append(tile); }); group.append(row); } holder.append(group); });
}
function renderHand() {
  const holder = $("#hand"); holder.replaceChildren();
  if (room.seat === null) { const spectator = document.createElement("div"); spectator.className = "spectator"; spectator.textContent = "观战模式 · 手牌已隐藏"; holder.append(spectator); return; }
  const discardable = new Set(room.game.actions.discard || []);
  room.game.hand.forEach(id => { const tile = tileNode(id); tile.disabled = !discardable.has(id); tile.classList.toggle("selected", id === selectedTile); tile.addEventListener("click", () => { selectedTile = selectedTile === id ? null : id; renderHand(); renderActions(); }); holder.append(tile); });
}
function actionButton(label, action, payload = {}, className = "secondary") { const button = document.createElement("button"); button.type = "button"; button.className = className; button.textContent = label; button.addEventListener("click", () => perform(action, payload)); return button; }
function renderActions() {
  const bar = $("#action-bar"); bar.replaceChildren(); const actions = room.game.actions || {};
  if (actions.pass) bar.append(actionButton("过", "pass", {}, "secondary pass-action"));
  if (actions.ron) bar.append(actionButton("荣和", "ron", {}, "primary gold"));
  if (actions.tsumo) bar.append(actionButton("自摸", "tsumo", {}, "primary gold"));
  for (const choice of actions.chi || []) bar.append(actionButton(`吃 ${choice.map(tileLabel).join(" ")}`, "chi", {tiles: choice}, "primary action-call"));
  for (const choice of actions.pon || []) bar.append(actionButton("碰", "pon", {tiles: choice}, "primary action-call"));
  for (const choice of actions.kan || []) bar.append(actionButton("杠", "kan", {tiles: choice}, "primary action-call"));
  for (const type of actions.ankan || []) bar.append(actionButton(`暗杠 ${tileLabel(type * 4)}`, "ankan", {tile_type: type}, "primary action-call"));
  for (const choice of actions.kakan || []) bar.append(actionButton(`加杠 ${tileLabel(choice.tile_type * 4)}`, "kakan", {meld_index: choice.meld_index}, "primary action-call"));
  if (actions.kyuushu) bar.append(actionButton("九种九牌", "kyuushu"));
  if (selectedTile !== null && (actions.discard || []).includes(selectedTile)) { if ((actions.riichi || []).includes(selectedTile)) bar.append(actionButton("立直打出", "riichi", {tile: selectedTile}, "primary gold")); bar.append(actionButton("打出", "discard", {tile: selectedTile}, "primary")); }
}
function resultCopy(result) {
  if (!result) return "结算中"; if (result.kind === "match") return `终局 · ${result.reason}`; if (result.kind === "途中流局") return result.reason; return resultNames[result.kind] || result.kind;
}
function renderResult() {
  const holder = $("#result"); holder.replaceChildren(); const resultKey = JSON.stringify([room.phase, room.version, room.game?.result, room.settlement]);
  if (!room.game?.result || !["hand_finished", "match_finished"].includes(room.phase) || dismissedResult === resultKey) { show("#result", false); return; }
  show("#result"); const heading = document.createElement("header"); const headingCopy = document.createElement("div"); const eyebrow = document.createElement("span"); eyebrow.textContent = room.phase === "match_finished" ? "MATCH RESULT" : "ROUND RESULT"; const title = document.createElement("h2"); title.textContent = resultCopy(room.game.result); const subtitle = document.createElement("small"); subtitle.textContent = room.phase === "match_finished" ? "本场最终排名" : "本局点数变化"; headingCopy.append(eyebrow, title, subtitle); const mark = document.createElement("b"); mark.textContent = room.phase === "match_finished" ? "终" : "局"; heading.append(headingCopy, mark);
  const rows = document.createElement("div"); rows.className = "result-rows";
  const order = room.settlement?.order || room.game.result.order || [0, 1, 2, 3].sort((a, b) => room.game.points[b] - room.game.points[a]);
  order.forEach((seat, index) => {
    const player = room.players[seat]; const row = document.createElement("div"); row.className = index === 0 ? "winner" : "";
    const rank = document.createElement("b"); rank.textContent = String(index + 1); const avatar = avatarNode(player, "result-avatar"); const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = player?.name || "玩家"; const note = document.createElement("small"); note.textContent = room.settlement?.payouts ? `摸鱼币 +${room.settlement.payouts[seat] || 0}` : ["东", "南", "西", "北"][seat] + "家"; copy.append(name, note);
    const score = document.createElement("span"); const points = document.createElement("strong"); points.textContent = room.game.points[seat].toLocaleString(); const delta = room.game.result.deltas?.[seat]; const change = document.createElement("small"); change.textContent = delta === undefined ? "" : `${delta >= 0 ? "+" : ""}${delta}`; score.append(points, change); row.append(rank, avatar, copy, score); rows.append(row);
  });
  const actions = document.createElement("div"); actions.className = "result-actions"; const close = document.createElement("button"); close.type = "button"; close.className = "primary gold"; close.textContent = room.phase === "match_finished" ? "返回大厅" : "继续牌局"; close.addEventListener("click", () => { dismissedResult = resultKey; show("#result", false); if (room.phase === "match_finished") void returnToLobby(); }); actions.append(close); holder.append(heading, rows, actions);
}
function renderGame() {
  document.body.dataset.tablePhase = "game";
  show("#waiting", false); show("#mahjong-table"); const order = seatOrder(); renderPlayer("#opponent-left", order.left); renderPlayer("#opponent-top", order.top); renderPlayer("#opponent-right", order.right); renderPlayer("#self-player", order.self);
  const round = `${winds[room.game.round_wind - 27] || "东"}${room.game.hand_number}局`;
  $("#round-label").textContent = `${round} · ${room.game.honba}本场`; $("#center-round").textContent = round; $("#remaining-count").textContent = `余 ${room.game.remaining} 张`; $("#turn-status").textContent = room.game.turn === room.seat ? "轮到你出牌" : `${room.players[room.game.turn]?.name || "玩家"} 思考中`;
  const dora = $("#dora"); dora.replaceChildren(document.createTextNode("宝牌指示 ")); room.game.dora_indicators.forEach(id => { const node = tileNode(id, true); node.disabled = true; dora.append(node); });
  renderRivers(); renderMelds(); renderHand(); renderActions(); renderResult();
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
  const list = $("#messages"); list.replaceChildren();
  for (const item of entries) { const row = document.createElement("div"); const avatar = document.createElement("i"); avatar.textContent = item.name?.slice(0, 1) || "?"; const copy = document.createElement("span"); const name = document.createElement("strong"); name.textContent = item.name; const text = document.createElement("b"); text.textContent = item.text; copy.append(name, text); row.append(avatar, copy); list.append(row); }
  list.scrollTop = list.scrollHeight;
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
  if (!room) return; feedback();
  try {
    const next = await client.action(room.id, room.version, action, payload);
    if (action === "leave") { await returnToLobby(); return; }
    setRoom(next); selectedTile = null; renderTable();
  } catch (error) { feedback(error.message, "error"); }
}
async function sendChatText(text) { if (!room || !text) return; $("#chat-send").disabled = true; try { await client.chat(room.id, text); setRoom(await client.snapshot(room.id)); renderMessages(); } catch (error) { feedback(error.message, "error"); } finally { $("#chat-send").disabled = false; } }
async function sendChat() { const input = $("#chat-input"); const text = input.value.trim(); if (!text) return; input.value = ""; await sendChatText(text); }
async function shareRoom() {
  if (!room) return;
  try {
    await sdk?.share?.({title: "摸鱼麻将", description: `${room.players[0]?.name || "玩家"}的牌桌 · 点击即可入座或观战`, params: JSON.stringify({roomId: room.id})});
  } catch (error) { feedback(error.message || "分享失败，请重试", "error"); }
}
function updateTimer() { const seconds = secondsLeft(); $("#timer").textContent = seconds === null ? "--" : `${seconds}s`; }

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
  if (coin) { const stake = Number($("#stake").value); $("#prize-copy").textContent = `每人 ${stake} 币，共 ${stake * 4} 币；最终第一名获得奖池，同分则平分。`; }
}
function openCustomSelect(root, focusOption = false) {
  closeCustomSelects(root); const menu = root.querySelector(".custom-select-menu");
  root.classList.add("open"); menu.hidden = false; root.querySelector(".custom-select-trigger").setAttribute("aria-expanded", "true");
  if (focusOption) (menu.querySelector('[aria-selected="true"]') || menu.querySelector("[role=option]"))?.focus();
}
customSelects.forEach(root => {
  const select = $(`#${root.dataset.selectFor}`); const trigger = root.querySelector(".custom-select-trigger"); const options = [...root.querySelectorAll("[role=option]")];
  syncCustomSelect(root); select.addEventListener("change", () => syncCustomSelect(root));
  trigger.addEventListener("click", () => root.classList.contains("open") ? closeCustomSelect(root) : openCustomSelect(root));
  trigger.addEventListener("keydown", event => { if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); openCustomSelect(root, true); } });
  options.forEach(option => {
    option.addEventListener("click", () => { select.value = option.dataset.value; select.dispatchEvent(new Event("change", {bubbles: true})); closeCustomSelect(root, true); });
    option.addEventListener("keydown", event => {
      const index = options.indexOf(event.currentTarget);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); options[(index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length].focus(); }
      if (event.key === "Escape") { event.preventDefault(); closeCustomSelect(root, true); }
    });
  });
});
document.addEventListener("pointerdown", event => { if (!event.target.closest(".custom-select")) closeCustomSelects(); });
$("#create-dialog").addEventListener("close", () => closeCustomSelects());
$("#room-type").addEventListener("change", syncCreateEconomy); $("#stake").addEventListener("change", syncCreateEconomy); syncCreateEconomy();

$("#refresh").addEventListener("click", () => boot(true)); $("#home").addEventListener("click", openHome); $("#club-back").addEventListener("click", openHome); $("#lobby-back").addEventListener("click", returnToLobby);
$("#create-room").addEventListener("click", () => $("#create-dialog").showModal()); $("#cancel-create").addEventListener("click", () => $("#create-dialog").close()); $("#confirm-create").addEventListener("click", event => { event.preventDefault(); void enterFullscreen(true); createRoom(); });
$("#claim").addEventListener("click", () => perform("claim")); $("#ready").addEventListener("click", () => perform($("#ready").dataset.action || "ready")); $("#start").addEventListener("click", () => perform("start")); $("#leave").addEventListener("click", () => perform("leave"));
$("#share-room").addEventListener("click", shareRoom);
$("#fullscreen").addEventListener("click", toggleFullscreen); document.addEventListener("fullscreenchange", updateFullscreenButton); document.addEventListener("webkitfullscreenchange", updateFullscreenButton);
$("#chat-toggle").addEventListener("click", openChat); $("#chat-preview").addEventListener("click", openChat); $("#chat-close").addEventListener("click", closeChat); $("#chat-send").addEventListener("click", sendChat); $("#chat-input").addEventListener("keydown", event => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); sendChat(); } });
document.querySelectorAll("[data-quick-chat]").forEach(button => button.addEventListener("click", () => sendChatText(button.dataset.quickChat)));
$("#channel-toggle").addEventListener("click", () => openClubDrawer("channel")); $("#channel-peek").addEventListener("click", () => openClubDrawer("channel")); $("#tasks-toggle").addEventListener("click", () => openClubDrawer("tasks")); $("#profile-toggle").addEventListener("click", () => openClubDrawer("profile"));
$("#club-drawer-close").addEventListener("click", closeClubDrawer); $("#club-drawer-backdrop").addEventListener("click", closeClubDrawer); document.querySelectorAll("[data-club-tab]").forEach(button => button.addEventListener("click", () => openClubDrawer(button.dataset.clubTab)));
$("#club-channel-send").addEventListener("click", async () => { const input = $("#club-channel-input"); const text = input.value.trim(); if (!text) return; try { await client.sendChannel(text); input.value = ""; await renderChannel(); } catch (error) { feedback(error.message, "error"); } });
$("#club-channel-input").addEventListener("keydown", event => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); $("#club-channel-send").click(); } });
$("#friend-add").addEventListener("click", async () => { const input = $("#friend-player-id"); try { await client.requestFriend(input.value.trim()); input.value = ""; await renderFriends(); } catch (error) { feedback(error.message, "error"); } });
$("#direct-back").addEventListener("click", () => renderFriends().catch(error => feedback(error.message, "error")));
$("#direct-send").addEventListener("click", async () => { const input = $("#direct-input"); const text = input.value.trim(); if (!activeDirectFriend || !text) return; try { await client.sendDirectMessage(activeDirectFriend.id, text); input.value = ""; await openDirect(activeDirectFriend); } catch (error) { feedback(error.message, "error"); } });
setInterval(updateTimer, 500); window.addEventListener("pagehide", () => client.dispose()); updateFullscreenButton(); boot();
