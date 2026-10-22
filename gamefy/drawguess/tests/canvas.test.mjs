import {test} from 'node:test';
import assert from 'node:assert/strict';

import {createCanvas} from '../publish/canvas.js';


class FakeContext {
  constructor(){this.calls=[];}
  setTransform(){}
  clearRect(){this.calls.push(['clear']);}
  beginPath(){this.calls.push(['begin']);}
  moveTo(x,y){this.calls.push(['move',x,y]);}
  lineTo(x,y){this.calls.push(['line',x,y]);}
  stroke(){this.calls.push(['stroke']);}
  save(){}
  restore(){}
}

class FakeCanvas {
  constructor(){this.listeners=new Map();this.ctx=new FakeContext();this.width=400;this.height=300;this.clientWidth=400;this.clientHeight=300;}
  addEventListener(name,fn){this.listeners.set(name,fn);}
  removeEventListener(name){this.listeners.delete(name);}
  getContext(){return this.ctx;}
  getBoundingClientRect(){return {left:10,top:20,width:400,height:300};}
  setPointerCapture(){}
  releasePointerCapture(){}
  fire(name,values={}){this.listeners.get(name)?.({pointerId:1,clientX:210,clientY:170,preventDefault(){},...values});}
}


test('normalizes pointer coordinates and batches selected tool every 100ms', async()=>{
  const element=new FakeCanvas(), batches=[];
  const canvas=createCanvas(element,{onBatch:batch=>batches.push(batch)});
  canvas.setEditable(true);
  canvas.setTool({tool:'pen',color:'#ef5b5b',width:0.016});
  element.fire('pointerdown');
  element.fire('pointermove',{clientX:410,clientY:320});
  element.fire('pointerup',{clientX:410,clientY:320});
  await new Promise(resolve=>setTimeout(resolve,130));
  const operations=batches.flat();
  assert.deepEqual(operations[0].points,[[0.5,0.5]]);
  assert.deepEqual(operations[1].points,[[1,1]]);
  assert.equal(operations[0].width,0.016);
  assert.equal(operations[0].color,'#ef5b5b');
  canvas.destroy();
});


test('deduplicates sequences and resets on a different turn',()=>{
  const element=new FakeCanvas();
  const canvas=createCanvas(element,{onBatch(){}});
  canvas.restore({turn_id:1,canvas:[]});
  const event={seq:1,turn_id:1,op:'begin',stroke_id:'s1',points:[[0.1,0.1],[0.2,0.2]],color:'#222222',width:0.008,tool:'pen'};
  canvas.applyEvents([event],1);
  const strokes=element.ctx.calls.filter(call=>call[0]==='stroke').length;
  canvas.applyEvents([event],1);
  assert.equal(element.ctx.calls.filter(call=>call[0]==='stroke').length,strokes);
  canvas.restore({turn_id:2,canvas:[]});
  canvas.applyEvents([{...event,seq:2}],1);
  assert.equal(element.ctx.calls.filter(call=>call[0]==='stroke').length,strokes);
  canvas.destroy();
});


test('undo and clear are local immediately and emitted to server', async()=>{
  const element=new FakeCanvas(), batches=[];
  const canvas=createCanvas(element,{onBatch:batch=>batches.push(batch)});
  canvas.setEditable(true);
  element.fire('pointerdown');element.fire('pointerup');
  await new Promise(resolve=>setTimeout(resolve,110));
  canvas.undo();canvas.clear();
  await new Promise(resolve=>setTimeout(resolve,110));
  assert.equal(batches.flat().some(item=>item.op==='undo'),true);
  assert.equal(batches.flat().some(item=>item.op==='clear'),true);
  canvas.destroy();
});


test('pointer cancel ends the stroke without joining the next one', async()=>{
  const element=new FakeCanvas(), batches=[];
  const canvas=createCanvas(element,{onBatch:batch=>batches.push(batch)});
  canvas.setEditable(true);
  element.fire('pointerdown');element.fire('pointercancel');
  element.fire('pointermove',{clientX:100,clientY:100});
  element.fire('pointerdown',{clientX:100,clientY:100});element.fire('pointerup',{clientX:120,clientY:120});
  await new Promise(resolve=>setTimeout(resolve,120));
  const begins=batches.flat().filter(item=>item.op==='begin');
  assert.equal(begins.length,2);
  assert.notEqual(begins[0].stroke_id,begins[1].stroke_id);
  canvas.destroy();
});
