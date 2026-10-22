export async function withTimeout(promise,label,timeoutMs=8000){
  let timer;
  try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error(`${label}超时，请重试`)),timeoutMs);})]);}
  finally{clearTimeout(timer);}
}

function requestId(){
  if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
  const bytes=new Uint8Array(16);globalThis.crypto?.getRandomValues?.(bytes);
  if(!bytes.some(Boolean))for(let i=0;i<bytes.length;i++)bytes[i]=Math.floor(Math.random()*256);
  return [...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
}

export class DrawguessClient{
  constructor({sdk,fetchImpl=fetch,apiBase,sleepImpl=ms=>new Promise(resolve=>setTimeout(resolve,ms))}){
    this.sdk=sdk;this.fetchImpl=fetchImpl.bind(globalThis);this.root=apiBase.replace(/\/$/,'')+'/api/drawguess';
    this.sleepImpl=sleepImpl;this.uid=null;this.pendingIdentity=null;this.state=null;this.stop=null;this.activeReader=null;this.strokesBlocked=false;
  }
  async identity(refresh=false){
    if(refresh){this.stop?.();this.uid=null;this.state=null;this.pendingIdentity=null;}
    if(this.uid&&!refresh)return this.uid;
    if(!this.pendingIdentity)this.pendingIdentity=(async()=>{
      const info=await withTimeout(this.sdk.user.info(),'读取玩家身份');
      if(typeof info?.id!=='string'||!info.id.trim())throw new Error('无法读取玩家身份，请重试');
      if(this.uid&&this.uid!==info.id){this.stop?.();this.state=null;}
      this.uid=info.id;return this.uid;
    })();
    try{return await this.pendingIdentity;}finally{this.pendingIdentity=null;}
  }
  async request(path,options={}){
    const uid=await this.identity(),controller=new AbortController();
    try{
      const value=await withTimeout((async()=>{
        const response=await this.fetchImpl(this.root+path,{...options,signal:controller.signal,headers:{Authorization:`DrawguessUid ${uid}`,...(options.body?{'Content-Type':'application/json'}:{})}});
        if(!response.ok){const body=await response.json().catch(()=>({}));const error=new Error(typeof body.detail==='string'?body.detail:'请求失败，请重试');error.status=response.status;throw error;}
        return response.json();
      })(),'连接游戏服务器');
      if(uid!==this.uid)throw new Error('账号已改变，请刷新房间');
      return value;
    }finally{controller.abort();}
  }
  rooms(){return this.request('/rooms');}
  create(roomType,stake){return this.request('/rooms',{method:'POST',body:JSON.stringify({room_type:roomType,stake})});}
  async snapshot(roomId){this.state=await this.request(`/rooms/${roomId}`);this.strokesBlocked=false;return this.state;}
  action(roomId,envelope){return this.request(`/rooms/${roomId}/actions`,{method:'POST',body:JSON.stringify({...envelope,request_id:envelope.request_id||requestId()})});}
  chat(roomId,envelope){return this.request(`/rooms/${roomId}/chat`,{method:'POST',body:JSON.stringify({...envelope,request_id:envelope.request_id||requestId()})});}
  async strokes(roomId,turnId,operations){
    if(this.strokesBlocked)throw new Error('请重新连接房间后继续绘画');
    const envelope={turn_id:turnId,request_id:requestId(),operations};let lastError;
    for(let attempt=0;attempt<3;attempt++){
      try{return await this.request(`/rooms/${roomId}/strokes`,{method:'POST',body:JSON.stringify(envelope)});}
      catch(error){lastError=error;if(attempt<2)await this.sleepImpl(100*(2**attempt));}
    }
    this.strokesBlocked=true;throw new Error(`绘画连接中断，请重新连接：${lastError?.message||'请求失败'}`);
  }
  follow(roomId,cursor,onUpdate,onError){
    this.stop?.();const controller=new AbortController(),signal=controller.signal;
    const stop=()=>{controller.abort();this.activeReader?.cancel?.().catch(()=>{});};this.stop=stop;
    (async()=>{
      let after=cursor;
      while(!signal.aborted){
        try{
          const uid=await this.identity();
          const response=await this.fetchImpl(`${this.root}/rooms/${roomId}/events?after=${after}`,{headers:{Authorization:`DrawguessUid ${uid}`},signal});
          if(!response.ok||!response.body)throw new Error('实时连接失败');
          const reader=response.body.getReader();this.activeReader=reader;const decoder=new TextDecoder();let buffer='';
          try{
            while(!signal.aborted){
              const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});
              let split;
              while((split=buffer.indexOf('\n\n'))>=0){
                const packet=buffer.slice(0,split);buffer=buffer.slice(split+2);
                if(packet.includes('event: unavailable'))throw new Error('房间或身份已不可用');
                const line=packet.split('\n').find(item=>item.startsWith('data: '));
                if(line&&!signal.aborted&&uid===this.uid){const data=JSON.parse(line.slice(6));after=data.cursor;if(data.snapshot)this.state=data.snapshot;onUpdate(data);}
              }
            }
          }finally{this.activeReader=null;await reader.cancel().catch(()=>{});}
        }catch(error){if(!signal.aborted)onError(error);}
        if(!signal.aborted)await this.sleepImpl(1000);
      }
    })();return stop;
  }
  async kvGet(key){try{return await this.sdk.kv.get(key);}catch{return null;}}
  async kvPut(key,value){try{await this.sdk.kv.put(key,value,{flush:true});return true;}catch{return false;}}
  dispose(){this.stop?.();this.stop=null;this.state=null;}
}

export function createClient(config){return new DrawguessClient(config);}
