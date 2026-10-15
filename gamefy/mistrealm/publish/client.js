export const requestId=()=>crypto.randomUUID();

export class MistrealmClient {
  constructor({sdk,apiBase,fetchImpl=globalThis.fetch}) {
    this.sdk=sdk; this.root=apiBase.replace(/\/$/,'')+'/api/mistrealm';
    this.fetchImpl=fetchImpl.bind(globalThis); this.uid=null; this.state=null; this.roomId=null; this.controller=null;
  }
  async request(path,options={},root=this.root) {
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try {
      const response=await this.fetchImpl(root+path,{...options,signal:controller.signal,
        headers:{Authorization:`MistrealmUid ${this.uid}`,...(options.body?{'Content-Type':'application/json'}:{})}});
      const data=await response.json();
      if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:'请求参数或服务器状态有误');error.status=response.status;throw error;}
      return data;
    } finally {clearTimeout(timer);}
  }
  async boot() {
    if(!this.sdk?.user?.info)throw new Error('无法读取平台身份，请在平台游戏卡中打开');
    let timer;
    const info=await Promise.race([this.sdk.user.info(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('读取平台身份超时，请重试')),10000);})]).finally(()=>clearTimeout(timer));
    if(typeof info?.id!=='string'||!info.id.trim())throw new Error('无法读取玩家身份');
    this.uid=info.id;
    const avatar=info.avatarUrl||info.avatar||info.avatar_url;
    await this.request('/players/me',{method:'POST',body:JSON.stringify({name:String(info.name||info.nickname||'旅人').slice(0,40),avatar:typeof avatar==='string'&&avatar.startsWith('https://')?avatar:null})});
    return this.request('/players/me');
  }
  startMatchmaking(){return this.request('/matchmaking',{method:'POST'});}
  heartbeatMatchmaking(ticket){return this.request('/matchmaking/heartbeat',{method:'POST',body:JSON.stringify({ticket})});}
  cancelMatchmaking(ticket){return this.request('/matchmaking/cancel',{method:'POST',body:JSON.stringify({ticket})});}
  create(id=requestId()){return this.request('/rooms',{method:'POST',body:JSON.stringify({request_id:id})});}
  join(code,id=requestId()){return this.request('/rooms/join',{method:'POST',body:JSON.stringify({code,request_id:id})});}
  snapshot(roomId=this.roomId){return this.request('/rooms/'+roomId);}
  action(action,payload={},id=requestId()){
    return this.request('/rooms/'+this.state.room_id+'/actions',{method:'POST',body:JSON.stringify({
      action,payload,request_id:id,version:this.state.state.version,match_id:this.state.match_id
    })});
  }
  accept(value) {
    if(value.room_id!==this.roomId)return false;
    if(this.state?.room_id===value.room_id&&this.state.state.version>value.state.version)return false;
    this.state=value; return true;
  }
  follow(roomId,onUpdate,onError) {
    this.stop();this.roomId=roomId;
    const controller=new AbortController();this.controller=controller;
    const signal=controller.signal;
    const wait=ms=>new Promise(resolve=>{
      const done=()=>{clearTimeout(timer);signal.removeEventListener('abort',done);resolve();};
      const timer=setTimeout(done,ms);signal.addEventListener('abort',done,{once:true});
    });
    (async()=>{
      let failures=0;
      while(!signal.aborted) {
        const connection=new AbortController();
        const abort=()=>connection.abort();
        signal.addEventListener('abort',abort,{once:true});
        let watchdog;
        const touch=()=>{clearTimeout(watchdog);watchdog=setTimeout(abort,30000);};
        try {
          const snap=await this.snapshot(roomId);
          if(signal.aborted)return;
          if(this.accept(snap))onUpdate(snap);
          touch();
          const response=await this.fetchImpl(this.root+'/rooms/'+roomId+'/events',{headers:{Authorization:`MistrealmUid ${this.uid}`},signal:connection.signal});
          if(!response.ok||!response.body)throw new Error('实时连接中断');
          const reader=response.body.getReader(),decoder=new TextDecoder();
          let buffer='';
          const cancel=()=>reader.cancel().catch(()=>{});
          connection.signal.addEventListener('abort',cancel,{once:true});
          try {
            while(!signal.aborted) {
              const {value,done}=await reader.read();if(done)throw new Error('实时连接已断开');touch();
              buffer+=decoder.decode(value,{stream:true}).replace(/\r\n/g,'\n');
              let end;
              while((end=buffer.indexOf('\n\n'))>=0) {
                const packet=buffer.slice(0,end);buffer=buffer.slice(end+2);
                if(packet.includes('event: unavailable'))throw new Error('房间已不可用，请刷新');
                const line=packet.split('\n').find(x=>x.startsWith('data: '));
                if(line&&!signal.aborted) {
                  const snap=JSON.parse(line.slice(6));
                  if(this.accept(snap)){failures=0;onUpdate(snap);}
                }
              }
            }
          } finally {connection.signal.removeEventListener('abort',cancel);await reader.cancel().catch(()=>{});}
        } catch(error) {
          if(signal.aborted)return;
          failures++;onError(error);
          if(error.status===403||error.status===404)return;
          // Snapshot polling and SSE attempts are sequential, never concurrent.
          await wait(failures>=3?5000:Math.min(4000,500*2**failures));
        } finally {
          clearTimeout(watchdog);signal.removeEventListener('abort',abort);connection.abort();
        }
      }
    })();
  }
  stop(){this.controller?.abort();this.controller=null;}
}
