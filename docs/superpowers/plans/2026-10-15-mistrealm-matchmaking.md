# Mistrealm Quick Match Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; execute in the existing isolated worktree.

**Goal:** 首页新增可取消的无段位快速匹配，配对后复用现有准备房间。
**Architecture:** 独立玩家记录保存匹配票据、排队时间及20秒租期。每2秒心跳；事务锁当前玩家并按排队时间选取其他未过期玩家，候选使用 SKIP LOCKED，配对及两席入座原子提交。不会搜索或加入自定义房间。
**Tech Stack:** 现有 SQLAlchemy / FastAPI / 原生 JS。
**Spec:** 本次用户请求增加匹配；延续现有 UID 模式、双人固定预组和无员工关联。

## Constraints and interfaces
- POST /matchmaking：幂等进入或恢复队列；已有房间则返回该房间。
- POST /matchmaking/heartbeat {ticket: UUID}：只续租当前有效票据，不自动重新入队。
- POST /matchmaking/cancel {ticket: UUID}：取消有效票据；配对先完成时返回已配对房间。
- 返回 status=idle/waiting/matched；waiting 含 ticket、queued_at_ms、expires_at_ms；matched 含 room 快照。
- 关闭页面停止心跳；超过20秒不再作为候选。刷新从 players/me 恢复尚未过期的队列。
- 创建/加入自定义房间在同一个玩家锁下清除排队状态。取消及心跳不影响新票据。
- 不新增积分、段位、机器人对手或自动开局。

## Tasks
- [x] Backend: tests first for pairing, no self-pair, FIFO, cancel/expiry/stale ticket, private-room isolation, active-room restoration; schema/migration112 and transactional methods/API.
- [x] Client: start/heartbeat/cancel wrappers, themed waiting UI, cancel, bounded polling, refresh recovery; generation guard ignores late responses.
- [x] Verify: PostgreSQL concurrent pairing/cancel/manual-room races and migration round-trip; real browser two-client match and original room flow.
- [x] Update README/deploy notes; run affected regression, inspect mobile/desktop UI, commit only this feature.

## Review focus
No ghost opponent after expired lease; no duplicate seats under concurrent requests; late heartbeat cannot rejoin cancelled queue; stale cancellation cannot remove a newer queue; private room is never advertised to queue.
