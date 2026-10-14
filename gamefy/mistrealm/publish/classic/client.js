import {MistrealmClient,requestId} from '../client.js';

export const remainingSeconds=(state,receivedAt,now=performance.now())=>state.deadline_ms==null?null:
 Math.max(0,Math.ceil((state.deadline_ms-state.server_time_ms-(now-receivedAt))/1000));

export class ClassicClient extends MistrealmClient {
 constructor(options){super(options);this.sharedRoot=this.root;this.root+='/classic';}
 async boot(){const root=this.root;this.root=this.sharedRoot;try{return await super.boot();}finally{this.root=root;}}
 post(path,body={}){return this.request(path,{method:'POST',body:JSON.stringify(body)});}
 decks(){return this.request('/decks');}
 saveDeck(deck){return this.post('/decks',deck);}
 deleteDeck(id){return this.post('/decks/'+id+'/delete');}
 startMatchmaking(deckId){return this.post('/matchmaking',{deck_id:deckId});}
 create(deckId,id=requestId()){return this.post('/rooms',{deck_id:deckId,request_id:id});}
 join(code,deckId,id=requestId()){return this.post('/rooms/join',{code,deck_id:deckId,request_id:id});}
}
