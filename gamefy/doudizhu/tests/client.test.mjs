import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DoudizhuClient} from '../publish/client.js';

test('coalesces identity reads and retries missing SDK identity', async()=>{
  let calls=0, id=null;
  const client=new DoudizhuClient({sdk:{user:{info:async()=>{calls++;return {id};}}},fetchImpl:async()=>{},apiBase:'https://example.com'});
  await assert.rejects(client.identity(), /身份/);
  id='alice';
  assert.deepEqual(await Promise.all([client.identity(),client.identity()]),['alice','alice']);
  assert.equal(calls,2);
});

test('switching identity clears state and old subscriptions', async()=>{
  let id='alice', stopped=false;
  const client=new DoudizhuClient({sdk:{user:{info:async()=>({id})}},fetchImpl:async()=>{},apiBase:'https://example.com'});
  await client.identity();
  client.state={hand:[0]}; client.stop=()=>{stopped=true;}; id='bob';
  assert.equal(await client.identity(true),'bob');
  assert.equal(client.state,null); assert.equal(stopped,true);
});

test('action retries preserve supplied id and do not auto-retry mutations',async()=>{
  const bodies=[];
  const client=new DoudizhuClient({sdk:{user:{info:async()=>({id:'alice'})}},apiBase:'https://example.com',fetchImpl:async(url,options)=>{
    assert.equal(options.headers.Authorization,'DoudizhuUid alice'); bodies.push(JSON.parse(options.body));
    if(bodies.length===1) throw new Error('offline');
    return {ok:true,json:async()=>({version:2})};
  }});
  const envelope={request_id:'same-id',action:'ready',round_id:null,version:1,payload:{}};
  await assert.rejects(client.action('room',envelope),/offline/);
  assert.equal(bodies.length,1);
  await client.action('room',envelope);
  assert.deepEqual(bodies[0],bodies[1]);
});

test('failed identity refresh clears old UID and blocks old-identity requests',async()=>{
  let available=true,stopped=false,requests=0;
  const client=new DoudizhuClient({sdk:{user:{info:async()=>{if(!available)throw new Error('SDK unavailable');return {id:'alice'};}}},apiBase:'https://example.com',fetchImpl:async()=>{requests++;return {ok:true,json:async()=>({hand:[0]})};}});
  await client.identity();client.state={hand:[0]};client.stop=()=>{stopped=true;};available=false;
  await assert.rejects(client.identity(true),/SDK unavailable/);
  assert.equal(client.uid,null);assert.equal(client.state,null);assert.equal(stopped,true);
  await assert.rejects(client.snapshot('room'),/SDK unavailable/);
  assert.equal(requests,0);
});
