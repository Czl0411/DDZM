const WIDTHS=new Set([0.003,0.008,0.016]);
const COLORS=new Set(['#222222','#ef5b5b','#f59e0b','#22a06b','#3b82f6','#8b5cf6','#ffffff']);

function id(){
  if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
  const bytes=new Uint8Array(16);globalThis.crypto?.getRandomValues?.(bytes);
  if(!bytes.some(Boolean))for(let i=0;i<bytes.length;i++)bytes[i]=Math.floor(Math.random()*256);
  return [...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
}

export function createCanvas(element,{onBatch}){
  const context=element.getContext('2d');
  let editable=false,currentTurn=null,lastSeq=0,active=null,destroyed=false;
  let tool={tool:'pen',color:'#222222',width:0.008};
  const strokes=new Map(),order=[];
  let queue=[],timer=null;

  function point(event){
    const rect=element.getBoundingClientRect();
    return [Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];
  }
  function emit(operation){
    queue.push(operation);
    if(!timer)timer=setTimeout(()=>{const batch=queue;queue=[];timer=null;if(batch.length&&!destroyed)onBatch(batch);},100);
  }
  function drawStroke(stroke){
    if(!stroke||!stroke.points.length)return;
    const width=element.width||element.clientWidth||400,height=element.height||element.clientHeight||300;
    context.save?.();context.globalCompositeOperation=stroke.tool==='eraser'?'destination-out':'source-over';
    context.strokeStyle=stroke.color;context.lineWidth=Math.max(1,stroke.width*width);context.lineCap='round';context.lineJoin='round';
    context.beginPath();
    const first=stroke.points[0];context.moveTo(first[0]*width,first[1]*height);
    for(const item of stroke.points.slice(1))context.lineTo(item[0]*width,item[1]*height);
    if(stroke.points.length===1)context.lineTo(first[0]*width+0.01,first[1]*height+0.01);
    context.stroke();context.restore?.();
  }
  function redraw(){
    context.clearRect(0,0,element.width||400,element.height||300);
    for(const strokeId of order)drawStroke(strokes.get(strokeId));
  }
  function apply(operation){
    if(operation.op==='clear'){strokes.clear();order.length=0;redraw();return;}
    if(operation.op==='undo'){
      strokes.delete(operation.stroke_id);const index=order.indexOf(operation.stroke_id);if(index>=0)order.splice(index,1);redraw();return;
    }
    let stroke=strokes.get(operation.stroke_id);
    if(operation.op==='begin'||!stroke){
      stroke={points:[],color:operation.color,width:operation.width,tool:operation.tool};
      strokes.set(operation.stroke_id,stroke);if(!order.includes(operation.stroke_id))order.push(operation.stroke_id);
    }
    stroke.points.push(...operation.points);stroke.color=operation.color;stroke.width=operation.width;stroke.tool=operation.tool;
    redraw();
  }
  function operation(kind,strokeId,points){return {op:kind,stroke_id:strokeId,points,color:tool.color,width:tool.width,tool:tool.tool};}
  function down(event){
    if(!editable||active!==null)return;event.preventDefault();active={pointer:event.pointerId,stroke:id()};
    element.setPointerCapture?.(event.pointerId);const op=operation('begin',active.stroke,[point(event)]);apply(op);emit(op);
  }
  function move(event){
    if(!editable||!active||event.pointerId!==active.pointer)return;event.preventDefault();
    const op=operation('append',active.stroke,[point(event)]);apply(op);emit(op);
  }
  function finish(event){
    if(!active||event.pointerId!==active.pointer)return;event.preventDefault();
    const stroke=active.stroke;active=null;element.releasePointerCapture?.(event.pointerId);
    emit(operation('end',stroke,event.type==='pointercancel'?[]:[point(event)]));
  }
  const listeners={pointerdown:down,pointermove:move,pointerup:finish,pointercancel:finish};
  for(const [name,handler] of Object.entries(listeners))element.addEventListener(name,handler,{passive:false});

  return {
    setEditable(value){editable=Boolean(value);if(!editable)active=null;},
    setTool(next){
      if(!next||!['pen','eraser'].includes(next.tool)||!COLORS.has(next.color)||!WIDTHS.has(next.width))throw new Error('画笔工具不正确');
      tool={...next};
    },
    applyEvents(events,turnId){
      if(turnId!==currentTurn)return;
      for(const event of events){if(event.turn_id!==currentTurn||event.seq<=lastSeq)continue;lastSeq=event.seq;apply(event);}
    },
    restore(snapshot){
      currentTurn=snapshot.turn_id;lastSeq=0;strokes.clear();order.length=0;
      for(const event of snapshot.canvas||[]){lastSeq=Math.max(lastSeq,event.seq||0);apply(event);}redraw();
    },
    undo(){
      if(!editable||!order.length)return;const strokeId=order.at(-1);const op={op:'undo',stroke_id:strokeId};apply(op);emit(op);
    },
    clear(){if(!editable)return;const op={op:'clear'};apply(op);emit(op);},
    destroy(){destroyed=true;if(timer)clearTimeout(timer);timer=null;queue=[];for(const [name,handler] of Object.entries(listeners))element.removeEventListener(name,handler);},
  };
}
