import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function fixture(){
 const nodes=new Map(),timers=[];
 const node=id=>{
  if(!nodes.has(id))nodes.set(id,{hidden:false,open:false,value:'',textContent:'',innerHTML:'',scrollTop:0,scrollHeight:100,clientHeight:100,
   classList:{toggle(){}},setAttribute(){},focus(){},append(child){child.parentElement=this;}});
  return nodes.get(id);
 };
 const source=readFileSync(new URL('../publish/v3/game.js',import.meta.url),'utf8');
 const context=vm.createContext({$:node,document:{querySelectorAll:()=>[]},images(){},esc:String,
  social:{sync(){},refresh(){}},profile:{},room:null,queue:null,channelOpen:false,channelItems:[],channelKnown:new Set(),channelTimer:null,channelRefreshing:false,channelLoaded:false,
  client:{channelMessages:async()=>({items:context.channelItems})},setTimeout(fn){timers.push(fn);return timers.length;},clearTimeout(){}});
 vm.runInContext(source.slice(source.indexOf('function syncChannel()'),source.indexOf('async function publishChallenge')),context);
 return {context,node,timers};
}
const message=id=>({id,kind:'text',text:'消息 '+id,player:{name:'旅人'},created_at:'2026-10-16T00:00:00Z'});

test('open chat and its draft survive modal entry and exit',()=>{
 const f=fixture(),c=f.context;
 c.channelOpen=true;f.node('channel-input').value='未发送草稿';c.syncChannel();
 assert.equal(f.node('channel').parentElement,f.node('game-shell'));
 f.node('modal').open=true;c.syncChannel();
 assert.equal(f.node('channel').parentElement,f.node('modal'));
 f.node('modal').open=false;c.room={};c.syncChannel();
 assert.equal(f.node('channel').parentElement,f.node('game-shell'));
 assert.equal(f.node('channel').hidden,false);assert.equal(c.channelOpen,true);
 assert.equal(f.node('channel-input').value,'未发送草稿');
 assert.equal(f.node('channel-challenge').hidden,true);
});

test('pushed channel updates render during a match without scheduling polling',()=>{
 const f=fixture(),c=f.context;c.room={};c.channelItems=[message(1)];c.renderChannel();
 assert.equal(f.timers.length,0);assert.equal(f.node('channel-preview').textContent,'旅人：消息 1');
});

test('unread messages accumulate until the chat is opened',()=>{
 const {context:c,node}=fixture();c.channelItems=[message(1)];c.renderChannel();
 assert.equal(node('channel-unread').hidden,true);
 c.channelItems.push(message(2));c.renderChannel();assert.equal(node('channel-unread').textContent,1);
 c.channelItems.push(message(3));c.renderChannel();assert.equal(node('channel-unread').textContent,2);
 c.toggleChannel(true);assert.equal(node('channel-unread').hidden,true);
});

test('refresh does not jump to the bottom while reading older messages',()=>{
 const {context:c,node}=fixture();c.channelOpen=true;
 Object.assign(node('channel-messages'),{scrollHeight:900,clientHeight:200,scrollTop:120});
 c.channelItems=[message(1)];c.renderChannel();assert.equal(node('channel-messages').scrollTop,120);
 node('channel-messages').scrollTop=700;c.renderChannel();assert.equal(node('channel-messages').scrollTop,900);
});
