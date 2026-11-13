const FALLBACK_STAKES = [5, 10, 20];

export async function loadEconomy(apiBase, game) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${apiBase.replace(/\/$/, "")}/api/club/economy-settings`, {cache: "no-store", signal: controller.signal});
    if (!response.ok) throw new Error("无法读取 Club 场次设置");
    const setting = (await response.json()).find(item => item.game === game);
    if (!setting || !Array.isArray(setting.coin_stakes) || !setting.coin_stakes.length) {
      throw new Error("Club 场次设置不完整");
    }
    return setting;
  } catch {
    return {game, coin_stakes: FALLBACK_STAKES, rake_percent: 20};
  } finally {
    clearTimeout(timer);
  }
}

export function renderCreateStrip(container, setting, documentRef = document) {
  const casual = documentRef.createElement("button");
  casual.type = "button";
  casual.dataset.createRoom = "casual";
  casual.dataset.stake = "0";
  casual.textContent = "休闲局";
  const coinButtons = setting.coin_stakes.map(stake => {
    const button = documentRef.createElement("button");
    button.type = "button";
    button.dataset.createRoom = "coin";
    button.dataset.stake = String(stake);
    button.textContent = `${stake} 币场`;
    return button;
  });
  container.replaceChildren(casual, ...coinButtons);
}

export function renderStakeChoices(container, stakes, documentRef = document) {
  const preferred = stakes.includes(10) ? 10 : stakes[0];
  container.replaceChildren(...stakes.map(stake => {
    const label = documentRef.createElement("label");
    const input = documentRef.createElement("input");
    input.type = "radio";
    input.name = "stake";
    input.value = String(stake);
    input.checked = stake === preferred;
    const copy = documentRef.createElement("span");
    copy.textContent = `${stake} 币`;
    label.append(input, copy);
    return label;
  }));
}
