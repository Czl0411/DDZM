import test from 'node:test';
import assert from 'node:assert/strict';
import {selectionOption,toggleSelection} from '../publish/v3/multi-select.js';
const pending={multi_select:{cards:['a','b','c'].map(id=>({id})),minimum:0,maximum:2,ordered:false},options:[{token:'skip',select_ids:[]},{token:'a',select_ids:['a']},{token:'b',select_ids:['b']},{token:'ab',select_ids:['a','b']},{token:'c',select_ids:['c']}]};
test('toggle preserves identity, deselects, checks quantity and valid combinations',()=>{
 let ids=toggleSelection(pending,[],'b').ids;
 ids=toggleSelection(pending,ids,'a').ids;
 assert.equal(selectionOption(pending,ids).token,'ab');
 assert.deepEqual(toggleSelection(pending,ids,'c').ids,ids);
 assert.match(toggleSelection(pending,['a'],'c').notice,/不能一起选择/);
 assert.deepEqual(toggleSelection(pending,ids,'b').ids,['a']);
 assert.equal(selectionOption(pending,[]).token,'skip');
 assert.match(toggleSelection(pending,[],'unknown').notice,/不是合法目标/);
});
test('exact two remains unconfirmed after one, ordered damage respects click order',()=>{
 const p={...pending,multi_select:{...pending.multi_select,minimum:2,ordered:true},options:[{token:'ab',select_ids:['a','b']},{token:'ba',select_ids:['b','a']}]};
 assert.equal(selectionOption(p,['a']),undefined);
 assert.equal(selectionOption(p,['b','a']).token,'ba');
 assert.equal(selectionOption(p,['a','b']).token,'ab');
});
