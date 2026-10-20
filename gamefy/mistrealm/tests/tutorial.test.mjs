import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {practiceAction as act,practiceState,setupTutorial} from '../publish/v3/tutorial.js';
const scenes=JSON.parse(readFileSync(new URL('../publish/v3/tutorial.json',import.meta.url)));
const scene=key=>scenes.find(s=>s.key===key).state;

test('practice rejects skipped actions and requires selection plus target confirmation',()=>{
 let s=practiceState();assert.equal(act(s,scenes,'pass'),s);
 s=act(s,scenes,'continue');const expected=scenes[s.step].expected;
 assert.equal(act(s,scenes,'play',expected.payload),s);
 s=act(s,scenes,'select',{card:expected.payload.card});
 assert.equal(act(s,scenes,'play',{...expected.payload,row:2}),s);
 s=act(s,scenes,'play',expected.payload);assert.equal(s.step,2);
 s={step:4,selected:null,choice:null};const choice=scenes[4].expected.payload;
 assert.equal(act(s,scenes,'choose',choice),s);
 s=act(s,scenes,'pick',choice);assert.equal(act(s,scenes,'choose',choice).step,5);
});

test('the complete two-round path reaches victory without modifying engine snapshots',()=>{
 const original=JSON.stringify(scenes);let s=practiceState();
 for(let i=0;i<scenes.length-1;i++){
  assert.equal(s.step,i);const e=scenes[i].expected;
  if(e.action==='play')s=act(s,scenes,'select',{card:e.payload.card});
  if(e.action==='choose')s=act(s,scenes,'pick',e.payload);
  s=act(s,scenes,e.action,e.payload);
 }
 assert.equal(s.step,scenes.length-1);assert.equal(scene('complete').phase,'finished');
 assert.equal(scene('complete').winner,0);assert.deepEqual(scene('complete').lives,[2,0]);
 assert.equal(JSON.stringify(scenes),original);
});

test('stopping, clearing, discard persistence and two-card draw match actual rules',()=>{
 const empty=scene('enemy-empty'),passed=scene('damage-spell');
 assert.equal(empty.players[1].hand_count,0);assert.equal(empty.players[1].leader_used,true);
 assert.equal(passed.players[1].passed,true);assert.equal(passed.players[0].score,passed.players[1].score);
 const end=scene('round-clear'),next=scene('round-draw');
 assert.deepEqual(end.lives,[2,1]);assert.equal(next.round,2);
 assert.equal(next.players[0].hand_count,end.players[0].hand_count+2);
 assert.equal(next.players[0].deck_count,end.players[0].deck_count-2);
 assert.equal(next.players[0].leader_used,true);
 for(let side=0;side<2;side++){
  assert.equal(next.players[side].rows.flat().length,0);
  const discard=new Set(next.players[side].discard.map(c=>c.id));
  for(const c of end.players[side].rows.flat().concat(end.players[side].discard))assert.ok(discard.has(c.id));
 }
});

test('enemy spy blocks the fourth slot and sacrifice returns it to the original owner',()=>{
 const full=scene('full-row'),freed=scene('space-freed');
 assert.equal(full.players[0].rows[0].length,4);
 const branch=full.players[0].hand.find(c=>c.card==='c069');
 assert.ok(!full.legal_moves.some(m=>m.action==='play'&&m.payload.card===branch.id));
 const spy=full.players[0].rows[0].find(c=>c.card==='c108');assert.ok(spy);
 assert.equal(freed.players[0].rows[0].length,3);
 assert.ok(freed.players[1].discard.some(c=>c.id===spy.id));
 assert.ok(!freed.players[0].discard.some(c=>c.id===spy.id));
 assert.ok(scene('branch').legal_moves.some(m=>m.action==='play'&&m.payload.card===branch.id));
 assert.equal(scene('enemy-oath').players[0].hand_count,scene('branch-sacrifice').players[0].hand_count+2);
});

test('automatic welcome remains new-player-only and replay stays available',t=>{
 const savedDocument=globalThis.document,savedStorage=globalThis.localStorage;
 t.after(()=>{globalThis.document=savedDocument;globalThis.localStorage=savedStorage;});
 const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:true,classList:{remove(){},add(){}},innerHTML:'',addEventListener(){},querySelector:()=>node('child'),querySelectorAll:()=>[],insertAdjacentHTML(){},remove(){},scrollIntoView(){}});return nodes.get(id);};
 globalThis.document={getElementById:node,addEventListener(){},querySelectorAll:()=>[]};
 const stored=new Map();globalThis.localStorage={getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v)};
 let history,offers=0;
 const setup=()=>setupTutorial({cards:()=>({cards:{}}),scenes:()=>scenes,view:()=>'',choices:()=>'',card:()=>'',inspect(){},uid:()=> 'a',eligible:()=>history===false,blocked:()=>false,home(){},modal(){offers++;},closeModal(){},sync(){}});
 setup().offer();assert.equal(offers,0);
 history=true;const veteran=setup();veteran.offer();assert.equal(offers,0);veteran.start();assert.equal(veteran.active(),true);
 history=false;const newcomer=setup();newcomer.offer();assert.equal(offers,1);newcomer.offer();assert.equal(offers,1);
 node('tutorial-skip').onclick();setup().offer();assert.equal(offers,1);
});

test('tutorial uses the shared real battle renderer and never calls game services',()=>{
 const tutorial=readFileSync(new URL('../publish/v3/tutorial.js',import.meta.url),'utf8');
 const game=readFileSync(new URL('../publish/v3/game.js',import.meta.url),'utf8');
 assert.match(game,/main.innerHTML=battleMarkup\(s,selection,playSelection,pickedOption\)/);
 assert.match(game,/view:battleMarkup,choices:choicePanel/);
 assert.doesNotMatch(tutorial,/client\.|fetch\(/);
});

 test('persistent spell occupies a spell slot and mercenary removes only the chosen enemy aura',()=>{
 const before=scene('persistent-spell'),active=scene('persistent-active'),choice=scene('destroy-persistent'),after=scene('persistent-destroyed');
 const spear=p=>p.rows[0].find(c=>c.card==='c002');
 assert.equal(active.players[0].spells.length,1);
 assert.equal(active.players[0].rows.flat().length,before.players[0].rows.flat().length);
 assert.equal(active.players[0].hand_count,before.players[0].hand_count-1);
 assert.equal(spear(active.players[0]).power,spear(before.players[0]).power+2);
 assert.equal(active.players[0].discard.length,before.players[0].discard.length);
 const ward=choice.players[1].spells.find(c=>c.card==='c118');
 assert.ok(choice.pending.options.some(o=>o.target_ids.includes(ward.id)));
 assert.equal(choice.players[1].rows[0][0].power,4);
 assert.equal(after.players[1].rows[0][0].power,2);
 assert.equal(after.players[1].spells.length,0);
 assert.ok(after.players[1].discard.some(c=>c.id===ward.id));
 assert.equal(after.players[0].spells.length,1);
 assert.equal(spear(after.players[0]).power,7);
 assert.equal(after.players[0].rows[0].length,3);
 assert.equal(scene('full-row').players[0].rows[0].length,4);
 assert.equal(scene('pass-second').players[0].hand_count,1);
 assert.equal(scene('pass-second').players[1].hand_count,0);
 assert.equal(scene('second-empty').players[0].passed,true);
});
