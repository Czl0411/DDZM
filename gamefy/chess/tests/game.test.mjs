import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveRoomId, ChessClient, canMove, canChat } from '../publish/game.js';

const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';

test('launch gp is validated and per-tab hash restores its own room', () => {
  assert.equal(resolveRoomId(JSON.stringify({ roomId: A }), `#room=${B}`), A);
  assert.equal(resolveRoomId(null, `#room=${B}`), B);
  assert.equal(resolveRoomId(null, ''), null);
  assert.equal(resolveRoomId('{bad', `#room=${B}`), null);
  assert.equal(resolveRoomId(JSON.stringify({ roomId: '../../other' }), ''), null);
});

test('a renewed platform token retries a request after 401', async () => {
  let infoCalls = 0;
  const sdk = { user: { info: async () => ({ token: `token-${++infoCalls}` }) } };
  const headers = [];
  const fetchImpl = async (_, options) => {
    headers.push(options.headers.Authorization);
    return { ok: headers.length > 1, status: headers.length > 1 ? 200 : 401, json: async () => ({ game: { status: 'waiting' } }) };
  };
  const client = new ChessClient({ sdk, fetchImpl, apiBase: 'https://chess.example.com', roomId: A });
  await client.snapshot();
  assert.deepEqual(headers, ['Bearer token-1', 'Bearer token-2']);
});

test('different room clients never redirect each other and stale moves reload', async () => {
  const paths = [];
  const sdk = { user: { info: async () => ({ token: 'token' }) } };
  let count = 0;
  const fetchImpl = async (url) => {
    paths.push(url);
    count++;
    if (url.endsWith('/moves')) return { ok: false, status: 422, json: async () => ({ detail: '棋局版本已变化' }) };
    return { ok: true, status: 200, json: async () => ({ game: { version: 9 } }) };
  };
  const first = new ChessClient({ sdk, fetchImpl, apiBase: 'https://chess.example.com', roomId: A });
  const second = new ChessClient({ sdk, fetchImpl, apiBase: 'https://chess.example.com', roomId: B });
  await first.move([0, 6], [0, 5], 1).catch(() => {});
  await second.snapshot();
  assert.deepEqual(paths, [
    `https://chess.example.com/api/chess/${A}/moves`,
    `https://chess.example.com/api/chess/${A}`,
    `https://chess.example.com/api/chess/${B}`,
  ]);
});

test('spectators cannot move but may chat until terminal state', () => {
  const playing = { role: 'spectator', game: { status: 'playing', position: { turn: 'red' } } };
  assert.equal(canMove(playing), false);
  assert.equal(canChat(playing), true);
  assert.equal(canMove({ ...playing, role: 'red' }), true);
  assert.equal(canChat({ ...playing, game: { status: 'finished' } }), false);
});

test('reconnect reloads the authoritative snapshot before reopening SSE', async () => {
  const calls = [];
  const controller = new AbortController();
  let snapshots = 0;
  const client = new ChessClient({
    sdk: { user: { info: async () => ({ token: 'token' }) } },
    apiBase: 'https://chess.example.com', roomId: A,
    fetchImpl: async (url) => {
      calls.push(url.endsWith('/events') ? 'events' : 'snapshot');
      if (url.endsWith('/events')) return { ok: true, status: 200, body: { getReader: () => ({ read: async () => ({ done: true }) }) } };
      return { ok: true, status: 200, json: async () => ({ game: { version: ++snapshots } }) };
    },
  });
  await client.follow(state => {
    if (state.game.version === 2) controller.abort();
  }, controller.signal);
  assert.deepEqual(calls, ['snapshot', 'events', 'snapshot']);
});
