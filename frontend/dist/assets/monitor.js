import {playbackRate} from './timing.js';
import {speakerMuted} from './timeline-edit.js';

export function monitoringPlan(p,time,mode){
  const plan=[],settings=p.settings;
  const add=(key,asset,offset,gain,rate=1)=>{if(asset&&gain>0)plan.push({key,asset,time:Math.max(0,offset),gain,rate});};
  if(mode==='original'){
    const known=p.dialogue.filter(l=>(l.source_start??l.start)<=time&&time<(l.source_end??l.end));
    const vocalsAllowed=!known.length||known.some(l=>!speakerMuted(p,l.speaker));
    if(!settings.original_muted&&vocalsAllowed)add('original',p.assets.vocals??p.assets.original_audio,time,1);
    if(p.assets.vocals&&!settings.background_muted)add('background',p.assets.background,time,settings.background_gain??.8);
  }else{
    const mode=settings.background_mode??'separated';
    if(mode==='separated'&&!settings.background_muted)add('background',p.assets.background,time,settings.background_gain??.8);
    if(mode==='original'&&!settings.original_muted)add('original',p.assets.original_audio,time,settings.background_gain??.8);
    for(const l of p.dialogue){
      if(!l.audio||speakerMuted(p,l.speaker)||time<l.start||time>=l.end)continue;
      const rate=playbackRate(p,l,l.audio.duration);
      if((time-l.start)*rate>=l.audio.duration)continue;
      add('line:'+l.id,l.audio.asset,(time-l.start)*rate,(settings.dialogue_gain??1)*(l.gain??1),rate);
    }
  }
  return plan;
}

export function createMonitor(asset,onError){
  const pool=new Map();let context=null;
  function activate(){
    const AudioContext=globalThis.AudioContext??globalThis.webkitAudioContext;
    if(!context&&AudioContext)context=new AudioContext();
    context?.resume().catch(()=>{});
  }
  function stop(){for(const item of pool.values())item.audio.pause();}
  function sync(p,time,mode,playing,muted){
    if(!playing||muted){stop();return;}
    const wanted=new Set();
    for(const part of monitoringPlan(p,time,mode)){
      const key=p.id+':'+part.key+':'+part.asset;wanted.add(key);
      let item=pool.get(key);
      if(!item){
        const audio=new Audio(asset(part.asset));audio.preload='auto';
        item={audio,gain:null,source:null,failed:false,warned:false};
        if(context){item.source=context.createMediaElementSource(audio);item.gain=context.createGain();item.source.connect(item.gain).connect(context.destination);}
        audio.onerror=()=>{if(!item.failed){item.failed=true;onError('Could not play an audio track. Check the take format or import WAV audio.');}};
        pool.set(key,item);
      }
      const a=item.audio;a.playbackRate=part.rate;
      if(item.gain)item.gain.gain.value=part.gain;else a.volume=Math.min(1,part.gain);
      if(Math.abs(a.currentTime-part.time)>.12){try{a.currentTime=part.time;}catch{/* Retry after metadata arrives. */}}
      if(a.paused&&!item.failed)a.play().catch(error=>{if(error.name!=='AbortError'&&!item.warned){item.warned=true;onError(error.message);}});
    }
    for(const [key,item] of pool)if(!wanted.has(key))item.audio.pause();
    // Bound the number of inactive elements in long episodes.
    if(pool.size>40)for(const [key,item] of pool){if(!wanted.has(key)){item.audio.onerror=null;item.audio.removeAttribute('src');item.audio.load();item.source?.disconnect();item.gain?.disconnect();pool.delete(key);if(pool.size<=30)break;}}
  }
  return {activate,sync,stop};
}
