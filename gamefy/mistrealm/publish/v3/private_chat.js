const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function setupPrivateChat({client,visible,onRead,onBack}){
 const $=id=>document.getElementById(id),drafts=new Map(),pending=new Map();
 let peer=null,items=[],epoch=0,loading=false,sending=false,reading=false,lastRead=0,more=false,refreshAgain=false;
 const feedback=text=>{$('private-feedback').textContent=text;};
 const atBottom=()=>{const n=$('private-messages');return n.scrollHeight-n.scrollTop-n.clientHeight<35;};
 const shown=()=>peer&&visible()&&!document.hidden;
 function saveDraft(){if(peer)drafts.set(peer.uid,$('private-input').value);}
 function draw(bottom=false,prepend=false){
  const list=$('private-messages'),top=list.scrollTop;
  list.innerHTML=items.map(m=>`<article class="private-message ${m.outgoing?'outgoing':'incoming'}"><small>${m.outgoing?'你':esc(peer.name)} · ${esc(new Date(m.created_at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}))}</small><p>${esc(m.text)}</p></article>`).join('')||'<div class="private-empty">向好友打声招呼吧<br><small>对方离线时，也能收到你的留言</small></div>';
  $('private-older').hidden=!more;
  if(bottom)list.scrollTop=list.scrollHeight;
  else list.scrollTop=prepend?0:top;
 }
 async function markRead(){
  if(!shown()||!atBottom()||reading||!items.length)return;
  const through=items.at(-1).id,token=epoch,target=peer.uid;
  if(through<=lastRead)return;
  reading=true;
  try{const result=await client.privateRead(target,through);if(token===epoch){lastRead=through;onRead(result.unread_messages);}}
  catch(e){if(token===epoch)feedback(e.message);}
  finally{if(token===epoch)reading=false;}
 }
 async function refresh(older=false){
  if(!peer)return;
  if(loading){if(!older)refreshAgain=true;return;}
  const token=epoch,target=peer.uid,initial=!items.length,bottom=initial||atBottom();loading=true;
  $('private-older').disabled=true;
  try{
   let catchUp;
   do{
   const cursor=older?{before:items[0]?.id}:items.length?{after:items.at(-1).id}:{};
   const value=await client.privateMessages(target,cursor);
   catchUp=!!cursor.after&&value.has_more&&value.items.length>0;
   if(token!==epoch)return;
   peer=value.player;$('private-name').textContent=peer.name;$('private-status').textContent=value.online?'在线 · 仅你们可见':'离线 · 留言将在上线后收到';
   if(initial||older)more=value.has_more;
   if(value.items.length||initial){items=[...new Map([...items,...value.items].map(m=>[m.id,m])).values()].sort((a,b)=>a.id-b.id);draw(!older&&bottom,older);}
   }while(catchUp&&token===epoch);
   if(!older)await markRead();
  }catch(e){if(token===epoch)feedback(e.message);}
  finally{if(token===epoch){loading=false;$('private-older').disabled=false;if(refreshAgain){refreshAgain=false;void refresh();}}}
 }
 async function send(){
  if(!peer||sending)return;
  const text=$('private-input').value.trim();if(!text)return;
  const token=epoch,target=peer.uid;
  let request=pending.get(target);
  if(!request||request.text!==text){request={text,id:crypto.randomUUID()};pending.set(target,request);}
  sending=true;$('private-send').disabled=true;feedback('发送中…');
  try{
   await client.privateSend(target,text,request.id);pending.delete(target);
   if(token!==epoch){if(drafts.get(target)?.trim()===text)drafts.delete(target);return;}
   if($('private-input').value.trim()===text){$('private-input').value='';drafts.delete(target);}
   feedback('');await refresh();
  }catch(e){if(token===epoch)feedback(`${e.message}，可点发送重试`);}
  finally{if(token===epoch){sending=false;$('private-send').disabled=false;}}
 }
 function open(player){
  saveDraft();peer=player;items=[];epoch++;loading=false;sending=false;reading=false;lastRead=0;more=false;refreshAgain=false;
  $('private-name').textContent=peer.name;$('private-status').textContent='正在加载…';
  $('private-input').value=drafts.get(peer.uid)||'';$('private-send').disabled=false;feedback('');draw();void refresh();
 }
 function close(){saveDraft();peer=null;epoch++;}
 $('private-send').onclick=send;$('private-older').onclick=()=>refresh(true);
 $('private-back').onclick=()=>{close();onBack();};
 $('private-input').oninput=saveDraft;
 $('private-input').onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();void send();}};
 $('private-messages').onscroll=()=>void markRead();
 return {open,close,refresh,active:()=>!!peer};
}
