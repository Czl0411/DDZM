const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons={bronze:'Ⅰ',silver:'Ⅱ',gold:'Ⅲ',platinum:'Ⅳ',diamond:'Ⅴ',crown:'♛'};
export const rankBadge=(key,label)=>`<span class="rank-badge rank-${esc(key)}" aria-label="${esc(label)}"><span>${icons[key]||'◇'}</span></span>`;
export function rankResult(state){
 const rank=state.ranked,result=rank?.result,seat=state.seat;
 if(!rank||state.phase!=='finished'||!result)return '';
 if(result.void)return '<div class="rank-result">本场未计入排位积分</div>';
 const change=result.deltas[seat];
 return `<div class="rank-result"><span>S${rank.season_id} 排位结算</span><strong>${change>0?'+':''}${change} 分</strong><span>${result.before[seat]} → ${result.after[seat]} · ${esc(result.tiers[seat].name)}</span></div>`;
}

export function setupRanked({client,main,uid,deck,home,start,run,images,onHonor}){
 const $=id=>document.getElementById(id);let active=false,epoch=0,info=null,board=null,tab='ladder',page=0,seasonIndex=0;
 const selectedSeason=()=>info.seasons[seasonIndex];
 function close(){active=false;epoch++;}
 async function open(){
  active=true;const request=++epoch;tab='ladder';page=0;seasonIndex=0;
  main.innerHTML='<section class="rank-loading"><h2>正在读取赛季战绩…</h2><button id="rank-back">返回大厅</button></section>';
  $('rank-back').onclick=home;
  try{const value=await client.rankedProfile();if(!active||request!==epoch)return;info=value;await load();}
  catch(e){if(active&&request===epoch)home();throw e;}
 }
 async function load(){
  const request=++epoch;
  if(tab==='ladder'){
   board=null;draw();const result=await client.rankedLeaderboard(selectedSeason().id,page);
   if(!active||request!==epoch)return;board=result;
  }
  if(active)draw();
 }
 function draw(){
  if(!active)return;
  const p=info.player,t=p.tier,s=info.season,current=selectedSeason(),progress=t.next?Math.min(100,Math.max(0,(p.rating-Math.max(1000,t.threshold))/(t.next-Math.max(1000,t.threshold))*100)):100;
  const date=value=>new Date(value).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric'});
  let content='';
  if(tab==='ladder')content=`<div class="rank-board-title"><button id="rank-older" ${seasonIndex>=info.seasons.length-1?'disabled':''}>‹</button><strong>S${current.id} 排行榜 <small>${current.status==='settled'?'已结算':current.status==='closing'?'对局结算中':'本赛季'}</small></strong><button id="rank-newer" ${seasonIndex===0?'disabled':''}>›</button></div><div class="rank-table"><div class="rank-table-head"><span>名次</span><span>玩家</span><span>段位 / 积分</span><span>胜场</span></div>${board?board.items.map(row=>`<div class="rank-table-row ${row.uid===uid()?'rank-self':''}"><b>${row.position}</b><div class="rank-player">${row.avatar?.startsWith('https://')?`<img src="${esc(row.avatar)}" alt="" referrerpolicy="no-referrer">`:'<span class="rank-avatar">◇</span>'}<span>${esc(row.name)}${row.uid===uid()?' <small>你</small>':''}</span></div><span>${esc(row.tier.name)} <b>${row.rating}</b></span><span>${row.wins} / ${row.games}</span></div>`).join('')||'<p class="rank-empty">还没有排位战绩，成为本赛季第一位挑战者。</p>':'<p class="rank-empty">正在读取排行榜…</p>'}</div><footer class="rank-pagination"><span>${board?.my_position?'我的排名 #'+board.my_position:'完成一场排位后上榜'}</span><button id="rank-prev" ${!page||!board?'disabled':''}>上一页</button><span>${page+1} / ${Math.max(1,Math.ceil((board?.total||0)/6))}</span><button id="rank-next" ${!board||(page+1)*6>=board.total?'disabled':''}>下一页</button></footer>`;
  if(tab==='rewards'){
   const rewards=info.rewards.slice(page*6,page*6+6);
   content=`<div class="rank-board-title"><strong>赛季荣誉 <small>按最高段位发放 · 永久保留</small></strong></div><div class="rank-rewards">${rewards.map(r=>`<article>${rankBadge(r.badge,r.title)}<div><b>${esc(r.title)}</b><small>赛季最高 ${r.peak} 分</small></div><button data-rank-equip="${r.season_id}" ${r.equipped?'disabled':''}>${r.equipped?'已佩戴':'佩戴'}</button></article>`).join('')||'<p class="rank-empty">赛季结束、跨季对局结算后自动发放。<br>本赛季参与排位即可获得对应最高段位的称号与徽章。</p>'}</div><footer class="rank-pagination"><button id="rank-unequip" ${info.honor?'':'disabled'}>卸下荣誉</button><button id="rank-prev" ${page?'':'disabled'}>上一页</button><span>${page+1} / ${Math.max(1,Math.ceil(info.rewards.length/6))}</span><button id="rank-next" ${(page+1)*6>=info.rewards.length?'disabled':''}>下一页</button></footer>`;
  }
  if(tab==='rules')content=`<div class="rank-board-title"><strong>征途规则</strong></div><div class="rank-rules"><p><b>整场计分</b>以两点生命的整场胜负结算 Elo；同分真人胜负通常 ±16，平局按双方评分结算。认输按负场处理。</p><p><b>实力匹配</b>初始搜索分差100以内，每5秒扩大100，最多400；真人优先，等待10秒后允许补位。补位对手基准1000分，计分幅度减半，不进入排行榜。</p><p><b>28天赛季</b>跨季对局归开局赛季，全部结束后发荣誉。新赛季积分向1000回归一半，战绩重新计算；荣誉永久保留。</p><p><b>段位与奖励</b>${info.tiers.map(x=>`${esc(x.name)} ${x.threshold||'初始'}`).join(' · ')}。胜败可升降段，奖励按最高段位。榜单同分依次比较胜场、达到时间、玩家编号。</p></div>`;
  main.innerHTML=`<section class="rank-screen"><header class="rank-header"><div><small>RANKED · 王冠征途</small><h2>${esc(s.name)}</h2></div><span>${date(s.starts_at)} — ${date(s.ends_at)} · 剩余 ${Math.ceil(s.remaining_ms/86400000)} 天</span><button id="rank-refresh">刷新</button><button id="rank-back" class="secondary">返回大厅</button></header><div class="rank-layout"><aside class="rank-summary">${rankBadge(t.key,t.name)}<h3>${esc(t.name)}</h3><strong class="rank-score">${p.rating}<small> 排位分</small></strong><div class="rank-progress"><span style="width:${progress}%"></span></div><small>${t.next?`距离下一段位 ${Math.max(0,t.next-p.rating)} 分`:'已达最高段位 · 争夺榜首'}</small><p>${p.wins} 胜 · ${p.losses} 负 · ${p.draws} 平<br>赛季最高 ${p.peak} 分</p><div class="rank-deck">出战牌组<b>${esc(deck()?.name||'请选择牌组')}</b></div><button id="rank-start">开始排位</button><small>普通对战与好友挑战不计分</small></aside><section class="rank-content"><nav class="rank-tabs">${[['ladder','排行榜'],['rewards','赛季荣誉'],['rules','规则与段位']].map(([key,label])=>`<button data-rank-tab="${key}" class="${tab===key?'selected':''}">${label}</button>`).join('')}</nav><div class="rank-content-body">${content}</div></section></div></section>`;
  $('rank-back').onclick=home;$('rank-refresh').onclick=()=>run(open);$('rank-start').onclick=()=>run(()=>start('ranked'));
  document.querySelectorAll('[data-rank-tab]').forEach(n=>n.onclick=()=>{tab=n.dataset.rankTab;page=0;run(load);});
  if($('rank-prev'))$('rank-prev').onclick=()=>{page--;run(load);};
  if($('rank-next'))$('rank-next').onclick=()=>{page++;run(load);};
  if($('rank-older'))$('rank-older').onclick=()=>{seasonIndex++;page=0;run(load);};
  if($('rank-newer'))$('rank-newer').onclick=()=>{seasonIndex--;page=0;run(load);};
  const equip=season=>run(async()=>{const result=await client.rankedHonor(season);if(!active)return;info.honor=result.honor;onHonor(result.honor);info.rewards.forEach(r=>r.equipped=r.season_id===season);draw();});
  document.querySelectorAll('[data-rank-equip]').forEach(n=>n.onclick=()=>equip(Number(n.dataset.rankEquip)));
  if($('rank-unequip'))$('rank-unequip').onclick=()=>equip(null);
  images();
 }
 return {open,close,active:()=>active};
}
