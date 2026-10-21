import test from 'node:test';
import assert from 'node:assert/strict';
import {expeditionFits} from '../publish/v3/expedition.js';
const cards={u:{type:'unit',hero:false},h:{type:'unit',hero:true},s:{type:'special',hero:false}};
const deck=[...Array.from({length:6},(_,i)=>({id:'u'+i,card:'u'})),{id:'hero',card:'h'},...Array.from({length:3},(_,i)=>({id:'s'+i,card:'s'}))];
test('full expedition deck requires a compatible replacement',()=>{
 for(const card of ['u','h','s'])assert.equal(expeditionFits(deck,card,cards),false);
 assert.equal(expeditionFits(deck,'u',cards,'u0'),true);
 assert.equal(expeditionFits(deck,'s',cards,'s0'),true);
 assert.equal(expeditionFits(deck,'s',cards,'u0'),false);
 assert.equal(expeditionFits(deck,'h',cards,'u0'),false);
 assert.equal(expeditionFits(deck,'h',cards,'hero'),true);
});
test('heroes occupy a unit slot and no more than one hero is allowed',()=>{
 assert.equal(expeditionFits(deck.slice(0,6),'h',cards),true);
 assert.equal(expeditionFits(deck.slice(0,7),'u',cards),false);
 assert.equal(expeditionFits([{id:'h',card:'h'}],'h',cards),false);
 assert.equal(expeditionFits([],'h',cards),true);
});
