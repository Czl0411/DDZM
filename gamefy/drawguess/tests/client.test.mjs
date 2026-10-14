import {test} from 'node:test';
import assert from 'node:assert/strict';

import {createClient,withTimeout} from '../publish/client.js';


const sdk=id=>({user:{info:async()=>({id})},kv:{get:async()=>null,put:async()=>{}}});
const response=value=>({ok:true,json:async()=>value});


test('identity failures can be retried and requests use UID header',async()=>{
  let id=null,calls=0;
  const client=createClient({sdk:{user:{info:async()=>({id})}},apiBase:'https://example.com',fetchImpl:async(url,options)=>{
    calls++;assert.equal(options.headers.Authorization,'DrawguessUid alice');return response([]);
  }});
  await assert.rejects(client.identity(),/身份/);
  id='alice';assert.equal(await client.identity(),'alice');
  assert.deepEqual(await client.rooms(),[]);assert.equal(calls,1);
});


test('timeout is bounded instead of hanging forever',async()=>{
  await assert.rejects(withTimeout(new Promise(()=>{}),'读取身份',10),/超时/);
});


test('stroke retries preserve request id and stop after three attempts',async()=>{
  const bodies=[];
  const client=createClient({sdk:sdk('alice'),apiBase:'https://example.com',sleepImpl:async()=>{},fetchImpl:async(url,options)=>{
    if(url.endsWith('/strokes')){bodies.push(JSON.parse(options.body));throw new Error('offline');}
    return response({room_id:'room',cursor:0,state:{turn_id:1}});
  }});
  await assert.rejects(client.strokes('room',1,[{op:'clear'}]),/绘画连接/);
  assert.equal(bodies.length,3);
  assert.equal(new Set(bodies.map(body=>body.request_id)).size,1);
  await assert.rejects(client.strokes('room',1,[{op:'clear'}]),/重新连接/);
  assert.equal(bodies.length,3);
  await client.snapshot('room');
  assert.equal(client.strokesBlocked,false);
});


test('cancelling follow prevents later callbacks',async()=>{
  let release;
  const encoder=new TextEncoder();
  const chunks=[
    encoder.encode('event: update\ndata: {"cursor":1,"snapshot":{"state":{"version":1}}}\n\n'),
    encoder.encode('event: update\ndata: {"cursor":2,"snapshot":{"state":{"version":2}}}\n\n'),
  ];
  let reads=0;
  const reader={
    async read(){
      if(reads===0){reads++;return {value:chunks[0],done:false};}
      await new Promise(resolve=>{release=resolve;});reads++;return {value:chunks[1],done:false};
    },
    async cancel(){release?.();},
  };
  const client=createClient({sdk:sdk('alice'),apiBase:'https://example.com',sleepImpl:async()=>{},fetchImpl:async()=>({ok:true,body:{getReader:()=>reader}})});
  const updates=[];
  const stop=client.follow('room',0,value=>updates.push(value),()=>{});
  while(updates.length===0)await new Promise(resolve=>setTimeout(resolve,1));
  stop();release?.();await new Promise(resolve=>setTimeout(resolve,5));
  assert.equal(updates.length,1);
  client.dispose();
});
