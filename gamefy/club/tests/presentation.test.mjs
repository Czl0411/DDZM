import test from 'node:test';
import assert from 'node:assert/strict';
import {actionText, seatStatus, newActions} from '../publish/games/card-table/presentation.js';

test('amounts distinguish added chips from a raise target', () => {
  assert.equal(actionText({action:'raise', amount:20, paid:15}), '加注至 20');
  assert.equal(actionText({action:'call', paid:5}), '跟注 5');
  assert.equal(actionText({action:'fold', automatic:true}), '超时自动弃牌');
});
test('persistent folded/all-in states take precedence over previous moves', () => {
  assert.equal(seatStatus({folded:['a'], action_history:[{player:'a',action:'call',paid:5}]}, 'a'), '已弃牌');
  assert.equal(seatStatus({all_in:['a']}, 'a'), '已全下');
  assert.equal(seatStatus({stood:['a']}, 'a'), '已停牌');
});
test('initial snapshots, duplicate messages, missed actions and new hands do not replay', () => {
  const event = n => ({sequence:n,player:'a',action:'check'});
  const room = (hand, seq) => ({id:'room',hand_number:hand,state:{action_history:[event(seq)]}});
  assert.deepEqual(newActions(null,room(1,5)),[]);
  assert.deepEqual(newActions(room(1,5),room(1,5)),[]);
  assert.deepEqual(newActions(room(1,5),room(1,8)),[]);
  assert.deepEqual(newActions(room(1,5),room(2,1)),[]);
  assert.deepEqual(newActions(room(1,5),room(1,6)),[event(6)]);
});
