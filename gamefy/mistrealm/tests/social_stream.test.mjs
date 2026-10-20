import test from 'node:test';
import assert from 'node:assert/strict';
import {followSocial} from '../publish/v3/social_stream.js';
const tick=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};

test('social SSE parses split UTF-8 and CRLF packets once, ignores heartbeats, and closes cleanly',async()=>{
 let source,closed=false,options;
 const stream=new ReadableStream({start(c){source=c;},cancel(){closed=true;}});
 const client={uid:'me',sharedRoot:'/api/mistrealm',fetchImpl:async(url,o)=>{options=o;assert.equal(url,'/api/mistrealm/social/events');return {ok:true,body:stream};}};
 const received=[],errors=[];const connection=followSocial(client,p=>received.push(p),e=>errors.push(e));
 const bytes=new TextEncoder().encode(': heartbeat\r\n\r\nevent: social\r\ndata: {"text":"你好"}\r\n\r\n');
 for(const byte of bytes)source.enqueue(Uint8Array.of(byte));
 await tick();await new Promise(r=>setTimeout(r,20));
 assert.deepEqual(received,[{text:'你好'}]);assert.equal(options.headers.Authorization,'MistrealmUid me');assert.equal(options.redirect,'error');
 connection.stop();await connection.finished;assert.equal(closed,true);assert.equal(errors.length,0);
});

test('broken streams reconnect and process a fresh snapshot',async()=>{
 let calls=0,source,connection;
 const received=[];
 const client={uid:'me',sharedRoot:'',fetchImpl:async()=>{
  calls++;return {ok:true,body:new ReadableStream({start(c){source=c;
   c.enqueue(new TextEncoder().encode('event: social\ndata: {"connection":'+calls+'}\n\n'));
   if(calls===1)c.close();
  }})};
 }};
 connection=followSocial(client,p=>{received.push(p);if(p.connection===2)connection.stop();},()=>{});
 await connection.finished;
 assert.equal(calls,2);assert.deepEqual(received,[{connection:1},{connection:2}]);
});

test('invalid identity is reported without an endless retry loop',async()=>{
 let calls=0;const errors=[];
 const connection=followSocial({uid:'',sharedRoot:'',fetchImpl:async()=>{calls++;return {ok:false,status:401};}},()=>{},e=>errors.push(e));
 await connection.finished;assert.equal(calls,1);assert.equal(errors[0].status,401);
});
