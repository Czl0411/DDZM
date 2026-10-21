import {selectionOption,toggleSelection} from './multi-select.js';

const rows=['近战','远程','攻城'];
const routes={normal:['普通战斗','胜利：10金币＋三选一卡牌'],elite:['精英战斗','敌方单位更强；胜利：18金币＋三选一卡牌'],shop:['旅途商店','购买卡牌15金币 · 移除卡牌10金币'],event:['随机事件','选择金币、卡牌或强化机遇'],upgrade:['篝火强化','选择一张单位，永久基础战力＋2'],boss:['英雄Boss','胜利：25金币＋三选一卡牌']};
const events={gold:['遗落的钱袋','获得15金币'],cache:['尘封的牌匣','从当前奖励池三选一'],training:['老兵的指点','选择一张单位，永久基础战力＋2']};

export function setupExpedition({main,client,getData,esc,modal,home}){
 let state=null,catalogue=null,active=false,working=false,error='',picked=null,hand=null,targetIds=[];
 const definition=c=>({...getData().cards,...catalogue.cards})[typeof c==='string'?c:c.card];
 const title=c=>definition(c).name;
 const btn=(label,action,extra='')=>`<button data-xp="${action}" ${extra}>${esc(label)}</button>`;
 function card(c,action,extra='',selected=false){
  if(typeof c==='string')c={card:c};const d=definition(c),power=c.power??d.power+(c.expedition_upgrade||0);
  return `<button class="xp-card ${selected?'xp-selected':''}" data-xp="${action}" ${extra} aria-pressed="${selected}"><img src="${esc(d.art)}" alt=""><span class="xp-card-power">${d.type==='unit'?power:d.persistent?'持续':'即时'}</span><div><b>${esc(d.name)}</b><small>${d.hero?'英雄 · ':''}${d.type==='unit'?d.rows.map(r=>rows[r]).join(' / '):d.persistent?'持续术':'即时术'}${c.expedition_upgrade?' · 强化＋'+c.expedition_upgrade:''}</small><p>${esc(d.text)}</p>${selected?'<em>✓ 已选</em>':''}</div></button>`;
 }
 async function load(){catalogue??=await client.request('/expedition/catalogue');state=await client.request('/expedition');}
 async function open(){active=true;error='';main.innerHTML='<section class="xp"><h2>正在读取远征进度…</h2></section>';try{await load();render();}catch(e){error=e.message;render();}}
 async function perform(action,payload={}){
  if(working)return;working=true;error='';render();
  try{state=action==='start'?await client.post('/expedition/start'):await client.post('/expedition/actions',{run_id:state.id,version:state.version,action,payload});picked=null;hand=null;targetIds=[];}
  catch(e){error=e.message;if(e.status===409){try{await load();picked=null;hand=null;targetIds=[];}catch{}}}
  finally{working=false;if(active)render();}
 }
 function confirm(text,action,payload={}){
  modal(`<section><h2>${esc(text)}</h2><p>远征每关单局定胜负。认输、战败或平局都会结束本次远征。</p><button id="xp-confirm">确认</button><button id="xp-cancel" class="secondary">取消</button></section>`,'expedition-dialog');
  document.getElementById('xp-cancel').onclick=()=>document.getElementById('modal').close();
  document.getElementById('xp-confirm').onclick=()=>{document.getElementById('modal').close();perform(action,payload);};
 }
 function detail(c){const d=definition(c);modal(`<section class="xp-detail"><img src="${esc(d.art)}" alt=""><div><small>${esc(catalogue.factions[d.faction]||getData().factions[d.faction]||'中立')} · ${d.hero?'英雄':d.type==='unit'?'普通单位':d.persistent?'持续术':'即时术'}</small><h2>${esc(d.name)}</h2><p>${esc(d.text)}</p><p>${d.type==='unit'?'基础战力 '+(d.power+(c.expedition_upgrade||0))+' · '+d.rows.map(r=>rows[r]).join(' / '):''}</p>${c.power!=null?'<p>当前战力 '+c.power+'</p>':''}</div></section>`,'expedition-dialog');}
 function deck(){modal(`<h2>远征牌组 · ${state.deck.length}张</h2><p>每场战斗重洗整副牌组，抽5张。强化跨关保留；本场伤害、阵亡与技能次数不带入下一关。</p><div class="xp-deck-list">${state.deck.map(c=>`<article><b>${esc(title(c))}</b><span>${definition(c).type==='unit'?'基础 '+(definition(c).power+c.expedition_upgrade):'术卡'}</span><p>${esc(definition(c).text)}</p></article>`).join('')}</div>`,'expedition-dialog');}
 function rules(){modal(`<h2>远征规则</h2><p>无领袖，先进行5次三选一。开局5张卡全部入手；之后每次开战重洗牌组并抽5张。每排4个单位位置，3个持续术位置，战力归零阵亡。</p><p>每关单局定胜负，双方停手后比较总战力。战败或平局结束本次远征。打赢战斗获得金币，再三选一获得卡牌。</p><p>依次挑战白骨王庭、绯夜血裔、赤砂斗场。每阵营3阶段，每阶段6个选择节点＋1个Boss，共63节点。每阵营4名英雄中随机出现3名，不重复。</p><p>第一节点没有商店，商店之后不连续出现商店。事件、商店、强化也占节点。强化仅增加所选实体的基础战力；所有远征收益仅在本次远征有效。</p><p>所有进度自动保存到当前UID，可返回大厅后继续。仅使用当前设备的本地预览UID时，切换UID会切换存档。</p>`,'expedition-dialog');}
 function offerCards(){return `<div class="xp-offers">${state.offers.map((c,i)=>card(c,'pick',`data-index="${i}"`,picked===i)).join('')}</div><div class="xp-actions">${btn('确认选择','confirm-choice',picked==null?'disabled':'')}</div>`;}
 function targetPanel(b){
  const p=b.pending;if(!p)return '';
  if(p.multi_select){const option=selectionOption(p,targetIds);return `<aside class="xp-targets"><h3>${esc(p.prompt||p.title)}</h3><div class="xp-target-list">${p.multi_select.cards.map(c=>btn(`${c.side==='own'?'己方':'敌方'} · ${c.label} · ${c.zone}${targetIds.includes(c.id)?' ✓ 已选':''}`,'multi',`data-id="${esc(c.id)}" aria-pressed="${targetIds.includes(c.id)}"`)).join('')}</div>${btn(`确认 ${targetIds.length} 张`,'target',option?`data-token="${esc(option.token)}"`:'disabled')}</aside>`;}
  return `<aside class="xp-targets"><h3>${esc(p.title)}</h3><div class="xp-target-list">${p.options.map(o=>btn(o.label+(o.hint?' · '+o.hint:''),'target',`data-token="${esc(o.token)}"`)).join('')}</div></aside>`;
 }
 function battlefield(){
  const b=state.battle,selected=b.players[0].hand.find(c=>c.id===hand),moves=b.legal_moves.filter(m=>m.action==='play'&&m.payload.card===hand);
  const side=(p,i)=>`<section class="xp-army"><h3>${i?'敌方 · '+esc(catalogue.factions[p.faction]):'你'} <strong>${p.score}战力</strong> <small>${p.passed?'已停手':'手牌 '+p.hand_count} · 牌库 ${p.deck_count} · 领袖：无</small></h3>${p.rows.map((cs,r)=>`<div class="xp-row"><span>${rows[r]}<b>${p.row_scores[r]}</b></span>${Array.from({length:4},(_,slot)=>{const c=cs[slot];return c?`<button data-xp="board" data-side="${i}" data-row="${r}" data-slot="${slot}"><img src="${esc(definition(c).art)}" alt=""><b>${c.power}</b><span>${esc(title(c))}</span></button>`:'<span class="xp-slot">◇</span>';}).join('')}</div>`).join('')}<div class="xp-spells"><small>持续术 ${p.spells.length}/3</small>${p.spells.map((c,j)=>btn(title(c)+(c.ticks!=null?' · 已触发'+c.ticks+'次':''),'spell',`data-side="${i}" data-slot="${j}"`)).join('')}${btn('弃牌区 '+p.discard.length+' · 查看','discard',`data-side="${i}"`)}</div></section>`;
  return `<div class="xp-battle"><div class="xp-board">${side(b.players[1],1)}${side(b.players[0],0)}</div><div class="xp-hand">${b.players[0].hand.map(c=>card(c,'hand',`data-id="${esc(c.id)}"`,hand===c.id)).join('')}</div><div class="xp-actions"><span>${selected?esc(title(selected)):b.players[1].passed?'对手已停手，超过对手战力后即可停手。':'选择手牌，查看效果并使用'}</span>${selected?btn('查看','inspect-hand'):''}${moves.map((m,i)=>btn(m.payload.row===-1?'使用术卡':'部署至'+rows[m.payload.row],'play',`data-index="${i}"`)).join('')}${b.legal_moves.some(m=>m.action==='pass')?btn('停手','pass'):''}${btn('认输','concede')}</div>${targetPanel(b)}<details class="xp-log"><summary>本场记录 · ${b.action_log.length}条</summary>${b.action_log.map(e=>`<p>${esc(e.text)} ${esc((e.details||[]).join(' · '))}</p>`).join('')}</details></div>`;
 }
 function render(){
  if(!active)return;
  let body='',heading='远征 · 无冠之路';
  if(!state)body=`<div class="xp-intro"><p class="eyebrow">EXPEDITION · 三族试炼</p><h1>带上五张牌，<br>走进未知之地。</h1><p>无领袖 · 自选起始牌 · 三个新阵营 · 九名英雄Boss</p><p>每阶段6个路线节点，再迎战英雄。单局定胜负，战败结束本次远征。</p>${btn('开始远征','start')}</div>`;
  else{
   if(state.phase==='draft'){heading=`选择起始牌 · ${state.deck.length+1} / 5`;body=offerCards();}
   if(state.phase==='route'){heading=`${catalogue.factions[state.faction]} · 第${state.stage+1}阶段`;body=`<p>当前Boss：${esc(title(state.boss))} · ${state.node===6?'英雄关':'路线节点 '+(state.node+1)+' / 6'}</p><div class="xp-route">${state.offers.map((k,i)=>`<button data-xp="route" data-index="${i}"><span>${({normal:'⚔',elite:'♜',shop:'◈',event:'?',upgrade:'✦',boss:'♛'})[k]}</span><h2>${routes[k][0]}</h2><p>${esc(k==='boss'?title(state.boss):routes[k][1])}</p><small>${k==='boss'?esc(definition(state.boss).text):'选择并进入 →'}</small></button>`).join('')}</div>`;}
   if(state.phase==='battle'){heading=routes[state.last_node][0]+' · '+catalogue.factions[state.faction];body=battlefield();}
   if(state.phase==='reward'){heading='旅途收获 · 三选一';body=`${state.last_result?`<p>上一场比分 ${state.last_result.scores.join(' : ')} · 胜利</p>`:''}<p>卡牌加入远征牌组，下次战斗重新洗牌抽5张。</p>`+offerCards();}
   if(state.phase==='shop'){heading='旅途商店';body=`<p>买牌15金币；移除10金币。牌组至少保留5张。</p><div class="xp-offers">${state.offers.map((c,i)=>`<article>${card(c,'shop-detail',`data-index="${i}"`)}${btn('购买 · 15金币','buy',`data-index="${i}" ${state.gold<15?'disabled':''}`)}</article>`).join('')}</div><div class="xp-remove">${state.deck.map(c=>btn('移除 '+title(c),'remove',`data-id="${esc(c.id)}" ${state.gold<10||state.deck.length<=5?'disabled':''}`)).join('')}</div>${btn('离开商店','leave')}`;}
   if(state.phase==='upgrade'){heading='强化一张单位 · 基础战力＋2';body=`<div class="xp-upgrades">${state.deck.filter(c=>definition(c).type==='unit').map(c=>card(c,'pick-upgrade',`data-id="${esc(c.id)}"`,picked===c.id)).join('')}</div>${btn('确认强化','upgrade',typeof picked==='string'?'':'disabled')} ${btn('跳过强化','leave')}`;}
   if(state.phase==='event'){heading='旅途奇遇';body=`<div class="xp-route">${state.offers.map((k,i)=>`<button data-xp="route" data-index="${i}"><h2>${events[k][0]}</h2><p>${events[k][1]}</p></button>`).join('')}</div>`;}
   if(['lost','finished'].includes(state.phase)){heading=state.phase==='finished'?'远征完成':'本次远征结束';body=`<div class="xp-intro"><h1>${state.phase==='finished'?'穿越三族，走出长夜。':state.last_result?.tied?'战力相同，未能突破。':'整顿行装，再踏征途。'}</h1><p>已通过 ${state.completed} / 63 个节点 · 牌组 ${state.deck.length}张</p>${btn('重新远征','restart')}${btn('返回大厅','home')}</div>`;}
  }
  main.innerHTML=`<section class="xp ${working?'xp-working':''}"><div class="xp-top"><div><small>EXPEDITION · ${state?'已通过 '+state.completed+' / 63':'单人冒险'}</small><h2>${esc(heading)}</h2></div><nav>${state?`<span>◈ ${state.gold} 金币</span>${btn('牌组 '+state.deck.length,'deck')}`:''}${state?.phase==='battle'?btn('记录','log'):btn('新阵营图鉴','catalogue')}${btn('规则','rules')}${btn('返回大厅','home')}</nav></div>${state&&!['draft','lost','finished'].includes(state.phase)?`<div class="xp-progress" aria-label="阶段进度">${Array.from({length:7},(_,i)=>`<span class="${i<state.node?'done':i===state.node?'current':''}">${i===6?'英雄Boss':i+1}</span>`).join('')}</div>`:''}<p class="xp-feedback ${error?'xp-error':''}" role="status">${esc(working?'正在保存并结算…':error||'进度自动保存 · 返回大厅后可继续')}</p><div class="xp-content">${body}</div></section>`;
 }
 main.addEventListener('click',event=>{
  const b=event.target.closest('[data-xp]');if(!active||!b||working)return;
  const action=b.dataset.xp,index=Number(b.dataset.index),id=b.dataset.id;
  if(action==='home'){active=false;home();return;}
  if(action==='catalogue'){modal('<h2>远征图鉴 · 48张新卡</h2><p>每阵营8张普通单位、4张术卡、4张英雄。仅用于远征。</p><div class="xp-deck-list">'+Object.entries(catalogue.cards).map(([id,d])=>'<article><small>'+esc(catalogue.factions[d.faction])+' · '+(d.hero?'英雄':d.type==='unit'?'普通单位':d.persistent?'持续术':'即时术')+'</small><h3>'+esc(d.name)+'</h3><p>'+esc(d.text)+'</p><small>'+(d.type==='unit'?'基础战力 '+d.power+' · '+d.rows.map(r=>rows[r]).join(' / '):'')+'</small></article>').join('')+'</div>','expedition-dialog');return;}
  if(action==='log'){modal('<h2>本场记录</h2>'+state.battle.action_log.map(e=>'<p>'+esc(e.text)+' '+esc((e.details||[]).join(' · '))+'</p>').join(''),'expedition-dialog');return;}
  if(action==='rules'){rules();return;}if(action==='deck'){deck();return;}
  if(action==='start'){perform('start');return;}
  if(action==='restart'){confirm('放弃旧进度，重新选择五张牌？','restart');return;}
  if(action==='pick'){picked=index;render();return;}
  if(action==='pick-upgrade'){picked=id;render();return;}
  if(action==='confirm-choice'){if(picked!=null)perform('choose',{index:picked});return;}
  if(action==='route'){perform('choose',{index});return;}
  if(action==='buy'){perform('buy',{index});return;}
  if(action==='remove'){perform('remove',{card:id});return;}
  if(action==='leave'){perform('leave');return;}
  if(action==='upgrade'){perform('upgrade',{card:picked});return;}
  if(action==='shop-detail'){detail({card:state.offers[index]});return;}
  const battle=state.battle;if(!battle)return;
  if(action==='hand'){hand=id;render();return;}
  if(action==='inspect-hand'){detail(battle.players[0].hand.find(c=>c.id===hand));return;}
  if(action==='play'){const move=battle.legal_moves.filter(m=>m.action==='play'&&m.payload.card===hand)[index];if(move)perform('battle',move);return;}
  if(action==='pass'){confirm('确认本场停手？','battle',{action:'pass',payload:{}});return;}
  if(action==='concede'){confirm('认输将结束本次远征，确定？','battle',{action:'concede',payload:{}});return;}
  if(action==='target'){perform('battle',{action:'choose',payload:{option:b.dataset.token}});return;}
  if(action==='multi'){const next=toggleSelection(battle.pending,targetIds,id);targetIds=next.ids;error=next.notice;render();return;}
  const p=battle.players[Number(b.dataset.side)],slot=Number(b.dataset.slot);
  if(action==='board')detail(p.rows[Number(b.dataset.row)][slot]);
  if(action==='spell')detail(p.spells[slot]);
  if(action==='discard')modal(`<h2>${Number(b.dataset.side)?'敌方':'己方'}弃牌区 · ${p.discard.length}</h2><div class="xp-deck-list">${p.discard.map(c=>`<article><b>${esc(title(c))}</b><p>${esc(definition(c).text)}</p></article>`).join('')||'<p>暂无弃牌</p>'}</div>`,'expedition-dialog');
 });
 return {open,close(){active=false;}};
}
