import test from 'node:test';
import assert from 'node:assert/strict';
import {feedbackBatches,powerChanges,stepText} from '../publish/v3/effect-feedback.js';
const power=(unit,amount)=>({kind:'power',unit,card:unit,seat:0,amount});
test('dense chains retain order in at most two beats',()=>{
 const steps=Array.from({length:40},(_,i)=>({events:[power('u',i)]})),batches=feedbackBatches(steps);
 assert.equal(batches.length,2);assert.deepEqual(batches.flat(),steps);assert.deepEqual(feedbackBatches([]),[]);
});
test('one beat aggregates actual changes per entity, not printed ability amounts',()=>{
 const steps=[{events:[power('a',1),power('b',-2)]},{events:[power('a',2),power('b',2)]}];
 assert.deepEqual(powerChanges(steps).map(e=>[e.unit,e.amount]),[['a',3]]);
});
test('trigger text identifies a public source and count without drawn card names',()=>{
 const step={source:'白枝',events:[{kind:'draw',seat:0,amount:1}]};
 assert.equal(stepText(step,x=>x,0),'白枝：己方抽1张牌');
 assert.equal(stepText(step,x=>x,1),'白枝：对手抽1张牌');
 assert.match(stepText({events:[power('a',2),power('b',2)]},x=>x,0),/己方2个单位 ＋2/);
});
test('return and sacrifice text show the public outcome and destination',()=>{
 assert.equal(stepText({source:'领袖',events:[{kind:'return',card:'间谍',seat:1,destination:0}]},x=>x,0),'领袖：间谍返回至己方手牌');
 assert.equal(stepText({events:[{kind:'death',card:'单位',reason:'sacrifice'}]},x=>x,0),'单位被献祭');
});
test('repeated draws from one source summarize the actual total',()=>{
 assert.equal(stepText({source:'白枝',events:[{kind:'draw',seat:0,amount:1},{kind:'draw',seat:0,amount:1}]},x=>x,0),'白枝：己方抽2张牌');
});
