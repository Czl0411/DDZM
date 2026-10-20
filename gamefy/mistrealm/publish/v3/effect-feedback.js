const rows=['近战','远程','攻城'];
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Dense chains share at most two beats; simultaneous row damage plays together.
export function feedbackBatches(steps){
 const useful=steps.filter(s=>s.events?.length),size=Math.max(1,Math.ceil(useful.length/2));
 return Array.from({length:Math.ceil(useful.length/size)},(_,i)=>useful.slice(i*size,(i+1)*size));
}
export function powerChanges(steps){
 const changes=new Map();
 for(const step of steps)for(const e of step.events)if(e.kind==='power'){
  const previous=changes.get(e.unit);changes.set(e.unit,{...e,amount:(previous?.amount||0)+e.amount});
 }
 return [...changes.values()].filter(e=>e.amount!==0);
}
export function stepText(step,cardName,viewer){
 const parts=[],powers=new Map(),draws=new Map(),side=seat=>seat===viewer?'己方':'对手';
 for(const e of step.events){
  const name=e.card?cardName(e.card):'';
  if(e.kind==='power'){
   const key=`${e.seat}:${e.amount}`,group=powers.get(key)||[];group.push(e);powers.set(key,group);
  }else if(e.kind==='move')parts.push(`${name}移至${rows[e.row]}`);
  else if(e.kind==='draw')draws.set(e.seat,(draws.get(e.seat)||0)+e.amount);
  else if(e.kind==='death')parts.push(`${name}${e.reason==='sacrifice'?'被献祭':'阵亡'}`);
  else if(e.kind==='return'||e.kind==='recover')parts.push(`${name}${e.kind==='recover'?'回收':'返回'}至${side(e.destination??e.seat)}手牌`);
  else if(e.kind==='leave')parts.push(`${name}离场`);
  else if(e.kind==='summon'||e.kind==='revive')parts.push(`${e.kind==='summon'?'召集':'复活'}${name}`);
 }
 for(const [seat,amount] of draws)parts.push(`${side(seat)}抽${amount}张牌`);
 for(const group of powers.values()){
  const e=group[0],amount=e.amount>0?'＋'+e.amount:'−'+Math.abs(e.amount);
  parts.push(`${group.length===1?cardName(e.card):side(e.seat)+group.length+'个单位'} ${amount}`);
 }
 return (step.source?cardName(step.source)+'：':'')+parts.join(' · ');
}

export function setupEffectFeedback({shell,getCard,getSeat}){
 const layer=document.createElement('section');layer.id='effect-feedback';layer.hidden=true;layer.setAttribute('aria-label','效果结算提示');shell.append(layer);
 let timers=[],finish=null,running=false;
 function clear(){for(const timer of timers)clearTimeout(timer);timers=[];finish=null;running=false;layer.hidden=true;layer.replaceChildren();}
 function complete(){const next=finish;clear();next?.();}
 function snapshot(){return new Map([...shell.querySelectorAll('.unit-slot [data-inspect]')].map(n=>[n.dataset.inspect,n.cloneNode(true)]));}
 function play(steps=[],oldCards=new Map(),done){
  const batches=feedbackBatches(steps);if(!batches.length)return false;
  clear();finish=done;running=true;layer.hidden=false;
  layer.innerHTML='<div class="effect-marks"></div><aside class="effect-chain"><b>效果结算</b><div role="status" aria-live="polite"></div><button type="button" aria-label="跳过效果动画">跳过 ›</button></aside>';
  layer.querySelector('button').onclick=complete;
  const duration=batches.length===1?650:500;
  function anchor(e){
   const card=[...shell.querySelectorAll('.unit-slot [data-inspect]')].find(n=>n.dataset.inspect===e.unit);
   return card?.closest('.unit-slot')||shell.querySelectorAll(`.combat-row[data-seat="${e.seat}"][data-row="${e.row}"] .unit-slot`)[e.slot];
  }
  function place(node,target){
   // offset coordinates stay correct when the whole game is rotated on phones.
   let x=0,y=0,n=target;while(n&&n!==shell){x+=n.offsetLeft;y+=n.offsetTop;n=n.offsetParent;}
   Object.assign(node.style,{left:x+'px',top:y+'px',width:target.offsetWidth+'px',height:target.offsetHeight+'px'});
   layer.querySelector('.effect-marks').append(node);
  }
  function beat(batch,index){
   layer.querySelector('.effect-marks').replaceChildren();
   const grouped=[];for(const step of batch){const last=grouped.at(-1);if(last&&last.source===step.source&&last.seat===step.seat)last.events.push(...step.events);else grouped.push({...step,events:[...step.events]});}
   const texts=grouped.map(step=>stepText(step,id=>getCard(id)?.name||'卡牌',getSeat())).filter(Boolean);
   layer.querySelector('.effect-chain b').textContent=`效果结算${batches.length>1?' · '+(index+1)+'/'+batches.length:''}`;
   layer.querySelector('.effect-chain [role="status"]').textContent=texts.join(' → ');
   for(const e of powerChanges(batch)){
    const target=anchor(e);if(!target)continue;
    const mark=document.createElement('div');mark.className='effect-power '+(e.amount>0?'gain':'loss');mark.innerHTML=`<b>${e.amount>0?'＋':'−'}${Math.abs(e.amount)}</b>`;place(mark,target);
   }
   const deaths=new Map(batch.flatMap(s=>s.events).filter(e=>e.kind==='death').map(e=>[e.unit,e]));
   for(const e of deaths.values()){
    const target=anchor(e);if(!target)continue;
    const ghost=document.createElement('div');ghost.className='effect-death';
    const old=oldCards.get(e.unit);
    if(old){const copy=old.cloneNode(true);copy.tabIndex=-1;ghost.append(copy);}
    else {const card=getCard(e.card);ghost.innerHTML=`<img src="${escape(card?.art)}" alt=""><span>${escape(card?.name)}</span>`;}
    ghost.setAttribute('aria-hidden','true');place(ghost,target);
   }
  }
  batches.forEach((batch,index)=>{if(index===0)beat(batch,index);else timers.push(setTimeout(()=>beat(batch,index),duration*index));});
  timers.push(setTimeout(complete,duration*batches.length));return true;
 }
 return {snapshot,play,clear,skip:complete,get active(){return running;}};
}
