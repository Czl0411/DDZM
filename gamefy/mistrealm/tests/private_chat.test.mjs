import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {V3Client} from '../publish/v3/client.js';

function fixture(){
 const nodes=new Map(),reads=[],sent=[],document={hidden:false,getElementById:node};let visible=true,uuid=0;
 function node(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,disabled:false,innerHTML:'',scrollHeight:100,clientHeight:100,scrollTop:0});return nodes.get(id);}
 const client={privateMessages:async uid=>({player:{uid,name:uid},online:false,has_more:false,items:[]}),
  privateRead:async(uid,id)=>{reads.push({uid,id});return {unread_messages:0};},privateSend:async(...args)=>{sent.push(args);}};
 const context=vm.createContext({document,crypto:{randomUUID:()=>`request-${++uuid}`},console,Map,Date});
 vm.runInContext(readFileSync(new URL('../publish/v3/private_chat.js',import.meta.url),'utf8').replace('export function','function'),context);
 const chat=context.setupPrivateChat({client,visible:()=>visible,onRead(){},onBack(){}});
 return {chat,client,node,document,reads,sent,hide:()=>visible=false};
}
const tick=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
const message=(id,text='留言')=>({id,text,outgoing:false,created_at:'2026-10-16T10:00:00Z'});

test('private text is escaped and read is acknowledged only when visible',async()=>{
 const f=fixture();f.client.privateMessages=async uid=>({player:{uid,name:'好友'},online:false,has_more:false,items:[message(1,'<img src=x onerror=alert(1)>')]});
 f.hide();f.chat.open({uid:'a',name:'a'});await tick();
 assert.equal(f.reads.length,0);assert.ok(f.node('private-messages').innerHTML.includes('&lt;img'));assert.ok(!f.node('private-messages').innerHTML.includes('<img'));
});

test('switching friends preserves drafts and rejects a late previous conversation',async()=>{
 const f=fixture();let complete;
 f.client.privateMessages=uid=>uid==='a'?new Promise(r=>complete=r):Promise.resolve({player:{uid,name:'乙'},online:true,has_more:false,items:[message(2,'乙的消息')]});
 f.chat.open({uid:'a',name:'甲'});f.node('private-input').value='给甲的草稿';f.node('private-input').oninput();
 f.chat.open({uid:'b',name:'乙'});await tick();
 complete({player:{uid:'a',name:'甲'},online:true,has_more:false,items:[message(1,'过期消息')]});await tick();
 assert.ok(!f.node('private-messages').innerHTML.includes('过期消息'));assert.equal(f.node('private-name').textContent,'乙');
 f.chat.open({uid:'a',name:'甲'});assert.equal(f.node('private-input').value,'给甲的草稿');
});

test('reading older history does not scroll or mark newly arriving messages read',async()=>{
 const f=fixture();let items=[message(1)];f.client.privateMessages=async uid=>({player:{uid,name:uid},online:true,has_more:false,items});
 f.chat.open({uid:'a',name:'a'});await tick();assert.equal(f.reads.length,1);
 Object.assign(f.node('private-messages'),{scrollHeight:800,clientHeight:100,scrollTop:40});items=[message(2)];await f.chat.refresh();
 assert.equal(f.node('private-messages').scrollTop,40);assert.equal(f.reads.length,1);
 f.node('private-messages').scrollTop=700;f.node('private-messages').onscroll();await tick();assert.equal(f.reads.at(-1).id,2);
});

test('failed send preserves draft and retries the same request id without duplicate submissions',async()=>{
 const f=fixture();f.chat.open({uid:'a',name:'a'});await tick();let fail=true;
 f.client.privateSend=async(...args)=>{f.sent.push(args);if(fail)throw Error('网络中断');};
 f.node('private-input').value='离线留言';await f.node('private-send').onclick();
 assert.equal(f.node('private-input').value,'离线留言');fail=false;await f.node('private-send').onclick();
 assert.equal(f.sent[0][2],f.sent[1][2]);assert.equal(f.node('private-input').value,'');
});

test('hidden document does not clear unread messages',async()=>{
 const f=fixture();f.document.hidden=true;f.client.privateMessages=async uid=>({player:{uid,name:uid},online:true,items:[message(1)]});
 f.chat.open({uid:'a',name:'a'});await tick();assert.equal(f.reads.length,0);
});

test('private client uses shared social endpoints and passes read boundary and retry key',async()=>{
 const calls=[];const client=new V3Client({sdk:{},apiBase:'',fetchImpl:async(url,o)=>{calls.push({url,body:o.body?JSON.parse(o.body):null});return {ok:true,json:async()=>({})};}});
 await client.privateConversations(1);await client.privateMessages('a&b',{before:31});await client.privateSend('a','你好','request');await client.privateRead('a',30);
 assert.equal(calls[0].url,'/api/mistrealm/social/conversations?page=1');assert.equal(new URL(calls[1].url,'https://x').searchParams.get('uid'),'a&b');
 assert.deepEqual(calls[2].body,{uid:'a',text:'你好',request_id:'request'});assert.deepEqual(calls[3].body,{uid:'a',through_id:30});
});

test('reconnect catches up through more than one page without losing or duplicating messages',async()=>{
 const f=fixture();let calls=[];
 f.client.privateMessages=async(uid,cursor)=>{calls.push(cursor);const after=cursor?.after||0;
  const items=after===0?[message(1)]:after===1?Array.from({length:30},(_,i)=>message(i+2)):[message(32),message(33)];
  return {player:{uid,name:uid},online:true,items,has_more:after===1};};
 f.chat.open({uid:'a',name:'a'});await tick();await f.chat.refresh();
 assert.deepEqual(calls.map(x=>x?.after),[undefined,1,31]);
 assert.equal((f.node('private-messages').innerHTML.match(/class="private-message /g)||[]).length,33);
 assert.equal(f.reads.at(-1).id,33);
});

test('an event arriving while messages load triggers a catch-up afterwards',async()=>{
 const f=fixture();let complete,calls=0;
 f.client.privateMessages=async uid=>{calls++;if(calls===1)return new Promise(r=>complete=r);
  return {player:{uid,name:uid},online:true,items:[message(2)],has_more:false};};
 f.chat.open({uid:'a',name:'a'});await f.chat.refresh();
 complete({player:{uid:'a',name:'a'},online:true,items:[message(1)],has_more:false});await tick();
 assert.equal(calls,2);assert.equal(f.reads.at(-1).id,2);
});
