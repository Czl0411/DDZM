// A separate connection from the match stream; stopping a match must not stop chat.
export function followSocial(client,onUpdate,onError){
 const controller=new AbortController(),signal=controller.signal;
 const wait=ms=>new Promise(resolve=>{
  const done=()=>{clearTimeout(timer);signal.removeEventListener('abort',done);resolve();};
  const timer=setTimeout(done,ms);signal.addEventListener('abort',done,{once:true});
 });
 const finished=(async()=>{
  let failures=0;
  while(!signal.aborted){
   const connection=new AbortController(),abort=()=>connection.abort();
   signal.addEventListener('abort',abort,{once:true});
   let watchdog;
   const touch=()=>{clearTimeout(watchdog);watchdog=setTimeout(abort,35000);};
   try{
    touch();
    const response=await client.fetchImpl(client.sharedRoot+'/social/events',{headers:{Authorization:`MistrealmUid ${client.uid}`},signal:connection.signal,redirect:'error',cache:'no-store',referrerPolicy:'no-referrer'});
    if(!response.ok||!response.body){const error=new Error('消息连接暂时中断，正在重连');error.status=response.status;throw error;}
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    const cancel=()=>reader.cancel().catch(()=>{});
    connection.signal.addEventListener('abort',cancel,{once:true});
    try{
     while(!signal.aborted){
      const {value,done}=await reader.read();if(done)throw new Error('消息连接已断开，正在重连');
      touch();buffer+=decoder.decode(value,{stream:true});
      let match;
      while((match=/\r?\n\r?\n/.exec(buffer))){
       const packet=buffer.slice(0,match.index);buffer=buffer.slice(match.index+match[0].length);
       const lines=packet.split(/\r?\n/),type=lines.find(x=>x.startsWith('event:'))?.slice(6).trim();
       if(type==='unavailable')throw new Error('消息服务暂时不可用，正在重连');
       if(type==='social'&&!signal.aborted){
        const payload=JSON.parse(lines.filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trimStart()).join('\n'));
        await onUpdate(payload);failures=0;
       }
      }
     }
    }finally{connection.signal.removeEventListener('abort',cancel);await reader.cancel().catch(()=>{});}
   }catch(error){
    if(signal.aborted)return;
    onError(error);failures++;
    if(error.status===401||error.status===403)return;
   }finally{clearTimeout(watchdog);signal.removeEventListener('abort',abort);connection.abort();}
   if(!signal.aborted)await wait(Math.min(10000,500*2**Math.min(failures,5)));
  }
 })();
 return {stop:()=>controller.abort(),finished};
}
