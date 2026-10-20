import {followSocial} from './social_stream.js';
import {ClassicClient,remainingSeconds} from '../classic/client.js';
export {remainingSeconds};
export class V3Client extends ClassicClient {
 constructor(options){super(options);this.root=this.sharedRoot+'/v3';}
 action(...args){if(this.watching)return Promise.reject(new Error('观战中不能操作对局'));return super.action(...args);}
 playerProfile(uid){return this.request('/profile'+(uid?'?'+new URLSearchParams({uid}):''));}
 savePreferences(values){return this.post('/profile/settings',values);}
 matchHistory(page=0){return this.request('/profile/history?'+new URLSearchParams({page}));}
 matchHistoryDetail(id){return this.request('/profile/history/'+encodeURIComponent(id));}
 selectDeck(id){return this.post('/decks/'+encodeURIComponent(id)+'/select',{});}
 rankedProfile(){return this.request('/ranked');}
 rankedLeaderboard(seasonId,page=0){return this.request('/ranked/leaderboard?'+new URLSearchParams({season_id:seasonId,page}));}
 rankedHonor(seasonId){return this.post('/ranked/honor',{season_id:seasonId});}
 startMatchmaking(deckId,mode='casual'){return this.post((mode==='ranked'?'/ranked':'')+'/matchmaking',{deck_id:deckId});}
 heartbeatMatchmaking(ticket,mode='casual'){return this.post((mode==='ranked'?'/ranked':'')+'/matchmaking/heartbeat',{ticket});}
 cancelMatchmaking(ticket,mode='casual'){return this.post((mode==='ranked'?'/ranked':'')+'/matchmaking/cancel',{ticket});}
 syncQuery(roomId){
  const value=this.syncState,watch=this.watching?'&'+new URLSearchParams({watch:this.watching.uid,watch_match:this.watching.match_id}):'';
  if(!value?.match_id||value.room_id!==roomId)return '?sync_match=&sync_log=0&sync_frame=0'+watch;
  return '?'+new URLSearchParams({sync_match:value.match_id,sync_log:value.state.action_log?.at(-1)?.id||0,sync_frame:value.state.action_frames?.at(-1)?.version||0})+watch;
 }
 request(path,options={},root=this.root){
  const match=path.match(/^\/rooms\/([^/?]+)(?:\/actions)?$/);
  return super.request(path+(match&&match[1]!=='join'?this.syncQuery(match[1]):''),options,root);
 }
 accept(value){if(this.watching&&value.state?.phase==='closed'&&value.room_id===this.roomId){this.state=value;return true;}return super.accept(value);}
 decodeRoom(value){
  if(!value?.room_id||!value.state)return value;
  if(this.watching&&value.state.phase==='closed'){this.syncState=value;return value;}
  const previous=this.syncState;
  if(previous?.room_id===value.room_id&&previous.state.version>value.state.version)return previous;
  if(value.history_delta){
   if(previous?.room_id!==value.room_id||previous.match_id!==value.match_id||
      (previous.state.action_log?.at(-1)?.id||0)<value.history_delta.log||
      (previous.state.action_frames?.at(-1)?.version||0)<value.history_delta.frame){
    this.syncState=null;throw new Error('对局记录需要重新同步');
   }
   const merge=(key,id,limit)=>[...new Map([...(previous.state[key]||[]),...(value.state[key]||[])].map(x=>[x[id],x])).values()].sort((a,b)=>a[id]-b[id]).slice(limit?-limit:0);
   value={...value,state:{...value.state,action_log:merge('action_log','id'),action_frames:merge('action_frames','version',80)}};
   delete value.history_delta;
  }
  this.syncState=value;return value;
 }
 async channelMessages(){
  const previous=this.channelItems||[],after=previous.at(-1)?.id;
  const params=new URLSearchParams();if(after)params.set('after',after);if(this.channelRevision)params.set('revision',this.channelRevision);
  const value=await this.request('/channel/messages'+(params.size?'?'+params:''),{},this.sharedRoot);
  return this.acceptChannel(value);
 }
 acceptChannel(value){
  const previous=this.channelItems||[];
  if(value.unchanged)return {items:previous};
  if(value.delta){
   const items=new Map([...previous,...value.items].map(x=>[x.id,x]));
   this.channelItems=value.ids.map(id=>items.get(id)).filter(Boolean).map(x=>({...x,player:value.players[x.player.uid]||x.player,...(value.challenges[x.id]?{challenge:value.challenges[x.id]}:{})}));
  }else this.channelItems=value.items;
  this.channelRevision=value.revision;return {items:this.channelItems};
 }
 followSocial(onUpdate,onError){return followSocial(this,onUpdate,onError);}
 privateConversations(page=0){return this.request('/social/conversations?'+new URLSearchParams({page}),{},this.sharedRoot);}
 privateMessages(uid,cursor={}){return this.request('/social/messages?'+new URLSearchParams({uid,...cursor}),{},this.sharedRoot);}
 privateSend(uid,text,requestId){return this.socialPost('messages',{uid,text,request_id:requestId});}
 privateRead(uid,throughId){return this.socialPost('messages/read',{uid,through_id:throughId});}
 socialPulse(){return this.request('/social/presence',{method:'POST'},this.sharedRoot);}
 socialPlayers(scope='all',search='',page=0){return this.request('/social/players?'+new URLSearchParams({scope,search,page}),{},this.sharedRoot);}
 socialPost(path,body){return this.request('/social/'+path,{method:'POST',body:JSON.stringify(body)},this.sharedRoot);}
 friend(uid,operation){return this.socialPost('friends',{uid,operation});}
 challenge(uid,deckId){return this.socialPost('challenges',{uid,deck_id:deckId});}
 challengeReply(id,operation,deckId=null){return this.socialPost('challenges/'+id,{operation,deck_id:deckId});}
 saveDeck({id,name,faction,leader,counts}){return super.saveDeck({id,name,faction,leader,counts});}
}
