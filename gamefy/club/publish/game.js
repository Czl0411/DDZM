import {ClubClient} from "./client.js";
import {CONFIG} from "./config.js";

const $ = selector => document.querySelector(selector);
const sdk = window.dzmm;
const client = new ClubClient({sdk, apiBase: CONFIG.apiBase});
let rooms = [], room = null, stopFollow = null, selectedTile = null, receivedAt = 0, bootReady = false;

const winds = ["东", "南", "西", "北"];
const phaseNames = {waiting: "候场", playing: "对局中", reaction: "鸣牌响应", hand_finished: "本局结算", match_finished: "终局", cancelled: "已取消"};
const resultNames = {tsumo: "自摸", ron: "荣和", "荒牌流局": "荒牌流局", "流局满贯": "流局满贯", "途中流局": "途中流局", match: "终局"};

function feedback(text = "") { $("#feedback").textContent = text; }
function show(selector, value = true) { $(selector).hidden = !value; }
function markReady() { if (!bootReady) { bootReady = true; sdk?.loading?.ready?.(); } }
function fullscreenElement() { return document.fullscreenElement || document.webkitFullscreenElement || null; }
function updateFullscreenButton() {
  const active = Boolean(fullscreenElement());
  $("#fullscreen").textContent = active ? "退" : "全";
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
function tileGlyph(id) {
  const type = tileType(id);
  if (type < 9) return String.fromCodePoint(0x1f007 + type);
  if (type < 18) return String.fromCodePoint(0x1f019 + type - 9);
  if (type < 27) return String.fromCodePoint(0x1f010 + type - 18);
  return String.fromCodePoint([0x1f000, 0x1f001, 0x1f002, 0x1f003, 0x1f006, 0x1f005, 0x1f004][type - 27]);
}
function tileSuit(id) { const type = tileType(id); return type < 9 ? "man" : type < 18 ? "pin" : type < 27 ? "sou" : "honor"; }
function tileNode(id, small = false) {
  const tile = document.createElement("button");
  tile.type = "button"; tile.className = `tile ${small ? "small" : ""}`; tile.dataset.id = String(id); tile.dataset.suit = tileSuit(id); tile.textContent = tileGlyph(id); tile.setAttribute("aria-label", tileLabel(id)); tile.title = tileLabel(id);
  return tile;
}
function gameCard(game) {
  const button = document.createElement("button"); button.type = "button"; button.className = "game-card";
  const art = document.createElement("span"); art.className = `game-art ${game.id}`; art.textContent = game.icon; art.style.backgroundImage = `url("${game.image}")`; art.setAttribute("aria-hidden", "true");
  const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = game.name; const description = document.createElement("small"); description.textContent = game.description; copy.append(name, description);
  const arrow = document.createElement("b"); arrow.textContent = "›"; button.append(art, copy, arrow);
  if (game.cardId) button.addEventListener("click", () => window.open(`https://www.aikda.com/chat?card=${encodeURIComponent(game.cardId)}`, "_blank", "noopener"));
  return button;
}
function renderGames() {
  const grid = $("#game-grid"); grid.replaceChildren();
  const mahjong = {id: "mahjong", name: "摸鱼麻将", icon: "雀", image: "./assets/game-mahjong.webp", description: "四人立直 · 休闲 / 摸鱼币"};
  const mahjongCard = gameCard(mahjong); mahjongCard.addEventListener("click", openLobby);
  grid.append(mahjongCard, ...CONFIG.games.map(gameCard));
}

async function boot(refresh = false) {
  feedback("正在进入 Club…"); sdk?.loading?.progress?.({phase: "runtime_initializing", progress: 20, message: "正在进入摸鱼 Club"});
  try {
    const uid = await client.identity(refresh); $("#identity").textContent = `ID · ${uid.slice(0, 6)}`;
    renderGames();
    const launch = await sdk?.getLaunchParams?.().catch?.(() => null);
    const roomId = launch?.roomId ?? launch?.params?.roomId;
    if (typeof roomId === "string" && roomId) await enterRoom(roomId);
    else openHome();
    feedback(); markReady();
  } catch (error) {
    feedback(error.message || "加载失败，请重试"); sdk?.loading?.error?.("CLUB_BOOT_FAILED", error.message || "加载失败");
  }
}
function stopRoom() { stopFollow?.(); stopFollow = null; room = null; selectedTile = null; }
function openHome() { stopRoom(); show("#club-home"); show("#mahjong-lobby", false); show("#table", false); document.body.dataset.view = "home"; }
async function openLobby() {
  stopRoom(); show("#club-home", false); show("#mahjong-lobby"); show("#table", false); document.body.dataset.view = "lobby"; feedback("正在刷新牌桌…");
  try { rooms = await client.rooms(); renderRooms(); feedback(); } catch (error) { feedback(error.message); }
}
function renderRooms() {
  $("#room-count").textContent = `${rooms.length} 桌`; const list = $("#rooms"); list.replaceChildren();
  if (!rooms.length) { const empty = document.createElement("div"); empty.className = "empty"; empty.innerHTML = "<b>今晚还没有牌桌</b><span>点击右上角「开一桌」邀请群友</span>"; list.append(empty); return; }
  for (const item of rooms) {
    const button = document.createElement("button"); button.className = "room-card"; button.type = "button";
    const icon = document.createElement("span"); icon.className = "room-icon"; icon.textContent = "🀄";
    const copy = document.createElement("div"); const title = document.createElement("strong"); title.textContent = `牌桌 ${item.short_id}`; const meta = document.createElement("small"); meta.textContent = `${item.room_type === "coin" ? "100 币" : "休闲"} · ${item.match_mode === "south" ? "半庄战" : "东风战"} · ${item.occupied}/4 人${item.mine ? " · 我已入座" : ""}`; copy.append(title, meta);
    const phase = document.createElement("b"); phase.textContent = phaseNames[item.phase] || item.phase; button.append(icon, copy, phase); button.addEventListener("click", () => enterRoom(item.id, null, true)); list.append(button);
  }
}
async function createRoom() {
  feedback("正在创建牌桌…");
  try { const next = await client.create($("#room-type").value, $("#match-mode").value); $("#create-dialog").close(); await enterRoom(next.id, next); } catch (error) { feedback(error.message); }
}
async function enterRoom(roomId, initial = null, immersive = false) {
  if (immersive) void enterFullscreen(true);
  stopFollow?.(); feedback("正在落座…");
  try {
    setRoom(initial || await client.snapshot(roomId)); show("#club-home", false); show("#mahjong-lobby", false); show("#table"); document.body.dataset.view = "table"; renderTable(); feedback();
    stopFollow = client.follow(roomId, next => { const changed = renderKey(next) !== renderKey(room); setRoom(next); if (changed) renderTable(); feedback(); }, error => feedback(`${error.message}，正在重连…`));
  } catch (error) { feedback(error.message); }
}
function setRoom(next) { room = next; receivedAt = Date.now(); if (selectedTile !== null && !room.game?.hand?.includes(selectedTile)) selectedTile = null; }
function renderKey(value) { const messages = value?.messages || []; return JSON.stringify([value?.phase, value?.version, value?.settlement, messages.length, messages.at(-1)?.id]); }
function seatOrder() { const self = room.seat ?? 0; return {self, right: (self + 1) % 4, top: (self + 2) % 4, left: (self + 3) % 4}; }
function playerText(seat) {
  const player = room.players[seat]; if (!player) return "空位";
  const points = room.game?.points?.[seat]; return `${player.name}${seat === room.creator_seat ? " · 房主" : ""}${points === undefined ? "" : ` · ${points.toLocaleString()}`}`;
}
function renderWaiting() {
  show("#waiting"); show("#mahjong-table", false); show("#result", false);
  $("#room-kind").textContent = `${room.room_type === "coin" ? "100 摸鱼币房" : "休闲房"} · ${room.match_mode === "south" ? "半庄战" : "东风战"}`; $("#room-code").textContent = room.code || room.short_id;
  const seats = $("#seats"); seats.replaceChildren();
  room.players.forEach((player, index) => { const item = document.createElement("div"); item.className = `waiting-seat ${player ? "occupied" : ""}`; const avatar = document.createElement("span"); avatar.textContent = player ? player.name.slice(0, 1) : "+"; const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = player?.name || "等待群友"; const status = document.createElement("small"); status.textContent = player ? (player.ready ? "已准备" : index === 0 ? "房主" : "未准备") : `座位 ${index + 1}`; copy.append(name, status); item.append(avatar, copy); seats.append(item); });
  show("#claim-controls", room.seat === null); show("#waiting-actions", room.seat !== null);
  if (room.seat !== null) { const mine = room.players[room.seat]; $("#ready").textContent = mine.ready ? "取消准备" : "准备"; $("#ready").dataset.action = mine.ready ? "unready" : "ready"; $("#start").hidden = room.seat !== 0; $("#start").disabled = room.players.some(player => !player?.ready); }
}
function renderPlayer(selector, seat) {
  const node = $(selector); const player = room.players[seat]; node.replaceChildren(); node.classList.toggle("active", room.game.turn === seat);
  const avatar = document.createElement("span"); avatar.textContent = player?.name?.slice(0, 1) || "?"; const copy = document.createElement("div"); const name = document.createElement("strong"); name.textContent = playerText(seat); const count = document.createElement("small"); count.textContent = `${winds[(seat - room.game.dealer + 4) % 4]}风 · ${room.game.hand_counts[seat]} 张${room.game.riichi[seat] ? " · 立直" : ""}`; copy.append(name, count); node.append(avatar, copy);
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
  const holder = $("#result"); holder.replaceChildren(); if (!room.game?.result || !["hand_finished", "match_finished"].includes(room.phase)) { show("#result", false); return; }
  show("#result"); const title = document.createElement("h2"); title.textContent = resultCopy(room.game.result); const rows = document.createElement("div"); rows.className = "result-rows";
  const order = room.settlement?.order || room.game.result.order || [0, 1, 2, 3].sort((a, b) => room.game.points[b] - room.game.points[a]);
  order.forEach((seat, index) => { const row = document.createElement("div"); const delta = room.game.result.deltas?.[seat]; row.innerHTML = `<b>${index + 1}</b><strong></strong><span>${room.game.points[seat].toLocaleString()}${delta === undefined ? "" : `（${delta >= 0 ? "+" : ""}${delta}）`}</span>`; row.querySelector("strong").textContent = room.players[seat]?.name || "玩家"; rows.append(row); }); holder.append(title, rows);
}
function renderGame() {
  show("#waiting", false); show("#mahjong-table"); const order = seatOrder(); renderPlayer("#opponent-left", order.left); renderPlayer("#opponent-top", order.top); renderPlayer("#opponent-right", order.right); renderPlayer("#self-player", order.self);
  const round = `${winds[room.game.round_wind - 27] || "东"}${room.game.hand_number}局`;
  $("#round-label").textContent = `${round} · ${room.game.honba}本场`; $("#center-round").textContent = round; $("#remaining-count").textContent = `余 ${room.game.remaining} 张`; $("#turn-status").textContent = room.game.turn === room.seat ? "轮到你出牌" : `${room.players[room.game.turn]?.name || "玩家"} 思考中`;
  const dora = $("#dora"); dora.replaceChildren(document.createTextNode("宝牌指示 ")); room.game.dora_indicators.forEach(id => { const node = tileNode(id, true); node.disabled = true; dora.append(node); });
  renderRivers(); renderMelds(); renderHand(); renderActions(); renderResult();
}
function renderMessages() { const list = $("#messages"); list.replaceChildren(); for (const item of room.messages || []) { const row = document.createElement("div"); const name = document.createElement("strong"); name.textContent = item.name; const text = document.createElement("span"); text.textContent = item.text; row.append(name, text); list.append(row); } list.scrollTop = list.scrollHeight; }
function renderTable() {
  $("#table-title").textContent = `牌桌 ${room.short_id}`; $("#round-label").textContent = phaseNames[room.phase] || room.phase;
  if (room.phase === "waiting") renderWaiting(); else renderGame(); renderMessages(); updateTimer();
}
async function perform(action, payload = {}) { if (!room) return; feedback(); try { setRoom(await client.action(room.id, room.version, action, payload)); selectedTile = null; renderTable(); } catch (error) { feedback(error.message); } }
async function sendChat() { const input = $("#chat-input"); const text = input.value.trim(); if (!room || !text) return; $("#chat-send").disabled = true; try { await client.chat(room.id, text); input.value = ""; setRoom(await client.snapshot(room.id)); renderMessages(); } catch (error) { feedback(error.message); } finally { $("#chat-send").disabled = false; } }
async function shareRoom() {
  if (!room) return;
  try {
    await sdk?.share?.({title: "摸鱼麻将", description: `牌桌 ${room.short_id} · 入座码 ${room.code || "见群内消息"}`, params: JSON.stringify({roomId: room.id})});
  } catch (error) { feedback(error.message || "分享失败，请重试"); }
}
function updateTimer() { const seconds = secondsLeft(); $("#timer").textContent = seconds === null ? "--" : `${seconds}s`; }

$("#refresh").addEventListener("click", () => boot(true)); $("#home").addEventListener("click", openHome); $("#club-back").addEventListener("click", openHome); $("#lobby-back").addEventListener("click", returnToLobby);
$("#create-room").addEventListener("click", () => $("#create-dialog").showModal()); $("#confirm-create").addEventListener("click", event => { event.preventDefault(); void enterFullscreen(true); createRoom(); });
$("#claim").addEventListener("click", () => perform("claim", {code: $("#seat-code").value.trim()})); $("#ready").addEventListener("click", () => perform($("#ready").dataset.action || "ready")); $("#start").addEventListener("click", () => perform("start")); $("#leave").addEventListener("click", () => perform("leave"));
$("#share-room").addEventListener("click", shareRoom);
$("#fullscreen").addEventListener("click", toggleFullscreen); document.addEventListener("fullscreenchange", updateFullscreenButton); document.addEventListener("webkitfullscreenchange", updateFullscreenButton);
$("#chat-toggle").addEventListener("click", () => show("#chat-drawer")); $("#chat-close").addEventListener("click", () => show("#chat-drawer", false)); $("#chat-send").addEventListener("click", sendChat); $("#chat-input").addEventListener("keydown", event => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); sendChat(); } });
setInterval(updateTimer, 500); window.addEventListener("pagehide", () => client.dispose()); updateFullscreenButton(); boot();
