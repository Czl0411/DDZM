export async function withTimeout(promise, label, timeoutMs = 8000) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label}超时，请重试`)), timeoutMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

export function requestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  globalThis.crypto?.getRandomValues?.(bytes);
  return [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
}

export class ClubClient {
  constructor({sdk, fetchImpl = fetch, apiBase, sleepImpl = ms => new Promise(resolve => setTimeout(resolve, ms))}) {
    this.sdk = sdk;
    this.fetchImpl = fetchImpl.bind(globalThis);
    this.root = `${apiBase.replace(/\/$/, "")}/api/club/mahjong`;
    this.sleepImpl = sleepImpl;
    this.uid = null;
    this.identityPromise = null;
    this.stop = null;
  }

  async identity(refresh = false) {
    if (refresh) {
      this.stop?.();
      this.uid = null;
      this.identityPromise = null;
    }
    if (this.uid) return this.uid;
    if (!this.identityPromise) {
      this.identityPromise = withTimeout(this.sdk.user.info(), "读取玩家身份")
        .then(info => {
          if (typeof info?.id !== "string" || !info.id.trim()) throw new Error("无法读取玩家身份，请重试");
          this.uid = info.id;
          return this.uid;
        });
    }
    try {
      return await this.identityPromise;
    } finally {
      this.identityPromise = null;
    }
  }

  async request(path, options = {}) {
    const uid = await this.identity();
    const controller = new AbortController();
    try {
      return await withTimeout((async () => {
        const response = await this.fetchImpl(this.root + path, {
          ...options,
          signal: controller.signal,
          headers: {
            Authorization: `ClubUid ${uid}`,
            ...(options.body ? {"Content-Type": "application/json"} : {}),
          },
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(typeof body.detail === "string" ? body.detail : "请求失败，请重试");
        }
        return response.json();
      })(), "连接 Club 服务器");
    } finally {
      controller.abort();
    }
  }

  rooms() { return this.request("/rooms"); }
  create(roomType, matchMode) {
    return this.request("/rooms", {method: "POST", body: JSON.stringify({request_id: requestId(), room_type: roomType, match_mode: matchMode})});
  }
  snapshot(roomId) { return this.request(`/rooms/${roomId}`); }
  action(roomId, version, action, payload = {}) {
    return this.request(`/rooms/${roomId}/actions`, {method: "POST", body: JSON.stringify({version, request_id: requestId(), action, payload})});
  }
  chat(roomId, text) {
    return this.request(`/rooms/${roomId}/chat`, {method: "POST", body: JSON.stringify({request_id: requestId(), text})});
  }
  follow(roomId, onUpdate, onError) {
    this.stop?.();
    const controller = new AbortController();
    this.stop = () => controller.abort();
    (async () => {
      while (!controller.signal.aborted) {
        try {
          const snapshot = await this.snapshot(roomId);
          if (!controller.signal.aborted) onUpdate(snapshot);
        } catch (error) {
          if (!controller.signal.aborted) onError(error);
        }
        if (!controller.signal.aborted) await this.sleepImpl(1000);
      }
    })();
    return this.stop;
  }
  dispose() { this.stop?.(); this.stop = null; }
}
