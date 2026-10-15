import {MistrealmClient} from './client.js';
import {CONFIG} from './config.js';
const root=new URL('./',import.meta.url);
async function boot(){
 const retry=document.getElementById('entry-retry');retry.hidden=true;
 try{
  window.dzmm?.loading?.progress?.({phase:'runtime_initializing',progress:10,message:'正在恢复你的军团'});
  const client=new MistrealmClient({sdk:window.dzmm,apiBase:CONFIG.apiBase});
  const profile=await client.boot();
  let classic=true;
  if(profile.room_id)classic=(await client.snapshot(profile.room_id)).state.rules_version===2;
  else if(profile.matchmaking?.status==='waiting')classic=profile.matchmaking.rules_version===2;
  const folder=new URL(classic?'classic/':'./',root);
  const response=await fetch(new URL(classic?'classic/index.html':'legacy.html',root));
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
