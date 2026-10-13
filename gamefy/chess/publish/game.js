const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function resolveRoomId(gp, hash) {
  if (gp != null) {
    try {
      const data = JSON.parse(gp);
      return data && typeof data.roomId === 'string' && UUID.test(data.roomId) ? data.roomId.toLowerCase() : null;
    } catch { return null; }
  }
  const match = /^#room=([0-9a-f-]+)$/i.exec(hash || '');
  return match && UUID.test(match[1]) ? match[1].toLowerCase() : null;
}

export function canMove(state) {
  return !!state && state.game.status === 'playing' && state.role === state.game.position?.turn;
}

export function canChat(state) { return !!state && state.game.status === 'playing'; }

export class ChessClient {
  constructor({ sdk, fetchImpl, apiBase, roomId }) {
    this.sdk = sdk;
    this.fetchImpl = fetchImpl.bind(globalThis);
    this.root = `${apiBase.replace(/\/$/, '')}/api/chess`;
    this.base = roomId ? `${this.root}/${roomId}` : this.root;
    this.token = null;
    this.authRetryAt = 0;
    this.state = null;
  }
  rooms() { return this.request('/rooms'); }
  selectRoom(roomId) { this.base = `${this.root}/${roomId}`; }
  async auth(force = false) {
    if (force || !this.token) {
      if (Date.now() < this.authRetryAt) throw new Error('登录凭证暂不可用，请稍后再试，避免连续刷新。');
      const info = await this.sdk.user.info();
      this.token = info?.token;
      if (!this.token) {
        this.authRetryAt = Date.now() + 60000;
        throw new Error(info?.id ? '平台暂未签发登录凭证，可能限流或服务异常。请至少等待 60 秒后再刷新棋局。' : '请先登录 DZMM。');
      }
      this.authRetryAt = 0;
    }
    return this.token;
  }
  async request(suffix = '', options = {}) {
    const send = async () => this.fetchImpl(this.base + suffix, {
      ...options,
      headers: { Authorization: `Bearer ${await this.auth()}`, ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
    });
    let response = await send();
    if (response.status === 401) { await this.auth(true); response = await send(); }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const error = new Error(typeof data.detail === 'string' ? data.detail : '请求失败，请刷新棋局。');
      error.status = response.status;
      throw error;
    }
    return response.json();
  }
  async snapshot() { this.state = await this.request(); return this.state; }
  async post(suffix, body) {
    try {
      this.state = await this.request(suffix, { method: 'POST', body: JSON.stringify(body) });
      return this.state;
    } catch (error) { await this.snapshot().catch(() => {}); throw error; }
  }
  move(from_xy, to_xy, version) { return this.post('/moves', { from_xy, to_xy, version }); }
  claim(code) { return this.post('/claim', { code }); }
  action(action, version) { return this.post('/actions', { action, version }); }
  async chat(text) {
    await this.request('/chat', { method: 'POST', body: JSON.stringify({ text }) });
    return this.snapshot();
  }
  async follow(onState, signal) {
    while (!signal.aborted) {
      try {
        onState(await this.snapshot());
        if (signal.aborted) break;
        let response = await this.fetchImpl(`${this.base}/events`, {
          headers: { Authorization: `Bearer ${await this.auth()}` }, signal,
        });
        if (response.status === 401) { await this.auth(true); continue; }
        if (!response.ok || !response.body) throw new Error('棋局连接中断');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (!signal.aborted) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary;
          while ((boundary = buffer.indexOf('\n\n')) >= 0) {
            const packet = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const data = packet.split('\n').find(line => line.startsWith('data: '));
            if (data) { this.state = JSON.parse(data.slice(6)); onState(this.state); }
          }
        }
      } catch (error) { if (!signal.aborted) onState(this.state, error); }
      if (!signal.aborted) await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
}

const PIECE = { R: '車', H: '馬', E: '相', A: '仕', K: '帥', C: '炮', P: '兵', r: '車', h: '馬', e: '象', a: '士', k: '將', c: '砲', p: '卒' };

async function boot() {
  const status = document.querySelector('#status');
  const loading = window.dzmm.loading;
  loading?.progress({ phase: 'start', message: '正在进入棋局' });
  let ready = false;
  const showReady = () => {
    if (!ready) { ready = true; loading?.ready(); }
  };
  const launch = await window.dzmm.getLaunchParams();
  let roomId = location.hash === '#lobby' ? null : resolveRoomId(launch?.gp, location.hash);
  if (!/^https:\/\//.test(window.CHESS_API_BASE || '')) { status.textContent = '棋局 API 尚未配置 HTTPS 地址。'; showReady(); return; }
  const client = new ChessClient({ sdk: window.dzmm, fetchImpl: fetch, apiBase: window.CHESS_API_BASE, roomId });
  if (!roomId) {
    const lobby = document.querySelector('#lobby');
    lobby.hidden = false;
    document.querySelector('.layout').hidden = true;
    showReady();
    roomId = await new Promise(resolve => {
      const refresh = async () => {
        const list = document.querySelector('#rooms');
        try {
          const rooms = await client.rooms();
          list.replaceChildren();
          status.textContent = rooms.length ? '选择棋局，输入入座码加入；也可以直接观战。' : '暂无可加入或观战的棋局。';
          for (const room of rooms) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = `${room.creator_name} · ${room.id.slice(0, 8)} · ${room.status === 'waiting' ? '等待入座' : '正在对局'} · 进入 / 观战`;
            button.addEventListener('click', () => resolve(room.id));
            list.append(button);
          }
        } catch (error) { status.textContent = error.message; }
      };
      document.querySelector('#refresh-rooms').addEventListener('click', refresh);
      refresh();
    });
    client.selectRoom(roomId);
    lobby.hidden = true;
    document.querySelector('.layout').hidden = false;
  }
  location.hash = `room=${roomId}`;
  document.querySelector('#back-to-rooms').addEventListener('click', () => {
    location.hash = 'lobby';
    location.reload();
  });
  const controller = new AbortController();
  let state = null;
  let selected = null;
  let serverOffset = 0;
  const board = document.querySelector('#board');

  function clockText(color) {
    if (!state) return '15:00';
    const game = state.game;
    let ms = game[`${color}_remaining_ms`];
    if (game.status === 'playing' && game.position?.turn === color) {
      ms -= Math.max(0, Date.now() - serverOffset - Date.parse(game.turn_started_at));
    }
    const seconds = Math.max(0, Math.ceil(ms / 1000));
    return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }
  function clocks() {
    document.querySelector('#red-clock').textContent = clockText('red');
    document.querySelector('#black-clock').textContent = clockText('black');
    const game = state?.game;
    const elapsed = game?.status === 'playing' ? Math.max(0, Date.now() - serverOffset - Date.parse(game.turn_started_at)) : 0;
    document.querySelector('#move-clock').textContent = String(Math.max(0, Math.ceil((60000 - elapsed) / 1000)));
  }
  function renderBoard() {
    board.replaceChildren();
    const rows = state.game.position?.board || Array(10).fill('.........');
    const flip = state.role === 'black';
    for (let row = 0; row < 10; row++) for (let col = 0; col < 9; col++) {
      const x = flip ? 8 - col : col;
      const y = flip ? 9 - row : row;
      const piece = rows[y][x];
      const cell = document.createElement('button');
      cell.type = 'button';
      cell.className = `cell${row === 4 ? ' river' : ''}${selected?.[0] === x && selected?.[1] === y ? ' selected' : ''}`;
      cell.setAttribute('aria-label', `${x},${y}${PIECE[piece] || ''}`);
      if (piece !== '.') {
        const disk = document.createElement('span');
        disk.className = `piece ${piece === piece.toUpperCase() ? 'red' : 'black'}`;
        disk.textContent = PIECE[piece];
        cell.append(disk);
      }
      cell.addEventListener('click', async () => {
        if (!canMove(state)) return;
        const own = piece !== '.' && (piece === piece.toUpperCase()) === (state.role === 'red');
        if (own) { selected = [x, y]; renderBoard(); return; }
        if (!selected) return;
        const from = selected;
        selected = null;
        try { render(await client.move(from, [x, y], state.game.version)); }
        catch (error) { render(client.state); status.textContent = error.message; }
      });
      board.append(cell);
    }
  }
  function render(next, error) {
    if (!next) { status.textContent = error?.message || '连接中…'; showReady(); return; }
    state = next;
    serverOffset = Date.now() - Date.parse(next.server_time || new Date().toISOString());
    const game = next.game;
    document.querySelector('#players').textContent = `红方 ${game.red_name || '待定'} · 黑方 ${game.black_name || '待定'}`;
    status.textContent = error ? '正在重新连接…' : game.status === 'waiting' ? '等待第二位棋手入座' : game.status === 'cancelled' ? '棋局已取消' : game.status === 'finished' ? `已结束：${game.result}` : `进行中 · 你是${next.role === 'spectator' ? '观众' : next.role === 'red' ? '红方' : '黑方'}`;
    document.querySelector('#claim-panel').hidden = game.status !== 'waiting' || next.role !== 'spectator';
    document.querySelector('#actions').hidden = !['red', 'black'].includes(next.role) || game.status !== 'playing';
    document.querySelector('#respond').hidden = !game.pending_offer || next.offer_mine || !['red', 'black'].includes(next.role);
    for (const button of document.querySelectorAll('#respond [data-action]')) {
      button.hidden = !button.dataset.action.endsWith(game.pending_offer || '');
    }
    document.querySelector('#offer-label').textContent = game.pending_offer ? `对手请求${game.pending_offer === 'undo' ? '悔棋' : '和棋'}` : '';
    document.querySelector('#chat-input').disabled = !canChat(next);
    document.querySelector('#chat-send').disabled = !canChat(next);
    const list = document.querySelector('#chat-list');
    list.replaceChildren();
    for (const message of next.messages || []) {
      const item = document.createElement('p');
      item.textContent = `${message.sender}：${message.text}`;
      list.append(item);
    }
    const moves = document.querySelector('#moves-list');
    moves.replaceChildren();
    for (const move of next.moves || []) {
      const item = document.createElement('span');
      item.textContent = `${move.ply}. ${move.from_xy.join(',')}→${move.to_xy.join(',')}  `;
      moves.append(item);
    }
    clocks(); renderBoard(); showReady();
  }
  document.querySelector('#claim-panel').addEventListener('submit', async event => {
    event.preventDefault();
    try { render(await client.claim(document.querySelector('#claim-code').value.trim())); }
    catch (error) { status.textContent = error.message; }
  });
  document.querySelector('#chat-form').addEventListener('submit', async event => {
    event.preventDefault();
    const input = document.querySelector('#chat-input');
    try { render(await client.chat(input.value)); input.value = ''; }
    catch (error) { status.textContent = error.message; }
  });
  for (const button of document.querySelectorAll('[data-action]')) button.addEventListener('click', async () => {
    const action = button.dataset.action;
    if (action === 'resign' && !confirm('确定认输吗？')) return;
    try { render(await client.action(action, state.game.version)); }
    catch (error) { render(client.state); status.textContent = error.message; }
  });
  setInterval(clocks, 250);
  await client.follow(render, controller.signal);
}

if (typeof document !== 'undefined') boot().catch(error => {
  document.querySelector('#status').textContent = error.message;
  window.dzmm.loading?.error('CHESS_BOOT_FAILED', error.message);
});
