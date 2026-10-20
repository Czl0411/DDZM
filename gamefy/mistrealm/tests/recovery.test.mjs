import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {battleStatus} from '../publish/v3/battle-info.js';
const source=readFileSync(new URL('../publish/v3/game.js',import.meta.url),'utf8').replaceAll('import.meta.url',"'http://localhost/v3/game.js'");
function fixture(){
 const ctx=vm.createContext({connectionLost:true,recoveredVersion:null,room:null,latestRoom:null,selection:'old',playSelection:true,returnToStory:false,receivedAt:0,
  client:{},performance:{now:()=>0},battleStatus,feedback:text=>ctx.message=text,clearReveal:()=>ctx.cleared=true,render:()=>ctx.rendered=true,updateBattleStatus(){},syncActionLog:()=>ctx.replayed=true});
 vm.runInContext(source.slice(source.indexOf('function accept('),source.indexOf('function enter(')),ctx);
 return ctx;
}
const value=(version=5,match_id='match')=>({room_id:'room',match_id,state:{version,phase:'playing',rules_version:3,balance_revision:2,round:2,seat:0,turn:1,players:[{passed:false},{passed:false}],pending:{actor:0,options:[{token:'new'}]}}});
test('recovery applies newest snapshot without replay and announces pending choice',()=>{
 const c=fixture();c.latestRoom=value(4);c.accept(value());
 assert.equal(c.connectionLost,false);assert.equal(c.recoveredVersion,5);assert.equal(c.selection,null);
 assert.equal(c.cleared,true);assert.equal(c.replayed,undefined);assert.match(c.message,/第2局.*请选择效果目标/);
 assert.equal(c.room.state.pending.options[0].token,'new');
});
test('stale snapshot cannot mark a disconnected game recovered',()=>{
 const c=fixture();c.latestRoom=value(7);c.accept(value(5));
 assert.equal(c.connectionLost,true);assert.equal(c.rendered,undefined);
});
test('new match in the same room may restart at lower version',()=>{
 const c=fixture();c.latestRoom=value(30,'old');c.accept(value(2,'new'));
 assert.equal(c.room.match_id,'new');assert.equal(c.connectionLost,false);
});
test('disconnected game cannot submit a stale play',async()=>{
 const c=fixture();c.room=value();
 vm.runInContext(source.slice(source.indexOf('async function act('),source.indexOf('function syncChannel(')),c);
 await assert.rejects(()=>c.act('play',{card:'old'}),/等待牌局同步/);
});
