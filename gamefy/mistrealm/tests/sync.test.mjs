import test from 'node:test';
import assert from 'node:assert/strict';
import {V3Client} from '../publish/v3/client.js';
const client=()=>new V3Client({sdk:{},apiBase:''});
const room=(version=1,match='match')=>({room_id:'room',match_id:match,state:{version,action_log:[{id:version}],action_frames:[{version}]}});

test('overlapping HTTP and SSE deltas merge once without losing earlier history',()=>{
 const c=client();c.decodeRoom(room());
 const delta={...room(3),history_delta:{log:1,frame:1}};
 delta.state.action_log.unshift({id:2});delta.state.action_frames.unshift({version:2});
 c.decodeRoom(delta);const merged=c.decodeRoom(structuredClone(delta));
 assert.deepEqual(merged.state.action_log.map(x=>x.id),[1,2,3]);
 assert.deepEqual(merged.state.action_frames.map(x=>x.version),[1,2,3]);
 assert.equal(c.decodeRoom(room(2)).state.version,3);
 assert.match(c.syncQuery('room'),/sync_log=3/);
});

test('rematch replaces history and missing baseline forces full recovery',()=>{
 const c=client();c.decodeRoom(room());c.decodeRoom(room(2,'new-match'));
 assert.deepEqual(c.syncState.state.action_log,[{id:2}]);
 assert.throws(()=>c.decodeRoom({...room(4,'new-match'),history_delta:{log:3,frame:3}}),/重新同步/);
 assert.match(c.syncQuery('room'),/sync_match=&sync_log=0/);
 c.decodeRoom(room(4,'new-match'));assert.equal(c.syncState.state.version,4);
});

test('HTTP action and reconnect snapshot send cursors without changing UID payload',async()=>{
 const c=client(),calls=[];c.uid='a';c.state=room();c.decodeRoom(c.state);
 c.fetchImpl=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({...room(2),history_delta:{log:1,frame:1}})};};
 const value=await c.snapshot('room');assert.deepEqual(value.state.action_log.map(x=>x.id),[1,2]);
 c.state=value;await c.action('pass',{},'id');
 assert.match(calls[0].url,/sync_log=1/);assert.match(calls[1].url,/actions\?sync_match=match&sync_log=2/);
 assert.equal(calls[1].options.headers.Authorization,'MistrealmUid a');
 assert.equal(JSON.parse(calls[1].options.body).action,'pass');
});

test('channel merges new text, removes deleted entries and updates existing player and challenge status',async()=>{
 const c=client(),item=id=>({id,player:{uid:'a',online:true},text:id});
 let values=[{items:[item('1'),{...item('2'),challenge:{status:'waiting'}}]},
  {delta:true,ids:['2','3'],items:[item('3')],players:{a:{uid:'a',online:false,name:'新昵称'}},challenges:{'2':{status:'ended'}}},
  {items:[item('9')]}];
 c.fetchImpl=async()=>({ok:true,json:async()=>values.shift()});
 await c.channelMessages();const value=await c.channelMessages();
 assert.deepEqual(value.items.map(x=>x.id),['2','3']);
 assert.equal(value.items[0].player.online,false);assert.equal(value.items[0].challenge.status,'ended');
 assert.equal(value.items[0].player.name,'新昵称');
 assert.deepEqual((await c.channelMessages()).items.map(x=>x.id),['9']);
});

test('unchanged channel reply preserves messages and sends its revision next time',async()=>{
 const c=client(),calls=[],items=[{id:'1',text:'hello',player:{uid:'a'}}];
 const values=[{items,revision:'hash'},{unchanged:true,revision:'hash'}];
 c.fetchImpl=async url=>{calls.push(url);return {ok:true,json:async()=>values.shift()};};
 await c.channelMessages();assert.deepEqual((await c.channelMessages()).items,items);
 assert.match(calls[1],/after=1&revision=hash/);
});
