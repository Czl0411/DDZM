const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Snapshots are exported from the real rules engine. Practice never sends match actions.
export function practiceState(){return {step:0,selected:null,choice:null};}
export function practiceAction(s,scenes,action,payload={}){
 const scene=scenes[s.step];if(!scene)return s;
 if(action==='select'){
  if(!scene.state.players[0].hand.some(c=>c.id===payload.card))return s;
  if(scene.expected.action==='select'&&scene.expected.payload.card===payload.card)return {step:s.step+1,selected:payload.card,choice:null};
  return {...s,selected:s.selected===payload.card?null:payload.card};
 }
 if(action==='pick')return scene.state.pending?.options.some(o=>o.token===payload.option)?{...s,choice:payload.option}:s;
 const expected=scene.expected;
 if(action!==expected.action||Object.keys(payload).length!==Object.keys(expected.payload).length||Object.keys(expected.payload).some(k=>payload[k]!==expected.payload[k]))return s;
 if(action==='play'&&s.selected!==payload.card||action==='choose'&&s.choice!==payload.option)return s;
 if(action==='finish')return s;
 return {step:s.step+1,selected:null,choice:null};
}

export function setupTutorial({cards,scenes,view,choices,card,inspect,uid,eligible,blocked,home,modal,closeModal,sync}){
 const $=id=>document.getElementById(id),main=$('main');let state=null,offered=false,graveSeen=null,collapsed=false;
 const key=()=>`mistrealm-tutorial-v1:${uid()}`;
 const current=()=>scenes()[state.step];
 function seen(){try{return !!localStorage.getItem(key());}catch{return false;}}
 function remember(value){offered=true;try{localStorage.setItem(key(),value);}catch{}}
 function exit(completed=false){remember(completed?'completed':'skipped');state=null;graveSeen=null;closeModal();$('game-shell').classList.remove('tutorial-active');home();sync();}
 function start(){if(blocked()||!scenes()?.length)return;closeModal();state=practiceState();graveSeen=null;collapsed=false;$('game-shell').classList.remove('preparing');$('game-shell').classList.add('battle','tutorial-active');main.onclick=null;draw();sync();}
 function offer(){
  if(offered||!eligible()||!cards()||!scenes()?.length||blocked()||seen()||!$('screen-entry').hidden)return;
  offered=true;
  modal(`<section class="tutorial-welcome"><p class="eyebrow">初入雾境</p><h2>两局练习，学会留牌与调度</h2><p>约5分钟，用正式战盘练习出牌、停手、换局补牌，持续术施放与摧毁，以及间谍占位后的献祭腾格。固定演练，没有倒计时，不影响牌组与战绩。</p><div class="actions"><button id="tutorial-start">开始教学</button><button id="tutorial-skip" class="secondary">跳过，进入大厅</button></div><small>随时可退出，之后从大厅的「新手教学」重玩。</small></section>`,'tutorial-welcome');
  $('tutorial-start').onclick=start;$('tutorial-skip').onclick=()=>exit();
 }
 function act(action,payload={}){
  const next=practiceAction(state,scenes(),action,payload);
  if(next.step!==state.step){collapsed=false;graveSeen=null;}
  state=next;draw();
 }
 function bind(id,fn){const node=$(id);if(node)node.onclick=fn;}
 function grave(seat){
  const p=current().state.players[seat];
  modal(`<section class="grave-view"><h2>${seat===0?'己方':'对手'}弃牌堆 · ${p.discard.length} 张</h2><p>弃牌不会自动洗回牌库；只有明确的复活、回收等效果才能取用。小局清场的单位也会进入这里。</p><div class="grave-grid">${p.discard.map(c=>card(c,`data-tutorial-grave="${c.id}"`)).join('')||'<p>暂无弃牌</p>'}</div><button id="tutorial-grave-back">返回教学</button></section>`,'grave');
  if(current().expected.action==='grave'&&current().expected.payload.seat===seat)graveSeen=seat;
  bind('tutorial-grave-back',closeModal);
  document.querySelectorAll('[data-tutorial-grave]').forEach(n=>n.onclick=()=>{
   inspect(p.discard.find(c=>c.id===n.dataset.tutorialGrave));
   $('modal-content').insertAdjacentHTML('beforeend','<button id="tutorial-back-grave">返回弃牌堆</button>');bind('tutorial-back-grave',()=>grave(seat));
  });
 }
 function leader(seat,confirm=false){
  const p=current().state.players[seat],d=cards().cards[p.leader],canUse=seat===0&&current().expected.action==='leader';
  modal(`<section class="leader-detail"><p class="eyebrow">${seat===0?'己方':'对手'}领袖 · ${p.leader_used?'已使用':'未使用'}</p><h2>${esc(d.name)}</h2><p class="leader-effect">${esc(d.text)}</p><p>整场只能使用一次，下一小局不会恢复。发动也消耗一次行动。</p>${confirm&&canUse?'<button id="tutorial-activate">确认发动</button>':''}</section>`,'tutorial-leader');
  bind('tutorial-activate',()=>{closeModal();act('leader');});
 }
 function pass(){
  const opponentPassed=current().state.players[1].passed;
  modal(`<section class="pass-confirm"><p class="eyebrow">结束本局行动</p><h2>确定本局停手？</h2><p>停手后本局不能再出牌或发动领袖。${opponentPassed?'对手已经停手':'对手已无手牌且领袖用尽，无法继续追分'}，你当前领先，可以保留手牌结束这一局。</p><div class="actions"><button id="tutorial-keep" class="secondary">继续查看</button><button id="tutorial-confirm-pass">确认停手</button></div></section>`,'pass-confirm');
  bind('tutorial-keep',closeModal);bind('tutorial-confirm-pass',()=>{closeModal();act('pass');});
 }
 function draw(){
  const scene=current(),expected=scene.expected,all=scenes();
  const s={...scene.state,legal_moves:scene.state.legal_moves.filter(m=>m.action===expected.action&&JSON.stringify(m.payload)===JSON.stringify(expected.payload))};
  if(s.pending?.options)s.pending={...s.pending,options:s.pending.options.filter(o=>o.token===expected.payload.option)};
  const picked=s.pending?.options?.find(o=>o.token===state.choice);
  main.innerHTML=view(s,state.selected,false,picked);
  main.onclick=null;
  // Keep the actual board, cards, counters and controls; guidance occupies unused hand-strip space.
  main.querySelector('.hand-area').insertAdjacentHTML('beforeend',`<aside class="tutorial-coach" aria-label="教学提示"><small>新手教学 · ${state.step+1} / ${all.length} · 第${s.round}局</small><h2>${esc(scene.title)}</h2><p role="status" aria-live="polite">${esc(scene.text)}</p>${expected.action==='continue'?`<button id="tutorial-next">${esc(scene.cta)}</button>`:expected.action==='finish'?`<button id="tutorial-finish">${esc(scene.cta)}</button>`:''}</aside>`);
  if(s.pending?.options)main.insertAdjacentHTML('beforeend',choices(s.pending,picked,{selected:state.choice,target:null,collapsed,notice:'',ids:null}));
  $('battle-status').textContent=s.phase==='finished'?'教学完成 · 你赢得整场对局':s.phase==='round_result'?'小局结束 · 点击提示进入第二局':s.players[1].passed?'对手已停手 · 比较总战力，再决定是否停手':s.turn===0?'轮到你行动 · 跟随金色提示':'观察对手行动';
  $('view-log').textContent='整场规则';bind('view-log',()=>modal('<h2>整场胜负与资源</h2><p>双方各2点生命。双方停手后，比三排总战力；输家失去1点生命，平局双方各失去1点。对手生命归零即获胜，同时归零则整场平局。通常三局两胜。</p><p>开局抽7张，可换最多2张；第二、第三局开始各抽2张，剩余手牌保留。场上单位与持续术通常进入原拥有者弃牌区，清场不触发阵亡；弃牌不会自动洗回牌库，特殊效果按卡牌说明。</p>','tutorial-rules'));
  $('concede')?.remove();$('leave')?.remove();$('rematch')?.remove();
  main.querySelector('.controls').insertAdjacentHTML('beforeend','<button id="tutorial-exit" class="secondary">退出教学</button>');bind('tutorial-exit',()=>exit());
  document.querySelectorAll('[data-hand]').forEach(n=>n.onclick=()=>act('select',{card:n.dataset.hand}));
  document.querySelectorAll('[data-inspect]').forEach(n=>n.onclick=()=>{
   const option=s.pending?.options?.find(o=>o.target_ids.includes(n.dataset.inspect));
   if(option){collapsed=true;act('pick',{option:option.token});}
   else inspect(s.players.flatMap(p=>p.rows.flat()).find(c=>c.id===n.dataset.inspect));
  });
  document.querySelectorAll('[data-spell]').forEach(n=>n.onclick=()=>{
   const option=s.pending?.options?.find(o=>o.target_ids.includes(n.dataset.spell));
   if(option){collapsed=true;act('pick',{option:option.token});}
   else inspect(s.players.flatMap(p=>p.spells).find(c=>c.id===n.dataset.spell));
  });
  document.querySelectorAll('[data-grave]').forEach(n=>n.onclick=()=>grave(Number(n.dataset.grave)));
  document.querySelectorAll('[data-battle-leader]').forEach(n=>n.onclick=()=>leader(Number(n.dataset.battleLeader)));
  const chosen=s.players[0].hand.find(c=>c.id===state.selected);
  bind('inspect-hand',()=>inspect(chosen));bind('dismiss-hand',()=>{state={...state,selected:null};draw();});
  bind('use-hand',()=>act('play',expected.payload));
  bind('use-leader',()=>leader(0,true));bind('pass',pass);
  bind('tutorial-next',()=>act('continue'));bind('tutorial-finish',()=>exit(true));
  document.querySelectorAll('[data-option]').forEach(n=>n.onclick=()=>act('pick',{option:n.dataset.option}));
  bind('confirm-choice',()=>act('choose',{option:state.choice}));bind('choice-board',()=>{collapsed=!collapsed;draw();});
  if(scene.focus)main.querySelectorAll(scene.focus).forEach(n=>n.classList.add('tutorial-highlight'));
  if(expected.action==='choose'&&!scene.focus?.includes('data-inspect'))main.querySelector('.choice-panel')?.classList.add('tutorial-highlight');
  if(picked)$('confirm-choice')?.classList.add('tutorial-highlight');
  if(chosen&&chosen.id===expected.payload.card)$('use-hand')?.classList.add('tutorial-highlight');
  main.querySelector('[data-hand].tutorial-highlight')?.scrollIntoView({block:'nearest',inline:'nearest'});
 }
 $('modal').addEventListener('close',()=>{if(state&&graveSeen!==null&&current().expected.action==='grave'){const seat=graveSeen;graveSeen=null;act('grave',{seat});}});
 document.addEventListener('gameentered',offer);
 return {offer,start,exit,active:()=>!!state};
}
