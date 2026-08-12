# 本机 DZMM 机器人管理桌面端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a macOS and Windows Electron desktop console that locally maintains a DZMM login session, monitors and sends messages for multiple configured groups through Socket.IO, and handles daily check-ins.

**Architecture:** Electron main owns a persistent DZMM session, the SQLite database, and a multi-group Socket.IO worker. A context-isolated React renderer communicates only through typed IPC; it never handles credentials. The worker accepts real-time `message:new` events as its primary input and calls group history only as a startup, reconnect, and periodic recovery path.

**Tech Stack:** Electron, React, TypeScript, Vite, socket.io-client, better-sqlite3, Vitest, React Testing Library, electron-builder.

## Global Constraints

- Create the desktop project under `desktop/`; do not alter the existing Python server/runtime code.
- Store all local state in Electron `app.getPath("userData")`; never store DZMM Cookie, access token, or password in SQLite or logs.
- Use `persist:dzmm` for both embedded login and main-process authenticated requests.
- Parse groups only from absolute chat URLs with a non-empty `c` parameter and a unique chatroom ID.
- `message:new` is the primary inbound path. `chatroom.getMessages` must only run after connection, after reconnection, and at the configured 5–60 second recovery interval.
- Support group text messages only. Do not add private messages, recalls, Bot API fallback, Webhooks, games, AI, PostgreSQL, or Python subprocesses.
- Mark outbound delivery successful only after `message:send` ACK `{ success: true }`; never silently retry via another transport.
- The only automatic command is exact text `签到`; database uniqueness on `(group_id, platform_user_id, checkin_date)` makes it idempotent.
- UI follows the approved dark, compact, Linear/Sentry-inspired direction without reusing their marks, icons, or assets.

---

## File Structure

```text
desktop/
  package.json                         # Scripts, runtime and development dependencies, builder metadata
  electron.vite.config.ts              # Electron main/preload/renderer Vite configuration
  tsconfig.json                        # TypeScript project references
  src/
    shared/contracts.ts                 # IPC payloads, database records, state and protocol types
    main/
      index.ts                          # Application lifecycle, BrowserWindow, IPC registration
      ipc.ts                            # Narrow IPC handlers and renderer event publishing
      database.ts                       # SQLite schema, repositories, migrations
      groups.ts                         # Chat URL validation and group CRUD service
      dzmm-session.ts                   # Persistent Electron session, token and tRPC request adapter
      dzmm-worker.ts                    # Multi-group Socket.IO connection, recovery and outbound ACKs
      user-directory.ts                 # Verified profile lookup and safe fallback contract
      checkins.ts                       # Exact check-in command and template rendering
      logs.ts                           # Sensitive-value-safe in-memory/database logging and export
    preload/index.ts                    # contextBridge API only
    renderer/
      index.html
      main.tsx
      App.tsx                           # Shell, navigation and app-wide event refresh
      styles.css                        # Dark compact design tokens and layout
      api.ts                            # Typed renderer wrapper around window.dzmm
      pages/DashboardPage.tsx
      pages/MessagesPage.tsx
      pages/GroupsPage.tsx
      pages/CheckinsPage.tsx
      pages/LogsPage.tsx
      pages/SettingsPage.tsx
      components/StatusPill.tsx
      components/EmptyState.tsx
  tests/
    setup.ts
    groups.test.ts
    database.test.ts
    dzmm-worker.test.ts
    checkins.test.ts
    user-directory.test.ts
    ipc.test.ts
    renderer/*.test.tsx
```

## Task 1: Scaffold the isolated Electron project

**Files:**
- Create: `desktop/package.json`
- Create: `desktop/electron.vite.config.ts`
- Create: `desktop/tsconfig.json`
- Create: `desktop/src/main/index.ts`
- Create: `desktop/src/preload/index.ts`
- Create: `desktop/src/renderer/index.html`
- Create: `desktop/src/renderer/main.tsx`
- Create: `desktop/tests/setup.ts`

**Interfaces:**
- Produces the `dev`, `test`, `typecheck`, `build`, and `dist` scripts used by all later tasks.
- Produces an Electron window with `contextIsolation: true`, `nodeIntegration: false`, and a preload script.

- [ ] **Step 1: Create the manifest and Vite configuration**

```json
{
  "name": "dzmm-desktop",
  "private": true,
  "version": "0.1.0",
  "main": "./out/main/index.js",
  "scripts": {
    "dev": "electron-vite dev",
    "build": "electron-vite build",
    "preview": "electron-vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit",
    "dist": "npm run build && electron-builder"
  },
  "dependencies": {
    "@vitejs/plugin-react": "latest",
    "better-sqlite3": "latest",
    "electron": "latest",
    "electron-vite": "latest",
    "react": "latest",
    "react-dom": "latest",
    "socket.io-client": "latest"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "latest",
    "@testing-library/react": "latest",
    "@types/better-sqlite3": "latest",
    "@types/node": "latest",
    "@types/react": "latest",
    "@types/react-dom": "latest",
    "electron-builder": "latest",
    "jsdom": "latest",
    "typescript": "latest",
    "vitest": "latest"
  },
  "build": { "appId": "ai.dzmm.desktop", "productName": "DZMM Console", "mac": { "target": "dmg" }, "win": { "target": "nsis" } }
}
```

- [ ] **Step 2: Add the safe Electron window bootstrap**

```ts
const window = new BrowserWindow({
  width: 1360,
  height: 860,
  minWidth: 1024,
  minHeight: 680,
  webPreferences: {
    preload: join(__dirname, "../preload/index.js"),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: false,
  },
});
```

- [ ] **Step 3: Install dependencies and run the baseline checks**

Run: `npm install && npm run typecheck && npm test`

Expected: dependency installation completes; typecheck and Vitest exit 0 with no tests yet.

- [ ] **Step 4: Commit**

```bash
git add desktop
git commit -m "feat: scaffold DZMM desktop application"
```

## Task 2: Define shared contracts and local SQLite repositories

**Files:**
- Create: `desktop/src/shared/contracts.ts`
- Create: `desktop/src/main/database.ts`
- Create: `desktop/tests/database.test.ts`

**Interfaces:**
- Produces `Group`, `StoredMessage`, `LogEntry`, `WorkerSnapshot`, `CheckinSettings`, and `Member` types.
- Produces `DatabaseStore` with `createGroup`, `updateGroup`, `removeGroup`, `listGroups`, `insertMessage`, `recordCheckin`, `listMessages`, `listLogs`, `upsertMember`, and `getCheckinSettings`.

- [ ] **Step 1: Write failing repository tests using a temporary SQLite database**

```ts
it("deduplicates a platform message and makes check-ins daily per group", () => {
  const store = new DatabaseStore(":memory:");
  const group = store.createGroup({ chatroomId: "room-a", chatUrl: "https://www.aikda.com/chat?c=room-a", name: "A" });
  expect(store.insertMessage(message("m-1", group.id))).toBe(true);
  expect(store.insertMessage(message("m-1", group.id))).toBe(false);
  expect(store.recordCheckin(group.id, "user-1", "2026-08-12")).toBe(true);
  expect(store.recordCheckin(group.id, "user-1", "2026-08-12")).toBe(false);
  expect(store.recordCheckin(group.id, "user-1", "2026-08-13")).toBe(true);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- database.test.ts`

Expected: FAIL because `DatabaseStore` does not exist.

- [ ] **Step 3: Implement schema initialization and repository methods**

```sql
CREATE TABLE IF NOT EXISTS checkins (
  group_id TEXT NOT NULL,
  platform_user_id TEXT NOT NULL,
  checkin_date TEXT NOT NULL,
  PRIMARY KEY (group_id, platform_user_id, checkin_date)
);
CREATE TABLE IF NOT EXISTS messages (
  platform_message_id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  sender_id TEXT NOT NULL,
  text TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  direction TEXT NOT NULL
);
```

- [ ] **Step 4: Run the repository tests and typecheck**

Run: `npm test -- database.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/shared/contracts.ts desktop/src/main/database.ts desktop/tests/database.test.ts
git commit -m "feat: add desktop SQLite storage"
```

## Task 3: Add multi-group configuration and check-in settings

**Files:**
- Create: `desktop/src/main/groups.ts`
- Modify: `desktop/src/main/database.ts`
- Create: `desktop/tests/groups.test.ts`

**Interfaces:**
- Consumes: `DatabaseStore` from Task 2.
- Produces `parseChatUrl(value: string): { chatroomId: string; chatUrl: string }` and `GroupService` CRUD methods.

- [ ] **Step 1: Write failing group URL and lifecycle tests**

```ts
it.each(["/chat?c=x", "https://www.aikda.com/chat", "https://www.aikda.com/chat?c="])(
  "rejects invalid group URL %s", (url) => expect(() => parseChatUrl(url)).toThrow("聊天链接必须包含 c 参数")
);

it("creates default check-in settings and preserves records on removal", () => {
  const group = service.add({ name: "值班群", chatUrl: "https://www.aikda.com/chat?c=room-a" });
  expect(store.getCheckinSettings(group.id)).toMatchObject({ enabled: false, successTemplate: "{name} 签到成功" });
  service.remove(group.id);
  expect(store.listGroups()).toEqual([]);
  expect(store.listMessages({ groupId: group.id })).toHaveLength(1);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test -- groups.test.ts`

Expected: FAIL because `parseChatUrl` and `GroupService` do not exist.

- [ ] **Step 3: Implement validation and transactional group creation**

```ts
export function parseChatUrl(value: string) {
  const url = new URL(value);
  const chatroomId = url.searchParams.get("c");
  if (!url.protocol.startsWith("http") || !url.host || !chatroomId) {
    throw new Error("聊天链接必须包含 c 参数");
  }
  return { chatroomId, chatUrl: url.toString() };
}
```

- [ ] **Step 4: Run focused tests and typecheck**

Run: `npm test -- groups.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/main/groups.ts desktop/src/main/database.ts desktop/tests/groups.test.ts
git commit -m "feat: manage local DZMM groups"
```

## Task 4: Implement the shared persistent DZMM session

**Files:**
- Create: `desktop/src/main/dzmm-session.ts`
- Create: `desktop/tests/dzmm-session.test.ts`
- Modify: `desktop/src/main/index.ts`

**Interfaces:**
- Produces `DzmmSession` with `openLogin()`, `getAccount()`, `getToken()`, `request(procedure, payload)`, `getCookieHeader(origin)`, and `clear()`.
- `getToken`, `request`, and `getCookieHeader` are main-process only and must not enter IPC payloads or logs.

- [ ] **Step 1: Write failing session tests with a fake Electron session and BrowserWindow factory**

```ts
it("uses the persist:dzmm session for login and returns only public account fields", async () => {
  const session = new DzmmSession(fakeElectron);
  await session.openLogin();
  expect(fakeElectron.windowOptions.webPreferences.session).toBe(fakeElectron.persistedSession);
  expect(await session.getAccount()).toEqual({ id: "me", displayName: "值班机器人" });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- dzmm-session.test.ts`

Expected: FAIL because `DzmmSession` does not exist.

- [ ] **Step 3: Implement token/tRPC access in the persisted session**

```ts
async getToken(): Promise<string> {
  return this.executeInAuthenticatedPage(`async () => {
    const response = await fetch('/api/auth/token');
    const body = await response.json();
    if (!response.ok || !body.access_token) throw new Error('DZMM access token unavailable');
    return body.access_token;
  }`);
}
```

- [ ] **Step 4: Run focused tests and typecheck**

Run: `npm test -- dzmm-session.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/main/dzmm-session.ts desktop/src/main/index.ts desktop/tests/dzmm-session.test.ts
git commit -m "feat: add persistent DZMM login session"
```

## Task 5: Build and validate the DZMM user profile adapter

**Files:**
- Create: `desktop/src/main/user-directory.ts`
- Create: `desktop/tests/user-directory.test.ts`
- Modify: `desktop/src/shared/contracts.ts`

**Interfaces:**
- Consumes: `DzmmSession.request`, `DatabaseStore.upsertMember`.
- Produces `DzmmUserDirectory.lookup(groupChatroomId: string, platformUserId: string): Promise<Member | undefined>`.

- [ ] **Step 1: Capture a real, redacted `user.getChatroomUser` request from the authenticated DZMM page**

Use browser developer instrumentation to record only the procedure name, JSON property names, and response field names. Replace IDs, names, Cookie, and token values with fixtures before saving. Do not proceed with a guessed payload.

Expected fixture shape committed to the test:

```ts
const profileResponse = { id: "member-1", nickname: "小雪" };
const expectedRequest = { chatroomId: "room-1", userId: "member-1" };
```

- [ ] **Step 2: Write failing adapter tests against the captured fixture**

```ts
it("caches a verified display name", async () => {
  const directory = new DzmmUserDirectory(fakeSession, store);
  await expect(directory.lookup("room-1", "member-1")).resolves.toMatchObject({ displayName: "小雪" });
  expect(fakeSession.request).toHaveBeenCalledWith("user.getChatroomUser", expectedRequest);
});

it("returns undefined when the platform request fails", async () => {
  fakeSession.request.mockRejectedValue(new Error("request failed"));
  await expect(directory.lookup("room-1", "member-1")).resolves.toBeUndefined();
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm test -- user-directory.test.ts`

Expected: FAIL because `DzmmUserDirectory` does not exist.

- [ ] **Step 4: Implement the captured request mapping and nickname extraction**

```ts
const profile = await this.session.request("user.getChatroomUser", { chatroomId, userId });
const displayName = typeof profile.nickname === "string" ? profile.nickname : undefined;
if (!displayName) return undefined;
return this.store.upsertMember({ groupId: chatroomId, platformUserId, displayName });
```

- [ ] **Step 5: Run focused tests and typecheck**

Run: `npm test -- user-directory.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/main/user-directory.ts desktop/src/shared/contracts.ts desktop/tests/user-directory.test.ts
git commit -m "feat: resolve DZMM group member profiles"
```

## Task 6: Implement exact daily check-in behavior

**Files:**
- Create: `desktop/src/main/checkins.ts`
- Create: `desktop/tests/checkins.test.ts`

**Interfaces:**
- Consumes: `DatabaseStore.recordCheckin`, `DatabaseStore.getCheckinSettings`, `DzmmUserDirectory.lookup`.
- Produces `CheckinService.handle(message: InboundMessage): Promise<CheckinReply | undefined>` where `CheckinReply` has `chatroomId`, `text`, and `outcome`.

- [ ] **Step 1: Write failing check-in tests**

```ts
it("handles only an exact 签到 message once each day", async () => {
  await expect(service.handle(inbound(" 签到"))).resolves.toBeUndefined();
  await expect(service.handle(inbound("签到"))).resolves.toMatchObject({ outcome: "success", text: "小雪 签到成功" });
  await expect(service.handle(inbound("签到"))).resolves.toMatchObject({ outcome: "duplicate", text: "小雪 今天已经签到过了" });
});

it("uses the safe fallback when profile lookup fails", async () => {
  directory.lookup.mockResolvedValue(undefined);
  await expect(service.handle(inbound("签到"))).resolves.toMatchObject({ text: "这位成员 签到成功" });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- checkins.test.ts`

Expected: FAIL because `CheckinService` does not exist.

- [ ] **Step 3: Implement exact command matching, templates, and local-day uniqueness**

```ts
if (message.text !== "签到" || !settings.enabled) return undefined;
const name = (await this.directory.lookup(message.chatroomId, message.senderId))?.displayName ?? "这位成员";
const created = this.store.recordCheckin(message.groupId, message.senderId, this.clock().toISOString().slice(0, 10));
return { chatroomId: message.chatroomId, text: render(created ? settings.successTemplate : settings.duplicateTemplate, name), outcome: created ? "success" : "duplicate" };
```

- [ ] **Step 4: Run focused tests and typecheck**

Run: `npm test -- checkins.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/main/checkins.ts desktop/tests/checkins.test.ts
git commit -m "feat: add local group check-ins"
```

## Task 7: Implement the authenticated multi-group Socket.IO worker

**Files:**
- Create: `desktop/src/main/dzmm-worker.ts`
- Create: `desktop/tests/dzmm-worker.test.ts`
- Modify: `desktop/src/main/logs.ts`

**Interfaces:**
- Consumes: `DzmmSession`, `DatabaseStore`, `GroupService`, `CheckinService`.
- Produces `DzmmWorker.start()`, `stop()`, `send(groupId, text)`, `setRecoveryInterval(seconds)`, `snapshot()`, and event subscription callbacks.

- [ ] **Step 1: Write failing Socket worker tests using a fake Socket.IO client**

```ts
it("joins all enabled groups, accepts an event only once, and ignores self", async () => {
  await worker.start();
  expect(socket.calls).toContainEqual(["message:join-room", { chatroomId: "room-a" }]);
  socket.emit("message:new", event("m-1", "room-a", "member-1", "hello"));
  socket.emit("message:new", event("m-1", "room-a", "member-1", "hello"));
  socket.emit("message:new", event("m-self", "room-a", "me", "签到"));
  expect(store.listMessages()).toHaveLength(1);
});

it("uses history only on ready/reconnect/recovery and confirms sends only after ACK", async () => {
  await worker.start();
  expect(session.request).toHaveBeenCalledWith("chatroom.getMessages", { chatroomId: "room-a" });
  await expect(worker.send(group.id, "hello")).resolves.toMatchObject({ success: true });
  socket.reply({ success: false, error: "rejected" });
  await expect(worker.send(group.id, "again")).rejects.toThrow("rejected");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- dzmm-worker.test.ts`

Expected: FAIL because `DzmmWorker` does not exist.

- [ ] **Step 3: Implement state changes, connection, subscriptions and recovery**

```ts
this.socket = io(origin, { path: "/ws/matching", auth: { token }, transports: ["websocket", "polling"], extraHeaders: { Cookie: cookie } });
this.socket.on("message:new", (event) => void this.accept(event));
this.socket.on("connect", () => void this.joinAndRecover());
this.socket.on("disconnect", () => this.setState("reconnecting"));
```

- [ ] **Step 4: Route an accepted exact check-in reply through the same ACK-gated send method**

```ts
const reply = await this.checkins.handle(inbound);
if (reply) await this.sendToChatroom(reply.chatroomId, reply.text);
```

- [ ] **Step 5: Run focused tests and typecheck**

Run: `npm test -- dzmm-worker.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/main/dzmm-worker.ts desktop/src/main/logs.ts desktop/tests/dzmm-worker.test.ts
git commit -m "feat: add realtime DZMM multi-group worker"
```

## Task 8: Expose only the approved IPC surface

**Files:**
- Create: `desktop/src/main/ipc.ts`
- Modify: `desktop/src/main/index.ts`
- Modify: `desktop/src/preload/index.ts`
- Create: `desktop/tests/ipc.test.ts`

**Interfaces:**
- Produces `window.dzmm` methods: `getSnapshot`, `startWorker`, `stopWorker`, `openLogin`, `listGroups`, `saveGroup`, `removeGroup`, `setGroupEnabled`, `getCheckinSettings`, `saveCheckinSettings`, `listMessages`, `sendMessage`, `listLogs`, `exportLogs`, `getSettings`, `saveSettings`, `clearLoginSession`, and event listeners `onSnapshot`, `onMessage`, `onLog`.

- [ ] **Step 1: Write a failing IPC allowlist test**

```ts
it("registers management operations but exposes no token, cookie, database path, or raw session method", () => {
  registerIpc(dependencies);
  expect(handledChannels).toEqual(expect.arrayContaining(["groups:list", "worker:start", "messages:send"]));
  expect(handledChannels).not.toEqual(expect.arrayContaining(["session:token", "session:cookie", "database:path"]));
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- ipc.test.ts`

Expected: FAIL because `registerIpc` does not exist.

- [ ] **Step 3: Implement IPC handlers, sender validation, and the typed preload bridge**

```ts
contextBridge.exposeInMainWorld("dzmm", {
  getSnapshot: () => ipcRenderer.invoke("worker:snapshot"),
  startWorker: () => ipcRenderer.invoke("worker:start"),
  sendMessage: (groupId: string, text: string) => ipcRenderer.invoke("messages:send", { groupId, text }),
  onMessage: (listener) => subscribe("messages:new", listener),
});
```

- [ ] **Step 4: Run focused tests and typecheck**

Run: `npm test -- ipc.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/main/ipc.ts desktop/src/main/index.ts desktop/src/preload/index.ts desktop/tests/ipc.test.ts
git commit -m "feat: expose safe desktop IPC controls"
```

## Task 9: Build the compact management UI

**Files:**
- Create: `desktop/src/renderer/App.tsx`
- Create: `desktop/src/renderer/api.ts`
- Create: `desktop/src/renderer/styles.css`
- Create: `desktop/src/renderer/components/StatusPill.tsx`
- Create: `desktop/src/renderer/components/EmptyState.tsx`
- Create: `desktop/src/renderer/pages/DashboardPage.tsx`
- Create: `desktop/src/renderer/pages/MessagesPage.tsx`
- Create: `desktop/src/renderer/pages/GroupsPage.tsx`
- Create: `desktop/src/renderer/pages/CheckinsPage.tsx`
- Create: `desktop/src/renderer/pages/LogsPage.tsx`
- Create: `desktop/src/renderer/pages/SettingsPage.tsx`
- Create: `desktop/tests/renderer/App.test.tsx`
- Create: `desktop/tests/renderer/GroupsPage.test.tsx`
- Create: `desktop/tests/renderer/CheckinsPage.test.tsx`

**Interfaces:**
- Consumes: the `window.dzmm` preload API from Task 8.
- Produces: all approved views and no direct Electron/Node imports in renderer files.

- [ ] **Step 1: Write failing renderer tests for critical user flows**

```tsx
it("shows authentication and worker state and starts the worker", async () => {
  render(<App api={fakeApi({ snapshot: { login: "auth_required", worker: "stopped" } })} />);
  expect(screen.getByText("需要登录")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "启动 Worker" }));
  expect(api.startWorker).toHaveBeenCalled();
});

it("rejects a group URL without c before saving", async () => {
  render(<GroupsPage api={api} />);
  await userEvent.type(screen.getByLabelText("聊天链接"), "https://www.aikda.com/chat");
  await userEvent.click(screen.getByRole("button", { name: "添加群聊" }));
  expect(screen.getByText("聊天链接必须包含 c 参数")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run renderer tests to verify they fail**

Run: `npm test -- App.test.tsx GroupsPage.test.tsx CheckinsPage.test.tsx`

Expected: FAIL because page components do not exist.

- [ ] **Step 3: Implement navigation, dashboard, message stream, groups, settings, check-ins and logs**

Use a fixed 220px sidebar; header pills for login and worker status; compact cards and tables; keyboard-accessible buttons, labels, error messages, and empty states. The message page must use a group selector and call `api.sendMessage`; it must not create an alternate sender.

- [ ] **Step 4: Implement log export and destructive login-session clearing confirmation**

```tsx
const clearSession = async () => {
  if (window.confirm("清除后需要重新登录 DZMM，是否继续？")) await api.clearLoginSession();
};
```

- [ ] **Step 5: Run all renderer tests and typecheck**

Run: `npm test -- renderer && npm run typecheck`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/renderer desktop/tests/renderer
git commit -m "feat: add DZMM desktop management UI"
```

## Task 10: Verify, package, and run the DZMM test-group smoke test

**Files:**
- Modify: `desktop/package.json`
- Create: `desktop/README.md`

**Interfaces:**
- Produces documented macOS/Windows development, test, packaging and non-secret test-group validation commands.

- [ ] **Step 1: Run unit, component and type verification**

Run: `npm test && npm run typecheck && npm run build`

Expected: every command exits 0.

- [ ] **Step 2: Build the native package on the host platform**

Run on macOS: `npm run dist -- --mac`

Run on Windows: `npm run dist -- --win`

Expected: a `.dmg` on macOS or an NSIS `.exe` on Windows under `desktop/dist/`.

- [ ] **Step 3: Smoke-test with a non-production DZMM group**

Run these manual checks without exposing credentials:

```text
1. Open Login, sign in, then restart app and confirm public account/status remains Ready.
2. Add and enable two test group links; start Worker; confirm each receives a real-time text event.
3. Disconnect network, send one text in a test group, reconnect, and confirm recovery shows it once.
4. Send a manual text and confirm a success ACK; induce a rejected send and confirm it remains failed.
5. Enable check-in; send 签到 twice from one account and confirm success then duplicate replies; verify next-day fixture/date behavior.
6. Confirm message UI, log export and SQLite contain no Cookie, access token or password.
```

- [ ] **Step 4: Commit documented verification**

```bash
git add desktop/package.json desktop/README.md
git commit -m "docs: add desktop packaging and smoke test guide"
```

## Plan Self-Review

- **Spec coverage:** Tasks 1–4 implement Electron, persistent session, local state and groups; Tasks 5–7 implement verified profiles, check-ins, Socket.IO, recovery and ACK sends; Tasks 8–9 implement safe IPC and every approved page; Task 10 verifies packaging and test-group behavior.
- **Placeholder scan:** No TBD/TODO or unspecified implementation steps. The one platform-dependent profile request is expressly gated on capturing the actual non-secret request/response field contract before writing it.
- **Type consistency:** `DatabaseStore`, `DzmmSession`, `DzmmUserDirectory`, `CheckinService`, `DzmmWorker`, and typed preload API are introduced before their dependents.
