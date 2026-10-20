import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {V3Client} from '../publish/v3/client.js';

function fixture(){
 const nodes=new Map(),tabs=['chat','all','friends','requests','invites','messages'].map(tab=>({dataset:{socialTab:tab},classList:{toggle(){}},setAttribute(){}})),timers=[],entered=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:false,textContent:'',innerHTML:'',value:'',classList:{toggle(){}},setAttribute(){},querySelector(){return node('span');}});return nodes.get(id);};
 node('channel-panel').hidden=true;
 const document={hidden:false,getElementById:node,querySelectorAll:s=>s==='[data-social-tab]'?tabs:[],addEventListener(){}};
 let receive,starts=0,stops=0;
 const client={followSocial(fn){receive=fn;starts++;return {stop(){stops++;}};},socialPulse:async()=>({online_count:1,friend_requests:0,invitations:[],joined_room_id:null}),socialPlayers:async()=>({items:[],total:0})};
 let busy=false;
 const context=vm.createContext({setupPrivateChat:()=>({active:()=>false,close(){},refresh(){}}),document,setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},console});
 vm.runInContext(readFileSync(new URL('../publish/v3/social.js',import.meta.url),'utf8').replace(/^import .*;\n/,'').replace('export function','function'),context);
 const social=context.setupSocial({client,ready:()=>true,currentRoom:()=>null,isBusy:()=>busy,deck:()=>({id:'deck',name:'旅团'}),enter:r=>entered.push(r),openChannel:open=>node('channel-panel').hidden=!open});
 return {social,client,node,tabs,document,timers,entered,setBusy:v=>busy=v,receive:p=>receive(p),starts:()=>starts,stops:()=>stops};
}

test('one social stream starts once and hidden pages do not open a connection',async()=>{
 const f=fixture();f.social.start();f.social.start();assert.equal(f.starts(),1);
 await f.receive({summary:{online_count:2,friend_requests:1,invitations:[]}});
 assert.equal(f.node('social-online').textContent,'在线 2');assert.equal(f.node('social-notice').hidden,false);
 f.social.stop();assert.equal(f.stops(),1);f.document.hidden=true;f.social.start();assert.equal(f.starts(),1);
 assert.equal(f.timers.length,0);
});

test('accepted invitation opens its room once without interrupting a current match',async()=>{
 const f=fixture();f.social.start();const packet={summary:{online_count:2,friend_requests:0,invitations:[],joined_room_id:'room'}};
 f.client.snapshot=async()=>({room_id:'room'});
 f.setBusy(true);await f.receive(packet);assert.equal(f.entered.length,0);
 f.setBusy(false);await f.receive(packet);await f.receive(packet);assert.equal(f.entered.length,1);
});

test('late player search cannot overwrite a different social tab',async()=>{
 const f=fixture();let finish;
 f.client.socialPlayers=()=>new Promise(r=>finish=r);
 f.tabs[1].onclick();
 f.tabs[4].onclick();assert.equal(f.node('social-heading').textContent,'挑战邀请');
 finish({items:[{uid:'stale',name:'过时搜索',presence:'online',friend:'none'}],total:1});
 await Promise.resolve();await Promise.resolve();
 assert.ok(!f.node('social-list').innerHTML.includes('过时搜索'));
});

test('social client uses shared UID endpoints and passes only selected deck IDs',async()=>{
 const calls=[];
 const client=new V3Client({sdk:{},apiBase:'',fetchImpl:async(url,o)=>{calls.push({url,body:o.body?JSON.parse(o.body):null});return {ok:true,json:async()=>({})};}});
 await client.socialPulse();await client.socialPlayers('all','雨 & 风',1);await client.friend('player','request');
 await client.challenge('player','deck');await client.challengeReply('invite','accept','deck');
 assert.equal(calls[0].url,'/api/mistrealm/social/presence');
 assert.equal(new URL(calls[1].url,'https://test').searchParams.get('search'),'雨 & 风');
 assert.deepEqual(calls[3].body,{uid:'player',deck_id:'deck'});
 assert.deepEqual(calls[4].body,{operation:'accept',deck_id:'deck'});
});

test('private unread badge opens conversations without exposing message text in the public bar',async()=>{
 const f=fixture();f.client.socialPulse=async()=>({online_count:2,friend_requests:0,invitations:[],unread_messages:3});
 f.client.privateConversations=async()=>({items:[],total:0});f.social.start();await f.receive({summary:await f.client.socialPulse()});
 assert.equal(f.node('social-message-count').textContent,3);assert.equal(f.node('social-notice').textContent,'消息 3');
 f.node('social-notice').onclick();await Promise.resolve();await Promise.resolve();
 assert.equal(f.node('social-heading').textContent,'好友私聊');assert.equal(f.node('social-search-form').hidden,true);
});
