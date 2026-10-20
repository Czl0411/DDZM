import {DoudizhuClient,withTimeout} from './client.js';
import {cardElement,cardLabel,selectGesture,toggleSelection} from './cards.js';

const $=id=>document.getElementById(id);
const kinds={single:'单张',pair:'对子',triple:'三张',triple_single:'三带一',triple_pair:'三带一对',straight:'顺子',pair_straight:'连对',airplane:'飞机',airplane_single:'飞机带单',airplane_pair:'飞机带对',four_single:'四带二',four_pair:'四带两对',bomb:'炸弹',rocket:'王炸'};
const phases={waiting:'等待三人入座准备',bidding:'叫分定地主',playing:'正在对局',finished:'本局结束',cancelled:'房间已取消'};
let client,state,roomId=null,stop=null,selected=new Set(),busy=false,handKey='',controlsKey='',hintIndex=0,lastVersion=null,clockOffset=0;
let navigation=0,savedRoomWrites=Promise.resolve();
let booting=false,bootStage='start',bootStarted=0;
function startupStage(stage,message){
  if(!booting)return;
  bootStage=stage;feedback(message);
  window.dzmm?.loading?.progress?.({phase:'runtime_initializing',message});
  window.dzmm?.log?.info?.('斗地主启动阶段',{stage,elapsedMs:Date.now()-bootStarted},'DDZ_BOOT_STAGE');
}
const text=(id,value)=>{$(id).textContent=value;};
function feedback(value,animate=false){const el=$('feedback');el.classList.remove('celebrate');text('feedback',value);if(animate){void el.offsetWidth;el.classList.add('celebrate');}}
function button(label,action,payload={}){const b=document.createElement('button');b.textContent=label;b.dataset.action=action;if(action==='bid')b.dataset.score=payload.score;b.onclick=()=>perform(action,payload);return b;}
function player(i){
  const p=state.players[i],el=document.createElement('div');el.className='player'+(state.turn===i?' active':'');
  const name=document.createElement('strong');name.textContent=p?p.name:'等待入座';el.append(name);
  const info=document.createElement('small');
  info.textContent=!p?'空席位':state.phase==='waiting'?(p.ready?'已准备':'未准备'):`${state.landlord===null?'待定':state.landlord===i?'地主':'农民'} · 剩 ${p.count} 张${p.count<=2?'！':''}${p.trustee?' · 托管':''}${p.online?' · 在线':' · 离线'}`;
  el.append(info);return el;
}
function paintHand(){
  const key=JSON.stringify([state.hand,[...selected]]);if(key===handKey)return;handKey=key;
  $('hand').replaceChildren(...[...state.hand].sort((a,b)=>b-a).map(id=>{const el=cardElement(id);el.classList.toggle('selected',selected.has(id));el.setAttribute('aria-pressed',String(selected.has(id)));return el;}));
}
function tick(){
  if(!state?.deadline){text('countdown','');return;}
  const seconds=Math.max(0,Math.ceil((Date.parse(state.deadline)-(Date.now()+clockOffset))/1000));
  text('countdown',state.phase==='waiting'?`准备剩余 ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`:`${state.players[state.turn]?.name||''} · ${seconds} 秒`);
}
function render(next,error){
  if(error){feedback(error.message);return;}
  if(!next||next.id!==roomId)return;
  if(state?.round_id!==next.round_id){selected.clear();hintIndex=0;}
  if(state&&next.round_id===state.round_id&&next.version<state.version)return;
  state=next;clockOffset=Date.parse(next.server_time)-Date.now();
  selected=new Set([...selected].filter(c=>state.hand.includes(c)));
  document.body.classList.add('table-open');$('lobby').hidden=true;$('table').hidden=false;
  text('room-label',`${state.creator_name||'玩家'}的房间`);text('multiplier',`× ${state.multiplier}`);
  const self=state.seat,others=self===null?[0,1,2]:[(self+1)%3,(self+2)%3];
  $('opponents').replaceChildren(...others.map(player));$('self').replaceChildren(...(self===null?[]:[player(self)]));
  $('bottom').replaceChildren(...(state.bottom.length?state.bottom.map(id=>cardElement(id,true)):Array.from({length:3},()=>{const el=document.createElement('span');el.className='card small';el.textContent='♠';return el;})));
  text('phase-label',phases[state.phase]);tick();
  $('plays').replaceChildren(...state.table.map((p,i)=>{const el=document.createElement('div');el.className='play';const name=document.createElement('small');name.textContent=state.players[i]?.name||'';el.append(name);const value=document.createElement('span');value.textContent=p?(p.kind==='pass'?'不出':`${kinds[p.kind]} ${p.cards.map(cardLabel).join(' ')}`):' ';el.append(value);return el;}));
  const key=JSON.stringify([state.phase,state.seat,state.version]);
  if(key!==controlsKey){
    controlsKey=key;hintIndex=0;$('actions').replaceChildren();
    $('claim-panel').hidden=state.phase!=='waiting'||self!==null||!state.players.includes(null);
    if(self!==null&&state.phase==='waiting')$('actions').append(button(state.players[self].ready?'取消准备':'准备',state.players[self].ready?'unready':'ready'),button(state.rematch_waiting?'退出并结束房间':'离开席位','leave'));
    if(self!==null&&state.phase==='bidding'&&state.turn===self){for(const score of [0,1,2,3])if(!score||score>state.bid)$('actions').append(button(score?`${score} 分`:'不叫','bid',{score}));}
    if(self!==null&&['bidding','playing'].includes(state.phase))$('actions').append(button(state.players[self].trustee?'取消托管':'托管',state.players[self].trustee?'resume':'takeover'));
    if(self!==null&&state.phase==='finished')$('actions').append(button('再来一局','rematch'));
  }
  const myTurn=self!==null&&state.phase==='playing'&&state.turn===self;
  $('play-actions').hidden=!myTurn;$('pass').disabled=!state.previous;$('pass').title=state.previous?'':'首家必须出牌';
  paintHand();
  $('messages').replaceChildren(...state.messages.map(m=>{const el=document.createElement('p');el.textContent=`${m.name}：${m.text}`;return el;}));
  const canChat=['waiting','bidding','playing'].includes(state.phase);$('chat-input').disabled=!canChat;$('chat-send').disabled=!canChat;
  $('result').hidden=!state.result;
  if(state.result){const title=document.createElement('h2');title.textContent=self===null?(state.result.winner==='landlord'?'地主胜利':'农民胜利'):(state.result.winners.includes(self)?'胜利！':'本局落败');const detail=document.createElement('p');detail.textContent=state.result.winners.map(i=>state.players[i]?.name).join('、')+' 获胜'+(state.result.spring==='spring'?' · 春天':state.result.spring==='reverse_spring'?' · 反春':'');$('result').replaceChildren(title,detail);}
  if(lastVersion!==null&&lastVersion!==state.version){const event=state.events.at(-1);if(event?.play)feedback(`${state.players[event.seat]?.name} · ${kinds[event.play.kind]}`,['straight','pair_straight','airplane','airplane_single','airplane_pair','bomb','rocket'].includes(event.play.kind));if(state.result?.spring)feedback(state.result.spring==='spring'?'春天！':'反春！',true);}
  lastVersion=state.version;
}
async function perform(action,payload={}){
  if(busy||!state)return;busy=true;
  const id=roomId,envelope={round_id:state.round_id,version:state.version,request_id:crypto.randomUUID(),action,payload};
  try{const next=await client.action(id,envelope);selected.clear();feedback('');render(next);}
  catch(error){feedback(error.message);try{render(await client.snapshot(id));}catch{}}
  finally{busy=false;}
}
function rememberRoom(id,uid=client.uid){
  const generation=navigation;
  savedRoomWrites=savedRoomWrites.then(async()=>{if(generation!==navigation||uid!==client.uid)return;await client.sdk.kv.put(`doudizhu:last-room:${uid}`,id,{flush:true});}).catch(()=>{});
}
async function enter(id){
  const generation=++navigation;
  const started=Date.now();let stage='request';
  const trace=(code)=>window.dzmm?.log?.info?.(code,{elapsedMs:Date.now()-started},code);
  trace('DDZ_ROOM_ENTER');feedback('正在进入房间…');
  try{
  stop?.();roomId=id;state=null;selected.clear();controlsKey=handKey='';lastVersion=null;
  const next=await client.snapshot(id);if(generation!==navigation)return;
  trace('DDZ_ROOM_FETCHED');stage='render';render(next);feedback('');
  trace('DDZ_ROOM_RENDERED');stage='connection';
  stop=client.follow(id,render);
  trace('DDZ_ROOM_FOLLOW_STARTED');
  rememberRoom(id);
  }catch(e){
    if(generation!==navigation)return;
    const code=`DDZ_ROOM_${stage.toUpperCase()}_FAILED`;
    window.dzmm?.log?.error?.(code,{stage,elapsedMs:Date.now()-started,status:e.status||null,errorType:e.name},code);
    feedback(`进入房间失败：${e.message}（${code}），请重试`);
    throw e;
  }
}
async function lobby(restore=false){
  const generation=++navigation;
  stop?.();roomId=null;state=null;selected.clear();document.body.classList.remove('table-open');$('table').hidden=true;$('lobby').hidden=false;
  $('rooms').replaceChildren();
  startupStage('identity','正在读取玩家身份…');
  await client.identity(true);if(generation!==navigation)return;
  startupStage('rooms','正在连接游戏服务器…');
  const rooms=await client.rooms();if(generation!==navigation)return;
  if(!restore)rememberRoom(null);
  if(restore){
    startupStage('storage','正在读取上次牌局…');
    const saved=(await withTimeout(client.sdk.kv.get(`doudizhu:last-room:${client.uid}`),'读取上次牌局'))?.value;
    if(generation!==navigation)return;
    if(typeof saved==='string'&&/^[a-f0-9-]{36}$/i.test(saved))try{startupStage('restore','正在恢复牌局…');await enter(saved);return;}catch(e){if(![403,404,409].includes(e.status))throw e;roomId=null;state=null;}
  }
  $('rooms').replaceChildren(...rooms.map(r=>{const b=document.createElement('button');b.className='room-card';const copy=document.createElement('span');const title=document.createElement('strong');const meta=document.createElement('small');const action=document.createElement('b');title.textContent=`${r.creator_name}的牌桌`;meta.textContent=`${r.room_type==='coin'?`${r.stake} 币场`:'休闲场'} · ${phases[r.phase]} · ${r.occupied}/3 人`;action.textContent=r.phase==='waiting'?'加入牌桌':'进入观战';copy.append(title,meta);b.append(copy,action);b.onclick=()=>enter(r.id).catch(e=>feedback(e.message));return b;}));
  if(!rooms.length)text('rooms','暂无牌局，可以先开一桌');feedback('');
}
$('claim').onclick=()=>perform('claim');
document.querySelectorAll('[data-create-room]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{const next=await client.create(button.dataset.createRoom,Number(button.dataset.stake));await enter(next.id);}catch(error){feedback(error.message);}finally{button.disabled=false;}});
$('play').onclick=()=>{if(!selected.size){feedback('请先选择要出的牌');return;}perform('play',{cards:[...selected]});};
$('pass').onclick=()=>perform('pass');
$('hint').onclick=async()=>{try{const id=roomId,version=state.version,plays=await client.suggestions(id);if(id!==roomId||version!==state.version)return;if(!plays.length){feedback('没有能压过的牌，可以选择不出');return;}selected=new Set(plays[hintIndex++%plays.length].cards);paintHand();}catch(e){feedback(e.message);}};
let visited=null;
function touchCard(target){const card=target?.closest?.('#hand .card');if(card&&visited){selected=selectGesture(selected,Number(card.dataset.card),visited);for(const el of $('hand').children){const active=selected.has(Number(el.dataset.card));el.classList.toggle('selected',active);el.setAttribute('aria-pressed',String(active));}}}
$('hand').addEventListener('pointerdown',e=>{if(!e.target.closest('.card'))return;visited=new Set();touchCard(e.target);e.preventDefault();});
document.addEventListener('pointermove',e=>{if(visited)touchCard(document.elementFromPoint(e.clientX,e.clientY));});
for(const event of ['pointerup','pointercancel'])document.addEventListener(event,()=>{visited=null;handKey='';});
$('hand').addEventListener('click',e=>{if(e.detail!==0)return;const card=e.target.closest('.card');if(card){selected=toggleSelection(selected,Number(card.dataset.card));paintHand();}});
let chatBusy=false;
async function sendChat(){if(chatBusy||!state)return;const value=$('chat-input').value.trim();if(!value)return;chatBusy=true;try{await client.chat(roomId,{round_id:state.round_id,request_id:crypto.randomUUID(),text:value});$('chat-input').value='';render(await client.snapshot(roomId));}catch(e){feedback(e.message);}finally{chatBusy=false;}}
$('chat-send').onclick=sendChat;$('chat-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();sendChat();}});
$('back').onclick=async()=>{try{if(state?.phase==='waiting'&&state?.seat!==null)await client.action(roomId,{round_id:state.round_id,version:state.version,request_id:crypto.randomUUID(),action:'leave',payload:{}});}catch(e){feedback(e.message);}finally{lobby().catch(e=>feedback(e.message));}};
$('refresh').onclick=()=>boot();
async function boot(){
  if(booting)return;
  booting=true;bootStage='start';bootStarted=Date.now();$('refresh').disabled=true;
  window.dzmm?.loading?.progress?.({phase:'start',message:'正在启动斗地主'});
  try{
    if(!window.DOUDIZHU_CONFIG?.apiBase)throw new Error('游戏后端尚未配置');
    if(!window.dzmm?.user)throw new Error('请从平台游戏卡进入');
    if(!client)client=new DoudizhuClient({sdk:window.dzmm,apiBase:window.DOUDIZHU_CONFIG.apiBase});
    await lobby(true);
    window.dzmm?.log?.info?.('斗地主启动完成',{elapsedMs:Date.now()-bootStarted},'DDZ_BOOT_READY');
    window.dzmm?.loading?.ready?.();
  }catch(e){
    const code=`DDZ_BOOT_${bootStage.toUpperCase()}`;
    const message=`${e.message}（${code}），可点击刷新重试`;
    feedback(message);
    window.dzmm?.log?.error?.('斗地主启动失败',{stage:bootStage,elapsedMs:Date.now()-bootStarted,status:e.status||null},code);
    window.dzmm?.loading?.error?.(code,message);
  }finally{booting=false;$('refresh').disabled=false;}
}
setInterval(tick,500);boot();
