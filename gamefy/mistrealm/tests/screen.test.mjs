import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function fixture({width=390,height=844,enabled=true,reject=false}={}){
 const nodes=new Map(),styles={},classes=new Set(),calls=[],listeners={};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{style:{},hidden:false,disabled:false,dispatchEvent(){}});return nodes.get(id);};
 const document={dispatchEvent(){},getElementById:node,fullscreenEnabled:enabled,fullscreenElement:null,addEventListener:(name,fn)=>listeners[name]=fn,
  documentElement:{style:{setProperty:(key,value)=>styles[key]=value},classList:{toggle:(name,on)=>on?classes.add(name):classes.delete(name)},requestFullscreen:async()=>{calls.push('fullscreen');if(reject)throw Error('not allowed');document.fullscreenElement=document.documentElement;}},
  exitFullscreen:async()=>{calls.push('exit');document.fullscreenElement=null;}};
 const context=vm.createContext({document,innerWidth:width,innerHeight:height,navigator:{userActivation:{isActive:false}},screen:{orientation:{lock:async value=>calls.push(value)}},Event:class{},addEventListener:(name,fn)=>listeners[name]=fn});
 vm.runInContext(readFileSync(new URL('../publish/v3/screen.js',import.meta.url),'utf8').replace('export function','function')+'\nsetupScreen();',context);
 return {node,styles,classes,calls,listeners,document,context};
}

test('portrait rotates the whole surface and physical landscape restores it',()=>{
 const f=fixture();assert.equal(f.styles['--game-width'],'844px');assert.equal(f.styles['--game-height'],'390px');
 assert.match(f.node('game-viewport').style.transform,/rotate\(90deg\)/);assert.ok(f.classes.has('screen-rotated'));
 f.context.innerWidth=844;f.context.innerHeight=390;f.listeners.resize();
 assert.match(f.node('game-viewport').style.transform,/rotate\(0deg\)/);assert.ok(!f.classes.has('screen-rotated'));
});

test('small embedded platform frame fits a complete landscape surface',()=>{
 const f=fixture({width:390,height:219});
 const width=parseFloat(f.styles['--game-width']),height=parseFloat(f.styles['--game-height']),scale=f.styles['--screen-scale'];
 assert.ok(width>=640&&height>=360);assert.ok(Math.abs(width*scale-390)<.01);assert.ok(Math.abs(height*scale-219)<.01);
});

test('one entry gesture requests fullscreen then orientation and opens the game',async()=>{
 const f=fixture();assert.deepEqual(f.calls,[]);
 await f.node('enter-game').onclick();assert.deepEqual(f.calls,['fullscreen','landscape']);
 assert.equal(f.node('screen-entry').hidden,true);assert.equal(f.node('enter-game').disabled,false);
 await f.node('fullscreen').onclick();assert.equal(f.calls.at(-1),'exit');
});

test('blocked fullscreen still enters the rotated game without trapping the player',async()=>{
 const f=fixture({reject:true});await f.node('enter-game').onclick();
 assert.equal(f.node('screen-entry').hidden,true);assert.ok(f.classes.has('screen-rotated'));
 assert.equal(f.node('enter-game').disabled,false);
});

test('unsupported fullscreen provides a platform hint and still attempts orientation',async()=>{
 const f=fixture({enabled:false});assert.match(f.node('screen-hint').textContent,/平台/);
 await f.node('enter-game').onclick();assert.deepEqual(f.calls,['landscape']);assert.equal(f.node('screen-entry').hidden,true);
});
