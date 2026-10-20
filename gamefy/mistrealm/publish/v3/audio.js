// Short local cues; no network assets, microphone access or automatic playback.
export function setupGameAudio(enabled){
 let context=null;
 function unlock(){
  if(!enabled())return;
  const Audio=globalThis.AudioContext||globalThis.webkitAudioContext;if(!Audio)return;
  context??=new Audio();void context.resume().catch(()=>{});
 }
 document.addEventListener('pointerdown',unlock);document.addEventListener('keydown',unlock);
 return {play(kind){
  if(!enabled()||context?.state!=='running')return;
  const oscillator=context.createOscillator(),volume=context.createGain(),now=context.currentTime;
  oscillator.type='sine';oscillator.frequency.setValueAtTime(kind==='turn'?660:330,now);
  volume.gain.setValueAtTime(.035,now);volume.gain.exponentialRampToValueAtTime(.001,now+.13);
  oscillator.connect(volume);volume.connect(context.destination);oscillator.start(now);oscillator.stop(now+.14);
  oscillator.onended=()=>{oscillator.disconnect();volume.disconnect();};
 }};
}
