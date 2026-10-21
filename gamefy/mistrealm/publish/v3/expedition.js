export function expeditionFits(deck,cid,cards,replace=null){
 const next=deck.filter(c=>c.id!==replace).map(c=>cards[c.card]).concat(cards[cid]);
 return next.filter(c=>c.type==='unit').length<=7&&next.filter(c=>c.type==='special').length<=3&&next.filter(c=>c.hero).length<=1;
}

const rows=['近战','远程','攻城'];
const routes={normal:['普通战斗','额外打一波小怪；胜利：10金币＋三选一卡牌'],elite:['精英战斗','额外挑战强化小怪；胜利：18金币＋三选一卡牌'],shop:['旅途商店','购买卡牌15金币 · 移除卡牌10金币'],event:['随机事件','选择金币、卡牌或强化机遇'],upgrade:['篝火强化','选择一张单位，永久基础战力＋2'],boss:['英雄Boss','胜利：25金币＋三选一卡牌']};
const events={gold:['遗落的钱袋','获得15金币'],cache:['尘封的牌匣','从当前奖励池三选一'],training:['老兵的指点','选择一张单位，永久基础战力＋2']};

export function setupExpedition({main,client,getData,esc,modal,home,showBattle,closeBattle}){
 let state=null,catalogue=null,active=false,working=false,error='',picked=null,replacement=null;
 const definition=c=>({...getData().cards,...catalogue.cards})[typeof c==='string'?c:c.card];
 const title=c=>definition(c).name;
 const fits=(cid,replace=null)=>expeditionFits(state.deck,cid,{...getData().cards,...catalogue.cards},replace);
 const composition=()=>`单位 ${state.deck.filter(c=>definition(c).type==='unit').length}/7 · 英雄 ${state.deck.filter(c=>definition(c).hero).length}/1（计入单位） · 术卡 ${state.deck.filter(c=>definition(c).type==='special').length}/3`;
 const btn=(label,action,extra='')=>`<button data-xp="${action}" ${extra}>${esc(label)}</button>`;
 function card(c,action,extra='',selected=false){
  if(typeof c==='string')c={card:c};const d=definition(c),power=c.power??d.power+(c.expedition_upgrade||0);
  return `<button class="xp-card ${selected?'xp-selected':''}" data-xp="${action}" ${extra} aria-pressed="${selected}"><img src="${esc(d.art)}" alt=""><span class="xp-card-power">${d.type==='unit'?power:d.persistent?'持续':'即时'}</span><div><b>${esc(d.name)}</b><small>${d.hero?'英雄 · ':''}${d.type==='unit'?d.rows.map(r=>rows[r]).join(' / '):d.persistent?'持续术':'即时术'}${c.expedition_upgrade?' · 强化＋'+c.expedition_upgrade:''}</small><p>${esc(d.text)}</p>${selected?'<em>✓ 已选</em>':''}</div></button>`;
 }
 async function load(){catalogue??=await client.request('/expedition/catalogue');state=await client.request('/expedition');}
 async function open(){active=true;error='';picked=null;replacement=null;main.innerHTML='<section class="xp"><h2>正在读取远征进度…</h2></section>';try{await load();render();}catch(e){error=e.message;render();}}
 async function perform(action,payload={}){
  if(working)return;working=true;error='';if(!state?.battle)render();
  try{state=action==='start'?await client.post('/expedition/start'):await client.post('/expedition/actions',{run_id:state.id,version:state.version,action,payload});picked=null;replacement=null;}
  catch(e){error=e.message;if(e.status===409){try{await load();picked=null;replacement=null;}catch{}}if(action==='battle')throw e;}
  finally{working=false;if(active)render();}
 }
 function confirm(text,action,payload={}){
  modal(`<section><h2>${esc(text)}</h2><p>远征每关单局定胜负。认输、战败或平局都会结束本次远征。</p><button id="xp-confirm">确认</button><button id="xp-cancel" class="secondary">取消</button></section>`,'expedition-dialog');
  document.getElementById('xp-cancel').onclick=()=>document.getElementById('modal').close();
  document.getElementById('xp-confirm').onclick=()=>{document.getElementById('modal').close();perform(action,payload);};
 }
 function detail(c){const d=definition(c);modal(`<section class="xp-detail"><img src="${esc(d.art)}" alt=""><div><small>${esc(catalogue.factions[d.faction]||getData().factions[d.faction]||'中立')} · ${d.type==='leader'?'领袖':d.hero?'英雄':d.type==='unit'?'普通单位':d.persistent?'持续术':'即时术'}</small><h2>${esc(d.name)}</h2><p>${esc(d.text)}</p><p>${d.type==='unit'?'基础战力 '+(d.power+(c.expedition_upgrade||0))+' · '+d.rows.map(r=>rows[r]).join(' / '):''}</p>${c.power!=null?'<p>当前战力 '+c.power+'</p>':''}</div></section>`,'expedition-dialog');}
 function deck(){modal(`<h2>远征牌组 · ${state.deck.length}张</h2><p>${esc(composition())}。每场战斗重洗整副牌组，抽5张。强化跨关保留；本场伤害、阵亡与技能次数不带入下一关。</p><div class="xp-deck-list">${state.deck.map(c=>`<article><b>${esc(title(c))}</b><span>${definition(c).type==='unit'?'基础 '+(definition(c).power+c.expedition_upgrade):'术卡'}</span><p>${esc(definition(c).text)}</p></article>`).join('')}</div>`,'expedition-dialog');}
 function rules(){modal(`<h2>远征规则</h2><p>无领袖，先进行5次三选一。牌组最多10张：7张单位（含最多1张英雄）、3张术卡；超限时自行选择替换旧牌。开局5张卡全部入手；之后每次开战重洗牌组并抽5张。每排4个单位位置，3个持续术位置，战力归零阵亡。</p><p>每关单局定胜负，双方停手后比较总战力。战败或平局结束本次远征。每次打赢战斗都获得金币和三选一卡牌，一般为2张普通单位与1张术卡。只有Boss胜利奖励池允许出现英雄。起手选卡已满3张术卡时，后续改为3张普通单位。</p><p>依次挑战白骨王庭、绯夜血裔、赤砂斗场。每阵营3阶段，每阶段6个选择节点＋1个Boss，共63节点。每阵营4名英雄中随机出现3名，不重复。</p><p>第一节点没有商店，商店之后不连续出现商店。每个选择节点先打普通小怪，领取奖励后再三选一路线；选普通或精英则额外战斗并再次领奖，精英金币更多。商店、事件、强化在此次选择后处理，之后开始下一节点的小怪战。强化仅增加所选实体的基础战力；所有远征收益仅在本次远征有效。</p><p>所有进度自动保存到当前UID，可返回大厅后继续。仅使用当前设备的本地预览UID时，切换UID会切换存档。</p>`,'expedition-dialog');}
 function replacementPanel(){
  if(picked==null||fits(state.offers[picked]))return '';
  return `<section class="xp-replacements"><h3>牌组已达上限 · 选择替换一张旧牌</h3><p>${esc(composition())}。获得「${esc(title(state.offers[picked]))}」将移除所选旧牌及其强化。</p><div class="xp-replacement-list">${state.deck.filter(c=>fits(state.offers[picked],c.id)).map(c=>btn(`${title(c)} · ${definition(c).type==='unit'?'战力 '+(definition(c).power+c.expedition_upgrade):'术卡'}${replacement===c.id?' ✓ 已选':''}`,'pick-replacement',`data-id="${esc(c.id)}" aria-pressed="${replacement===c.id}"`)).join('')}</div></section>`;
 }
 function confirmChoice(){return btn(state.phase==='shop'?'确认替换并购买':'确认选择','confirm-choice',picked==null||!fits(state.offers[picked],replacement)?'disabled':'');}
 function offerCards(){return `<div class="xp-offers">${state.offers.map((c,i)=>card(c,'pick',`data-index="${i}"`,picked===i)).join('')}</div>${replacementPanel()}<div class="xp-actions">${confirmChoice()}</div>`;}
 function render(){
  if(!active)return;
  if(state?.battle){showBattle(state);if(error)document.getElementById('feedback').textContent=error;return;}
  closeBattle();
  let body='',heading='远征 · 无冠之路';
  if(!state)body=`<div class="xp-intro"><p class="eyebrow">EXPEDITION · 三族试炼</p><h1>带上五张牌，<br>走进未知之地。</h1><p>无领袖 · 自选起始牌 · 三个新阵营 · 九名英雄Boss</p><p>每阶段先打小怪、领奖，再选路线，完成6次后迎战英雄。单局定胜负，战败结束本次远征。</p>${btn('开始远征','start')}</div>`;
  else{
   if(state.phase==='draft'){heading=`选择起始牌 · ${state.deck.length+1} / 5`;body=offerCards();}
   if(state.phase==='route'){heading=`${catalogue.factions[state.faction]} · 第${state.stage+1}阶段`;body=`<p>${state.node===6?'六个选择节点已完成，迎战Boss。':'小怪已击败，战斗奖励已领取；现在选择路线。'}</p><p>当前Boss：${esc(title(state.boss))} · ${state.node===6?'英雄关':'路线节点 '+(state.node+1)+' / 6'}</p><div class="xp-route">${state.offers.map((k,i)=>`<button data-xp="route" data-index="${i}"><span>${({normal:'⚔',elite:'♜',shop:'◈',event:'?',upgrade:'✦',boss:'♛'})[k]}</span><h2>${routes[k][0]}</h2><p>${esc(k==='boss'?title(state.boss):routes[k][1])}</p><small>${k==='boss'?esc(definition(state.boss).text):'选择并进入 →'}</small></button>`).join('')}</div>`;}
   if(state.phase==='reward'){heading='旅途收获 · 三选一';body=`${state.last_result?`<p>上一场比分 ${state.last_result.scores.join(' : ')} · 胜利</p>`:''}<p>${esc(composition())} · 超限时选择替换旧牌。下场战斗重新洗牌抽5张。</p>`+offerCards();}
   if(state.phase==='shop'){heading='旅途商店';body=`<p>买牌15金币；移除10金币。牌组至少保留5张。</p><div class="xp-offers">${state.offers.map((c,i)=>`<article>${card(c,'shop-detail',`data-index="${i}"`)}${btn('购买 · 15金币','buy',`data-index="${i}" ${state.gold<15?'disabled':''}`)}</article>`).join('')}</div><div class="xp-remove">${state.deck.map(c=>btn('移除 '+title(c),'remove',`data-id="${esc(c.id)}" ${state.gold<10||state.deck.length<=5?'disabled':''}`)).join('')}</div>${replacementPanel()}${picked!=null&&!fits(state.offers[picked])?confirmChoice():''}${btn('离开商店','leave')}`;}
   if(state.phase==='upgrade'){heading='强化一张单位 · 基础战力＋2';body=`<div class="xp-upgrades">${state.deck.filter(c=>definition(c).type==='unit').map(c=>card(c,'pick-upgrade',`data-id="${esc(c.id)}"`,picked===c.id)).join('')}</div>${btn('确认强化','upgrade',typeof picked==='string'?'':'disabled')} ${btn('跳过强化','leave')}`;}
   if(state.phase==='event'){heading='旅途奇遇';body=`<div class="xp-route">${state.offers.map((k,i)=>`<button data-xp="route" data-index="${i}"><h2>${events[k][0]}</h2><p>${events[k][1]}</p></button>`).join('')}</div>`;}
   if(['lost','finished'].includes(state.phase)){heading=state.phase==='finished'?'远征完成':'本次远征结束';body=`<div class="xp-intro"><h1>${state.phase==='finished'?'穿越三族，走出长夜。':state.last_result?.tied?'战力相同，未能突破。':'整顿行装，再踏征途。'}</h1><p>已通过 ${state.completed} / 63 个节点 · 牌组 ${state.deck.length}张</p>${btn('重新远征','restart')}${btn('返回大厅','home')}</div>`;}
  }
  main.innerHTML=`<section class="xp ${working?'xp-working':''}"><div class="xp-top"><div><small>EXPEDITION · ${state?'已通过 '+state.completed+' / 63':'单人冒险'}</small><h2>${esc(heading)}</h2></div><nav>${state?`<span>◈ ${state.gold} 金币</span>${btn('牌组 '+state.deck.length,'deck')}`:''}${btn('新阵营图鉴','catalogue')}${btn('规则','rules')}${btn('返回大厅','home')}</nav></div>${state&&!['draft','lost','finished'].includes(state.phase)?`<div class="xp-progress" aria-label="阶段进度">${Array.from({length:7},(_,i)=>`<span class="${i<state.node?'done':i===state.node?'current':''}">${i===6?'英雄Boss':i+1}</span>`).join('')}</div>`:''}<p class="xp-feedback ${error?'xp-error':''}" role="status">${esc(working?'正在保存并结算…':error||'进度自动保存 · 返回大厅后可继续')}</p><div class="xp-content">${body}</div></section>`;
 }
 main.addEventListener('click',event=>{
  const b=event.target.closest('[data-xp]');if(!active||!b||working)return;
  const action=b.dataset.xp,index=Number(b.dataset.index),id=b.dataset.id;
  if(action==='home'){active=false;home();return;}
  if(action==='catalogue'){modal('<h2>远征图鉴 · 60张新卡</h2><p>每阵营12张普通单位、4张英雄、1张即时术、1张持续术、2名领袖。领袖仅供图鉴查看，远征不启用。</p><div class="xp-deck-list xp-catalogue">'+Object.entries(catalogue.cards).map(([id,d])=>'<article><img src="'+esc(d.art)+'" alt="'+esc(d.name)+'" loading="lazy"><small>'+esc(catalogue.factions[d.faction])+' · '+(d.type==='leader'?'领袖':d.hero?'英雄':d.type==='unit'?'普通单位':d.persistent?'持续术':'即时术')+'</small><h3>'+esc(d.name)+'</h3><p>'+esc(d.text)+'</p><small>'+(d.type==='unit'?'基础战力 '+d.power+' · '+d.rows.map(r=>rows[r]).join(' / '):'')+'</small></article>').join('')+'</div>','expedition-dialog');return;}
  if(action==='rules'){rules();return;}if(action==='deck'){deck();return;}
  if(action==='start'){perform('start');return;}
  if(action==='restart'){confirm('放弃旧进度，重新选择五张牌？','restart');return;}
  if(action==='pick'){picked=index;replacement=null;render();return;}
  if(action==='pick-upgrade'){picked=id;render();return;}
  if(action==='pick-replacement'){replacement=id;render();return;}
  if(action==='confirm-choice'){if(picked!=null&&fits(state.offers[picked],replacement))perform(state.phase==='shop'?'buy':'choose',{index:picked,...(replacement?{replace:replacement}:{})});return;}
  if(action==='route'){perform('choose',{index});return;}
  if(action==='buy'){if(fits(state.offers[index]))perform('buy',{index});else{picked=index;replacement=null;render();}return;}
  if(action==='remove'){perform('remove',{card:id});return;}
  if(action==='leave'){perform('leave');return;}
  if(action==='upgrade'){perform('upgrade',{card:picked});return;}
  if(action==='shop-detail'){detail({card:state.offers[index]});return;}

 });
 return {open,close(){active=false;},catalogue:()=>catalogue,
  battleAction:(action,payload)=>perform('battle',{action,payload}),
  continueJourney(){state.battle=null;closeBattle();render();}
 };
}
