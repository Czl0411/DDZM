export function battleStatus(state,{reconnecting=false,animating=false,submitting=false}={}){
 if(reconnecting)return '连接中断，正在重连…';
 if(animating)return '正在结算效果…';
 if(state.phase==='finished')return state.winner===null?'对局平局':state.spectator?(state.players[state.winner].name||'玩家')+' 获胜':state.winner===state.seat?'你赢得了对局':'对手赢得了对局';
 if(state.phase==='round_result')return '本局结束，等待下一局';
 if(['choose_first','mulligan'].includes(state.phase))return '双方正在准备';
 if(state.spectator&&state.pending)return (state.players[state.pending.actor]?.name||'玩家')+' 正在选择效果目标';
 if(state.pending)return state.pending.actor===state.seat&&!state.spectator?'请选择效果目标':'对手正在选择效果目标';
 if(submitting)return '正在提交行动…';
 if(state.spectator)return (state.players[state.turn]?.name||'玩家')+' 正在行动';
 if(state.players[state.seat].passed)return '你已停手，等待对手结束本局';
 return state.turn===state.seat?'轮到你行动':'等待对手出牌';
}

export function groupMatchActions(log,frames=[]){
 const effects=new Map(frames.map(f=>[f.log_id,f.effects||[]])),actions=[];
 for(const event of log){
  const previous=actions.at(-1),step={...event,effects:event.effects||effects.get(event.id)||[]};
  if(event.kind==='choose'&&previous&&previous.round===event.round&&['play','leader'].includes(previous.kind))previous.steps.push(step);
  else actions.push({...event,steps:[step]});
 }
 return actions;
}
