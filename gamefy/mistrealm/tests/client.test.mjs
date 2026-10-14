import test from 'node:test';
import assert from 'node:assert/strict';
import {MistrealmClient} from '../publish/client.js';

test('reads SDK UID, registers separate player, never requests token',async()=>{
 const calls=[];
 const client=new MistrealmClient({sdk:{user:{info:async()=>({id:'public-1',name:'玩家'})}},apiBase:'https://example.test',fetchImpl:async(url,options)=>{
   calls.push({url,options}); return {ok:true,json:async()=>({room_id:null})};
 }});
 await client.boot();
 assert.equal(calls[0].options.headers.Authorization,'MistrealmUid public-1');
 assert.ok(calls[0].url.endsWith('/players/me'));
 assert.equal(JSON.parse(calls[0].options.body).name,'玩家');
});
test('missing UID fails instead of inventing anonymous identity',async()=>{
 const client=new MistrealmClient({sdk:{user:{info:async()=>({})}},apiBase:''});
 await assert.rejects(client.boot(),/身份/);
});
test('HTTP error preserves useful message and status',async()=>{
 const client=new MistrealmClient({sdk:{},apiBase:'',fetchImpl:async()=>({ok:false,status:409,json:async()=>({detail:'状态已更新'})})});
 client.uid='a';
 await assert.rejects(client.request('/rooms'),e=>e.status===409&&e.message==='状态已更新');
});
test('old room and stale versions never replace current snapshot',()=>{
 const client=new MistrealmClient({sdk:{},apiBase:''});
 client.roomId='new';
 assert.equal(client.accept({room_id:'old',state:{version:9}}),false);
 assert.equal(client.accept({room_id:'new',state:{version:5}}),true);
 assert.equal(client.accept({room_id:'new',state:{version:3}}),false);
 assert.equal(client.state.state.version,5);
});
test('action submits version match and stable supplied request ID',async()=>{
 let body;
 const client=new MistrealmClient({sdk:{},apiBase:'',fetchImpl:async(url,o)=>{body=JSON.parse(o.body);return {ok:true,json:async()=>({})};}});
 client.uid='a';client.state={room_id:'room',match_id:'match',state:{version:7}};
 await client.action('pass',{},'request');
 assert.deepEqual(body,{action:'pass',payload:{},request_id:'request',version:7,match_id:'match'});
});
test('fetch executes with the browser global receiver',async()=>{
 const client=new MistrealmClient({sdk:{},apiBase:'',fetchImpl:async function(){assert.equal(this,globalThis);return {ok:true,json:async()=>({})};}});
 client.uid='a';await client.request('/players/me');
});
test('SSE watchdog recovers a half-open fetch',async(t)=>{
 t.mock.timers.enable({apis:['setTimeout']});
 let failed=0,attempts=0;
 const client=new MistrealmClient({sdk:{},apiBase:'',fetchImpl:async(url,options)=>{
   if(!url.endsWith('/events'))return {ok:true,json:async()=>({room_id:'r',state:{version:1}})};
   attempts++;
   return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true}));
 }});
 client.uid='a';client.follow('r',()=>{},()=>failed++);
 for(let i=0;i<10;i++)await Promise.resolve();
 assert.equal(attempts,1);
 t.mock.timers.tick(31000);
 for(let i=0;i<10;i++)await Promise.resolve();
 assert.equal(failed,1);
 client.stop();t.mock.timers.reset();
});
test('matchmaking start, heartbeat and cancellation use separate queue endpoints',async()=>{
 const calls=[];
 const client=new MistrealmClient({sdk:{},apiBase:'',fetchImpl:async(url,options)=>{
  calls.push({url,options});return {ok:true,json:async()=>({status:'waiting',ticket:'ticket'})};
 }});
 client.uid='a';
 await client.startMatchmaking();
 await client.heartbeatMatchmaking('ticket');
 await client.cancelMatchmaking('ticket');
 assert.deepEqual(calls.map(c=>c.url),['/api/mistrealm/matchmaking','/api/mistrealm/matchmaking/heartbeat','/api/mistrealm/matchmaking/cancel']);
 assert.deepEqual(JSON.parse(calls[1].options.body),{ticket:'ticket'});
 assert.deepEqual(JSON.parse(calls[2].options.body),{ticket:'ticket'});
});
