import {V3Client,remainingSeconds} from './client.js';
import {CONFIG} from './config.js';
const client=new V3Client({sdk:window.dzmm,apiBase:CONFIG.apiBase});
const $=id=>document.getElementById(id),main=$('main');
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rows=['近战','远程','攻城'];
const abilityNames={bond:'同袍',spy:'间谍',medic:'复活',agile:'灵活',muster:'召集'};
let data,profile,decks=[],selectedDeck=null,room=null,receivedAt=0,busy=false,selection=null,picks=new Set(),draft=null;
let queue=null,queueEpoch=0,queueTimer=null;
let channelOpen=false,channelItems=[],channelKnown=new Set(),channelTimer=null,homeActive=false,returnToStory=false;
const cardData=c=>data.transforms[c.form]||data.cards[c.card]||data.cards[c];
const selected=()=>decks.find(d=>d.id===selectedDeck)||decks[0];
const desc=c=>c.text;
function feedback(text,error=false){$('feedback').textContent=text;$('feedback').classList.toggle('error',error);}
function bind(id,fn){const n=$(id);if(n)n.onclick=fn;}
function images(){document.querySelectorAll('img').forEach(img=>{img.onerror=()=>{img.hidden=true;img.parentElement.classList.add('missing-art');};});}
const emblem=id=>`<img class="faction-emblem" src="../assets/classic/ui/${id}.svg" alt="">`;
function button(text,id,cls='primary'){return `<button id="${id}" class="${cls}">${text}</button>`;}
function modal(html){$('modal-content').innerHTML=html;if(!$('modal').open)$('modal').showModal();images();}
function identity(p,self){return `<div class="identity"><span class="avatar"><span>${esc((p.name||'旅')[0])}</span>${p.avatar?.startsWith('https://')?`<img src="${esc(p.avatar)}" alt="" referrerpolicy="no-referrer">`:''}</span><div><b>${esc(p.name||'旅人')}</b><small>${self?'你':'对手'}</small></div></div>`;}
function card(c,attrs='',chosen=false){const d=cardData(c);return `<button class="card ${d.hero?'hero-card':''} ${chosen?'selected':''}" ${attrs} title="${esc(d.name+' · '+desc(d))}"><img src="${esc(d.art)}" alt="" loading="lazy"><span class="art-sigil">${esc(data.factions[d.faction]?.slice(0,2)||'雾境')}</span><span class="power">${d.type==='unit'?(c.power??d.power):d.type==='leader'?'领':'术'}</span><span class="card-copy"><b>${esc(d.name)}</b><small>${esc(d.hero?'条件英雄':d.type==='leader'?'领袖':d.type==='special'?(d.persistent?'持续术 · 占术位':'即时术'):d.abilities.map(a=>abilityNames[a]).join(' · ')||'部署单位')}</small></span></button>`;}
function inspectCard(c,back=false){const d=cardData(c),p=c.power_detail;modal(`<div class="card-detail"><img src="${esc(d.art)}" alt=""><div><p class="eyebrow">${esc(data.factions[d.faction]||'中立')} · ${d.hero?'英雄':d.type==='leader'?'领袖':d.type==='unit'?'单位':'特殊牌'}</p><h2>${esc(d.name)}</h2><p>${esc(desc(d)||'依靠基础战力争夺本局优势。')}</p><p>基础战力 ${d.power} · ${d.rows.map(r=>rows[r]).join(' / ')||'特殊位置'}</p>${p?`<section class="power-breakdown"><h3>当前战力 ${p.power}</h3><p>基础 ${p.base} + 强化 ${p.boost} + 条件 ${p.condition} − 伤害 ${p.damage}<br>护盾 ${p.shield}${p.sealed?' · 已封印':''}</p></section>`:''}${back?button('返回组牌','back-builder','secondary'):''}</div></div>`);if(back)bind('back-builder',builderView);}
async function run(fn){if(busy)return;busy=true;document.body.classList.add('busy');try{await fn();feedback('已连接 · 牌局由服务器同步');}catch(e){feedback(e.message,true);if(e.status===409&&room){try{accept(await client.snapshot());}catch{}}}finally{busy=false;document.body.classList.remove('busy');}}
function accept(value){if(value.state.phase==='closed'){client.stop();location.reload();return;}if(value.state.rules_version!==3){client.stop();location.replace((value.state.rules_version===2?'../classic/':'../')+location.search+location.hash);return;}if(room?.room_id===value.room_id&&room.state.version>value.state.version)return;room=value;returnToStory=value.state.mode==='story';client.state=value;client.roomId=value.room_id;receivedAt=performance.now();render();}
function enter(value){queue=null;clearTimeout(queueTimer);queueEpoch++;selection=null;picks.clear();client.stop();room=null;accept(value);if(!room)return;client.follow(value.room_id,accept,e=>feedback(e.message+'，正在重连…',true));}
async function act(action,payload={}){
 for(let attempt=0;attempt<3;attempt++){
  try{accept(await client.action(action,payload));break;}
  catch(e){
   if(e.status!==409||!['lock','unlock','mulligan','rematch'].includes(action)||attempt===2)throw e;
   accept(await client.snapshot());
   if(!room)break;
   const s=room.state,p=s.players[s.seat];
   if(['lock','unlock'].includes(action)&&(s.phase!=='waiting'||p.locked===(action==='lock')))break;
   if(action==='mulligan'&&(s.phase!=='mulligan'||p.mulligan_done))break;
   if(action==='rematch'&&(s.phase!=='finished'||p.rematch))break;
  }
 }
 selection=null;render();
}

function setHomeActive(active){
 homeActive=active;$('channel').hidden=!active;
 clearTimeout(channelTimer);
 if(active&&profile){channelRefresh();}
}
function channelLabel(item){return item.kind==='challenge'?'发布了约战':item.text;}
function renderChannel(){
 const last=channelItems.at(-1);$('channel-preview').textContent=last?`${last.player.name}：${channelLabel(last)}`:'暂时还没有人发言';
 const list=$('channel-messages');
 list.innerHTML=channelItems.map(item=>`<article class="channel-message"><span class="channel-avatar">${esc((item.player.name||'旅')[0])}${item.player.avatar?.startsWith('https://')?`<img src="${esc(item.player.avatar)}" alt="" referrerpolicy="no-referrer">`:''}</span><div><b>${esc(item.player.name)}</b><small>${new Date(item.created_at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</small>${item.kind==='challenge'?`<section class="challenge-card"><strong>公开约战</strong><p>${item.challenge.status==='waiting'?'等待对手加入':'房间已经结束'}</p>${item.challenge.status==='waiting'?`<button data-channel-code="${esc(item.challenge.code)}">加入对局</button>`:''}</section>`:`<p>${esc(item.text)}</p>`}</div></article>`).join('')||'<p class="channel-empty">成为第一个发言的人吧。</p>';
 document.querySelectorAll('[data-channel-code]').forEach(node=>node.onclick=()=>run(async()=>enter(await client.join(node.dataset.channelCode,selected().id))));
 if(channelOpen){list.scrollTop=list.scrollHeight;channelKnown=new Set(channelItems.map(item=>item.id));$('channel-unread').hidden=true;}
 else{
  const unread=channelItems.filter(item=>!channelKnown.has(item.id)).length;
  if(channelKnown.size&&unread){$('channel-unread').textContent=unread;$('channel-unread').hidden=false;}
  channelItems.forEach(item=>channelKnown.add(item.id));
 }
 images();
}
async function channelRefresh(){
 if(!homeActive)return;
 try{channelItems=(await client.channelMessages()).items;renderChannel();}
 catch(e){if(channelOpen)$('channel-messages').innerHTML=`<p class="channel-empty">${esc(e.message)}</p>`;}
 finally{clearTimeout(channelTimer);if(homeActive)channelTimer=setTimeout(channelRefresh,4000);}
}
function toggleChannel(open){
 channelOpen=open;$('channel-panel').hidden=!open;$('channel').classList.toggle('open',open);
 if(open){channelKnown=new Set(channelItems.map(item=>item.id));$('channel-unread').hidden=true;renderChannel();$('channel-input').focus();}
}
async function publishChallenge(value){await client.channelChallenge(value.room_id);enter(value);}

async function storyView(){
 setHomeActive(false);document.body.classList.remove('battle');returnToStory=true;
 try{
  const progress=await client.story(),deck=selected();
  main.innerHTML=`<section class="story-select"><div class="story-heading"><div><p class="eyebrow">MISTREALM · SOLO STORY</p><h1>雾境纪事</h1><p>独自穿过五段迷雾。剧情进度会自动保存。</p></div>${button('返回大厅','story-back','secondary')}</div><div class="story-chapters">${progress.chapters.map(item=>`<article class="story-chapter ${item.locked?'locked':''}"><span>第 ${item.id} 章</span><h2>${esc(item.title)}</h2><p>${esc(item.summary)}</p><small>对手 · ${esc(item.enemy)}</small>${item.completed?'<b>已通关</b>':''}${item.locked?'<button disabled>尚未解锁</button>':`<button data-story="${item.id}">${item.completed?'再次挑战':'开始关卡'}</button>`}</article>`).join('')}</div><div class="story-deck"><span>当前军团</span><b>${esc(deck.name)}</b><small>${esc(data.factions[deck.faction])}</small>${button('更换军团','story-deck-change','secondary')}</div></section>`;
  bind('story-back',()=>{returnToStory=false;home();});bind('story-deck-change',deckPicker);
  document.querySelectorAll('[data-story]').forEach(node=>node.onclick=()=>run(async()=>enter(await client.startStory(Number(node.dataset.story),selected().id))));
 }catch(e){feedback(e.message,true);home();}
}

function home(){if(room)return render();returnToStory=false;setHomeActive(true);document.body.classList.remove('battle');const d=selected();main.innerHTML=`<section class="hero"><div class="hero-copy"><p class="eyebrow">FIVE FACTIONS · ONE LAST CARD</p><h1>王冠将倾<br>群鸦将至</h1><p class="intro">组建你的军团。在三排战场上争夺优势，<br>也为下一局，留住一张底牌。</p>${identity(profile,true)}<div class="deck-choice"><small>当前出战牌组</small><h2 id="selected-deck">${esc(d?.name||'尚无牌组')}</h2><p>${esc(data.factions[d?.faction])} · ${esc(data.cards[d?.leader]?.name)}</p><div class="actions">${button('更换军团','choose-deck','secondary')}${button('编辑牌组','edit-deck','secondary')}</div></div><div class="play-modes"><button id="story-mode" class="mode-card"><small>单人 · 随时可玩</small><strong>剧情模式</strong><span>五章旅程，对抗规则 AI</span></button><button id="quick-match" class="mode-card"><small>双人 · 在线匹配</small><strong>玩家对战</strong><span>寻找同样等待的雾境旅人</span></button></div><div class="actions">${button('创建私人房间','create-room','secondary')}</div><div id="join-form"><input id="room-code-input" placeholder="六位房间码" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" aria-label="房间码" aria-describedby="join-feedback"><button id="join-room" type="button">加入房间</button></div><p id="join-feedback" class="join-feedback" role="status" aria-live="polite" hidden></p></div><aside class="home-note"><img class="home-portrait" src="${esc(data.cards[d?.leader]?.art)}" alt=""><div><span>120</span><p>张原创卡牌<br>5 个阵营 · 10 位领袖</p><small>四格战列 · 条件英雄<br>伤害 · 死亡 · 三格术区</small></div></aside></section>`;
 bind('choose-deck',()=>deckPicker());bind('edit-deck',()=>builder());bind('story-mode',storyView);bind('quick-match',()=>run(startQueue));bind('create-room',()=>run(async()=>enter(await client.create(selected().id))));bind('join-room',joinRoom);$('room-code-input').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();joinRoom();}};images();}
function joinRoom(){
 if(busy)return;
 const code=$('room-code-input').value.trim(),hint=$('join-feedback'),button=$('join-room');
 hint.hidden=false;hint.classList.remove('error');
 if(!/^[0-9]{6}$/.test(code)){hint.textContent='请输入6位数字房间码';hint.classList.add('error');hint.scrollIntoView({block:'nearest'});return;}
 return run(async()=>{
  hint.textContent='正在加入房间…';hint.scrollIntoView({block:'nearest'});button.disabled=true;button.textContent='正在加入…';
  try{enter(await client.join(code,selected().id));}
  catch(e){if(e.status===404)e.message='房间不存在，请检查房间码';hint.textContent=e.message;hint.classList.add('error');hint.scrollIntoView({block:'nearest'});throw e;}
  finally{if(button.isConnected){button.disabled=false;button.textContent='加入房间';}}
 });
}
function deckPicker(){modal(`<p class="eyebrow">YOUR ARMIES</p><h2>选择出战军团</h2><div class="deck-list">${decks.map(d=>`<button data-deck="${d.id}" class="deck-tile"><b>${esc(d.name)}</b><small>${esc(data.factions[d.faction])} · ${esc(data.cards[d.leader].name)}</small></button>`).join('')}</div><h3>建立新牌组</h3><div class="actions">${Object.entries(data.factions).map(([id,name])=>`<button data-new="${id}">${esc(name)}</button>`).join('')}</div>`);
 document.querySelectorAll('[data-deck]').forEach(n=>n.onclick=()=>{selectedDeck=n.dataset.deck;$('modal').close();if(room){run(()=>act('select_deck',{deck_id:selectedDeck}));}else home();});
 document.querySelectorAll('[data-new]').forEach(n=>n.onclick=()=>builder({...structuredClone(data.starters.find(d=>d.faction===n.dataset.new)),id:null}));}
function builder(value=selected()){draft=structuredClone(value);builderView();}
function builderView(){const unitCount=Object.entries(draft.counts).reduce((n,[id,v])=>n+(data.cards[id].type==='unit'?v:0),0),specialCount=Object.entries(draft.counts).reduce((n,[id,v])=>n+(data.cards[id].type==='special'?v:0),0),heroCount=Object.entries(draft.counts).reduce((n,[id,v])=>n+(data.cards[id].hero?v:0),0);
 modal(`<section id="builder"><p class="eyebrow">DECK WORKSHOP · ${esc(data.factions[draft.faction])}</p><h2>编制军团</h2><input id="deck-name" aria-label="牌组名称" value="${esc(draft.name)}" maxlength="40"><div class="builder-counts ${unitCount<14||specialCount>6||unitCount+specialCount!==20||heroCount>2?'invalid':''}">总数 <b>${unitCount+specialCount}</b> / 20 · 单位 ${unitCount} / 至少14 · 英雄 ${heroCount} / 最多2 · 术卡 ${specialCount} / 最多6</div><h3>领袖</h3><div class="leader-options">${Object.entries(data.cards).filter(([,c])=>c.type==='leader'&&c.faction===draft.faction).map(([id,c])=>`<button data-leader="${id}" aria-pressed="${draft.leader===id}" class="${draft.leader===id?'chosen':''}">${esc(c.name)}<small>${esc(desc(c))}</small></button>`).join('')}</div><div class="builder-grid">${Object.entries(data.cards).filter(([,c])=>c.type!=='leader'&&[draft.faction,'neutral'].includes(c.faction)).map(([id,c])=>`<article>${card({card:id},`data-inspect="${id}"`)}<div class="quantity"><button data-minus="${id}" aria-label="移除${esc(c.name)}" ${!draft.counts[id]?'disabled':''}>−</button><b>${draft.counts[id]||0} / ${c.copies}</b><button data-plus="${id}" aria-label="添加${esc(c.name)}" ${(draft.counts[id]||0)>=c.copies?'disabled':''}>＋</button></div></article>`).join('')}</div><div class="builder-save">${button('保存牌组','save-deck')}<span>英雄计入单位数，领袖独立于牌库</span></div></section>`);
 $('deck-name').oninput=e=>draft.name=e.target.value;
 document.querySelectorAll('[data-inspect]').forEach(n=>n.onclick=()=>inspectCard({card:n.dataset.inspect},true));
 document.querySelectorAll('[data-leader]').forEach(n=>n.onclick=()=>{draft.leader=n.dataset.leader;builderView();});
 for(const key of ['plus','minus'])document.querySelectorAll('[data-'+key+']').forEach(n=>n.onclick=()=>{draft.counts[n.dataset[key]]=(draft.counts[n.dataset[key]]||0)+(key==='plus'?1:-1);builderView();});
 bind('save-deck',()=>run(async()=>{const d=await client.saveDeck(draft);decks=(await client.decks()).decks;selectedDeck=d.id;$('modal').close();home();}));}
async function startQueue(){const epoch=++queueEpoch;const value=await client.startMatchmaking(selected().id);if(epoch!==queueEpoch)return;updateQueue(value);}
function updateQueue(value){if(value.status==='matched'){enter(value.room);return;}if(value.status!=='waiting'){queue=null;home();return;}setHomeActive(false);queue={...value,elapsed_ms:(value.elapsed_ms||0)+(value===queue?performance.now()-value.receivedAt:0),receivedAt:performance.now()};main.innerHTML=`<section class="match-panel"><p class="eyebrow">QUICK MATCH · 双人对战</p><div class="match-mark">◇</div><h2>群鸦正在寻找对手</h2><p>出战牌组已锁定：${esc(value.deck?.name||'已锁定军团')}</p><p class="muted">匹配成功后同时揭晓阵营与领袖。<br>取消匹配后可以更换牌组。</p><p class="match-elapsed">已等待 <strong id="elapsed">${Math.floor(queue.elapsed_ms/1000)}</strong> 秒</p>${button('取消匹配','cancel-match')}<small>等待期间请保持页面在线</small></section>`;
 bind('cancel-match',()=>run(async()=>{queueEpoch++;clearTimeout(queueTimer);try{updateQueue(await client.cancelMatchmaking(queue.ticket));}catch(e){updateQueue(queue);throw e;}}));
 clearTimeout(queueTimer);const epoch=queueEpoch;queueTimer=setTimeout(async()=>{try{const result=await client.heartbeatMatchmaking(queue.ticket);if(epoch===queueEpoch)updateQueue(result);}catch(e){if(epoch===queueEpoch){feedback(e.message+'，正在重连…',true);queueTimer=setTimeout(()=>{if(epoch===queueEpoch)updateQueue(queue);},2000);}}},4500);}
function render(){if(!room)return home();setHomeActive(false);const s=room.state,you=s.seat,me=s.players[you];if(selection&&!me.hand?.some(c=>c.id===selection))selection=null;
 if(s.phase==='waiting'){document.body.classList.remove('battle');main.innerHTML=`<div class="room-bar"><div><small>邀请朋友加入</small><strong id="room-code">${esc(room.code)}</strong></div><div class="actions">${!s.players[1]?button('发布到公共频道','publish-room','secondary'):''}${button('离开房间','leave','secondary')}</div></div><div class="players">${s.players.map((p,i)=>`<section class="player-panel" data-player="${i}">${p&&i===you?`<img class="room-leader" src="${esc(data.cards[p.selection.leader].art)}" alt="">`: '<span class="hidden-army">◇</span>'}${p?`${identity(p,i===you)}<p class="eyebrow">${p.locked?'军团已锁定':'正在整备'}</p><h2>${i===you?esc(data.factions[p.selection.faction]):'阵营待揭晓'}</h2><p>${i===you?esc(data.cards[p.selection.leader].name):'双方锁定后，同时公开阵营与领袖'}</p>${i===you&&!p.locked?button('更换牌组','room-deck','secondary'):''}`:'<h2>等待来客</h2><p>分享上方房间码，邀请对手加入。</p>'}</section>`).join('')}</div><div class="room-actions">${button(me.locked?'解锁牌组':'锁定牌组','lock-deck')}<p>双方锁定后自动进入换牌阶段</p></div>`;bind('publish-room',()=>run(async()=>{await client.channelChallenge(room.room_id);feedback('约战已发布到公共频道');render();}));bind('leave',()=>run(()=>act('leave')));bind('room-deck',deckPicker);bind('lock-deck',()=>run(()=>act(me.locked?'unlock':'lock')));}
 else if(s.phase==='choose_first'){main.innerHTML=`<section class="match-panel"><p class="eyebrow">寒霜盟约 · 先手选择</p><h2>${s.chooser===you?'谁先踏入战场？':'对手正在选择先手'}</h2>${s.chooser===you?button('我先行动','first-self')+button('对手先行动','first-other','secondary'):''}</section>`;bind('first-self',()=>run(()=>act('first',{seat:you})));bind('first-other',()=>run(()=>act('first',{seat:1-you})));}
 else if(s.phase==='mulligan'){main.innerHTML=`<section class="prep"><p class="eyebrow">PREPARE YOUR HAND</p><h2>${me.mulligan_done?'等待对手完成换牌':'选择最多两张手牌替换'}</h2><p class="muted">起手7张，第二与第三局各抽2张。每排4个单位位；为英雄与后续小局留出空间。</p><div class="hand">${me.hand.map(c=>card(c,`data-pick="${c.id}"`,picks.has(c.id))).join('')}</div>${!me.mulligan_done?button('保留手牌 / 确认换牌','confirm-mulligan'):''}</section>`;document.querySelectorAll('[data-pick]').forEach(n=>n.onclick=()=>{if(me.mulligan_done)return;if(picks.has(n.dataset.pick))picks.delete(n.dataset.pick);else if(picks.size<2)picks.add(n.dataset.pick);render();});bind('confirm-mulligan',()=>run(async()=>{await act('mulligan',{cards:[...picks]});picks.clear();}));}
 else battle();images();tick();if(s.pending?.options)requestAnimationFrame(()=>document.querySelector('.choice-panel')?.scrollIntoView({block:'nearest'}));}
function battle(){document.body.classList.add('battle');const s=room.state,you=s.seat,me=s.players[you],enemy=s.players[1-you],moves=s.legal_moves||[],chosen=me.hand?.find(c=>c.id===selection),available=moves.filter(m=>m.action==='play'&&m.payload.card===selection),isStory=s.mode==='story';
 const panel=(p,i)=>`<aside class="army-summary">${identity(p,i===you)}<div class="score">${p.score}<small>总战力</small></div><p class="gems">${'◆'.repeat(s.lives[i])}${'◇'.repeat(2-s.lives[i])}</p><p class="faction-name">${emblem(p.faction)}${esc(data.factions[p.faction])}</p><small>${esc(data.cards[p.leader].name)}</small><p class="muted">手牌 ${p.hand_count} · 牌库 ${p.deck_count} · 弃牌 ${p.discard.length}</p>${p.passed?'<b class="passed">已停手</b>':''}<button data-grave="${i}" class="secondary">查看弃牌</button></aside>`;
 const lane=(p,i,r)=>{const destination=chosen&&cardData(chosen).abilities.includes('spy')?1-you:you;const playable=i===destination&&available.some(m=>m.payload.row===r);return `<div class="combat-row ${playable?'eligible':''}" data-row="${r}" data-seat="${i}"><div class="row-title"><img src="../assets/classic/ui/row-${['melee','ranged','siege'][r]}.svg" alt=""><span>${rows[r]}</span><b>${p.row_scores[r]}</b><small>${p.rows[r].length}/4</small></div><div class="row-slots">${Array.from({length:4},(_,slot)=>p.rows[r][slot]?`<div class="unit-slot occupied">${card(p.rows[r][slot],`data-inspect="${p.rows[r][slot].id}"`)}<small class="unit-status">${p.rows[r][slot].power_detail.shield?'盾 '+p.rows[r][slot].power_detail.shield:''}${p.rows[r][slot].power_detail.sealed?' 封印':''}</small></div>`:`<div class="unit-slot empty-slot"><span>${playable?'部署':'◇'}</span></div>`).join('')}</div></div>`;};
 const spells=(p)=>`<div class="spell-slots" aria-label="持续术区">${Array.from({length:3},(_,i)=>p.spells[i]?`<button data-spell="${p.spells[i].id}" title="${esc(desc(cardData(p.spells[i])))}"><img src="${esc(cardData(p.spells[i]).art)}" alt=""><b>${esc(cardData(p.spells[i]).name)}</b><small>${p.spells[i].row>=0?rows[p.spells[i].row]:'指定目标'} · 占位</small></button>`:`<div class="empty-spell">持续术位 ${i+1}</div>`).join('')}</div>`;

 main.innerHTML=`<div class="battle-top"><div><p class="eyebrow">${isStory?`STORY · 第 ${s.story.chapter} 章 · ${esc(s.story.title)}`:'V3 · FOUR SLOTS PER ROW'}</p><b>第 ${s.round} 局</b></div><strong>${s.phase==='finished'?(s.winner===null?'平局':s.winner===you?(isStory?'关卡完成':'你赢得了对局'):(isStory?'挑战失败':'对手赢得了对局')):s.phase==='round_result'?'本局结束':s.pending?(s.pending.actor===you?'请选择卡牌':'对手正在选择卡牌'):s.turn===you?'轮到你行动':isStory?'对手正在行动':'等待对手行动'}</strong><span id="countdown"></span></div><section class="army enemy">${panel(enemy,1-you)}<div class="lanes">${spells(enemy)}${[2,1,0].map(r=>lane(enemy,1-you,r)).join('')}</div></section><div class="battle-divider"><span>◇</span> 每排4位 · 战力归零即阵亡 <span>◇</span></div><section class="army self">${panel(me,you)}<div class="lanes">${[0,1,2].map(r=>lane(me,you,r)).join('')}${spells(me)}</div></section><section class="hand-area"><div class="hand-label"><b>你的手牌 · ${me.hand_count}</b><span>点击卡牌，再选择部署战列</span></div><div class="hand">${(me.hand||[]).map(c=>card(c,`data-hand="${c.id}"`,selection===c.id)).join('')}</div></section><div class="controls"><div class="selection-info"><strong>${chosen?esc(cardData(chosen).name):'以少胜多，为下一局留牌'}</strong><p>${chosen?esc(desc(cardData(chosen)))+(!available.length&&s.turn===you&&!s.pending?' · 当前不可出牌：战列/术位已满，或没有合法目标。':''):'双方停手后结算本局；停手后本局不能再次行动。'}</p></div>${available.some(m=>m.payload.row===-1)?button('打出此牌','play-special'):''}${moves.some(m=>m.action==='leader')?button('领袖能力','use-leader','secondary'):''}${moves.some(m=>m.action==='pass')?button('本局停手','pass'):''}${s.phase==='finished'?(isStory?button('返回章节','leave','secondary'):(moves.some(m=>m.action==='rematch')?button('再战一局','rematch'):'<span>等待对手再战</span>')+button('返回大厅','leave','secondary')):button('认输','concede','secondary')}</div>${s.events?.length?`<div class="battle-log" aria-live="polite">${s.events.map(esc).join(' · ')}</div>`:''}${s.pending?.options?`<section class="choice-panel"><p class="eyebrow">${esc(s.pending.title)}</p><div class="target-options">${s.pending.options.map(o=>`<button data-option="${esc(o.token)}">${o.card?`<img src="${esc(cardData(o.card).art)}" alt="">`:''}<span>${esc(o.label)}${o.hint?`<small>${esc(o.hint)}</small>`:''}</span></button>`).join('')}</div></section>`:''}`;

 document.querySelectorAll('[data-hand]').forEach(n=>n.onclick=()=>{selection=selection===n.dataset.hand?null:n.dataset.hand;render();});
 document.querySelectorAll('.eligible').forEach(n=>n.onclick=e=>{if(e.target.closest('[data-inspect]'))return;run(()=>act('play',{card:selection,row:Number(n.dataset.row)}));});
 document.querySelectorAll('[data-option]').forEach(n=>n.onclick=()=>run(()=>act('choose',{option:n.dataset.option})));
 document.querySelectorAll('[data-inspect]').forEach(n=>n.onclick=()=>inspectCard(s.players.flatMap(p=>p.rows.flat()).find(c=>c.id===n.dataset.inspect)));
 document.querySelectorAll('[data-spell]').forEach(n=>n.onclick=()=>inspectCard(s.players.flatMap(p=>p.spells).find(c=>c.id===n.dataset.spell)));
 document.querySelectorAll('[data-grave]').forEach(n=>n.onclick=()=>modal(`<h2>弃牌</h2><div class="hand">${s.players[Number(n.dataset.grave)].discard.map(c=>card(c)).join('')||'暂无弃牌'}</div>`));
 bind('play-special',()=>run(()=>act('play',{card:selection,row:-1})));bind('use-leader',()=>run(()=>act('leader')));bind('pass',()=>run(()=>act('pass')));bind('rematch',()=>run(()=>act('rematch')));bind('leave',()=>run(()=>act('leave')));
 bind('concede',()=>modal(`<h2>结束这场对局？</h2><p>认输后对手赢得本场对局。</p>${button('确认认输','confirm-concede')}`));
 if($('concede'))$('concede').addEventListener('click',()=>bind('confirm-concede',()=>run(async()=>{$('modal').close();await act('concede');})));
}
function tick(){if(queue&&$('elapsed'))$('elapsed').textContent=Math.floor(((queue.elapsed_ms||0)+performance.now()-queue.receivedAt)/1000);if(room&&$('countdown')){const n=remainingSeconds(room.state,receivedAt);$('countdown').textContent=n===null?'':n+' 秒';}}
async function boot(){profile=await client.boot();if(profile.matchmaking?.status==='waiting'&&profile.matchmaking.rules_version!==3){location.replace((profile.matchmaking.rules_version===2?'../classic/':'../')+location.search+location.hash);return;}data=await(await fetch('./cards.json')).json();decks=(await client.decks()).decks;if(!decks.length){for(const d of data.starters)await client.saveDeck(d);decks=(await client.decks()).decks;}selectedDeck=decks[0].id;client.sdk?.loading?.ready?.();if(profile.room_id)enter(await client.snapshot(profile.room_id));else if(profile.matchmaking?.status==='waiting'&&profile.matchmaking.rules_version===3){queueEpoch++;updateQueue(profile.matchmaking);}else home();}
bind('close-modal',()=>$('modal').close());bind('home',e=>{e.preventDefault();if(!room&&!queue)home();});bind('reconnect',()=>run(async()=>{if(room)accept(await client.snapshot());else await boot();}));
bind('channel-toggle',()=>toggleChannel(true));bind('channel-close',()=>toggleChannel(false));
bind('channel-challenge',()=>run(async()=>publishChallenge(await client.create(selected().id))));
function sendChannel(){const input=$('channel-input'),text=input.value.trim();if(!text)return;run(async()=>{await client.channelPost(text);input.value='';await channelRefresh();});}
bind('channel-send',sendChannel);$('channel-input').onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();sendChannel();}};
bind('fullscreen',()=>run(async()=>{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}));
bind('rules',()=>modal(`<h2>四格战阵 · 第三版</h2><div class="rule-text"><p>每方两点生命，小局败者失去一点，平局双方各失去一点。最多三小局，手牌跨局保留。</p><p>牌组恰好20张，至少14张单位（含最多2张英雄），术卡最多6张。起手7张，最多换2张；第二和第三局各抽2张。</p><p>每次行动出一张牌、使用领袖或停手。三排各4个单位位，满排不能部署；召集只拉牌库中的牌，受空位限制。间谍占对方一格，整场每张只抽牌一次。</p><p>战力 = 基础 + 强化 + 条件 − 伤害，归零即死亡。强化最多+4，护盾最多3。英雄可受伤、被封印，条件随场面实时变化；英雄和间谍不能复活。</p><p>每方有3个持续术位，即时术结算后弃置。术位满时不能再打持续术。号角、鼓舞及旧阵营免费被动已移除。</p></div>`));
setInterval(tick,250);run(boot);
