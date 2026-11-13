import {actionText, seatStatus, newActions} from "./presentation.js";
import {moduleEnvironment} from "../module-document.js";
import {loadEconomy, renderStakeChoices} from "../economy.js";

const environment = moduleEnvironment();
const document = environment.document;
const location = environment.location;
const moduleContext = environment.context;
const CLUB_API_BASE = "https://49.234.20.159";
const API_BASE = `${CLUB_API_BASE}/api/club/cards`;
const params = new URLSearchParams(location.search);
const game = params.get("game");
const sdk = window.MoyuClubRuntime?.sdk || window.dzmm;
const runtime = window.MoyuClubRuntime;
const $ = selector => document.querySelector(selector);
const GAMES = {
  niuniu: {name: "斗牛", mark: "牛", subtitle: "庄闲对决 · 牛牛赢庄接庄", description: "2～6人，同时配牛亮牌。闲家各自与庄家比牌，牛牛赢庄者接庄。", art: "../../assets/game-zhajinhua-table-v1.webp", limits: "2～6 人", maximum: 6},
  texas: {name: "德州扑克", mark: "德", subtitle: "无限注德州 · 连续牌桌", description: "2～8 人，大小盲、公共牌、边池与全下完整结算。", art: "../../assets/game-texas-table-v1.webp", limits: "2～8 人", maximum: 8},
  zhajinhua: {name: "炸金花", mark: "金", subtitle: "经典三张 · 看牌比牌", description: "2～6 人，闷牌、看牌、跟注、加注、弃牌与比牌。", art: "../../assets/game-zhajinhua-table-v1.webp", limits: "2～6 人", maximum: 6},
  blackjack: {name: "21 点", mark: "21", subtitle: "多人竞技 · 点数对决", description: "2～5 人轮流行动，可连续要牌；最高且不爆牌者赢得本手。", art: "../../assets/game-blackjack-table-v1.webp", limits: "2～5 人", maximum: 5},
};
const META = GAMES[game] || null;
let renderedRoom = null, chatBusy = false;
let niuSelection = [], niuHandKey = "";
let uid = null, identity = null, rooms = [], room = null, followController = null, countdown = null, busy = false, layoutObserver = null;
let economy = {coin_stakes: [5, 10, 20], rake_percent: 20};

async function refreshEconomy() {
  economy = await loadEconomy(CLUB_API_BASE, game);
  renderStakeChoices(document.querySelector("#stake-field .stakes"), economy.coin_stakes, document);
  document.querySelector(".economy-note").textContent = `摸鱼币场每手按赢家有效收益的 ${economy.rake_percent}% 向下取整抽水；休闲场不结算摸鱼币。`;
}

function syncLayout() {
  const bounds = document.body.getBoundingClientRect();
  document.body.dataset.layout = bounds.width >= bounds.height ? "landscape" : "portrait";
  document.body.dataset.compact = String(bounds.height <= 560);
}
function watchLayout() {
  syncLayout();
  if (typeof ResizeObserver === "function") {
    layoutObserver = new ResizeObserver(syncLayout);
    layoutObserver.observe(document.body);
  }
  addEventListener("resize", syncLayout);
}

function requestId() { return crypto.randomUUID(); }
function feedback(text = "", kind = "info") { const node = $("#feedback"); node.textContent = text; node.dataset.kind = kind; const local = $("dialog[open] .local-feedback") || (!$("#chat").hidden ? $("#chat-feedback") : null); if (local && text) { local.textContent = text; local.dataset.kind = kind; } }
async function identify() {
  if (uid) return uid;
  const info = await sdk.user.info();
  if (!info?.id) throw new Error("无法读取玩家身份，请重试");
  uid = info.id;
  const response = await fetch("https://49.234.20.159/api/club/session", {method: "POST", headers: {Authorization: `ClubUid ${uid}`, "Content-Type": "application/json"}, body: JSON.stringify({name: info.name || info.displayName || info.nickname || null, avatar_url: info.avatar_url || info.avatarUrl || info.avatar || null})});
  if (!response.ok) throw new Error("无法同步玩家资料，请重试");
  identity = await response.json(); return uid;
}
async function request(path, options = {}) {
  await identify();
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${API_BASE}/${game}${path}`, {...options, signal: controller.signal, headers: {Authorization: `ClubUid ${uid}`, ...(options.body ? {"Content-Type": "application/json"} : {})}});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "请求失败，请重试");
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("连接牌桌超时，请重试");
    throw error;
  } finally { clearTimeout(timer); }
}
const api = {
  rooms: () => request("/rooms"),
  create: (roomType, stake) => request("/rooms", {method: "POST", body: JSON.stringify({request_id: requestId(), room_type: roomType, stake})}),
  snapshot: id => request(`/rooms/${id}`),
  action: (id, version, action, payload = {}) => request(`/rooms/${id}/actions`, {method: "POST", body: JSON.stringify({version, request_id: requestId(), action, payload})}),
  chat: (id, text) => request(`/rooms/${id}/chat`, {method: "POST", body: JSON.stringify({request_id: requestId(), text})}),
};

function avatarButton(player, className = "") {
  const button = document.createElement("button"); button.type = "button"; button.className = className; button.textContent = player?.name?.slice(0, 1) || "?";
  button.setAttribute("aria-label", `查看${player?.name || "玩家"}的主页`);
  if (player?.avatar_url) { const image = document.createElement("img"); image.src = player.avatar_url; image.alt = ""; image.referrerPolicy = "no-referrer"; image.addEventListener("error", () => image.remove(), {once: true}); button.append(image); }
  if (player?.id) button.addEventListener("click", () => runtime?.openProfile?.(player));
  return button;
}
function cardNode(value) {
  const node = document.createElement("span"); node.className = "card";
  if (!value) { node.classList.add("back"); node.textContent = "牌"; return node; }
  const [suit, rank] = value; const symbols = {clubs: "♣", diamonds: "♦", hearts: "♥", spades: "♠"};
  node.textContent = `${{14: "A", 13: "K", 12: "Q", 11: "J"}[rank] || rank}${symbols[suit]}`;
  if (suit === "diamonds" || suit === "hearts") node.classList.add("red");
  return node;
}
function gamePlayer(raw) { return room.players.find(player => player.id === raw); }
function roomCard(item) {
  const button = document.createElement("button"); button.type = "button"; button.className = "room-card";
  const copy = document.createElement("div"); const title = document.createElement("strong"); title.textContent = `${item.creator_name}的牌桌`; const meta = document.createElement("small"); meta.textContent = `${item.room_type === "coin" ? `${item.stake} 币场` : "休闲场"} · ${item.occupied}/${item.maximum} 人${item.mine ? " · 我在桌上" : ""}`; copy.append(title, meta);
  const phase = document.createElement("b");
  phase.textContent = item.phase === "hand_finished" && !item.mine && item.occupied < item.maximum
    ? "可加入下一手"
    : {waiting: "候场", playing: "牌局中", hand_finished: item.mine ? "等待下一手" : "本手结束"}[item.phase] || "牌桌";
  button.append(copy, phase); button.addEventListener("click", () => enterRoom(item.id)); return button;
}
function renderRooms() {
  const list = $("#rooms"); list.replaceChildren();
  if (!rooms.length) { const empty = document.createElement("div"); empty.className = "empty"; empty.textContent = "还没有牌桌，开第一桌邀请群友吧。"; list.append(empty); return; }
  rooms.forEach(item => list.append(roomCard(item)));
}
async function openLobby() {
  stopFollowing(); room = null; renderedRoom = null; runtime?.clearRoomContext?.(); $("#room").hidden = true; $("#lobby").hidden = false; feedback("正在刷新牌桌…");
  try { rooms = (await api.rooms()).filter(item => item.game === game); renderRooms(); feedback(); } catch (error) { feedback(error.message, "error"); }
}
async function restoreRoomOrLobby() {
  feedback("正在恢复牌桌…");
  rooms = (await api.rooms()).filter(item => item.game === game);
  const current = rooms.find(item => item.mine);
  if (current) { await enterRoom(current.id); return; }
  $("#room").hidden = true; $("#lobby").hidden = false; renderRooms(); feedback();
}
async function enterRoom(id, initial = null) {
  feedback("正在进入牌桌…");
  try { const next = initial || await api.snapshot(id); if (next.game !== game) throw new Error("房间玩法不匹配，请返回大厅重试"); room = next; $("#lobby").hidden = true; $("#room").hidden = false; renderRoom(); startFollowing(); feedback(); } catch (error) { feedback(error.message, "error"); }
}
function startFollowing() {
  stopFollowing();
  const controller = new AbortController(); followController = controller;
  countdown = setInterval(updateTurnCountdown, 250);
  (async () => {
    while (!controller.signal.aborted && room) {
      try {
        const roomId = room.id;
        const response = await fetch(`${API_BASE}/${game}/rooms/${roomId}/events`, {signal: controller.signal, headers: {Authorization: `ClubUid ${uid}`}});
        if (!response.ok || !response.body) throw new Error("牌桌实时连接失败");
        feedback();
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
        while (!controller.signal.aborted && room?.id === roomId) {
          const {done, value} = await reader.read(); if (done) break;
          buffer += decoder.decode(value, {stream: true}).replaceAll("\r\n", "\n");
          let boundary;
          while ((boundary = buffer.indexOf("\n\n")) >= 0) {
            const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
            const event = frame.split("\n").find(line => line.startsWith("event:"))?.slice(6).trim();
            const data = frame.split("\n").filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
            if (event === "unavailable") { void openLobby(); return; }
            if (!data) continue;
            const next = JSON.parse(data);
            if (!room || next.id !== room.id || next.game !== game) continue;
            if (next.version < room.version || (next.version === room.version && next.messages.length < room.messages.length)) continue;
            const changed = next.version !== room.version || next.messages.length !== room.messages.length;
            room = next; if (changed) renderRoom(); else updateTurnCountdown();
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) { renderedRoom = null; feedback("实时连接中断，正在重连…", "error"); }
      }
      if (!controller.signal.aborted) { renderedRoom = null; await new Promise(resolve => setTimeout(resolve, 1000)); }
    }
  })();
}
function stopFollowing() { followController?.abort(); clearInterval(countdown); followController = null; countdown = null; }
function playerSeat(player, index) {
  const state = room.state || {}; const node = document.createElement("article"); node.className = `seat${state.turn === player.id ? " active" : ""}`; node.dataset.seat = index; node.dataset.player = player.id; node.classList.toggle("folded", (state.folded || []).includes(player.id)); node.classList.toggle("mine", player.id === room.me.id);
  const avatar = avatarButton(player); const copy = document.createElement("span"); const name = document.createElement("b"); name.textContent = `${player.name}${player.id === room.me.id ? " · 你" : ""}`; const meta = document.createElement("small");
  const chips = state.chips?.[player.id]; const bet = state.contributions?.[player.id]; meta.textContent = `${chips == null ? (state.hands?.[player.id] ? `手牌 ${state.hands[player.id].length} 张` : "等待下一手") : `筹码 ${chips}`}${bet ? ` · 注 ${bet}` : ""}`; const status = document.createElement("em"); status.className = "seat-action"; status.textContent = game === "niuniu" ? `${player.id === state.banker ? "庄家 · " : "闲家 · "}${state.evaluations?.[player.id]?.label || "配牛中"}` : seatStatus(state, player.id); copy.append(name, meta, status); node.append(avatar, copy);
  if (game === "niuniu") {
    const hand = document.createElement("div"); hand.className = "niu-seat-cards";
    (state.hands?.[player.id] || []).forEach(card => hand.append(cardNode(player.id === room.me.id && !state.revealed?.includes(player.id) ? null : card)));
    node.append(hand);
  }
  return node;
}
function renderWaiting() {
  $("#table").hidden = true; $("#waiting").hidden = false; $("#result").hidden = true;
  const seats = $("#waiting-seats"); seats.replaceChildren();
  room.players.forEach(player => { const row = document.createElement("article"); row.className = "waiting-seat"; const avatar = avatarButton(player); const copy = document.createElement("span"); const name = document.createElement("b"); name.textContent = player.name; const status = document.createElement("small"); status.textContent = `${room.ready.includes(player.id) ? "已准备" : player.id === room.creator_id ? "房主" : "未准备"}${game === "niuniu" ? ` · ${player.id === room.scheduled_banker ? "庄家" : "闲家"}` : ""}`; copy.append(name, status); row.append(avatar, copy); seats.append(row); });
  const mine = room.players.some(player => player.id === room.me.id); const ready = room.ready.includes(room.me.id); const actions = $("#waiting-actions"); actions.replaceChildren();
  const add = (label, style, handler, disabled = false) => { const button = document.createElement("button"); button.type = "button"; button.className = style; button.textContent = label; button.disabled = disabled; button.addEventListener("click", handler); actions.append(button); };
  if (!mine) add("加入牌桌", "primary", () => perform("claim"));
  else { add(ready ? "取消准备" : "准备", ready ? "secondary" : "primary", () => perform(ready ? "unready" : "ready")); add("离开牌桌", "secondary", () => perform("leave")); }
  if (room.me.id === room.creator_id) add("开始本手", "primary", () => perform("start"), room.players.length < 2 || room.ready.length !== room.players.length);
  const pending = room.players.filter(player => !room.ready.includes(player.id));
  $("#waiting-note").textContent = `${room.players.length < 2 ? "还需1位玩家入座" : pending.length ? `等待 ${pending.map(player => player.name).join("、")} 准备` : "所有玩家已准备，等待房主开始"} · ${META.limits} · ${room.room_type === "coin" ? (game === "niuniu" ? `底注 ${room.stake} 币；闲家托管 ${room.stake * 3} 币，庄家托管 ${room.stake * 3 * (room.players.length - 1)} 币。庄闲身份见座位，结算退回剩余托管。` : `每手带入 ${room.stake} 摸鱼币`) : "休闲场不结算摸鱼币"}`;
}
function renderBoard() {
  const state = room.state; $("#waiting").hidden = true; $("#table").hidden = false;
  const seats = $("#seats"); seats.replaceChildren(); room.players.forEach((player, index) => seats.append(playerSeat(player, index)));
  const board = $("#board"); board.replaceChildren(); (state.board || []).forEach(card => board.append(cardNode(card)));
  $("#dealer").replaceChildren();
  if (game === "niuniu") $("#dealer").textContent = `本局庄家：${gamePlayer(state.banker)?.name || "玩家"}`;
  const mine = $("#my-cards"); mine.replaceChildren();
  const unseen = game === "zhajinhua" && room.phase === "playing" && !state.seen?.includes(room.me.id);
  const handKey = `${room.id}:${room.hand_number}`;
  if (handKey !== niuHandKey) { niuSelection = []; niuHandKey = handKey; }
  (state.hands?.[room.me.id] || []).forEach((card, index) => {
    const node = cardNode(unseen ? null : card);
    if (game === "niuniu" && canArrangeNiu()) {
      const button = document.createElement("button"); button.type = "button"; button.className = "niu-card-button";
      button.setAttribute("aria-label", `选择${node.textContent}`); button.setAttribute("aria-pressed", String(niuSelection.includes(index)));
      button.append(node); button.onclick = () => {
        if (busy) return;
        if (niuSelection.includes(index)) niuSelection = niuSelection.filter(i => i !== index);
        else if (niuSelection.length < 3) niuSelection.push(index);
        else { feedback("已选三张，再点已选牌可取消"); return; }
        renderBoard();
      }; mine.append(button);
    } else mine.append(node);
  });
  mine.setAttribute("aria-label", unseen ? "尚未看牌，可闷牌下注或点击看牌" : "你的手牌");
  $("#pot").textContent = game === "niuniu" ? `底注 ${state.base}${room.room_type === "coin" ? "币" : "分"} · 牛七起2倍 · 牛牛3倍` : `奖池 ${state.pot || 0}`;
  $("#my-cards").classList.toggle("folded", (state.folded || []).includes(room.me.id));
  renderActivity();
  renderActions(); renderResult();
}
function renderActivity() {
  const history = room.state.action_history || [];
  const latest = history.at(-1);
  $("#last-action").textContent = latest ? `${gamePlayer(latest.player)?.name || "玩家"} · ${actionText(latest, id => gamePlayer(id)?.name || "玩家")}` : room.state.last_action || "等待首次行动";
  const list = $("#action-history"); list.replaceChildren();
  for (const event of [...history].reverse()) {
    const line = document.createElement("p");
    line.textContent = `${event.sequence}. ${gamePlayer(event.player)?.name || "玩家"} · ${actionText(event, id => gamePlayer(id)?.name || "玩家")}`;
    list.append(line);
  }
  if (!history.length) list.textContent = "本手还没有行动记录";
}
function animateActions(events) {
  if (!events.length || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const previous = renderedRoom?.state || {};
  for (const [selector, before] of [["#board", previous.board || []], ["#my-cards", previous.hands?.[room.me.id] || []]]) {
    [...$(selector).children].slice(before.length).forEach(card => card.animate([{opacity:0,transform:"translateY(-12px)"},{opacity:1,transform:"translateY(0)"}], {duration:300}));
  }
  for (const event of events) {
    if (event.action === "fold" && event.player === room.me.id) $("#my-cards").animate([{opacity:1},{opacity:.32}], {duration:250});
    const seat = [...document.querySelectorAll(".seat")].find(node => node.dataset.player === event.player);
    if (!seat) continue;
    if (event.action === "reveal") seat.querySelector(".niu-seat-cards")?.animate([{opacity:0,transform:"scaleX(.8)"},{opacity:1,transform:"scaleX(1)"}], {duration:250});
    seat.querySelector(".seat-action").animate([{opacity: .2, transform: "translateY(6px)"}, {opacity: 1, transform: "translateY(0)"}], {duration: 300});
    if (event.paid > 0) {
      const chip = document.createElement("span"); chip.className = "moving-chip"; chip.textContent = `+${event.paid}`;
      const table = $("#table"); const bounds = table.getBoundingClientRect(); const origin = seat.getBoundingClientRect(); const pot = $("#pot").getBoundingClientRect();
      chip.style.left = `${origin.left - bounds.left + origin.width / 2}px`; chip.style.top = `${origin.top - bounds.top}px`; table.append(chip);
      const animation = chip.animate([{transform: "translate(-50%,0)", opacity: 1}, {transform: `translate(${pot.left - origin.left}px,${pot.top - origin.top}px)`, opacity: 0}], {duration: 480, easing: "ease-in"});
      animation.onfinish = () => chip.remove();
    }
  }
}
function actionButton(label, action, payload = {}, primary = false, disabled = false) { const button = document.createElement("button"); button.type = "button"; button.className = primary ? "primary" : "secondary"; button.textContent = label; button.disabled = disabled; button.addEventListener("click", () => perform(action, payload)); return button; }
function updateTurnCountdown() {
  const note = $("[data-turn-countdown]");
  if (!note || !room?.state) return;
  if (room.phase !== "playing") { note.textContent = "本手已结束 · 查看结算"; return; }
  if (!room.state.turn_deadline) { note.textContent = room.state.turn === room.me.id ? "轮到你行动" : "等待玩家行动"; return; }
  const seconds = Math.max(0, Math.ceil((Date.parse(room.state.turn_deadline) - Date.now()) / 1000));
  const actor = game === "niuniu" ? (canArrangeNiu() ? "请配牛亮牌" : "等待其他玩家亮牌") : room.state.turn === room.me.id ? "你的回合" : `${gamePlayer(room.state.turn)?.name || "玩家"}思考中`;
  note.classList.toggle("urgent", seconds <= 8);
  note.classList.toggle("your-turn", game === "niuniu" ? canArrangeNiu() : room.state.turn === room.me.id);
  note.textContent = seconds ? `${actor} · ${seconds}秒` : `${actor} · 正在超时处理`;
}
function canArrangeNiu() {
  return room?.phase === "playing" && room.state.players?.includes(room.me.id) && !room.state.revealed?.includes(room.me.id);
}
function renderNiuActions(holder) {
  const own = room.state.own_evaluation;
  const hint = document.createElement("span"); hint.className = "niu-hint";
  const sum = niuSelection.reduce((total, i) => { const rank = room.state.hands[room.me.id][i][1]; return total + (rank === 14 ? 1 : Math.min(rank, 10)); }, 0);
  hint.textContent = own.bull ? `选择三张凑10的倍数 · 已选 ${niuSelection.length}/3 · 合计 ${sum}` : "无牛：没有三张牌能凑10的倍数，可直接亮牌";
  const auto = document.createElement("button"); auto.type = "button"; auto.className = "secondary"; auto.textContent = "自动配牛";
  auto.onclick = () => { niuSelection = [...own.group]; renderBoard(); };
  holder.append(hint, auto, actionButton("亮牌", "reveal", {hand_number: room.hand_number, cards: own.bull ? niuSelection : null}, true, !!own.bull && (niuSelection.length !== 3 || sum % 10 !== 0)));
}
function renderActions() {
  const holder = $("#actions"); holder.replaceChildren(); const state = room.state; const mine = game === "niuniu" ? canArrangeNiu() : state.turn === room.me.id && room.phase === "playing";
  const note = document.createElement("span"); note.className = "turn-countdown"; note.dataset.turnCountdown = "true"; holder.append(note); updateTurnCountdown();
  if (!mine) return;
  if (game === "niuniu") { renderNiuActions(holder); }
  else if (game === "texas") {
    const toCall = Math.max(0, state.current_bet - (state.street_bets?.[room.me.id] || 0));
    holder.append(actionButton("弃牌", "fold"), actionButton(toCall ? `跟注 ${Math.min(toCall, state.chips?.[room.me.id] || 0)}` : "过牌", toCall ? "call" : "check", {}, true), actionButton("全下", "all_in"));
    const wrap = document.createElement("label"); wrap.className = "raise-control"; const input = document.createElement("input"); input.type = "range"; input.setAttribute("aria-label", "加注后的本轮总下注额"); input.min = state.current_bet + state.minimum_raise; input.max = (state.street_bets?.[room.me.id] || 0) + (state.chips?.[room.me.id] || 0); input.value = input.min; const button = document.createElement("button"); button.type = "button"; button.className = "secondary"; button.textContent = `加注至 ${input.value}`; input.addEventListener("input", () => button.textContent = `加注至 ${input.value}`); button.addEventListener("click", () => perform("raise", {amount: Number(input.value)})); wrap.append(input, button); if (Number(input.max) >= Number(input.min)) holder.append(wrap);
  } else if (game === "zhajinhua") {
    const seen = state.seen.includes(room.me.id); if (!seen) holder.append(actionButton("看牌", "look"));
    const cost = state.base_bet * (seen ? 2 : 1); const chips = state.chips[room.me.id];
    holder.append(actionButton("弃牌", "fold"));
    for (const [label, action, amount] of [["跟注", "call", cost], ["加注", "raise", cost * 2]]) {
      const button = actionButton(`${label} ${amount}${chips < amount ? " · 不足" : ""}`, action, {}, action === "call", chips < amount);
      button.title = `需 ${amount} 筹码，剩余 ${chips}${chips < amount ? "，筹码不足" : ""}`; holder.append(button);
    }
    const compare = document.createElement("button"); compare.type = "button"; compare.className = "secondary"; compare.textContent = `比牌 ${cost * 2}${chips < cost * 2 ? " · 不足" : ""}`; compare.disabled = chips < cost * 2; compare.title = `需 ${cost * 2} 筹码，剩余 ${chips}`;
    compare.onclick = () => {
      const targets = $("#compare-targets"); targets.replaceChildren();
      state.players.filter(id => id !== room.me.id && !state.folded.includes(id)).forEach(id => targets.append(actionButton(`与 ${gamePlayer(id)?.name || "玩家"} 比牌`, "compare", {target: id})));
      $("#compare-cost").textContent = `本次支付 ${cost * 2} 筹码，选择一名仍在牌局中的玩家。`;
      $("#compare-dialog .local-feedback").textContent = ""; $("#compare-dialog").showModal();
    }; holder.append(compare);
  } else holder.append(actionButton("要牌", "hit", {}, true), actionButton("停牌", "stand"));
}
function renderResult() {
  const holder = $("#result"); if (room.phase !== "hand_finished") { holder.hidden = true; return; } holder.hidden = false; holder.replaceChildren();
  const head = document.createElement("header"); const copy = document.createElement("div"); const eyebrow = document.createElement("span"); eyebrow.textContent = `第 ${room.hand_number} 手 · 结算`; const title = document.createElement("h3"); title.textContent = room.state.result_label || "本手结算"; copy.append(eyebrow, title); const winner = document.createElement("b"); winner.textContent = (room.state.winners || []).includes(room.me.id) ? "胜" : "结"; head.append(copy, winner); holder.append(head);
  const rows = document.createElement("div"); rows.className = "showdown-list";
  const handPlayers = new Set(room.state.players || []);
  room.players.filter(player => handPlayers.has(player.id)).forEach(player => {
    const id = player.id; const won = (room.state.winners || []).includes(id); const row = document.createElement("article"); row.className = won ? "showdown-row winner" : "showdown-row";
    const avatar = avatarButton(player); const info = document.createElement("div"); const name = document.createElement("strong"); name.textContent = `${player.name}${id === room.me.id ? " · 你" : ""}${game === "niuniu" && id === room.state.banker ? " · 庄" : ""}`;
    const rank = document.createElement("small"); const folded = (room.state.folded || []).includes(id); const total = room.state.totals?.[id]; rank.textContent = game === "blackjack" ? `${total ?? "—"} 点 · ${room.state.results?.[id] || "已结算"}` : folded ? "已弃牌" : room.state.hand_ranks?.[id] || (won ? "胜出" : "未摊牌"); info.append(name, rank);
    const cards = document.createElement("div"); cards.className = "showdown-cards";
    const hand = room.state.hands?.[id] || []; const group = game === "niuniu" ? room.state.evaluations?.[id]?.group || [] : [];
    const order = [...group, ...hand.map((_, i) => i).filter(i => !group.includes(i))];
    order.forEach((index, position) => { const node = cardNode(hand[index]); if (group.length && position === 2) node.classList.add("niu-group-end"); cards.append(node); });
    const amount = document.createElement("span"); amount.className = "settle-amount"; const payout = Number(room.state.payouts?.[id] || 0); const net = game === "niuniu" ? room.state.net?.[id] || 0 : payout - (room.room_type === "coin" ? room.stake : 0); amount.textContent = room.room_type === "coin" ? `${net >= 0 ? "+" : ""}${net} 币` : game === "niuniu" ? `${net >= 0 ? "+" : ""}${net} 分` : won ? "胜" : "负";
    row.append(avatar, info, cards, amount); rows.append(row);
  });
  holder.append(rows);
  if (game === "niuniu") {
    const details = document.createElement("section"); details.className = "niu-payments";
    for (const payment of room.state.payments || []) {
      const line = document.createElement("p");
      line.textContent = `${gamePlayer(payment.payer)?.name || "玩家"} → ${gamePlayer(payment.payee)?.name || "玩家"}：${payment.base} × ${payment.multiplier} = ${payment.amount}${room.room_type === "coin" ? "币" : "分"}`; details.append(line);
    }
    const refund = document.createElement("p");
    refund.textContent = room.room_type === "coin" && room.state.players.includes(room.me.id) ? `你的托管 ${room.state.buy_ins[room.me.id]} 币，结算入账 ${room.state.payouts[room.me.id]} 币（含剩余托管）` : "休闲场仅计分，不扣摸鱼币"; details.append(refund);
    const next = document.createElement("b"); const nextBanker = gamePlayer(room.scheduled_banker || room.state.next_banker);
    next.textContent = nextBanker ? `下一局庄家：${nextBanker.name}${(room.scheduled_banker || room.state.next_banker) !== room.state.next_banker ? " · 原庄离桌重新定庄" : room.state.next_banker === room.state.banker ? " · 继续坐庄" : " · 牛牛赢庄接庄"}` : "原庄已离桌，下一局重新随机定庄";
    details.append(next); holder.append(details);
  }
  const readyList = document.createElement("div"); readyList.className = "next-ready"; room.players.forEach(player => { const item = document.createElement("span"); item.className = room.ready.includes(player.id) ? "ready" : ""; item.textContent = `${player.name} ${room.ready.includes(player.id) ? "已准备" : "未准备"}`; readyList.append(item); }); holder.append(readyList);
  const mine = room.players.some(player => player.id === room.me.id); const ready = room.ready.includes(room.me.id); const allReady = room.players.length >= 2 && room.players.every(player => room.ready.includes(player.id)); const footer = document.createElement("footer");
  if (mine) {
    footer.append(actionButton(ready ? "取消准备" : "准备下一手", ready ? "unready" : "ready", {}, !ready));
    footer.append(actionButton("退出牌桌", "leave"));
  } else if (room.players.length < META.maximum) {
    footer.append(actionButton("加入下一手", "claim", {}, true));
  } else {
    footer.append(actionButton("牌桌已满", "claim", {}, false, true));
  }
  if (room.me.id === room.creator_id) footer.append(actionButton(allReady ? "开始下一手" : `等待准备 ${room.ready.length}/${room.players.length}`, "start", {}, true, !allReady));
  holder.append(footer);
}
function renderMessages() {
  const list = $("#messages"); const bottom = !list.children.length || list.scrollHeight - list.scrollTop - list.clientHeight < 48; const scroll = list.scrollTop; list.replaceChildren(); (room.messages || []).forEach(item => { const row = document.createElement("article"); row.className = "message"; const avatar = avatarButton(item.player, "chat-player"); const copy = document.createElement("div"); const name = document.createElement("b"); name.textContent = item.player.name; name.role = "button"; name.tabIndex = 0; name.addEventListener("click", () => runtime?.openProfile?.(item.player)); const text = document.createElement("p"); text.textContent = item.text; copy.append(name, text); row.append(avatar, copy); list.append(row); }); list.scrollTop = bottom ? list.scrollHeight : scroll;
}
function renderRoom() {
  $("#room-title").textContent = `${room.players.find(player => player.id === room.creator_id)?.name || "玩家"}的牌桌`; const rakeCopy = room.room_type === "coin" && room.state?.rake_percent !== undefined ? ` · 抽水 ${room.state.rake_percent}%` : ""; $("#hand-label").textContent = `第 ${Math.max(1, room.hand_number)} 手 · ${{waiting: "候场", playing: "进行中", hand_finished: "已结算"}[room.phase]}${rakeCopy}`;
  runtime?.setRoomContext?.({game, phase: room.phase, roomId: room.id, host: room.players.find(player => player.id === room.creator_id)?.name || "玩家"});
  if (room.phase === "waiting") renderWaiting(); else renderBoard(); renderMessages();
  animateActions(newActions(renderedRoom, room)); renderedRoom = room;
}
async function perform(action, payload = {}) {
  if (busy || !room) return;
  if (action === "all_in" && !confirm(`确认全下剩余 ${room.state.chips?.[room.me.id] || 0} 筹码？`)) return;
  if (action === "fold" && game === "texas" && room.state.current_bet === (room.state.street_bets?.[room.me.id] || 0) && !confirm("当前可以免费过牌，仍要弃牌吗？")) return;
  busy = true; feedback(); document.querySelectorAll("#actions button, #waiting-actions button, #result footer button, #compare-targets button").forEach(button => button.disabled = true);
  try { const next = await api.action(room.id, room.version, action, payload); if (action === "leave") { await openLobby(); return; } if (game !== "niuniu" || next.version >= room.version) room = next; if (action === "compare") $("#compare-dialog").close(); renderRoom(); } catch (error) { feedback(error.message, "error"); } finally { busy = false; document.querySelectorAll("#compare-targets button").forEach(button => button.disabled = false); if (room) { if (room.phase === "waiting") renderWaiting(); else { renderActions(); renderResult(); } } }
}
async function sendChat() { if (chatBusy) return; const input = $("#chat-input"); const text = input.value.trim(); if (!text || !room) return; chatBusy = true; $("#chat-send").disabled = true; $("#chat-feedback").textContent = ""; try { await api.chat(room.id, text); if (input.value.trim() === text) input.value = ""; room = await api.snapshot(room.id); renderMessages(); } catch (error) { feedback(error.message, "error"); } finally { chatBusy = false; $("#chat-send").disabled = false; } }
async function boot() {
  if (!META) { feedback("无法识别游戏类型，请返回 Club 重新进入", "error"); sdk?.loading?.error?.("CARD_TABLE_GAME_MISSING", "无法识别游戏类型"); return; }
  document.body.dataset.game = game;
  if (game === "niuniu") {
    $("#niu-rules").hidden = false;
    $("#stake-field legend").textContent = "每对比牌底注（开局另按最大赔付托管）";
  }
  document.documentElement.style.setProperty("--table-art", `url("${META.art}")`); $("#game-title").textContent = META.name; $("#game-mark").textContent = META.mark; $("#game-subtitle").textContent = META.subtitle; $("#game-description").textContent = META.description; $("#create-title").textContent = `新建${META.name}房`;
  try { await refreshEconomy(); await identify(); const roomId = params.get("room"); if (roomId) await enterRoom(roomId); else await restoreRoomOrLobby(); sdk?.loading?.ready?.(); } catch (error) { feedback(error.message, "error"); sdk?.loading?.error?.("CARD_TABLE_BOOT_FAILED", error.message); }
}

$("#back").addEventListener("click", () => {
  if (room?.phase === "playing") {
    if (!confirm("牌局尚未结束。返回大厅后座位会保留，倒计时继续，超时将自动操作；重新进入 Club 会回到本桌。确定返回吗？")) return;
    stopFollowing();
    if (moduleContext?.close) moduleContext.close();
    else openLobby();
    return;
  }
  if (room) openLobby();
  else if (moduleContext?.close) moduleContext.close();
  else parent.postMessage({type: "moyu-club-close"}, "*");
});
$("#refresh").addEventListener("click", () => room ? enterRoom(room.id) : openLobby()); $("#public-channel").addEventListener("click", () => runtime?.openChannel?.());
$("#create").addEventListener("click", async () => { await refreshEconomy(); $("#create-dialog").showModal(); }); $("#cancel-create").addEventListener("click", () => $("#create-dialog").close());
$("#confirm-create").addEventListener("click", async () => { if (busy) return; busy = true; $("#confirm-create").disabled = true; const roomType = document.querySelector('[name="room-type"]:checked').value; const stake = roomType === "coin" ? Number(document.querySelector('[name="stake"]:checked').value) : 0; try { const created = await api.create(roomType, stake); $("#create-dialog").close(); await enterRoom(created.id, created); } catch (error) { feedback(error.message, "error"); } finally { busy = false; $("#confirm-create").disabled = false; } });
document.querySelectorAll('[name="room-type"]').forEach(input => input.addEventListener("change", () => $("#stake-field").hidden = input.checked && input.value === "casual"));
$("#share").addEventListener("click", async () => { if (!room) return; try { await runtime?.shareRoom?.({game, phase: room.phase, roomId: room.id, host: room.players.find(player => player.id === room.creator_id)?.name || "玩家"}); } catch (error) { feedback(error.message || "分享失败", "error"); } });
$("#room-public-channel").addEventListener("click", () => runtime?.openChannel?.());
$("#chat-toggle").addEventListener("click", () => { $("#chat").hidden = false; }); $("#chat-close").addEventListener("click", () => { $("#chat").hidden = true; }); $("#chat-send").addEventListener("click", sendChat); $("#chat-input").addEventListener("keydown", event => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); sendChat(); } });
addEventListener("pagehide", stopFollowing); watchLayout(); boot();

export function unmount() { stopFollowing(); layoutObserver?.disconnect(); layoutObserver = null; removeEventListener("resize", syncLayout); runtime?.clearRoomContext?.(); }

$("#history-toggle").addEventListener("click", () => { $("#history-panel").hidden = !$("#history-panel").hidden; $("#history-toggle").setAttribute("aria-expanded", String(!$("#history-panel").hidden)); });
$("#history-close").addEventListener("click", () => { $("#history-panel").hidden = true; $("#history-toggle").setAttribute("aria-expanded", "false"); });

$("#compare-cancel").addEventListener("click", () => $("#compare-dialog").close());

$("#niu-rules").onclick = () => $("#niu-rules-dialog").showModal();
$("#niu-rules-close").onclick = () => $("#niu-rules-dialog").close();
