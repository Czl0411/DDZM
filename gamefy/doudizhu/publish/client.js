export class DoudizhuClient {
  constructor({sdk,fetchImpl=fetch,apiBase}){this.sdk=sdk;this.fetchImpl=fetchImpl.bind(globalThis);this.root=apiBase.replace(/\/$/,'')+'/api/doudizhu';this.uid=null;this.pending=null;this.state=null;this.stop=null;}
  async identity(refresh=false){
    if(this.uid&&!refresh)return this.uid;
    if(!this.pending)this.pending=(async()=>{
      const info=await this.sdk.user.info();
      if(typeof info?.id!=='string'||!info.id.trim())throw new Error('无法读取玩家身份，请重试');
      if(this.uid&&this.uid!==info.id){this.stop?.();this.state=null;}
      this.uid=info.id;return this.uid;
    })();
    try{return await this.pending;}finally{this.pending=null;}
  }
  async request(path,options={}){
    const uid=await this.identity();
    const res=await this.fetchImpl(this.root+path,{...options,headers:{Authorization:`DoudizhuUid ${uid}`,...(options.body?{'Content-Type':'application/json'}:{})}});
    if(!res.ok){const data=await res.json().catch(()=>({}));const error=new Error(typeof data.detail==='string'?data.detail:'请求失败，请刷新后重试');error.status=res.status;throw error;}
    const data=await res.json();
    if(uid!==this.uid)throw new Error('账号已改变，请刷新房间');
    return data;
  }
  rooms(){return this.request('/rooms');}
  async snapshot(id){this.state=await this.request(`/rooms/${id}`);return this.state;}
  action(id,envelope){return this.request(`/rooms/${id}/actions`,{method:'POST',body:JSON.stringify(envelope)});}
  chat(id,payload){return this.request(`/rooms/${id}/chat`,{method:'POST',body:JSON.stringify(payload)});}
  suggestions(id){return this.request(`/rooms/${id}/suggestions`);}
  follow(id,onSnapshot){
    this.stop?.();const controller=new AbortController();const signal=controller.signal;
    const stop=()=>controller.abort();this.stop=stop;
    (async()=>{
      while(!signal.aborted){
        try{
          const initial=await this.snapshot(id);if(signal.aborted)return;onSnapshot(initial);
          const uid=await this.identity();
          const res=await this.fetchImpl(`${this.root}/rooms/${id}/events`,{headers:{Authorization:`DoudizhuUid ${uid}`},signal});
          if(!res.ok||!res.body)throw new Error('连接中断，正在重连');
          const reader=res.body.getReader(),decoder=new TextDecoder();let buffer='';
          try{while(!signal.aborted){
            const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});
            let split;
            while((split=buffer.indexOf('\n\n'))>=0){
              const packet=buffer.slice(0,split);buffer=buffer.slice(split+2);
              if(packet.includes('event: unavailable'))throw new Error('房间或身份已不可用');
              const line=packet.split('\n').find(v=>v.startsWith('data: '));
              if(line&&!signal.aborted&&uid===this.uid){this.state=JSON.parse(line.slice(6));onSnapshot(this.state);}
            }
          }}finally{await reader.cancel().catch(()=>{});}
        }catch(error){if(!signal.aborted)onSnapshot(null,error);}
        if(!signal.aborted)await new Promise(resolve=>{const timer=setTimeout(resolve,1500);signal.addEventListener('abort',()=>{clearTimeout(timer);resolve();},{once:true});});
      }
    })();return stop;
  }
}
