export function estimateSeconds(text,wpm=150){
  const words=String(text??'').match(/[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g)??[];
  if(!words.length)return 0;
  const pauses=(text.match(/[,;:]/g)??[]).length*.1+(text.match(/[.!?]+(?=\s|$)/g)??[]).length*.15;
  return Math.round((words.length*60/wpm+pauses)*100)/100;
}
export function playbackRate(p,l,duration){
  const factor=duration/(l.end-l.start);
  return p.settings.fit_duration!==false&&l.auto_fit!==false&&factor>=.8&&factor<=1.25?factor:(l.playback_rate??1);
}
export function timingInfo(p,l,text=l.translation){
  const measured=Boolean(l.audio)&&text===l.translation;
  const seconds=measured?l.audio.duration:estimateSeconds(text,p.settings.estimated_speech_wpm??150);
  const target=l.end-l.start,rate=seconds?playbackRate(p,l,seconds):1,played=seconds/rate;
  const status=!seconds?'empty':played>target+(measured?.08:target*.15)?'long':played<target*.75?'short':'fit';
  const label=!seconds?'No English text':`${measured?'Take':'Estimate'} ${seconds.toFixed(1)}s / ${target.toFixed(1)}s slot${Math.abs(rate-1)>.01?` · ${rate.toFixed(2)}×`:''}${status==='long'?' · may run long':status==='short'?' · may run short':''}`;
  return {seconds,target,rate,played,status,label,measured};
}

// Offer an explicit fix; never shift another clip or discard the original take.
export function timingFix(p,l){
  const t=timingInfo(p,l);
  if(!t.measured||t.status!=='long')return null;
  const factor=t.seconds/t.target;
  if(factor>=.8&&factor<=1.25)return {kind:'speed',label:'Fit with speech speed',rate:factor};
  const end=Math.ceil((l.start+t.played)*1000)/1000;
  if(!p.media||end>p.media.duration)return {reason:'No room before the video ends. Shorten the wording and regenerate.'};
  const muted=new Set(p.speakers.filter(s=>s.muted).map(s=>s.id));
  if(p.dialogue.some(other=>other.id!==l.id&&!muted.has(other.speaker)&&other.end>l.end&&other.start<end))return {reason:'Extension would overlap another voice clip. Adjust speed or shorten the wording and regenerate.'};
  return {kind:'extend',label:`Extend slot to ${(end-l.start).toFixed(2)}s`,end};
}
export function exportIssues(p){
  const muted=new Set(p.speakers.filter(s=>s.muted).map(s=>s.id));
  return p.dialogue.flatMap((l,index)=>muted.has(l.speaker)?[]:!l.audio?[{line:l,index,type:'missing',reason:'No replacement voice take'}]:timingInfo(p,l).status==='long'?[{line:l,index,type:'timing',reason:timingInfo(p,l).label}]:[]);
}
