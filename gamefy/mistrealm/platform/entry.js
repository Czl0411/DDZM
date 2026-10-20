import {MistrealmClient} from './client.js';
import {CONFIG} from './config.js';
const root=new URL('./',import.meta.url);
async function boot(){
 const retry=document.getElementById('entry-retry');retry.hidden=true;
 try{
  window.dzmm?.loading?.progress?.({phase:'runtime_initializing',progress:10,message:'正在恢复你的军团'});
  const client=new MistrealmClient({sdk:window.dzmm,apiBase:CONFIG.apiBase});
  const profile=await client.boot();
  let version=3,originalV3=false,revisionOne=false;
  if(profile.room_id){const state=(await client.snapshot(profile.room_id)).state;version=state.rules_version||1;originalV3=version===3&&!state.balance_revision&&state.phase!=='closed';revisionOne=version===3&&state.balance_revision===1&&state.phase!=='closed';}
  else if(profile.matchmaking?.status==='waiting')version=profile.matchmaking.rules_version||1;
  const route={1:['./','legacy.html'],2:['classic/','classic/index.html'],3:originalV3?['v3-original/','v3-original/index.html']:revisionOne?['v3-r1/','v3-r1/index.html']:['v3/','v3/index.html']}[version];
  if(!route)throw new Error('此对局版本暂不支持，请联系游戏作者');
  const folder=new URL(route[0],root);
  const response=await fetch(new URL(route[1],root));
  if(!response.ok)throw new Error('界面加载失败，请重试');
  const page=new DOMParser().parseFromString(await response.text(),'text/html');
  let base=document.querySelector('base');
  if(!base){base=document.createElement('base');document.head.prepend(base);}
  base.href=folder.href;
  await Promise.all([...page.querySelectorAll('link[rel="stylesheet"]')].map(link=>new Promise((resolve,reject)=>{
   const style=document.createElement('link');style.rel='stylesheet';style.href=new URL(link.getAttribute('href'),folder).href;
   style.onload=resolve;style.onerror=()=>reject(new Error('界面样式加载失败，请重试'));document.head.append(style);
  })));
  page.querySelectorAll('script').forEach(script=>script.remove());
  document.title=page.title;document.getElementById('entry-style').remove();
  document.body.innerHTML=page.body.innerHTML;
  await import(new URL('game.js',folder).href);
 }catch(error){
  const status=document.getElementById('entry-status');
  if(status){status.textContent=error.message;retry.hidden=false;}
  window.dzmm?.loading?.error?.('MISTREALM_ENTRY_FAILED',error.message);
 }
}
document.getElementById('entry-retry').onclick=boot;
boot();
