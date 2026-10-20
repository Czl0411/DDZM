import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../publish/v3/game.js',import.meta.url),'utf8');
function fixture(){
 const handlers={},actions=[],events=[];let content;
 const context=vm.createContext({modal:(html,view)=>content={html,view},button:(text,id)=>`<button id="${id}">${text}</button>`,bind:(id,fn)=>handlers[id]=fn,
  $:id=>({close:()=>events.push('close'),focus:()=>events.push('focus:'+id)}),run:fn=>fn(),act:async action=>actions.push(action)});
 vm.runInContext(source.slice(source.indexOf('function confirmPass()'),source.indexOf('function tick()')),context);
 context.confirmPass();return {handlers,actions,events,content};
}
test('opening the pass reminder or cancelling never submits a pass',()=>{
 const f=fixture();assert.match(f.content.html,/本局不能再出牌或使用领袖能力/);assert.equal(f.content.view,'pass-confirm');
 assert.deepEqual(f.actions,[]);assert.ok(f.events.includes('focus:cancel-pass'));
 f.handlers['cancel-pass']();assert.deepEqual(f.actions,[]);assert.equal(f.events.at(-1),'close');
});
test('only explicit confirmation submits the pass',async()=>{
 const f=fixture();await f.handlers['confirm-pass']();assert.deepEqual(f.actions,['pass']);assert.equal(f.events.at(-1),'close');
 assert.match(source,/bind\('pass',confirmPass\)/);
});
