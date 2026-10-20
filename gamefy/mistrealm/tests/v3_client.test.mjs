import test from 'node:test';
import assert from 'node:assert/strict';
import {V3Client} from '../publish/v3/client.js';

test('v3 keeps platform identity shared and routes deck/room/queue/story requests to v3',async()=>{
 const calls=[];
 const client=new V3Client({sdk:{user:{info:async()=>({id:'uid',name:'旅人'})}},apiBase:'',fetchImpl:async(url,options)=>{
  calls.push({url,body:options.body?JSON.parse(options.body):null});return {ok:true,json:async()=>({})};
 }});
 await client.boot();await client.decks();await client.create('deck','create');await client.join('012345','deck','join');
 await client.startMatchmaking('deck');await client.heartbeatMatchmaking('ticket');await client.cancelMatchmaking('ticket');
 await client.startStory(1,'deck');
 assert.deepEqual(calls.map(c=>c.url),[
  '/api/mistrealm/players/me','/api/mistrealm/players/me','/api/mistrealm/v3/decks',
  '/api/mistrealm/v3/rooms','/api/mistrealm/v3/rooms/join','/api/mistrealm/v3/matchmaking',
  '/api/mistrealm/v3/matchmaking/heartbeat','/api/mistrealm/v3/matchmaking/cancel','/api/mistrealm/v3/story/start'
 ]);
 assert.equal(calls[4].body.code,'012345');
});

test('saving a returned v3 deck strips read-only metadata rejected by the API',async()=>{
 let body;
 const client=new V3Client({sdk:{},apiBase:'',fetchImpl:async(url,o)=>{body=JSON.parse(o.body);return {ok:true,json:async()=>({})};}});
 const deck={id:'deck',name:'独守',faction:'crown',leader:'c019',counts:{c001:2},rules_version:3};
 await client.saveDeck(deck);
 assert.deepEqual(body,{id:'deck',name:'独守',faction:'crown',leader:'c019',counts:{c001:2}});
});

test('spectator snapshots and SSE carry the same friend/match scope and cannot send actions',async()=>{
 const calls=[];
 const client=new V3Client({sdk:{},apiBase:'',fetchImpl:async(url)=>{calls.push(url);return {ok:true,json:async()=>({})};}});
 client.watching={uid:'friend & one',match_id:'match'};
 await client.snapshot('room');
 const query=new URL(calls[0],'https://test').searchParams;
 assert.equal(query.get('watch'),'friend & one');assert.equal(query.get('watch_match'),'match');
 assert.equal(new URLSearchParams(client.syncQuery('room')).get('watch'),'friend & one');
 await assert.rejects(client.action('concede'),/观战中不能操作对局/);
 assert.equal(calls.length,1);
 client.watching=null;
 assert.equal(new URLSearchParams(client.syncQuery('room')).has('watch'),false);
});

test('an ended spectator match exits even if the room restarted at a lower version',()=>{
 const client=new V3Client({sdk:{},apiBase:''});
 client.watching={uid:'friend',match_id:'old'};client.roomId='room';
 client.state=client.syncState={room_id:'room',match_id:'old',state:{version:100}};
 const closed={room_id:'room',match_id:'old',state:{version:0,phase:'closed'}};
 assert.equal(client.decodeRoom(closed),closed);assert.equal(client.accept(closed),true);
});
