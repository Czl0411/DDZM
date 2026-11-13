const labels = {fold: "弃牌", check: "过牌", call: "跟注", raise: "加注", all_in: "全下", look: "看牌", compare: "比牌", hit: "要牌", stand: "停牌", reveal: "亮牌"};

export function actionText(event, name = () => "玩家") {
  let text = labels[event.action] || "行动";
  if (event.action === "raise" && event.amount != null) text += `至 ${event.amount}`;
  else if (event.paid > 0) text += ` ${event.paid}`;
  if (event.target) text += ` · ${name(event.target)}`;
  return `${event.automatic ? "超时自动" : ""}${text}`;
}

export function seatStatus(state, id) {
  if (state.folded?.includes(id)) return "已弃牌";
  if (state.busted?.includes(id)) return "已爆牌";
  if (state.all_in?.includes(id)) return "已全下";
  if (state.stood?.includes(id)) return "已停牌";
  const latest = state.action_history?.findLast(event => event.player === id);
  return latest ? actionText(latest) : state.seen?.includes(id) ? "已看牌" : state.turn === id ? "正在行动" : "等待行动";
}

export function newActions(previous, next) {
  // Initial entry, a new hand or a gap restores state without replaying old moves.
  if (!previous || previous.id !== next.id || previous.hand_number !== next.hand_number) return [];
  const last = previous.state?.action_history?.at(-1)?.sequence || 0;
  const events = (next.state?.action_history || []).filter(event => event.sequence > last);
  return events.length === 1 && events[0].sequence === last + 1 ? events : [];
}
