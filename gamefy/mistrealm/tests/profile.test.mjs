import test from 'node:test';
import assert from 'node:assert/strict';
import {matchOutcome,matchScore,rankChange,setupProfile} from '../publish/v3/profile.js';
import {V3Client} from '../publish/v3/client.js';

test('history reports whole-match result, viewer-ordered rounds and settled rank delta',()=>{
 const item={seat:1,winner:1,rounds:[{winner:0},{winner:1},{winner:1}],ranked:{result:{deltas:[-16,16]}}};
 assert.equal(matchOutcome(item),'胜利');assert.equal(matchScore(item),'2 : 1');assert.equal(rankChange(item),'+16 分');
 assert.equal(matchOutcome({...item,winner:null}),'平局');assert.equal(rankChange({...item,ranked:null}),'不计排位分');
 assert.equal(rankChange({...item,ranked:{result:{void:true}}}),'未计分');
});

test('profile client only addresses authenticated personal history and encodes public UID',async()=>{
 const calls=[],client=new V3Client({sdk:{},apiBase:'',fetchImpl:async(url,o)=>{calls.push({url,body:o.body?JSON.parse(o.body):null});return {ok:true,json:async()=>({})};}});
 await client.playerProfile('旅人&x');await client.savePreferences({challenges:'friends',sound:false});await client.matchHistory(2);await client.matchHistoryDetail('match-id');
 assert.equal(new URL(calls[0].url,'http://test').searchParams.get('uid'),'旅人&x');
 assert.deepEqual(calls[1].body,{challenges:'friends',sound:false});assert.equal(calls[2].url,'/api/mistrealm/v3/profile/history?page=2');assert.equal(calls[3].url,'/api/mistrealm/v3/profile/history/match-id');
});

test('closed profile does not reopen from a late fetch; public profile has no settings or history tabs',async()=>{
 const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{open:true,dataset:{view:'profile-center'}});return nodes.get(id);};
 const before=globalThis.document;globalThis.document={getElementById:node,querySelectorAll:()=>[]};
 try{
  let resolve,html='';const api={playerProfile:()=>new Promise(r=>resolve=r)};
  const p=setupProfile({client:api,uid:()=> 'self',modal:text=>html=text,cards:()=>({}),isBusy:()=>false});
  const pending=p.open('other');node('modal').open=false;
  resolve({uid:'other',self:false});await pending;assert.ok(html.includes('正在读取'));
  node('modal').open=true;api.playerProfile=async()=>({uid:'other',name:'<unsafe>',self:false,rank:{tier:{key:'bronze',name:'青铜'},rating:1000,peak:1000,wins:1,losses:0,draws:0},season:{name:'S1'},interaction:{friend:'none',challenge_reason:'暂不接受挑战',friend_request_reason:'暂不接受好友申请',presence:'online'}});
  await p.open('other');assert.ok(html.includes('&lt;unsafe&gt;'));assert.ok(!html.includes('data-profile-tab="history"'));assert.ok(!html.includes('data-profile-tab="privacy"'));assert.ok(html.includes('暂不接受挑战'));
 }finally{globalThis.document=before;}
});
