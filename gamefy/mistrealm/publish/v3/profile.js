import {rankBadge} from './ranked.js';
import {groupMatchActions} from './battle-info.js';
import {stepText} from './effect-feedback.js';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const modes={ranked:'排位赛',casual:'休闲对战',story:'剧情模式'};
const date=value=>new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
export function matchOutcome(item){return item.winner===null?'平局':item.winner===item.seat?'胜利':'失利';}
export function matchScore(item){const wins=[0,0];for(const round of item.rounds)if(round.winner!==null)wins[round.winner]++;return `${wins[item.seat]} : ${wins[1-item.seat]}`;}
export function rankChange(item){const r=item.ranked?.result;if(!r)return '不计排位分';if(r.void)return '未计分';const d=r.deltas[item.seat];return `${d>0?'+':''}${d} 分`;}

export function setupProfile({client,uid,modal,cards,onSettings,onHonor,playTutorial,isBusy,deck,spectate,privateChat}){
 const $=id=>document.getElementById(id);
 let info=null,honors=null,history=null,detail=null,tab='overview',page=0,logPage=0,epoch=0,working=false,message='';
 const visible=()=>$('modal').open&&$('modal').dataset.view==='profile-center';
 const avatar=p=>`<span class="profile-avatar">${esc((p.name||'旅')[0])}${p.avatar?.startsWith('https://')?`<img src="${esc(p.avatar)}" alt="" referrerpolicy="no-referrer">`:''}</span>`;
 async function open(target=uid()){
  if(working)return;
  const request=++epoch;info=null;honors=null;history=null;detail=null;tab='overview';page=0;logPage=0;message='';
  modal('<section class="profile-loading"><p class="eyebrow">旅人档案</p><h2>正在读取个人资料…</h2></section>','profile-center');
  try{
   const value=await client.playerProfile(target);if(request!==epoch||!visible())return;info=value;
   if(info.self){honors=await client.rankedProfile();if(request!==epoch||!visible())return;info.honor=honors.honor;info.rank=honors.player;onSettings(info.settings);}
   draw();
  }catch(e){if(request===epoch&&visible())modal(`<section class="profile-loading"><h2>暂时无法读取</h2><p>${esc(e.message)}</p><button id="profile-retry">重试</button></section>`,'profile-center');if($('profile-retry'))$('profile-retry').onclick=()=>open(target);}
 }
 function pager(previous,next,current,total){return `<footer class="profile-pagination"><button id="${previous}" ${current?'':'disabled'}>上一页</button><span>${current+1} / ${Math.max(1,total)}</span><button id="${next}" ${current+1>=total?'disabled':''}>下一页</button></footer>`;}
 function overview(){
  const r=info.rank,h=info.honor,p=info.interaction;
  return `<div class="profile-overview"><div class="profile-rank">${rankBadge(r.tier.key,r.tier.name)}<div><small>${esc(info.season.name)}</small><h2>${esc(r.tier.name)} <em>${r.rating}</em></h2><p>赛季最高 ${r.peak} 分</p></div></div><div class="profile-stats"><span><b>${r.wins}</b>胜场</span><span><b>${r.losses}</b>负场</span><span><b>${r.draws}</b>平局</span></div><section class="profile-honor"><small>当前称号与徽章</small><p>${h?rankBadge(h.badge,h.title)+esc(h.title):'尚未佩戴赛季荣誉'}</p>${info.self?`<label for="profile-honor">佩戴荣誉</label><select id="profile-honor"><option value="">不佩戴</option>${honors.rewards.map(r=>`<option value="${r.season_id}" ${r.equipped?'selected':''}>${esc(r.title)}</option>`).join('')}</select><button id="profile-equip">保存佩戴</button>`:''}</section>${!info.self?`<div class="profile-public-actions">${p.friend==='friend'?'<button id="profile-dm">私聊</button>':p.friend==='received'?'<button id="profile-friend-accept">同意好友申请</button>':`<button id="profile-friend" ${p.friend==='sent'||p.friend_request_reason?'disabled':''}>${p.friend==='sent'?'申请已发送':p.friend_request_reason||'加好友'}</button>`}<button id="profile-challenge" ${p.challenge_reason||isBusy()?'disabled':''}>${esc(p.challenge_reason||'发起挑战')}</button>${p.spectate_room_id?`<button id="profile-watch" ${isBusy()?'disabled':''}>观战好友</button>`:''}</div><p class="profile-muted">${p.presence==='offline'?'离线':p.presence==='playing'?'对战中':p.presence==='online'?'在线':'忙碌中'} · 对局记录仅本人可见</p>`:''}</div>`;
 }
 function historyView(){
  if(!history)return '<p class="profile-empty">正在读取对局记录…</p>';
  return `<div class="profile-history"><p class="profile-muted">按完整一场结算 · 共 ${history.total} 场留存记录</p><div class="profile-match-list">${history.items.map(h=>{const other=h.players[1-h.seat],own=h.players[h.seat];return `<button class="profile-match" data-match="${h.match_id}"><strong data-result="${matchOutcome(h)}">${matchOutcome(h)}<small>${matchScore(h)}${h.conceded?' · 认输结束':''}</small></strong><span><b>对手 · ${esc(other.name)}</b><small>${esc(cards().factions[own.faction])} / ${esc(cards().factions[other.faction])}</small></span><span>${modes[h.mode]}<small>${date(h.finished_at)}</small></span><span class="profile-match-points">${rankChange(h)}<small>查看战报 ›</small></span></button>`;}).join('')||'<p class="profile-empty">还没有完整对局记录。<br>完成一场对局后，会保存在这里。</p>'}</div>${pager('profile-prev','profile-next',page,Math.ceil(history.total/5))}<small class="profile-muted">历史仅展示已留存的记录，未留存的旧对局无法补回。</small></div>`;
 }
 function detailView(){
  const h=detail,groups=groupMatchActions(h.actions),actions=groups.slice(logPage*6,logPage*6+6);
  return `<section class="profile-report"><header><button id="profile-history-back">‹ 返回记录</button><strong>${matchOutcome(h)} · ${modes[h.mode]} · ${rankChange(h)}</strong></header><div class="profile-rounds">${h.rounds.map(r=>`<span>第${r.round}局 <b>${r.scores[h.seat]} : ${r.scores[1-h.seat]}</b> ${r.winner===null?'平':r.winner===h.seat?'胜':'负'}</span>`).join('')||'<span>在小局结算前结束</span>'}</div><small class="profile-muted">比分按你 / 对手排列${h.conceded?' · 本场以认输结束':''}</small><div class="profile-log">${actions.map(a=>`<details><summary><small>第${a.round}局 · ${a.seat===null?'系统':a.seat===h.seat?'你':esc(h.players[a.seat]?.name||'对手')}</small><b>${esc(a.text)}</b></summary>${a.steps.map(step=>`<div>${(step.effects||[]).map(cue=>`<p>${esc(stepText(cue,id=>cards().cards[id]?.name||'卡牌',h.seat))}</p>`).join('')}${(step.details||[]).map(d=>`<p>${esc(d)}</p>`).join('')||(!(step.effects||[]).length?'<p>本次行动无额外结算。</p>':'')}</div>`).join('')}</details>`).join('')||'<p>此历史对局未留存操作记录。</p>'}</div>${pager('profile-log-prev','profile-log-next',logPage,Math.ceil(groups.length/6))}</section>`;
 }
 function preferences(){const s=info.settings;
  return `<form id="profile-settings" class="profile-settings">${tab==='privacy'?`<label><span><b>接受挑战</b><small>非好友双方每天限发起一次</small></span><select name="challenges"><option value="all" ${s.challenges==='all'?'selected':''}>所有玩家</option><option value="friends" ${s.challenges==='friends'?'selected':''}>仅好友</option><option value="off" ${s.challenges==='off'?'selected':''}>关闭</option></select></label>${toggle('friend_requests','接受好友申请','加好友仍需你同意',s.friend_requests)}${toggle('spectate','允许好友观战','关闭后，正在观战的好友也会退出',s.spectate)}`:`${toggle('animations','出牌动画','关闭后直接显示最新战场与结算',s.animations)}${toggle('sound','游戏音效','轻量出牌与回合提示音，默认关闭',s.sound)}<div class="profile-setting-note"><span><b>新手教学</b><small>可跳过、可随时重玩</small></span><button type="button" id="profile-tutorial" ${isBusy()?'disabled':''}>重玩教学</button></div><p class="profile-muted">停手二次确认始终保留，避免误操作。</p>`}<footer><span>设置跟随账号保存</span><button type="submit" ${working?'disabled':''}>${working?'保存中…':'保存设置'}</button></footer></form>`;
 }
 function toggle(name,label,description,value){return `<label><span><b>${label}</b><small>${description}</small></span><input type="checkbox" name="${name}" ${value?'checked':''} role="switch" aria-label="${label}"></label>`;}
 function draw(){
  if(!info||!visible())return;
  const tabs=info.self?[['overview','个人资料'],['history','对局记录'],['privacy','互动设置'],['game','游戏设置']]:[['overview','玩家资料']];
  modal(`<section class="profile-center"><aside class="profile-sidebar"><p class="eyebrow">旅人档案</p>${avatar(info)}<h2>${esc(info.name)}</h2><small class="profile-uid">UID · ${esc(info.uid)}</small><nav aria-label="个人中心">${tabs.map(([key,label])=>`<button data-profile-tab="${key}" class="${tab===key?'selected':''}" aria-current="${tab===key?'page':'false'}">${label}<span>›</span></button>`).join('')}</nav></aside><section class="profile-content"><header><div><small>雾境 · 王冠与群鸦</small><h2>${detail?'整场战报':tabs.find(t=>t[0]===tab)[1]}</h2></div><button id="profile-refresh" ${working?'disabled':''}>刷新</button></header><div class="profile-body">${detail?detailView():tab==='overview'?overview():tab==='history'?historyView():preferences()}</div><p id="profile-message" role="status">${esc(message)}</p></section></section>`,'profile-center');
  document.querySelectorAll('[data-profile-tab]').forEach(n=>n.onclick=()=>selectTab(n.dataset.profileTab));
  $('profile-refresh').onclick=()=>tab==='history'?loadHistory():open(info.uid);
  if($('profile-settings'))$('profile-settings').onsubmit=e=>{e.preventDefault();const form=new FormData(e.currentTarget),values=tab==='privacy'?{challenges:form.get('challenges'),friend_requests:form.has('friend_requests'),spectate:form.has('spectate')}:{animations:form.has('animations'),sound:form.has('sound')};void execute(async()=>{const value=await client.savePreferences(values);info.settings=value.settings;onSettings(value.settings);},'设置已保存');};
  if($('profile-tutorial'))$('profile-tutorial').onclick=()=>{if(isBusy())return;$('modal').close();playTutorial();};
  if($('profile-equip'))$('profile-equip').onclick=()=>{const season=$('profile-honor').value;void execute(async()=>{const r=await client.rankedHonor(season?Number(season):null);info.honor=r.honor;honors.rewards.forEach(x=>x.equipped=x.season_id===Number(season));onHonor(r.honor);},'荣誉已保存');};
  if($('profile-prev'))$('profile-prev').onclick=()=>{page--;void loadHistory();};
  if($('profile-next'))$('profile-next').onclick=()=>{page++;void loadHistory();};
  document.querySelectorAll('[data-match]').forEach(n=>n.onclick=()=>void execute(async()=>{detail=await client.matchHistoryDetail(n.dataset.match);logPage=0;},''));
  if($('profile-history-back'))$('profile-history-back').onclick=()=>{detail=null;draw();};
  if($('profile-log-prev'))$('profile-log-prev').onclick=()=>{logPage--;draw();};
  if($('profile-log-next'))$('profile-log-next').onclick=()=>{logPage++;draw();};
  if($('profile-friend'))$('profile-friend').onclick=()=>void interact(()=>client.friend(info.uid,'request'),'好友申请已发送');
  if($('profile-friend-accept'))$('profile-friend-accept').onclick=()=>void interact(()=>client.friend(info.uid,'accept'),'已成为好友');
  if($('profile-challenge'))$('profile-challenge').onclick=()=>void interact(()=>{if(isBusy())throw new Error('请先离开房间或取消匹配');return client.challenge(info.uid,deck()?.id);},'挑战已发送，60秒内有效');
  if($('profile-dm'))$('profile-dm').onclick=()=>{$('modal').close();privateChat(info);};
  if($('profile-watch'))$('profile-watch').onclick=()=>void execute(async()=>{if(isBusy())throw new Error('请先离开房间或取消匹配');await spectate(info.interaction);$('modal').close();},'');
 }
 async function interact(fn,notice){return execute(async()=>{await fn();info=await client.playerProfile(info.uid);},notice);}
 async function execute(fn,notice){if(working)return;working=true;const request=epoch;try{await fn();if(request===epoch)message=notice;}catch(e){if(request===epoch)message=e.message;}finally{working=false;if(request===epoch&&visible())draw();}}
 async function selectTab(value){if(working)return;++epoch;tab=value;detail=null;message='';draw();if(tab==='history')await loadHistory();}
 async function loadHistory(){const request=++epoch;history=null;draw();try{const result=await client.matchHistory(page);if(request!==epoch||!visible())return;history=result;draw();}catch(e){if(request===epoch&&visible()){message=e.message;draw();}}}
 return {open};
}
