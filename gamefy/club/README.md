# 摸鱼 Club

统一游戏大厅，首个内置游戏为四人经典立直麻将；象棋、斗地主和你画我猜从大厅跳转到现有游戏卡。

## 首版范围

- 四人东风战、半庄战
- 休闲房和 100 摸鱼币房
- 摸鱼币房固定奖池：第 1～4 名分别获得 200、120、60、20 币
- 15 秒基础出牌时间，整场每人 60 秒时间银行
- 吃、碰、明杠、暗杠、加杠、立直、自摸、荣和、流局和断线自动摸切
- 玩家和观众均可使用牌桌聊天
- 页面固定为一个手机视口，牌桌和聊天独立滚动

## 本地检查

```bash
node --test gamefy/club/tests/client.test.mjs
PYTHONPATH=. .venv/bin/pytest -q gamefy/club/tests/test_club_sandbox.py
```

## 发布前配置

创建独立 Gamefy 草稿后，把游戏 ID 写入 `dzmm.json`，上传 `publish/`，并在服务器环境中配置：

```text
DZMM_CLUB_GAME_ID=<游戏 ID>
DZMM_CLUB_GAME_URL=https://www.aikda.com/chat?card=<游戏 ID>
DZMM_CLUB_PUBLIC_API_URL=https://49.234.20.159
DZMM_CLUB_CHATROOM_ID=4fc4a2fd-465a-4436-9884-dbb5e60c6af2
```
