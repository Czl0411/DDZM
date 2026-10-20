// One landscape surface, including a rotation fallback where orientation lock is unavailable.
export function setupScreen(){
 const viewport=document.getElementById('game-viewport'),shell=document.getElementById('game-shell');
 const gate=document.getElementById('screen-entry'),start=document.getElementById('enter-game'),hint=document.getElementById('screen-hint');
 function resize(){
  const width=innerWidth,height=innerHeight,rotated=height>width;
  const availableWidth=rotated?height:width,availableHeight=rotated?width:height;
  const scale=Math.min(1,availableWidth/640,availableHeight/360);
  const gameWidth=availableWidth/scale,gameHeight=availableHeight/scale;
  document.documentElement.style.setProperty('--game-width',gameWidth+'px');
  document.documentElement.style.setProperty('--game-height',gameHeight+'px');
  viewport.style.width=gameWidth+'px';viewport.style.height=gameHeight+'px';
  viewport.style.transform=`translate(-50%,-50%) rotate(${rotated?90:0}deg) scale(${scale})`;
  document.documentElement.classList.toggle('screen-rotated',rotated);
  document.documentElement.style.setProperty('--screen-scale',scale);
  document.getElementById('fullscreen').textContent=document.fullscreenElement?'退出全屏':'全屏';
  shell.dispatchEvent(new Event('screenresize'));
 }
 async function enter(){
  start.disabled=true;
  try{
   if(!document.fullscreenElement&&document.fullscreenEnabled)await document.documentElement.requestFullscreen();
   if(screen.orientation?.lock)await screen.orientation.lock('landscape');
  }catch{
   // Sandboxed/iOS browsers can reject either API; the landscape surface still works.
  }finally{gate.hidden=true;start.disabled=false;resize();document.dispatchEvent(new Event('gameentered'));}
 }
 start.onclick=enter;
 document.getElementById('fullscreen').onclick=async()=>{
  if(document.fullscreenElement){await document.exitFullscreen();resize();}
  else await enter();
 };
 if(!document.fullscreenEnabled)hint.textContent='点击进入横屏画面；如需铺满手机，请使用平台的全屏入口。';
 addEventListener('resize',resize);document.addEventListener('fullscreenchange',resize);
 resize();
 // Preserve an activation supplied by hosts that open the game directly from a tap.
 if(navigator.userActivation?.isActive)void enter();
}
