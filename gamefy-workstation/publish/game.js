"use strict";

(() => {
  const config = window.workstationConfig;
  const banner = document.getElementById("connection-state");
  const previewControls = document.getElementById("preview-controls");
  const previewSelect = document.getElementById("preview-equipment");
  const demoItems = [
    [1, "monitor-main", "主显示器", 2], [2, "monitor-left", "左侧竖屏", 1],
    [3, "monitor-right", "右侧竖屏", 1], [4, "screen-light", "屏幕挂灯", 1],
    [5, "keyboard", "机械键盘", 1], [6, "mouse", "桌面鼠标", 1],
    [7, "desk-lamp", "暖光台灯", 1], [8, "handheld", "桌面掌机", 1],
    [9, "pc", "侧透主机", 3], [10, "chair", "人体工学椅", 2],
  ];

  function preview() {
    const mode = previewSelect.value;
    const selected = mode === "all" ? demoItems
      : mode === "starter" ? demoItems.filter(item => [1, 5, 10].includes(item[0])) : [];
    const equipped = selected.map(([number, asset_key, name, daily_income]) => ({
      number, asset_key, name, daily_income,
    }));
    return {
      display_name: "预览", employee_number: "#0001", equipped,
      daily_income: equipped.reduce((total, item) => total + item.daily_income, 0),
      currency_name: "摸鱼币", income_settlement_enabled: false,
    };
  }

  function requestError(error) {
    return error.name === "TimeoutError"
      ? new Error("加载超时，请检查网络后重试；完整工位原图较大，请耐心等待。") : error;
  }

  async function workstationRequest(path, options = {}, timeoutMs = 20000) {
    let endpoint;
    try {
      endpoint = new URL(config.apiBaseUrl);
      if (endpoint.protocol !== "https:" || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
        throw new Error();
      }
    } catch {
      throw new Error("工位服务地址配置有误，请联系管理员。");
    }
    if (typeof window.dzmm?.user?.info !== "function") {
      throw new Error("请从 DZMM 平台打开工位游戏，以读取你的真实装备。");
    }
    let identity;
    let identityTimer;
    try {
      identity = await Promise.race([
        window.dzmm.user.info(),
        new Promise((resolve, reject) => {
          identityTimer = setTimeout(() => reject(new Error("登录信息读取超时，请刷新游戏重试。")), 15000);
        }),
      ]);
    } catch {
      throw new Error("暂时无法读取登录信息，请刷新游戏重试。");
    } finally {
      clearTimeout(identityTimer);
    }
    if (!identity?.token) {
      throw new Error("请先登录 DZMM，再打开工位游戏。");
    }
    const response = await fetch(`${endpoint.href.replace(/\/$/, "")}/api/gamefy/workstation${path}`, {
      ...options,
      headers: {Authorization: `Bearer ${identity.token}`, ...(options.body ? {"Content-Type": "application/json"} : {})},
      credentials: "omit", cache: "no-store", signal: AbortSignal.timeout(timeoutMs),
    }).catch(error => { throw requestError(error); });
    if (!response.ok) {
      const messages = {
        401: "登录信息已失效，请刷新游戏重新登录。",
        403: "请先在目标群发送 /我的工位，再刷新本页（24小时内有效）。",
        404: "未找到员工档案或工位，请返回大厅刷新；尚未入职请回群里发送 /入职 名字。",
        409: "这次发送已选择其他群，请刷新后重试。",
        429: "发送过于频繁，请在一分钟后再试。",
        503: "工位服务暂时不可用，请稍后刷新重试。",
      };
      const error = new Error(messages[response.status] || "服务暂不可用，请稍后重试。");
      error.status = response.status;
      throw error;
    }
    return response.json().catch(error => { throw requestError(error); });
  }

  async function readRealWorkstation(number) {
    const workstation = await workstationRequest(number ? `/employees/${number}` : "");
    banner.textContent = "已连接真实工位 · 可浏览同事工位，群内操作后刷新查看";
    return workstation;
  }

  const previewMode = config.apiBaseUrl === "";
  banner.textContent = previewMode
    ? "素材预览 · 尚未连接真实工位，以下是演示装备和预计收入"
    : "工位大厅 · 浏览同事的布置，也可以进入我的工位";
  previewControls.hidden = !previewMode;
  document.getElementById("page-note").textContent = previewMode
    ? "本页为素材预览，切换装备不会购买、扣币或改变真实工位。"
    : "大厅展示员工工位；购买和装卸请使用群指令，发送到群里仅限自己的工位。";
  previewSelect.addEventListener("change", () => document.getElementById("refresh").click());
  window.workstationSource = Object.freeze({
    assetBase: "./assets/",
    load: previewMode ? async number => ({...preview(), is_owner: !number || number === 1,
      ...(number === 2 ? {display_name: "小小糯", employee_number: "#0002", equipped: [], daily_income: 0} : {})}) : readRealWorkstation,
    lobby: previewMode ? async ({query, page}) => {
      const items = [
        {number: 1, display_name: "预览", employee_number: "#0001", asset_keys: preview().equipped.map(item => item.asset_key),
          equipped_count: preview().equipped.length, daily_income: preview().daily_income},
        {number: 2, display_name: "小小糯", employee_number: "#0002", asset_keys: [], equipped_count: 0, daily_income: 0},
      ].filter(item => !query || item.display_name.includes(query) || item.employee_number.includes(query));
      return {items: page === 1 ? items : [], total: items.length, page, page_size: 24, my_number: 1};
    } : ({query, page}) => workstationRequest(`/lobby?${new URLSearchParams({query, page})}`),
    downloadRestricted: window.parent !== window,
    ...(!previewMode ? {
      share: payload => workstationRequest("/share", {method: "POST", body: JSON.stringify(payload)}),
      shareStatus: requestId => workstationRequest(`/shares/${encodeURIComponent(requestId)}`),
      image: number => workstationRequest(`/employees/${number}/image`, {}, 90000),
    } : {}),
    setLoading: loading => { previewSelect.disabled = loading; },
  });
})();
