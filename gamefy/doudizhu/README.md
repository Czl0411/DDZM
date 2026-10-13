# 群聊斗地主 H5

独立游戏，不覆盖象棋。发布前在 `publish/config.js` 填公开 HTTPS 后端，平台创建独立游戏卡后才生成包含真实卡 ID 的 `dzmm.json`。未配置时显示提示，不连接示例服务器。

静态文件使用 ASCII 名称、相对路径和平台注入的 `window.dzmm`。无前端密钥，不使用浏览器本地存储；最近房间保存在平台 KV。

身份为用户明确选择的 UID 信任模式，不防止伪造 UID 冒充；不涉及摸鱼币。手牌按请求 UID 投影，观众没有私有牌。

测试：`node --test gamefy/doudizhu/tests/*.test.mjs` 与 `.venv/bin/python -m pytest gamefy/doudizhu/tests/test_doudizhu_sandbox.py -q`。浏览器测试使用本机 Chrome 的实际 iframe 沙箱，不依赖表单提交。
