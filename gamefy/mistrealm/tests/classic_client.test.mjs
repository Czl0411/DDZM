import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
const path=new URL('../publish/classic/client.js',import.meta.url);
async function api(){assert.ok(existsSync(path),'Classic client must exist');return import(path.href);}

test('SDK profile registration stays shared while decks and queue use Classic routes',async()=>{
 const {ClassicClient}=await api(),calls=[];
 const c=new ClassicClient({sdk:{user:{info:async()=>({id:'uid',name:'旅人',avatarUrl:'https://example.com/a.png'})}},apiBase:'',fetchImpl:async(url,options)=>{
  calls.push({url,options});return {ok:true,json:async()=>({room_id:null})};
 }});
 await c.boot();await c.decks();await c.startMatchmaking('deck-1');
 assert.equal(calls[0].url,'/api/mistrealm/players/me');
 assert.equal(JSON.parse(calls[0].options.body).avatar,'https://example.com/a.png');
 assert.equal(calls[2].url,'/api/mistrealm/classic/decks');
 assert.equal(calls[3].url,'/api/mistrealm/classic/matchmaking');
 assert.equal(JSON.parse(calls[3].options.body).deck_id,'deck-1');
});

test('room creation and join submit deck references without trusting card lists',async()=>{
 const {ClassicClient}=await api(),calls=[];
 const c=new ClassicClient({sdk:{},apiBase:'',fetchImpl:async(url,o)=>{calls.push(JSON.parse(o.body));return {ok:true,json:async()=>({})};}});
 await c.create('deck-a','req-a');await c.join('123456','deck-b','req-b');
 assert.deepEqual(calls,[{deck_id:'deck-a',request_id:'req-a'},{code:'123456',deck_id:'deck-b',request_id:'req-b'}]);
});

test('story stays on Classic routes while the public channel uses the shared root',async()=>{
 const {ClassicClient}=await api(),calls=[];
 const c=new ClassicClient({sdk:{},apiBase:'',fetchImpl:async(url,o={})=>{
  calls.push({url,body:o.body?JSON.parse(o.body):null});return {ok:true,json:async()=>({})};
 }});
 await c.story();await c.startStory(2,'deck-2');await c.channelMessages();
 await c.channelPost('来一局');await c.channelChallenge('room-1');
 assert.deepEqual(calls,[
  {url:'/api/mistrealm/classic/story',body:null},
  {url:'/api/mistrealm/classic/story/start',body:{chapter:2,deck_id:'deck-2'}},
  {url:'/api/mistrealm/channel/messages',body:null},
  {url:'/api/mistrealm/channel/messages',body:{text:'来一局'}},
  {url:'/api/mistrealm/channel/challenges',body:{room_id:'room-1'}},
 ]);
});

test('countdown depends on server remaining duration and monotonic elapsed time',async()=>{
 const {remainingSeconds}=await api();
 const state={deadline_ms:120000,server_time_ms:100000};
 assert.equal(remainingSeconds(state,500,5500),15);
 assert.equal(remainingSeconds(state,500,1000000),0);
 assert.equal(remainingSeconds({deadline_ms:null,server_time_ms:100000},500,5500),null);
});
