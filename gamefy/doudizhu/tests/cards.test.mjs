import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cardLabel,toggleSelection,selectGesture} from '../publish/cards.js';

test('card labels distinguish ranks suits and jokers',()=>{
  assert.equal(cardLabel(0),'♠3'); assert.equal(cardLabel(48),'♠2');
  assert.equal(cardLabel(52),'小王'); assert.equal(cardLabel(53),'大王');
});
test('selection does not mutate previous set and touch gesture visits once',()=>{
  const original=new Set([0]);
  assert.deepEqual([...toggleSelection(original,4)],[0,4]);
  assert.deepEqual([...original],[0]);
  const visited=new Set();
  let selected=selectGesture(new Set(),0,visited);
  selected=selectGesture(selected,0,visited);
  assert.deepEqual([...selected],[0]);
  selected=selectGesture(selected,4,visited);
  assert.deepEqual([...selected],[0,4]);
});
