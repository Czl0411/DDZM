import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {filterCatalogue,cardSkillLabel} from '../publish/v3/catalogue.js';
const {cards}=JSON.parse(readFileSync(new URL('../publish/v3/cards.json',import.meta.url)));
const faction=cards.c050.faction;
test('catalogue combines name, row, type and effect without changing cards',()=>{
 const before=JSON.stringify(cards);
 assert.deepEqual(filterCatalogue(cards,faction,{query:'冰崖',row:'1',type:'normal',effect:'move'}).map(([id])=>id),['c050']);
 assert.equal(filterCatalogue(cards,faction,{query:'冰崖',row:'0'}).length,0);
 assert.equal(filterCatalogue(cards,faction,{query:'不存在的卡'}).length,0);
 assert.equal(JSON.stringify(cards),before);
});
test('catalogue includes neutral cards but excludes other armies and leaders',()=>{
 const found=filterCatalogue(cards,faction);
 assert.ok(found.some(([,c])=>c.faction==='neutral'));
 assert.ok(found.every(([,c])=>[faction,'neutral'].includes(c.faction)&&c.type!=='leader'));
 for(const type of ['instant','persistent']){
  const result=filterCatalogue(cards,faction,{type});assert.ok(result.length);
  assert.ok(result.every(([,c])=>c.type==='special'&&c.persistent===(type==='persistent')));
 }
 assert.ok(filterCatalogue(cards,faction,{effect:'draw'}).length);
});

test('deck composition counts copies, spells and flexible rows explicitly',async()=>{
 const {deckCounts}=await import('../publish/v3/catalogue.js');
 const cards={a:{type:'unit',rows:[0,1],hero:false},b:{type:'unit',rows:[2],hero:true},c:{type:'special',persistent:true},d:{type:'special',persistent:false}};
 assert.deepEqual(deckCounts(cards,{a:2,b:1,c:1,d:3}),{units:3,heroes:1,instant:3,persistent:1,rows:[2,2,1],flexible:2});
});

test('unsaved comparison ignores zero-count entries and property order but includes name and leader',async()=>{
 const {deckChanged}=await import('../publish/v3/catalogue.js');
 const a={name:'军团',faction:'crown',leader:'a',counts:{x:2,y:1}};
 assert.equal(deckChanged({...a,counts:{y:1,x:2,z:0}},a),false);
 assert.equal(deckChanged({...a,name:'新名称'},a),true);
 assert.equal(deckChanged({...a,leader:'b'},a),true);
 assert.equal(deckChanged({...a,counts:{x:1,y:1}},a),true);
});

test('card summaries describe current skills rather than normal or hero unit type',()=>{
 const expected={c047:'召集 · 灵活',c048:'部署 · 强化',c049:'强化',c050:'部署',c051:'部署 · 复活',c052:'部署',c107:'部署 · 灵活',c044:'间谍 · 灵活',c024:'间谍',c064:'召集 · 阵亡',c067:'阵亡',c068:'部署 · 强化',c070:'部署 · 复活',c075:'强化',c038:'强化',c043:'特殊',c037:'部署'};
 for(const [id,label] of Object.entries(expected))assert.equal(cardSkillLabel(cards[id]),label,`${id}: ${cards[id].name}`);
 assert.equal(cardSkillLabel(cards.c118),'持续术 · 增益');
 assert.equal(cardSkillLabel(cards.c111),'即时术');
 assert.equal(cardSkillLabel(cards.c019),'领袖');
 for(const c of Object.values(cards).filter(c=>c.type==='unit'))assert.ok(!/普通单位|英雄/.test(cardSkillLabel(c)));
});

test('effect labels distinguish dealing damage from reacting to or absorbing damage',()=>{
 const expected={c027:'部署 · 伤害',c036:'强化',c057:'部署 · 伤害',c071:'阵亡 · 强化',c076:'部署 · 强化',c096:'强化',c102:'特殊',c041:'灵活 · 强化'};
 for(const [id,label] of Object.entries(expected))assert.equal(cardSkillLabel(cards[id]),label,`${id}: ${cards[id].name}`);
});
test('every persistent spell identifies damage, debuff or benefit without mistaking negative power for a benefit',()=>{
 const expected={c014:'增益',c034:'减益',c054:'伤害',c074:'增益',c094:'增益',c113:'减益',c114:'伤害',c118:'增益',c120:'减益'};
 assert.deepEqual(Object.keys(expected).sort(),Object.keys(cards).filter(id=>cards[id].persistent).sort());
 for(const [id,label] of Object.entries(expected))assert.equal(cardSkillLabel(cards[id]),`持续术 · ${label}`,cards[id].name);
});
