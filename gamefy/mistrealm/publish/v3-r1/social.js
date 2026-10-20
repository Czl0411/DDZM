import {setupPrivateChat} from './private_chat.js';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={online:'在线',offline:'离线',playing:'对战中',room:'房间中',matching:'匹配中'};
const avatar=p=>`<span class="social-avatar">${esc((p.name||'旅')[0])}${p.avatar?.startsWith('https://')?`<img src="${esc(p.avatar)}" alt="" referrerpolicy="no-referrer">`:''}</span>`;

export function setupSocial({client,ready,currentRoom,isBusy,deck,enter,openChannel,onChannel}){
 const $=id=>document.getElementById(id);
 let tab='chat',page=0,search='',summary={friend_requests:0,invitations:[]},stream=null,working=false,loadId=0,loadedRoom=null,signature='';
 const privateChat=setupPrivateChat({client,visible:()=>tab==='messages'&&!$('channel-panel').hidden,onRead:count=>{summary.unread_messages=count;notice();},onBack:()=>selectTab('messages')});
 const tell=(text,error=false)=>{$('social-feedback').textContent=text;$('social-feedback').classList.toggle('error',error);};
 function sync(){
  $('channel-chat').hidden=tab!=='chat';$('social-view').hidden=tab==='chat'||privateChat.active();$('private-chat').hidden=tab!=='messages'||!privateChat.active();
  $('channel-challenge').hidden=tab!=='chat'||isBusy();
  document.querySelectorAll('[data-social-tab]').forEach(n=>{n.classList.toggle('active',n.dataset.socialTab===tab);n.setAttribute('aria-selected',String(n.dataset.socialTab===tab));});
 }
 function pagination(total){
  const count=Math.max(1,Math.ceil(total/6));
  $('social-pages').innerHTML=`<button id="social-prev" ${page===0?'disabled':''} aria-label="上一页">‹</button><span>${page+1} / ${count} · 共 ${total} 位</span><button id="social-next" ${page+1>=count?'disabled':''} aria-label="下一页">›</button>`;
  $('social-prev').onclick=()=>{page--;void load();};$('social-next').onclick=()=>{page++;void load();};
 }
 async function execute(fn,message){
  if(working)return;working=true;
  try{await fn();tell(message);signature='';await load();}
  catch(e){tell(e.message,true);}
  finally{working=false;}
 }
 async function load(){
  const id=++loadId;
  if(tab==='chat')return;
  if(tab==='messages'&&privateChat.active()){await privateChat.refresh();return;}
  if(tab==='invites'){renderInvites();return;}
  if(tab==='messages'){await conversations(id);return;}
  try{
   const value=await client.socialPlayers(tab,search,page);
   if(id!==loadId)return;
   if(page&&page*6>=value.total){page=Math.max(0,Math.ceil(value.total/6)-1);return load();}
   const next=JSON.stringify([tab,value,isBusy()]);if(next===signature)return;signature=next;
   $('social-list').innerHTML=value.items.map(p=>`<article class="social-player" data-presence="${p.presence}">${avatar(p)}<div class="social-player-copy"><b title="${esc(p.name)}">${esc(p.name)}</b><small class="presence ${p.presence}"><i></i>${labels[p.presence]}</small></div><div class="social-actions">${p.friend==='received'?`<button data-friend="accept" data-uid="${esc(p.uid)}">同意</button><button data-friend="decline" data-uid="${esc(p.uid)}" class="quiet">忽略</button>`:p.friend==='friend'?`<button data-dm="${esc(p.uid)}">私聊</button>`:p.friend==='sent'?'<span class="friend-label">申请已发送</span>':`<button data-friend="request" data-uid="${esc(p.uid)}">加好友</button>`}${tab!=='requests'?`<button data-challenge="${esc(p.uid)}" ${p.challenge_reason||isBusy()?'disabled':''} title="${esc(p.challenge_reason||(isBusy()?'请先离开当前房间':'使用当前牌组发起挑战'))}">挑战</button>`:''}</div>${p.challenge_reason==='今日挑战已用完'?'<small class="social-limit">今日挑战已用完</small>':''}</article>`).join('')||`<div class="social-empty"><span>◇</span><b>${search?'没有找到这位旅人':tab==='friends'?'还没有好友':tab==='requests'?'暂无好友申请':'暂时没有其他玩家'}</b><p>${tab==='friends'?'在全服玩家中认识你的下一位对手。':'稍后回来看看，或换个昵称搜索。'}</p></div>`;
   pagination(value.total);
   document.querySelectorAll('[data-dm]').forEach(n=>n.onclick=()=>openPrivate(value.items.find(p=>p.uid===n.dataset.dm)));
   document.querySelectorAll('[data-friend]').forEach(n=>n.onclick=()=>execute(()=>client.friend(n.dataset.uid,n.dataset.friend),n.dataset.friend==='request'?'好友申请已发送':n.dataset.friend==='accept'?'已成为好友':'已忽略申请'));
   document.querySelectorAll('[data-challenge]').forEach(n=>n.onclick=()=>execute(async()=>{if(isBusy())throw new Error('请先离开房间或取消匹配');if(!deck())throw new Error('请先选择出战牌组');await client.challenge(n.dataset.challenge,deck().id);},'挑战已发送，等待对方接受（60秒内有效）'));
  }catch(e){if(id===loadId)tell(e.message,true);}
 }
 function renderInvites(){
  const items=summary.invitations;
  page=Math.min(page,Math.max(0,Math.ceil(items.length/6)-1));
  const states={accepted:'已接受',declined:'已拒绝',cancelled:'已取消',expired:'已过期'};
  $('social-list').innerHTML=items.slice(page*6,(page+1)*6).map(i=>`<article class="social-player invitation">${avatar(i.player)}<div class="social-player-copy"><b>${esc(i.player.name)}</b><small>${i.outgoing?'你发出的挑战':'邀请你进行对战'}</small></div><div class="social-actions">${i.status==='pending'?i.outgoing?`<span>等待回应</span><button data-invite="${i.id}" data-operation="cancel" class="quiet">取消</button>`:`<button data-invite="${i.id}" data-operation="accept" ${isBusy()?'disabled title="请先离开当前房间或取消匹配"':''}>接受</button><button data-invite="${i.id}" data-operation="decline" class="quiet">拒绝</button>`:`<span>${states[i.status]||'已结束'}</span>`}</div></article>`).join('')||'<div class="social-empty"><span>◇</span><b>暂无挑战邀请</b><p>向在线旅人发出邀请，开始一场对决。</p></div>';
  pagination(items.length);$('social-pages').querySelector('span').textContent=`${page+1} / ${Math.max(1,Math.ceil(items.length/6))} · 共 ${items.length} 条`;
  document.querySelectorAll('[data-invite]').forEach(n=>n.onclick=()=>execute(async()=>{
   if(n.dataset.operation==='accept'&&isBusy())throw new Error('请先离开房间或取消匹配');
   const response=await client.challengeReply(n.dataset.invite,n.dataset.operation,deck()?.id);
   if(response.room){loadedRoom=response.room.room_id;enter(response.room);openChannel(false);}
  },n.dataset.operation==='accept'?'已接受挑战':n.dataset.operation==='cancel'?'已取消挑战':'已拒绝挑战'));
 }
 function openPrivate(player){
  tab='messages';++loadId;privateChat.open(player);tell('');sync();
 }
 async function conversations(id){
  try{
   const value=await client.privateConversations(page);if(id!==loadId)return;
   if(page&&page*6>=value.total){page=Math.max(0,Math.ceil(value.total/6)-1);return load();}
   const next=JSON.stringify(value);if(next===signature)return;signature=next;
   $('social-list').innerHTML=value.items.map(c=>`<button class="social-player conversation" data-dm="${esc(c.player.uid)}">${avatar(c.player)}<div class="social-player-copy"><b>${esc(c.player.name)} ${c.unread?`<i class="private-unread">${c.unread}</i>`:''}</b><small class="presence ${c.online?'online':'offline'}"><i></i>${c.online?'在线':'离线'}</small></div><p class="conversation-preview">${c.message.outgoing?'你：':''}${esc(c.message.text)}</p></button>`).join('')||'<div class="social-empty"><span>◇</span><b>还没有私聊消息</b><p>在「我的好友」中点击私聊，给好友留言。</p></div>';
   pagination(value.total);$('social-pages').querySelector('span').textContent=`${page+1} / ${Math.max(1,Math.ceil(value.total/6))} · 共 ${value.total} 个会话`;
   document.querySelectorAll('[data-dm]').forEach(n=>n.onclick=()=>openPrivate(value.items.find(c=>c.player.uid===n.dataset.dm).player));
  }catch(e){if(id===loadId)tell(e.message,true);}
 }
 function notice(){
  const incoming=summary.invitations.filter(i=>!i.outgoing&&i.status==='pending').length,unread=summary.unread_messages||0,count=incoming+summary.friend_requests+unread;
  $('social-notice').hidden=!count;$('social-notice').textContent=`消息 ${count}`;$('social-notice').setAttribute('aria-label',`${incoming}条挑战，${summary.friend_requests}条好友申请，${unread}条未读私聊`);
  $('social-request-count').textContent=summary.friend_requests||'';$('social-invite-count').textContent=incoming||'';$('social-message-count').textContent=unread||'';
 }
 async function receive(packet){
  if(document.hidden)return;
  if(packet.channel)onChannel?.(packet.channel);
  if(packet.summary){
   summary=packet.summary;
   $('social-online').textContent=`在线 ${summary.online_count}`;
   notice();
   if(summary.joined_room_id&&summary.joined_room_id!==currentRoom()&&summary.joined_room_id!==loadedRoom&&!isBusy()){
    const value=await client.snapshot(summary.joined_room_id);loadedRoom=summary.joined_room_id;enter(value);openChannel(false);
   }
  }
  if(!$('channel-panel').hidden&&(packet.players_changed||packet.social_changed||packet.messages_changed))await load();
 }
 function start(){
  if(!ready()||document.hidden||stream)return;
  stream=client.followSocial(receive,e=>{
   $('social-online').textContent='重连中';if(!$('channel-panel').hidden)tell(e.message,true);
  });
 }
 function stop(){stream?.stop();stream=null;}
 function selectTab(value){
  privateChat.close();tab=value;page=0;search='';signature='';$('social-search').value='';
  $('social-search-form').hidden=tab==='invites'||tab==='messages';$('social-heading').textContent={all:'全服旅人',friends:'我的好友',requests:'好友申请',invites:'挑战邀请',messages:'好友私聊'}[tab]||'';
  $('social-description').textContent=tab==='messages'?'仅好友之间可私聊 · 离线也能留言':tab==='invites'?`当前出战：${deck()?.name||'未选择'} · 接受后双方进入整备房间。`:'在线优先 · 非好友双方每日一次挑战 · 北京时间零点重置';
  tell('');sync();void load();
 }
 document.querySelectorAll('[data-social-tab]').forEach(n=>n.onclick=()=>selectTab(n.dataset.socialTab));
 $('social-notice').onclick=()=>{openChannel(true);selectTab(summary.invitations.some(i=>!i.outgoing&&i.status==='pending')?'invites':summary.friend_requests?'requests':'messages');};
 const searchPlayers=()=>{search=$('social-search').value.trim();page=0;signature='';void load();};
 $('social-search-button').onclick=searchPlayers;$('social-search').onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();searchPlayers();}};
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();else start();});
 globalThis.addEventListener?.('pagehide',stop);
 globalThis.addEventListener?.('pageshow',start);
 return {start,stop,sync,refresh:load,showPlayer(uid){openChannel(true);selectTab('all');search=uid;$('social-search').value=uid;void load();}};
}
