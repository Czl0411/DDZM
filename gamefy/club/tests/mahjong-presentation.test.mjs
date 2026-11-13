import test from 'node:test';
import assert from 'node:assert/strict';
import {tablePosition, mahjongChanges} from '../publish/mahjong-presentation.js';
const snapshot = () => ({id:'room',version:10,seat:2,game:{round_wind:27,hand_number:1,honba:0,hand:[1,2,3],discards:[[],[],[],[]],melds:[[],[],[],[]]}});

test('all four viewers see their own seat below and opponents in relative directions', () => {
  for(let viewer=0;viewer<4;viewer++) {
    assert.deepEqual([0,1,2,3].map(offset => tablePosition((viewer+offset)%4, viewer)), ['self','right','top','left']);
  }
  assert.equal(tablePosition(0,null),'self');
});
test('initial load, repeated snapshot, reconnect gap and next hand never replay actions', () => {
  const before=snapshot(), next=structuredClone(before); next.game.discards[0].push({tile:4});
  assert.deepEqual(mahjongChanges(null,next),[]);
  assert.deepEqual(mahjongChanges(before,next),[]);
  next.version=13; assert.deepEqual(mahjongChanges(before,next),[]);
  next.version=11; next.game.honba=1; assert.deepEqual(mahjongChanges(before,next),[]);
  next.game.honba=0; next.id='another'; assert.deepEqual(mahjongChanges(before,next),[]);
});
test('one discard plus a draw can animate together without revealing other hands', () => {
  const before=snapshot(), next=structuredClone(before); next.version++;
  next.game.discards[1].push({tile:4,riichi:true,called:false}); next.game.hand.push(5);
  assert.deepEqual(mahjongChanges(before,next),[{kind:'discard',seat:1,tile:4,riichi:true,called:false},{kind:'draw',seat:2,tile:5}]);
  next.seat=null; next.game.hand=[];
  assert.equal(mahjongChanges(before,next).some(event=>event.kind==='draw'),false);
});
test('new meld and added kan produce one cue, unchanged meld does not replay', () => {
  const before=snapshot(); before.game.melds[0]=[{kind:'pon',tiles:[4,5,6]}];
  const next=structuredClone(before); next.version++; next.game.melds[0][0].kind='kakan'; next.game.melds[1].push({kind:'chi',tiles:[8,12,16]});
  assert.deepEqual(mahjongChanges(before,next),[{kind:'meld',seat:0,meld:'kakan',index:0},{kind:'meld',seat:1,meld:'chi',index:0}]);
  next.game.melds=structuredClone(before.game.melds); assert.deepEqual(mahjongChanges(before,next),[]);
});

test('opponent draws use only public counts and never include a tile identity', () => {
  const before=snapshot(); before.game.hand_counts=[13,13,13,13];
  const next=structuredClone(before); next.version++; next.game.hand_counts[3]++;
  assert.deepEqual(mahjongChanges(before,next),[{kind:'draw',seat:3}]);
  next.game.hand_counts[3]-=3;
  assert.deepEqual(mahjongChanges(before,next),[]);
  next.seat=null; next.game.hand=[]; next.game.hand_counts[0]++;
  assert.deepEqual(mahjongChanges(before,next),[{kind:'draw',seat:0}]);
});

test('wait labels distinguish no yaku, tsumo-only, mixed waits and furiten', async () => {
  const {waitStatus, handHintStatus} = await import('../publish/mahjong-presentation.js');
  const allowed = {ron_reason:null,tsumo_reason:null};
  const noYaku = {ron_reason:'no_yaku',tsumo_reason:'no_yaku'};
  const tsumoOnly = {ron_reason:'no_yaku',tsumo_reason:null};
  assert.equal(waitStatus(noYaku).label,'无役');
  assert.equal(waitStatus(tsumoOnly).label,'仅自摸');
  assert.equal(handHintStatus({waits:[allowed,noYaku]}).label,'部分受限');
  assert.equal(handHintStatus({waits:[noYaku,noYaku]}).label,'无役');
  assert.equal(handHintStatus({waits:[tsumoOnly]}).label,'仅可自摸');
  for (const furiten of ['discard','temporary','riichi_pass']) {
    const value = {furiten,waits:[{...noYaku,ron_reason:furiten}]};
    assert.match(handHintStatus(value).label,/振听/);
    assert.match(handHintStatus(value).detail,/普通自摸也无役/);
    assert.equal(waitStatus(value.waits[0]).tsumo,'自摸无役');
  }
  // A real special-yaku ron supersedes the ordinary no-yaku preview.
  assert.equal(waitStatus({...noYaku,ron_now:true}).ron,'可荣和');
  assert.equal(handHintStatus({waits:[{...noYaku,ron_now:true}]}).label,'可荣和');
});
