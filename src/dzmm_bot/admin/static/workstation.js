"use strict";

const layerOrder = {
  "monitor-main": 20, "monitor-left": 10, "monitor-right": 10,
  "screen-light": 30, "keyboard": 40, "mouse": 40, "desk-lamp": 40,
  "handheld": 40, "pc": 40, "chair": 60,
};
const refreshButton = document.getElementById("refresh");
const statusText = document.getElementById("status");
const content = document.getElementById("workstation-content");
const token = window.location.pathname.split("/").pop();
const source = window.workstationSource;
const layoutToggle = document.getElementById("layout-toggle");
const shareButton = document.getElementById("share-image");
const shareGroup = document.getElementById("share-group");
const shareStatus = document.getElementById("share-status");
let sharing = false;
let pendingShare = null;
const lobby = document.getElementById("workstation-lobby");
const lobbyButton = document.getElementById("lobby-button");
const myButton = document.getElementById("my-workstation");
const downloadButton = document.getElementById("download-image");
const downloadDialog = document.getElementById("download-dialog");
let selectedNumber = null;
let currentWorkstation = null;
let view = source?.lobby ? "lobby" : "detail";
let loadVersion = 0;
let lobbyPage = 1;
let lobbyQuery = "";
let downloadVersion = 0;

function beginLoad(nextView) {
  view = nextView;
  currentWorkstation = null;
  downloadDialog?.close();
  downloadVersion += 1;
  content.hidden = true;
  if (lobby) lobby.hidden = true;
  layoutToggle.hidden = view === "lobby";
  if (lobbyButton) lobbyButton.hidden = view === "lobby";
  const sharePanel = document.getElementById("share-panel");
  if (sharePanel) sharePanel.hidden = true;
  refreshButton.disabled = true;
  source?.setLoading?.(true);
  statusText.hidden = false;
  statusText.classList.remove("is-error");
  statusText.textContent = view === "lobby" ? "正在加载工位大厅…" : "正在加载工位…";
  return ++loadVersion;
}

function finishLoad(version) {
  if (version !== loadVersion) return;
  refreshButton.disabled = sharing;
  source?.setLoading?.(false);
}

function showLoadError(error, version) {
  if (version !== loadVersion) return;
  statusText.hidden = false;
  statusText.classList.add("is-error");
  statusText.textContent = error.name === "TimeoutError"
    ? "加载超时，请检查网络后点击刷新重试。"
    : error instanceof TypeError ? "网络连接失败，请检查网络后点击刷新重试。" : error.message;
}

async function loadLobby() {
  const version = beginLoad("lobby");
  document.getElementById("workstation-title").textContent = "工位大厅";
  document.getElementById("employee-number").hidden = true;
  document.title = "工位大厅 · 摸鱼公司";
  try {
    const result = await source.lobby({query: lobbyQuery, page: lobbyPage});
    if (version !== loadVersion) return;
    const cards = result.items.map(item => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "workstation-card";
      card.setAttribute("aria-label", `查看${item.display_name}的工位 ${item.employee_number}`);
      const thumbnail = document.createElement("div");
      thumbnail.className = "scene lobby-thumbnail";
      const keys = [...item.asset_keys].filter(key => Object.hasOwn(layerOrder, key))
        .sort((first, second) => layerOrder[first] - layerOrder[second]);
      for (const filename of ["core-base.png", ...keys.map(key => `${key}-layer.png`)]) {
        const image = document.createElement("img");
        image.alt = "";
        image.loading = "lazy";
        image.src = `${source.assetBase}${filename}`;
        if (filename !== "core-base.png") image.className = "equipment-layer";
        thumbnail.append(image);
      }
      const name = document.createElement("h2");
      name.textContent = item.display_name;
      const number = document.createElement("p");
      number.className = "card-number";
      number.textContent = `${item.employee_number}${item.number === result.my_number ? " · 我的工位" : ""}`;
      const summary = document.createElement("p");
      summary.className = "muted";
      summary.textContent = `已装备 ${item.equipped_count} 件 · 查看工位 →`;
      const details = document.createElement("div");
      details.className = "card-details";
      details.append(name, number, summary);
      card.append(thumbnail, details);
      card.addEventListener("click", () => {
        selectedNumber = item.number === result.my_number ? null : item.number;
        loadWorkstation();
      });
      return card;
    });
    document.getElementById("lobby-list").replaceChildren(...cards);
    document.getElementById("lobby-summary").textContent = result.total
      ? `共 ${result.total} 位员工 · 点击工位卡片前去看看`
      : "没有找到匹配的员工，试试其他名字或工号。";
    const pages = Math.max(1, Math.ceil(result.total / result.page_size));
    document.getElementById("lobby-page").textContent = `第 ${result.page} 页 / 共 ${pages} 页`;
    document.getElementById("previous-page").disabled = result.page <= 1;
    document.getElementById("next-page").disabled = result.page >= pages;
    lobby.hidden = false;
    statusText.hidden = true;
  } catch (error) {
    showLoadError(error, version);
  } finally {
    finishLoad(version);
  }
}

layoutToggle.addEventListener("click", () => {
  const tiled = document.querySelector("main").classList.toggle("is-tiled");
  layoutToggle.setAttribute("aria-pressed", String(tiled));
  layoutToggle.textContent = tiled ? "侧栏布局" : "平铺布局";
});

function loadImage(filename, className = "") {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.alt = "";
    image.className = className;
    const timer = setTimeout(() => reject(new Error("工位图片加载超时，请点击刷新重试。")), 20000);
    image.onload = () => { clearTimeout(timer); resolve(image); };
    image.onerror = () => { clearTimeout(timer); reject(new Error("工位图片加载失败，请点击刷新重试。")); };
    image.src = `${source ? source.assetBase : "../static/workstation/"}${filename}`;
  });
}

async function loadWorkstation() {
  const version = beginLoad("detail");
  if (shareButton) shareButton.disabled = true;
  try {
    const response = source ? null : await fetch(`../api/workstations/${encodeURIComponent(token)}`, {
      cache: "no-store", credentials: "omit", signal: AbortSignal.timeout(20000),
    });
    if (response && !response.ok) {
      throw new Error(response.status === 404
        ? "工位链接无效或已失效，请在群里重新发送 /我的工位。"
        : "工位暂时无法加载，请稍后刷新重试。");
    }
    const workstation = source ? await source.load(selectedNumber) : await response.json();
    if (version !== loadVersion) return;
    const equipped = workstation.equipped;
    const visible = equipped.filter(item => Object.hasOwn(layerOrder, item.asset_key))
      .sort((first, second) => layerOrder[first.asset_key] - layerOrder[second.asset_key]);
    const images = await Promise.all([
      loadImage("core-base.png"),
      ...visible.map(item => loadImage(`${item.asset_key}-layer.png`, "equipment-layer")),
    ]);
    if (version !== loadVersion) return;
    currentWorkstation = workstation;
    document.getElementById("scene").replaceChildren(...images);
    document.getElementById("scene").setAttribute("aria-label",
      `${workstation.display_name}的工位，${equipped.length ? equipped.map(item => item.name).join("、") : "暂无装备"}`);
    document.getElementById("workstation-title").textContent = `${workstation.display_name}的工位`;
    const employeeNumber = document.getElementById("employee-number");
    employeeNumber.textContent = workstation.employee_number ? `工号：${workstation.employee_number}` : "";
    employeeNumber.hidden = !workstation.employee_number;
    if (shareButton && typeof source?.share === "function" && workstation.is_owner !== false && selectedNumber === null) {
      document.getElementById("share-panel").hidden = false;
      const selectedGroup = shareGroup.value;
      const options = (workstation.share_groups || []).map(group => {
        const option = document.createElement("option");
        option.value = group.id;
        option.textContent = group.name || "未命名群聊";
        return option;
      });
      shareGroup.replaceChildren(...options);
      if (options.some(option => option.value === selectedGroup)) shareGroup.value = selectedGroup;
      shareGroup.disabled = sharing || !options.length;
      shareButton.disabled = sharing || !options.length;
      if (!sharing) shareStatus.textContent = options.length
        ? "将当前实际装备合成为图片，每分钟可发送一次。"
        : "请先在目标群发送 /我的工位，再刷新本页（24小时内有效）。";
    }
    document.title = `${workstation.display_name}的工位 · 摸鱼公司`;
    document.getElementById("equipped-count").textContent = `${equipped.length} 件`;
    const unit = document.createElement("span");
    unit.className = "unit";
    unit.textContent = workstation.currency_name;
    document.getElementById("income").replaceChildren(String(workstation.daily_income), unit);
    const rows = equipped.map(item => {
      const row = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = `#${item.number} ${item.name}`;
      const income = document.createElement("span");
      income.textContent = `+${item.daily_income}/日`;
      row.append(label, income);
      return row;
    });
    document.getElementById("equipment-list").replaceChildren(...rows);
    document.getElementById("empty").hidden = equipped.length !== 0;
    document.getElementById("empty").textContent = workstation.is_owner === false
      ? `${workstation.display_name}还没有装备物品。`
      : "还是一个简陋工位。回群里发送 /装备商城，挑选第一件装备吧。";
    content.hidden = false;
    statusText.hidden = visible.length === equipped.length;
    statusText.textContent = "部分装备暂未提供图片，已在装备清单中列出。";
  } catch (error) {
    showLoadError(error, version);
  } finally {
    finishLoad(version);
  }
}

refreshButton.addEventListener("click", () => view === "lobby" ? loadLobby() : loadWorkstation());
lobbyButton?.addEventListener("click", loadLobby);
myButton?.addEventListener("click", () => { selectedNumber = null; loadWorkstation(); });
document.getElementById("lobby-search")?.addEventListener("submit", event => {
  event.preventDefault();
  lobbyQuery = document.getElementById("lobby-query").value.trim();
  lobbyPage = 1;
  loadLobby();
});
document.getElementById("clear-search")?.addEventListener("click", () => {
  document.getElementById("lobby-query").value = "";
  lobbyQuery = "";
  lobbyPage = 1;
  loadLobby();
});
document.getElementById("previous-page")?.addEventListener("click", () => { lobbyPage -= 1; loadLobby(); });
document.getElementById("next-page")?.addEventListener("click", () => { lobbyPage += 1; loadLobby(); });

downloadButton?.addEventListener("click", async () => {
  if (!currentWorkstation) return;
  const version = ++downloadVersion;
  const workstation = currentWorkstation;
  const downloadStatus = document.getElementById("download-status");
  const preview = document.getElementById("download-preview");
  const link = document.getElementById("download-file");
  preview.hidden = true;
  preview.removeAttribute("src");
  link.hidden = true;
  link.removeAttribute("href");
  downloadStatus.textContent = "正在合成完整工位图片…";
  downloadDialog.showModal();
  try {
    let dataUrl;
    if (source?.image) {
      const result = await source.image(Number(workstation.employee_number.replace("#", "")));
      dataUrl = result.data_url;
    } else {
      const images = [...document.querySelectorAll("#scene img")];
      const canvas = document.createElement("canvas");
      canvas.width = images[0].naturalWidth;
      canvas.height = images[0].naturalHeight;
      const context = canvas.getContext("2d");
      for (const image of images) context.drawImage(image, 0, 0, canvas.width, canvas.height);
      dataUrl = canvas.toDataURL("image/png");
    }
    if (version !== downloadVersion || !downloadDialog.open) return;
    if (!dataUrl?.startsWith("data:image/png;base64,")) throw new Error("工位图片生成失败，请稍后重试。");
    preview.src = dataUrl;
    preview.hidden = false;
    link.href = dataUrl;
    link.download = `${workstation.employee_number}-${workstation.display_name}-工位.png`.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_");
    link.hidden = Boolean(source?.downloadRestricted);
    downloadStatus.textContent = source?.downloadRestricted
      ? "完整原图已生成。平台限制直接下载，请右键图片选择“图片另存为”；手机可长按图片保存。"
      : "完整原图已生成。点击下方下载 PNG 图片，也可以右键或长按图片保存。";
  } catch (error) {
    if (version === downloadVersion) downloadStatus.textContent = error.message || "生成失败，请关闭后重试。";
  }
});
document.getElementById("close-download")?.addEventListener("click", () => downloadDialog.close());
shareButton?.addEventListener("click", async () => {
  if (sharing || !shareGroup.value || !currentWorkstation || selectedNumber !== null || currentWorkstation.is_owner === false) return;
  sharing = true;
  shareButton.disabled = true;
  shareGroup.disabled = true;
  refreshButton.disabled = true;
  pendingShare ||= {group_id: shareGroup.value, request_id: crypto.randomUUID()};
  shareStatus.textContent = "正在提交工位图片…";
  try {
    const result = await source.share(pendingShare);
    if (result.status === "sent") pendingShare = null;
    shareStatus.textContent = result.status === "sent" ? "工位图片已发送到群里。" : "已加入发送队列，正在合成并发送…";
    for (let attempt = 0; attempt < 20 && result.status !== "sent"; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const state = await source.shareStatus(result.request_id);
      if (state.status === "sent") {
        pendingShare = null;
        shareStatus.textContent = "工位图片已发送到群里。";
        break;
      }
      if (state.status === "failed") {
        pendingShare = null;
        throw new Error("图片发送失败，请稍后重试。");
      }
      if (attempt === 19) shareStatus.textContent = "图片仍在排队，请稍后到所选群查看。";
    }
  } catch (error) {
    if (error.status && error.status < 500) pendingShare = null;
    shareStatus.textContent = error.message || "发送状态暂无法确认，请重试；同一次请求不会重复发送。";
  } finally {
    sharing = false;
    shareButton.disabled = !shareGroup.options.length;
    shareGroup.disabled = !shareGroup.options.length;
    refreshButton.disabled = false;
  }
});
shareGroup?.addEventListener("change", () => { pendingShare = null; });
if (view === "lobby") loadLobby();
else loadWorkstation();
