export const EFFECT_FILTERS=[['all','全部效果'],['move','移动'],['draw','抽牌'],['damage','伤害'],['boost','强化'],['death','阵亡'],['sacrifice','献祭'],['summon','召集'],['revive','复活']];
const effects={move:/移动|转阵/,draw:/抽[一二两三四五六七八九十\d]+张|摸[一二两三\d]+张|加入手牌|入手/,damage:/伤害/,boost:/强化|战力[＋+]|增加.*战力/,death:/阵亡/,sacrifice:/献祭|牺牲|吞噬/,summon:/召集/,revive:/复活/};
export function filterCatalogue(cards,faction,{query='',row='all',type='all',effect='all'}={}){
 const q=query.trim().toLocaleLowerCase();
 return Object.entries(cards).filter(([,c])=>{
  if(c.type==='leader'||![faction,'neutral'].includes(c.faction))return false;
  if(q&&!`${c.name} ${c.text}`.toLocaleLowerCase().includes(q))return false;
  if(row!=='all'&&(c.type!=='unit'||!c.rows.includes(Number(row))))return false;
  if(type==='normal'&&(c.type!=='unit'||c.hero))return false;
  if(type==='hero'&&!c.hero)return false;
  if(type==='instant'&&(c.type!=='special'||c.persistent))return false;
  if(type==='persistent'&&!c.persistent)return false;
  return effect==='all'||!!effects[effect]?.test(c.text);
 });
}

export function deckCounts(cards,counts){
 const result={units:0,heroes:0,instant:0,persistent:0,rows:[0,0,0],flexible:0};
 for(const [id,n] of Object.entries(counts)){
  const c=cards[id];
  if(c.type==='unit'){result.units+=n;if(c.hero)result.heroes+=n;for(const r of c.rows)result.rows[r]+=n;if(c.rows.length>1)result.flexible+=n;}
  else if(c.type==='special')result[c.persistent?'persistent':'instant']+=n;
 }
 return result;
}

export function deckChanged(draft,original){
 const canonical=d=>JSON.stringify([d.name,d.faction,d.leader,Object.entries(d.counts).filter(([,n])=>n>0).sort(([a],[b])=>a.localeCompare(b))]);
 return !!draft&&!!original&&canonical(draft)!==canonical(original);
}

export function cardSkillLabel(c){
 if(c.type==='leader')return '领袖';
 const boosts=/强化[＋+]|战力[＋+]|获得等于.*条件战力|战力总和加给自己/.test(c.text)||c.abilities.includes('bond');
 const damages=/(?:造成|受到)(?:\d+|X)点伤害/.test(c.text);
 if(c.type==='special'){
  if(!c.persistent)return '即时术';
  const tags=['持续术'];
  if(damages)tags.push('伤害');
  if(/条件战力[－-]|封印目标|伤害[＋+]/.test(c.text))tags.push('减益');
  if(boosts||/抽\d+张牌/.test(c.text))tags.push('增益');
  return tags.join(' · ');
 }
 const tags=[];
 if(c.abilities.includes('spy'))tags.push('间谍');
 if(c.abilities.includes('muster'))tags.push('召集');
 if(/(?:^|[。；])部署[:：]/.test(c.text))tags.push('部署');
 if(/(?:^|[。；])阵亡(?:时|[:：])/.test(c.text))tags.push('阵亡');
 if(/部署[:：]复活/.test(c.text))tags.push('复活');
 if(c.rows.length>1)tags.push('灵活');
 if(boosts)tags.push('强化');
 if(damages)tags.push('伤害');
 return tags.join(' · ')||'特殊';
}
