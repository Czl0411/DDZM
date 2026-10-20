export function selectionOption(pending,ids){
 return pending.options.find(o=>o.select_ids?.length===ids.length&&(pending.multi_select.ordered?o.select_ids.every((id,i)=>id===ids[i]):ids.every(id=>o.select_ids.includes(id))));
}
export function toggleSelection(pending,ids,id){
 if(ids.includes(id))return {ids:ids.filter(x=>x!==id),notice:''};
 if(!pending.multi_select.cards.some(c=>c.id===id))return {ids,notice:'此牌不是合法目标'};
 const next=[...ids,id];
 if(next.length>pending.multi_select.maximum)return {ids,notice:`最多选择${pending.multi_select.maximum}张，请先取消已选卡牌`};
 if(!pending.options.some(o=>o.select_ids&&next.every(x=>o.select_ids.includes(x))))return {ids,notice:'这些卡牌不能一起选择，请检查目标战列或条件'};
 return {ids:next,notice:''};
}
