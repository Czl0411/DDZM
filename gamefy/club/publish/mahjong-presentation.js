export function tablePosition(seat, viewer = 0) {
  return ["self", "right", "top", "left"][(seat - (viewer ?? 0) + 4) % 4];
}

export function waitStatus(item) {
  const ron = item.ron_now || !item.ron_reason, tsumo = !item.tsumo_reason;
  const furiten = ["discard", "temporary", "riichi_pass"].includes(item.ron_reason);
  return {
    label: item.ron_now ? "可荣和" : ron ? "可胡" : furiten ? "振听" : tsumo ? "仅自摸" : "无役",
    tone: ron ? "ready" : "restricted",
    ron: ron ? "可荣和" : furiten ? "振听，不能荣和" : item.ron_reason === "no_yaku" ? "荣和无役" : "不能荣和",
    tsumo: tsumo ? "可自摸" : item.tsumo_reason === "no_yaku" ? "自摸无役" : "不能自摸",
  };
}

export function handHintStatus(value) {
  const entries = value?.waits || [];
  if (entries.some(item => item.ron_now)) return {label:"可荣和", detail:"本次可胡，请点荣和", tone:"ready"};
  const furiten = {discard:"弃牌振听", temporary:"暂时振听", riichi_pass:"立直振听"}[value?.furiten];
  const tsumo = entries.some(item => !item.tsumo_reason);
  if (furiten) return {label:furiten, detail:tsumo ? "不能荣和；自摸需有役" : "不能荣和；普通自摸也无役", tone:"restricted"};
  const blocked = entries.filter(item => item.ron_reason);
  if (!blocked.length) return {label:"听牌", detail:"有役，可荣和或自摸", tone:"ready"};
  if (blocked.length < entries.length) return {label:"部分受限", detail:"各张待牌胡牌条件不同", tone:"restricted"};
  return tsumo ? {label:"仅可自摸", detail:"荣和无役；自摸需看对应牌", tone:"restricted"} : {label:"无役", detail:"缺少役种，通常不能胡", tone:"restricted"};
}

export function sameMahjongHand(before, next) {
  return !!before?.game && !!next?.game && before.id === next.id &&
    ["round_wind", "hand_number", "honba"].every(key => before.game[key] === next.game[key]);
}

export function mahjongChanges(before, next) {
  if (!sameMahjongHand(before, next) || next.version !== before.version + 1) return [];
  const changes = [];
  next.game.discards.forEach((river, seat) => {
    if (river.length === before.game.discards[seat].length + 1) changes.push({kind: "discard", seat, ...river.at(-1)});
  });
  next.game.melds.forEach((melds, seat) => {
    melds.forEach((meld, index) => {
      const old = before.game.melds[seat][index];
      if (!old || old.kind !== meld.kind) changes.push({kind: "meld", seat, meld: meld.kind, index});
    });
  });
  if (next.seat !== null && next.seat === before.seat) {
    const added = next.game.hand.filter(id => !before.game.hand.includes(id));
    if (added.length === 1) changes.push({kind: "draw", seat: next.seat, tile: added[0]});
  }
  next.game.hand_counts?.forEach((count, seat) => {
    if (seat !== next.seat && count === before.game.hand_counts?.[seat] + 1) changes.push({kind: "draw", seat});
  });
  return changes;
}
