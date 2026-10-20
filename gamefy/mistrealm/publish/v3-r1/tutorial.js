const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const steps=[
 ['查看手牌','先点击「荒境佣兵」。点选只展示效果，不会直接出牌。'],
 ['选择战列','点击高亮的己方近战排。单位只能部署到允许的战列，每排最多4张。'],
 ['对手也会行动','你打出了一张5战力单位。双方轮流行动；现在看看对手的回应。'],
 ['部署技能','对手的弩客造成2点伤害，佣兵从5降到3。选择「漂泊弩客」，点击使用。'],
 ['部署到远程排','漂泊弩客是远程单位。点击己方远程排，再选择技能目标。'],
 ['选择敌方目标','点击对方的荒境佣兵，造成2点伤害。出牌后的部署技能属于同一次行动。'],
 ['使用即时术','现在双方都是6战力。选择「渡雾剑诀」，点击使用，练习移除对方单位。'],
 ['战力归零即阵亡','点击敌方3战力的佣兵。剑诀造成4点伤害，目标归零后直接进入弃牌堆。'],
 ['查看弃牌堆','点击「弃牌堆 · 查看」。即时术结算后也会弃置，不占持续术位。'],
 ['认识领袖技能','点击「领袖技能」查看说明，再确认发动。领袖整场只能使用一次，也会消耗一次行动。'],
 ['保留下一局的资源','你的两名单位各增加3战力。演练中的对手已经停手，不能再行动；你仍可以继续出牌或停手。'],
 ['确认停手','点击「本局停手」并确认。你已经领先，不必为了更多点数把手牌全部用完。'],
 ['完成练习','你以12比3赢得这一小局，对方失去1点生命。正式对局仍需继续，直到一方生命归零。'],
];

// A fixed practice scene only. It never calls the game API or changes the player's deck.
export function practiceState(){return {step:0,selected:null,hand:['c101','c103','c111','c102','c113'],own:[],enemy:[{card:'c101',power:5,row:0}],discard:[],enemyDiscard:[],leaderUsed:false};}
export function practiceAction(s,action,id){
 const next=structuredClone(s);
 const advance=()=>{next.step++;next.selected=null;return next;};
 const expected={0:'c101',3:'c103',6:'c111'}[s.step];
 if(action==='select'&&s.hand.includes(id)){next.selected=s.selected===id?null:id;return next;}
 if(action==='use'&&s.selected===expected)return advance();
 if(action==='row'&&s.step===1&&id===0){next.hand=next.hand.filter(c=>c!=='c101');next.own.push({card:'c101',power:5,row:0});return advance();}
 if(action==='next'&&s.step===2){next.enemy.push({card:'c103',power:3,row:1});next.own[0].power=3;return advance();}
 if(action==='row'&&s.step===4&&id===1){next.hand=next.hand.filter(c=>c!=='c103');next.own.push({card:'c103',power:3,row:1});return advance();}
 if(action==='target'&&id==='c101'&&s.step===5){next.enemy[0].power-=2;return advance();}
 if(action==='target'&&id==='c101'&&s.step===7){next.enemyDiscard.push(next.enemy.shift());next.hand=next.hand.filter(c=>c!=='c111');next.discard.push({card:'c111'});return advance();}
 if(action==='grave'&&s.step===8)return advance();
 if(action==='leader'&&s.step===9){next.own.forEach(c=>c.power+=3);next.leaderUsed=true;return advance();}
 if(action==='next'&&s.step===10)return advance();
 if(action==='pass'&&s.step===11)return advance();
 return s;
}

export function setupTutorial({cards,uid,eligible,blocked,home,modal,closeModal,sync}){
 const $=id=>document.getElementById(id),main=$('main');let state=null,offered=false;
 const key=()=>`mistrealm-tutorial-v1:${uid()}`;
 function seen(){try{return !!localStorage.getItem(key());}catch{return false;}}
 function remember(value){offered=true;try{localStorage.setItem(key(),value);}catch{}}
 function exit(completed=false){remember(completed?'completed':'skipped');state=null;closeModal();home();sync();}
 function start(){if(blocked())return;closeModal();state=practiceState();$('game-shell').classList.remove('battle','preparing');main.onclick=null;draw();sync();}
 function offer(){
  if(offered||!eligible()||!cards()||blocked()||seen()||!$('screen-entry').hidden)return;
  offered=true;
  modal(`<section class="tutorial-welcome"><p class="eyebrow">初入雾境</p><h2>先练一手，再上战场</h2><p>用5张固定手牌和预设的对手场面，练习出牌、技能、弃牌堆和停手留牌。没有倒计时，不影响正式对局。</p><div class="actions"><button id="tutorial-start">开始短教学</button><button id="tutorial-skip" class="secondary">跳过，进入大厅</button></div><small>之后随时可从大厅的「新手教学」重玩。</small></section>`,'tutorial-welcome');
  $('tutorial-start').onclick=start;$('tutorial-skip').onclick=()=>exit();
 }
 function act(action,id){state=practiceAction(state,action,id);draw();}
 function picture(id,power,attrs=''){
  const d=cards().cards[id];return `<button class="tutorial-card" ${attrs} aria-label="${esc(d.name)}${power===undefined?'':'，战力'+power}"><img src="${esc(d.art)}" alt=""><b>${power??(d.type==='unit'?d.power:'术')}</b><span>${esc(d.name)}</span></button>`;
 }
 function detail(id,extra=''){
  const d=cards().cards[id];modal(`<section class="tutorial-detail"><img src="${esc(d.art)}" alt=""><div><h2>${esc(d.name)}</h2><p>${esc(d.text)}</p>${extra}</div></section>`,'tutorial-detail');
 }
 function grave(){
  modal(`<h2>教学弃牌堆</h2><p>点击卡牌可查看效果。复活、回收效果需满足各自条件。</p><div class="tutorial-graves"><section><h3>对手 · 阵亡单位</h3>${state.enemyDiscard.map(c=>picture(c.card,undefined,`data-tutorial-detail="${c.card}"`)).join('')||'暂无弃牌'}</section><section><h3>己方 · 已使用的术卡</h3>${state.discard.map(c=>picture(c.card,undefined,`data-tutorial-detail="${c.card}"`)).join('')||'暂无弃牌'}</section></div><button id="tutorial-grave-back">返回教学</button>`,'tutorial-grave');
  if(state.step===8)act('grave');
  $('tutorial-grave-back').onclick=closeModal;
  document.querySelectorAll('[data-tutorial-detail]').forEach(n=>n.onclick=()=>{
   detail(n.dataset.tutorialDetail,'<button id="tutorial-detail-back">返回弃牌堆</button>');$('tutorial-detail-back').onclick=grave;
  });
 }
 function draw(){
  const s=state,[title,text]=steps[s.step],d=s.selected?cards().cards[s.selected]:null,expected={0:'c101',3:'c103',6:'c111'}[s.step];
  const army=(units,enemy)=>`<section class="tutorial-army"><header>${enemy?'对手':'你'}<strong>${units.reduce((v,c)=>v+c.power,0)} <small>总战力</small></strong></header>${['近战','远程','攻城'].map((label,row)=>{
   const eligible=!enemy&&((s.step===1&&row===0)||(s.step===4&&row===1));
   return `<div class="tutorial-row ${eligible?'tutorial-highlight':''}"><span>${label}</span><div class="tutorial-slots">${Array.from({length:4},(_,i)=>{
    const c=units.filter(c=>c.row===row)[i];
    return c?picture(c.card,c.power,`data-tutorial-unit="${c.card}" data-enemy="${enemy}" data-tutorial-target="${enemy&&c.card==='c101'&&[5,7].includes(s.step)}"`):`<button class="tutorial-slot" data-tutorial-row="${row}" ${eligible?'':'disabled'} aria-label="${enemy?'对手':'己方'}${label}空位">${eligible?'部署':'◇'}</button>`;
   }).join('')}</div></div>`;
  }).join('')}<footer>持续术区 · 3个专属位置 <span>◇ ◇ ◇</span></footer></section>`;
  main.innerHTML=`<section class="tutorial"><header class="tutorial-heading"><div><b>新手教学</b><small>固定演练 · 不计正式战绩</small></div><button id="tutorial-exit" class="secondary">退出教学</button></header><div class="tutorial-layout"><section class="tutorial-playfield">${army(s.enemy,true)}${army(s.own,false)}</section><aside class="tutorial-guide"><small>步骤 ${s.step+1} / ${steps.length}</small><h2>${title}</h2><p>${text}</p>${d?`<section class="tutorial-inspector"><b>${esc(d.name)}</b><p>${esc(d.text)}</p><button id="tutorial-use" ${s.selected===expected?'':'disabled'}>使用</button>${s.selected!==expected?'<small>先按当前提示练习，这张牌留在手中。</small>':''}</section>`:''}<div class="tutorial-tools" ${s.step===12?'hidden':''}><button id="tutorial-grave" class="${s.step===8?'tutorial-highlight':''}">弃牌堆 · 查看 ›</button><button id="tutorial-leader" ${s.leaderUsed?'disabled':''} class="${s.step===9?'tutorial-highlight':''}">${s.leaderUsed?'领袖已使用':'领袖技能 · 查看'}</button></div>${[2,10].includes(s.step)?'<button id="tutorial-next">继续</button>':''}${s.step===11?'<button id="tutorial-pass" class="tutorial-highlight">本局停手</button>':''}${s.step===12?`<div class="tutorial-result"><b>小局获胜 · 剩余手牌 ${s.hand.length} 张</b><p>这些牌留到下一局。正式对局开局抽7张，第二、第三局各抽2张：你下一局将有 ${s.hand.length}+2＝${s.hand.length+2} 张牌。</p><button id="tutorial-finish">完成教学，进入大厅</button></div>`:''}</aside></div><section class="tutorial-hand"><header>练习手牌 · ${s.hand.length} 张 <small>点选查看 → 使用 → 选择位置或目标</small></header><div>${s.hand.map(id=>picture(id,undefined,`data-tutorial-hand="${id}" aria-pressed="${s.selected===id}"`)).join('')}</div></section></section>`;
  $('tutorial-exit').onclick=()=>exit();$('tutorial-grave').onclick=grave;
  document.querySelectorAll('[data-tutorial-hand]').forEach(n=>n.onclick=()=>act('select',n.dataset.tutorialHand));
  document.querySelectorAll('[data-tutorial-row]').forEach(n=>n.onclick=()=>act('row',Number(n.dataset.tutorialRow)));
  document.querySelectorAll('[data-tutorial-unit]').forEach(n=>n.onclick=()=>{
   if(n.dataset.enemy==='true'&&[5,7].includes(state.step))act('target',n.dataset.tutorialUnit);else detail(n.dataset.tutorialUnit);
  });
  if($('tutorial-use'))$('tutorial-use').onclick=()=>act('use');
  if($('tutorial-next'))$('tutorial-next').onclick=()=>act('next');
  if($('tutorial-finish'))$('tutorial-finish').onclick=()=>exit(true);
  $('tutorial-leader').onclick=()=>{
   detail('c019',s.step===9?'<button id="tutorial-activate">确认发动</button>':'<p>先完成当前步骤，稍后会练习发动领袖。</p>');
   if($('tutorial-activate'))$('tutorial-activate').onclick=()=>{closeModal();act('leader');};
  };
  if($('tutorial-pass'))$('tutorial-pass').onclick=()=>{
   modal('<h2>确定本局停手？</h2><p>停手后，本局不能再出牌或使用领袖能力。剩余手牌保留到下一局。</p><div class="actions"><button id="tutorial-keep" class="secondary">继续出牌</button><button id="tutorial-confirm-pass">确认停手</button></div>','tutorial-pass');
   $('tutorial-keep').onclick=closeModal;$('tutorial-confirm-pass').onclick=()=>{closeModal();act('pass');};
  };
 }
 document.addEventListener('gameentered',offer);
 return {offer,start,exit,active:()=>!!state};
}
