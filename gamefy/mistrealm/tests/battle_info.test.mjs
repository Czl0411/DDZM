import test from 'node:test';
import assert from 'node:assert/strict';
import {battleStatus,groupMatchActions} from '../publish/v3/battle-info.js';
const state={phase:'playing',seat:0,turn:1,players:[{name:'甲'},{name:'乙'}]};
test('connection and effect playback take priority over turn and pending choice',()=>{
 const s={...state,pending:{actor:1}};
 assert.match(battleStatus(s),/对手正在选择效果目标/);
 assert.match(battleStatus(s,{animating:true}),/正在结算/);
 assert.match(battleStatus(s,{animating:true,reconnecting:true}),/正在重连/);
 assert.match(battleStatus({...s,pending:{actor:0}}),/请选择/);
 assert.match(battleStatus({...s,spectator:true}),/乙 正在选择/);
 assert.match(battleStatus(state),/等待对手出牌/);
 assert.match(battleStatus({...state,turn:0},{submitting:true}),/提交行动/);
});
test('choices from either seat belong to the initiating action; rounds and passes remain separate',()=>{
 const log=[{id:1,round:1,kind:'play',seat:0},{id:2,round:1,kind:'choose',seat:0},{id:3,round:1,kind:'choose',seat:1},{id:4,round:1,kind:'pass',seat:1},{id:5,round:2,kind:'play',seat:1}];
 const before=JSON.stringify(log),groups=groupMatchActions(log,[{log_id:2,effects:[{events:[]}]}]);
 assert.deepEqual(groups.map(g=>g.steps.length),[3,1,1]);
 assert.equal(groups[0].steps[1].effects.length,1);
 assert.equal(JSON.stringify(log),before);
});
test('persisted public effects remain usable after short-lived animation frames expire',()=>{
 const effects=[{seat:0,events:[{kind:'draw',seat:0,amount:1}]}];
 assert.deepEqual(groupMatchActions([{id:1,kind:'play',round:1,effects}])[0].steps[0].effects,effects);
});
