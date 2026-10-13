import {DoudizhuClient} from './client.js';
import {cardElement,cardLabel,selectGesture,toggleSelection} from './cards.js';

const $=id=>document.getElementById(id);
const kinds={single:'单张',pair:'对子',triple:'三张',triple_single:'三带一',triple_pair:'三带一对',straight:'顺子',pair_straight:'连对',airplane:'飞机',airplane_single:'飞机带单',airplane_pair:'飞机带对',four_single:'四带二',four_pair:'四带两对',bomb:'炸弹',rocket:'王炸'};
const phases={waiting:'等待三人入座准备',bidding:'叫分定地主',playing:'正在对局',finished:'本局结束',cancelled:'房间已取消'};
let client,state,roomId=null,stop=null,selected=new Set(),busy=false,handKey='',controlsKey='',hintIndex=0,lastVersion=null,clockOffset=0;
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
  $('lobby').hidden=true;$('table').hidden=false;
  text('room-label',`房间 ${state.short_id}`);text('multiplier',`× ${state.multiplier}`);
  const self=state.seat,others=self===null?[0,1,2]:[(self+1)%3,(self+2)%3];
  $('opponents').replaceChildren(...others.map(player));$('self').replaceChildren(...(self===null?[]:[player(self)]));
  $('bottom').replaceChildren(...(state.bottom.length?state.bottom.map(id=>cardElement(id,true)):Array.from({length:3},()=>{const el=document.createElement('span');el.className='card small';el.textContent='♠';return el;})));
  text('phase-label',phases[state.phase]);tick();
  $('plays').replaceChildren(...state.table.map((p,i)=>{const el=document.createElement('div');el.className='play';const name=document.createElement('small');name.textContent=state.players[i]?.name||'';el.append(name);const value=document.createElement('span');value.textContent=p?(p.kind==='pass'?'不出':`${kinds[p.kind]} ${p.cards.map(cardLabel).join(' ')}`):' ';el.append(value);return el;}));
  const key=JSON.stringify([state.phase,state.seat,state.version]);
  if(key!==controlsKey){
    controlsKey=key;hintIndex=0;$('actions').replaceChildren();
    $('claim-panel').hidden=state.phase!=='waiting'||self!==null||!state.players.includes(null);
    if(self!==null&&state.phase==='waiting')$('actions').append(button(state.players[self].ready?'取消准备':'准备',state.players[self].ready?'unready':'ready'),button('离开席位','leave'));
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
async function enter(id){
  stop?.();roomId=id;state=null;selected.clear();controlsKey=handKey='';lastVersion=null;
  const next=await client.snapshot(id);render(next);feedback('');
  try{await client.sdk.kv.put(`doudizhu:last-room:${client.uid}`,id);await client.sdk.kv.flush?.();}catch{}
  location.hash=`room=${id}`;stop=client.follow(id,render);
}
async function lobby(restore=false){
  stop?.();roomId=null;state=null;selected.clear();$('table').hidden=true;$('lobby').hidden=false;
  await client.identity(true);const rooms=await client.rooms();
  if(restore&&location.hash!=='#lobby'){
    const requested=/^#room=([a-f0-9-]{36})$/i.exec(location.hash)?.[1];
    let saved=requested;
    if(!saved)try{saved=(await client.sdk.kv.get(`doudizhu:last-room:${client.uid}`))?.value;}catch{}
    if(typeof saved==='string'&&/^[a-f0-9-]{36}$/i.test(saved))try{await enter(saved);return;}catch{roomId=null;state=null;}
  }
  $('rooms').replaceChildren(...rooms.map(r=>{const b=document.createElement('button');b.textContent=`${r.short_id} · ${phases[r.phase]} · ${r.occupied}/3 人`;b.onclick=()=>enter(r.id).catch(e=>feedback(e.message));return b;}));
  if(!rooms.length)text('rooms','暂无牌局，请在群里发送 /斗地主');feedback('');
}
$('claim').onclick=()=>{const code=$('code').value.trim();if(!/^\d{4}$/.test(code)){feedback('请输入四位数字入座码');return;}perform('claim',{code});};
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
$('back').onclick=()=>{location.hash='lobby';lobby().catch(e=>feedback(e.message));};
$('refresh').onclick=()=>boot();
async function boot(){try{if(!window.DOUDIZHU_CONFIG?.apiBase)throw new Error('游戏后端尚未配置');if(!window.dzmm?.user)throw new Error('请从平台游戏卡进入');if(!client)client=new DoudizhuClient({sdk:window.dzmm,apiBase:window.DOUDIZHU_CONFIG.apiBase});await lobby(true);}catch(e){feedback(e.message);}finally{window.dzmm?.loading?.ready?.();}}
setInterval(tick,500);boot();
