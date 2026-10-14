import {MistrealmClient,requestId} from './client.js';
import {CONFIG} from './config.js';

const sdk=window.dzmm,client=new MistrealmClient({sdk,apiBase:CONFIG.apiBase});
const $=id=>document.getElementById(id),main=$('main');
let cards={},profile=null,room=null,busy=false,selection=null,picks=[],targets=[],row=0,readySent=false;

const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const factions={raven:'黑鸦议会',crown:'烬冠军团'};
const leader=faction=>faction==='raven'?'raven_king':'crown_regent';
function feedback(text,error=false){$('feedback').textContent=text;$('feedback').classList.toggle('error',error);}
function button(text,id,disabled=false,cls=''){return `<button id="${id}" class="${cls}" ${disabled?'disabled':''}>${text}</button>`;}
function bind(id,fn){const node=$(id);if(node)node.onclick=fn;}
function modal(html){$('modal-content').innerHTML=html;if(!$('modal').open)$('modal').showModal();imageFallback();}
function imageFallback(){document.querySelectorAll('img').forEach(img=>{img.onerror=()=>{img.style.visibility='hidden';};});}
function resetSelection(){selection=null;picks=[];targets=[];row=0;}
function my(){return room.state.players[room.state.seat];}
function enemy(){return room.state.players[1-room.state.seat];}
function markReady(){if(!readySent){readySent=true;sdk?.loading?.ready?.();}}

async function run(fn){
 if(busy)return;busy=true;render();
 try{await fn();}
 catch(error){
  feedback(error.name==='AbortError'?'连接超时，请刷新后重试':error.message,true);
  if(error.status===409&&room){try{update(await client.snapshot());}catch{}}
 }finally{busy=false;render();}
}
function update(value){
 if(value.state.phase==='closed'){client.stop();room=null;client.state=null;client.roomId=null;resetSelection();feedback('房间已关闭或已退出');render();return;}
 if(room&&value.room_id===room.room_id&&value.state.version<room.state.version)return;
 const changed=!room||value.room_id!==room.room_id||value.state.version!==room.state.version;
 room=value;client.roomId=value.room_id;client.accept(value);
 if(changed){resetSelection();feedback('已同步房间');}
 render();
}
function enter(value){update(value);if(!room)return;client.follow(value.room_id,update,error=>{
 if(error.status===403||error.status===404){
  client.stop();room=null;client.state=null;client.roomId=null;resetSelection();render();
  feedback('房间已关闭或席位已释放，可以重新创建或加入。');return;
 }
 feedback(error.message+'，正在自动重连…',true);
});}
async function send(action,payload={}){
 return run(async()=>{
  const id=requestId(),result=await client.action(action,payload,id);
  update(result);
 });
}
async function boot(){
 feedback('正在读取平台身份…');
 sdk?.loading?.progress?.({phase:'runtime_initializing',progress:20,message:'正在进入雾境'});
 try{
  if(!Object.keys(cards).length){
   const response=await fetch('./cards.json');if(!response.ok)throw new Error('卡牌数据加载失败，请重试');
   cards=await response.json();
  }
  profile=await client.boot();
  if(profile.room_id)enter(await client.snapshot(profile.room_id));else render();
  feedback('欢迎回来，'+profile.name);markReady();
 }catch(error){
  feedback(error.message,true);
  const node=$('boot-retry');if(node){node.textContent='重试连接';node.disabled=false;node.onclick=boot;}
  sdk?.loading?.error?.('MISTREALM_BOOT_FAILED',error.message);
 }
}
function render(){
 if(!profile)return;
 document.body.classList.toggle('battle',!!room&&room.state.phase!=='waiting');
 if(!room){renderHome();return;}
 const s=room.state;
 main.dataset.version=String(s.version);main.dataset.phase=s.phase;
 if(s.phase==='waiting')renderRoom();
 else if(s.phase==='mulligan'||s.phase==='reserve')renderPrep();
 else if(s.phase==='round_result'||s.phase==='finished')renderResult();
 else renderBattle();
 imageFallback();
}
function renderHome(){
 main.innerHTML=`<section class="hero"><div class="hero-copy"><p class="eyebrow">MISTREALM · A GAME OF CHOICES</p><h1>王冠将倾<br>群鸦将至</h1><p class="intro">两支军团，三局交锋。<br>决定胜负的，是你留下的最后一张牌。</p><div class="actions">${button('创建房间','create',busy,'primary')}${button('游戏规则','home-rules')}</div><div class="join-form" id="join-form"><input id="join-code" aria-label="六位房间码" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="输入六位房间码" required><button ${busy?'disabled':''}>加入房间</button></div><p class="muted">公开双人对战 · 固定预组 · 三局决胜</p></div></section>`;
 bind('create',()=>run(async()=>enter(await client.create())));
 const join=()=>{const code=$('join-code').value.trim();if(!/^[0-9]{6}$/.test(code)){feedback('请输入六位数字房间码',true);return;}run(async()=>enter(await client.join(code)));};
 $('join-form').querySelector('button').onclick=join;
 $('join-code').onkeydown=e=>{if(e.key==='Enter')join();};
 bind('home-rules',showRules);
}
function renderRoom(){
 const s=room.state;
 main.innerHTML=`<div class="room-bar"><div><p class="eyebrow">召集你的对手</p><span class="code">${esc(room.code)}</span></div><div class="actions">${button('复制房间码','copy-code')}${button('离开房间','leave',busy)}</div></div><div class="players">${s.players.map((p,i)=>p?`<article class="player-panel faction-${p.faction}"><img class="leader-art" src="${cards[leader(p.faction)].art}" alt=""><div class="player-info"><p class="eyebrow">${i===0?'房主':'挑战者'} · ${i===s.seat?'你':'对手'}</p><h2>${esc(p.name||p.uid)}</h2><p>${factions[p.faction]}</p><span class="readiness ${p.ready?'ready':'muted'}">${p.ready?'已准备':'正在整备'}</span>${i===s.seat?`<div class="faction-picker" role="group" aria-label="选择阵营">${['raven','crown'].map(f=>`<button type="button" class="faction-option ${f} ${p.faction===f?'is-selected':''}" data-faction="${f}" aria-pressed="${p.faction===f}" ${busy?'disabled':''}><img src="./assets/ui/icons/${f}.svg" alt=""><span><strong>${factions[f]}</strong><small>${f==='raven'?'伤害 · 追击':'协同 · 增益'}</small></span><span class="faction-check" aria-hidden="true">${p.faction===f?'◆':'◇'}</span></button>`).join('')}</div>`:''}<p class="muted">${esc(cards[leader(p.faction)].text)}</p></div></article>`:`<article class="player-panel empty-seat"><div class="player-info"><p class="eyebrow">空席</p><h2>等待挑战者</h2><p class="muted">将上方六位房间码告诉朋友，便可加入同一场对局。</p></div></article>`).join('')}</div><div class="room-actions">${button(my().ready?'取消准备':'准备就绪','ready',busy,'primary')}${s.seat===0?button('开始对战','start',busy||!s.players.every(p=>p?.ready)):''}</div>`;
 bind('copy-code',async()=>{try{await navigator.clipboard.writeText(room.code);feedback('房间码已复制');}catch{feedback('房间码：'+room.code+'，请手动复制');}});
 bind('leave',()=>send('leave'));bind('ready',()=>send(my().ready?'unready':'ready'));bind('start',()=>send('start'));
 document.querySelectorAll('[data-faction]').forEach(el=>el.onclick=()=>{if(el.dataset.faction!==my().faction)send('select_faction',{faction:el.dataset.faction});});
}
function cardHTML(c,{selected=false,targetable=false,location='hand'}={}){
 const info=cards[c.key];
 return `<button class="card ${selected?'selected':''} ${targetable?'targetable':''}" data-card="${esc(c.id)}" data-location="${location}" aria-label="${esc(info.name+'，'+info.text)}" aria-pressed="${selected}" title="${esc(info.text)}"><img src="${info.art}" alt="" loading="lazy"><span class="power">${c.power??(info.type==='unit'?info.power:'✦')}</span>${c.armor?`<span class="armor">盾${c.armor}</span>`:''}<span class="card-name">${info.name}</span></button>`;
}
function renderPrep(){
 const s=room.state,p=my(),mull=s.phase==='mulligan',done=p[mull?'mulligan_done':'reserve_done'];
 main.innerHTML=`<section class="prep"><p class="eyebrow">对局准备 · 首局先手：${s.first===s.seat?'你':'对手'} · <span data-timer></span></p><h2>${mull?'调整你的开局':'留下一张预备牌'}</h2><p class="muted">${mull?'可替换至多两张手牌，也可以保留全部。':'选择一张牌暂存，第三局开始时取回。'} ${done?'你已确认，等待对手。':''}</p><div class="hand">${p.hand.map(c=>cardHTML(c,{selected:picks.includes(c.id)})).join('')}</div><div class="actions" style="justify-content:center">${button(mull?`确认换牌（${picks.length}/2）`:'确认预备牌','confirm-prep',busy||done||(!mull&&picks.length!==1),'primary')}</div></section>`;
 document.querySelectorAll('[data-card]').forEach(el=>el.onclick=()=>{
  if(done||busy)return;const id=el.dataset.card;
  if(picks.includes(id))picks=picks.filter(x=>x!==id);
  else if(mull){if(picks.length<2)picks.push(id);}else picks=[id];
  render();
 });
 bind('confirm-prep',()=>send(mull?'mulligan':'reserve',mull?{cards:picks}:{card:picks[0]}));timer();
}
function targetOptions(){
 if(!selection)return {ids:[],min:0,max:0};
 const p=my(),op=enemy(),key=selection.key,e=cards[key].effect;
 const friends=p.rows.flat().filter(c=>c.id!==selection.id),enemies=op.rows.flat();
 let options=[],min=0,max=0;
 if(['damage2','damage3','assassin','pierce'].includes(e)){options=enemies;min=max=1;}
 if(['buff3','protect','regent'].includes(e)){options=friends;min=max=1;}
 if(['buff3two','buff2two'].includes(e)){options=friends;min=1;max=2;}
 if(e==='commander'&&p.rows[row].length>=2){options=p.rows[row];min=max=2;}
 if(!options.length)min=max=0;
 return {ids:options.map(c=>c.id),min,max};
}
function renderBattle(){
 const s=room.state,p=my(),op=enemy(),active=s.turn===s.seat&&!p.passed,opt=targetOptions();
 const unit=selection&&cards[selection.key].type==='unit';
 const noTargets=selection&&cards[selection.key].type!=='unit'&&opt.ids.length===0;
 const playable=selection&&targets.length>=opt.min&&targets.length<=opt.max&&!noTargets&&(!unit||p.rows[row].length<6);
 const rowHtml=(owner,index)=>{
  const pp=s.players[owner],own=owner===s.seat;
  const eligible=own&&unit&&(cards[selection.key].row==='any'||(cards[selection.key].row==='front'?index===0:index===1));
  return `<div class="battle-row ${own?'':'enemy'} ${eligible?'eligible':''}" data-row="${index}" data-owner="${owner}"><span class="row-label">${own?'我方':'敌方'} · ${index===0?'前列':'后列'}</span><div class="row-cards">${pp.rows[index].map(c=>cardHTML(c,{selected:targets.includes(c.id),targetable:opt.ids.includes(c.id),location:'board'})).join('')}${pp.rows[index].length?'':'<span class="row-empty">空战列</span>'}</div></div>`;
 };
 main.innerHTML=`<div class="battle-top"><span class="round">第 ${s.round} 局 <small> / 3</small></span><span>${active?'轮到你行动':p.passed?'你已停手，等待对手':'等待对手行动'} · <b data-timer></b></span>${button('认输','concede',busy,'danger')}</div><div class="arena"><aside class="sidebar"><div class="statbox"><strong>${op.power}</strong><div><p>${esc(op.name)} · ${s.scores[1-s.seat]/2} 局分</p><p>手牌 ${op.hand_count} · 牌库 ${op.deck_count}</p><p>${op.passed?'已停手':factions[op.faction]}</p></div></div><div class="statbox"><strong>${p.power}</strong><div><p>你的军团 · ${s.scores[s.seat]/2} 局分</p><p>牌库 ${p.deck_count} · 弃牌 ${p.discard.length}</p><p>${p.leader_used?'领袖已使用':'领袖可用'}</p></div></div></aside><div class="board">${rowHtml(1-s.seat,1)}${rowHtml(1-s.seat,0)}${rowHtml(s.seat,0)}${rowHtml(s.seat,1)}</div></div><div class="hand-label"><span>你的手牌 · ${p.hand_count}</span><span>${s.first_bonus&&s.first===s.seat?'首局首个单位 +2 战力':'点选手牌查看效果'}</span></div><div class="hand">${p.hand.map(c=>cardHTML(c,{selected:selection?.id===c.id})).join('')}</div><div class="controls"><div class="selection-info"><strong>${selection?cards[selection.key].name:'选择你的行动'}</strong><p>${selection?esc(cards[selection.key].text)+(unit?` 放置：${row===0?'前列':'后列'}。`:'')+(opt.max?` 已选目标 ${targets.length}/${opt.max}。`:''): '打出一张牌、使用领袖，或停手保存实力。'}</p></div>${selection?button('确认行动','play',busy||!active||!playable,'primary'):''}${selection?button('取消','cancel'):''}${button('领袖','leader',busy||!active||p.leader_used)}${button('停手','pass',busy||!active)}</div>`;
 document.querySelectorAll('[data-card]').forEach(el=>el.onclick=e=>{
  e.stopPropagation();if(busy)return;const id=el.dataset.card;
  if(el.dataset.location==='hand'){
   const c=p.hand.find(c=>c.id===id);if(!active){showCard(c.key);return;}
   selection=c;targets=[];row=cards[c.key].row==='back'?1:0;render();
  }else if(selection&&opt.ids.includes(id)){
   if(targets.includes(id))targets=targets.filter(x=>x!==id);
   else if(targets.length<opt.max)targets.push(id);
   render();
  }else{const c=[...p.rows.flat(),...op.rows.flat()].find(c=>c.id===id);showCard(c.key);}
 });
 document.querySelectorAll('[data-row]').forEach(el=>el.onclick=()=>{
  if(el.classList.contains('eligible')){row=Number(el.dataset.row);targets=[];render();}
 });
 bind('leader',()=>{selection={id:'leader',key:leader(p.faction)};targets=[];render();});
 bind('cancel',()=>{resetSelection();render();});
 bind('play',()=>send(selection.id==='leader'?'leader':'play',selection.id==='leader'?{targets}:{card:selection.id,row,targets}));
 bind('pass',()=>confirmAction('本局停手后将无法继续出牌，确定停手？',()=>send('pass')));
 bind('concede',()=>confirmAction('确定认输并结束本场对局？',()=>send('concede')));timer();
}
function renderResult(){
 const s=room.state,finished=s.phase==='finished',winner=finished?s.winner:s.results.at(-1).winner;
 const won=winner===s.seat,tie=winner===null;
 main.innerHTML=`<section class="result"><p class="eyebrow">${finished?'对局结束':'本局结束'}</p><img src="./assets/ui/badges/${tie?'draw':won?'victory':'defeat'}.svg" alt=""><h1>${tie?'势均力敌':won?'胜利属于你':'王冠暂别'}</h1><p class="muted">${s.reason==='cancelled'?'双方连续超时，比赛取消':s.reason==='concede'?'有玩家认输':s.reason==='timeout'?'连续超时，比赛结束':finished?'军团已经完成这一场交锋。':'下一局即将开始 · '}<span data-timer></span></p><div class="results">${s.results.map(r=>`<div><p class="eyebrow">第 ${r.round} 局</p><b>${r.powers[s.seat]} : ${r.powers[1-s.seat]}</b></div>`).join('')}</div><h2>局分 ${s.scores[s.seat]/2} : ${s.scores[1-s.seat]/2}</h2>${finished?`<div class="actions">${button(my().rematch?'已请求再战，等待对手':'再战一场','rematch',busy||my().rematch,'primary')}${button('返回首页','leave',busy)}</div>`:''}</section>`;
 bind('rematch',()=>send('rematch'));bind('leave',()=>send('leave'));timer();
}
function confirmAction(text,fn){modal(`<h2>确认操作</h2><p class="rule-text">${esc(text)}</p><div class="actions">${button('确认','confirm-yes',false,'primary')}${button('取消','confirm-no')}</div>`);bind('confirm-yes',()=>{$('modal').close();fn();});bind('confirm-no',()=>$('modal').close());}
function showCard(key){const c=cards[key];modal(`<h2>${c.name}</h2><div class="catalog"><article><img src="${c.art}" alt="${c.name}"><p>${c.text}</p><p>基础战力：${c.power||'—'} · ${c.row==='front'?'前列':c.row==='back'?'后列':'任意战列'}</p></article></div>`);}
function showRules(){modal(`<h2>雾境 · 对局规则</h2><div class="rule-text"><p>每套预组20张，含16张单位与4张战术；每人拥有前后两列，每列最多6个单位。战力总和更高的一方赢得本局，护甲不计分。</p><p>开局抽9张，最多换2张，再暂存1张预备牌。第二、三局各抽3张；第三局取回预备牌。剩余手牌跨局保留。</p><p>每回合可打出一张牌、使用一次领袖能力或停手。停手后本局不能再行动；另一方可以连续行动至停手。首局先手首次打出的单位获得2增益。</p><p>伤害先扣护甲，再扣战力；战力归零则进入弃牌堆。受伤指当前战力低于基础战力；增益可以超过基础战力。</p><p>单局胜利得1分、平局双方各得0.5分，最多三局，无法追平时提前结束。上一局胜者先手，平局交换先手。领袖能力整场只能使用一次。</p><p>换牌限时45秒，预备牌30秒，每行动45秒；超时会自动选择或停手，连续两次准备或行动超时判负，双方同时达到条件则取消。断线不重置时间，可以刷新恢复。</p></div>`);}
$('rules-open').onclick=showRules;
$('catalog-open').onclick=()=>modal('<h2>军团图鉴</h2><div class="catalog">'+Object.values(cards).map(c=>`<article><img src="${c.art}" alt="" loading="lazy"><h3>${c.name}</h3><span class="badge">${c.faction==='neutral'?'中立':factions[c.faction]}</span><p>${c.text}</p></article>`).join('')+'</div>');
$('settings-open').onclick=()=>{modal('<h2>显示设置</h2><p class="muted">设置仅在本次打开期间生效。</p><label><input id="motion" type="checkbox"> 减少动态效果</label>');$('motion').checked=document.body.classList.contains('reduced-motion');$('motion').onchange=e=>document.body.classList.toggle('reduced-motion',e.target.checked);};
$('modal-close').onclick=()=>$('modal').close();
$('refresh').onclick=()=>run(async()=>{if(room)enter(await client.snapshot());else await boot();});
$('home-link').onclick=e=>{e.preventDefault();if(room)feedback('请通过房间内的离开或认输按钮退出');else render();};
function timer(){if(!room)return;const s=room.state;document.querySelectorAll('[data-timer]').forEach(el=>{el.textContent=s.phase==='finished'?'':Math.max(0,Math.ceil((s.deadline_ms-Date.now())/1000))+'秒';});}
setInterval(timer,500);
window.addEventListener('pagehide',()=>client.stop());
boot();
