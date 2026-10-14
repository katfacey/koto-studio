export const speakerMuted=(p,id)=>p.speakers.find(s=>s.id===id)?.muted===true;
export const audibleLines=p=>p.dialogue.filter(l=>!speakerMuted(p,l.speaker));

export function preserveSource(line){
  line.source_start??=line.start;line.source_end??=line.end;
}

export function moveClip(p,id,target,start){
  const line=p.dialogue.find(l=>l.id===id);
  if(!line||!p.speakers.some(s=>s.id===target))return false;
  const length=line.end-line.start;
  const limit=p.media?.duration??Math.max(18,...p.dialogue.map(l=>l.end+3));
  const next=Number.isFinite(start)?Math.max(0,Math.min(limit-length,start)):line.start;
  if(line.speaker===target&&Math.abs(next-line.start)<.0005)return false;
  if(line.speaker!==target&&line.audio?.kind==='generated'&&!(line.voice_profile&&line.voice?.reference_mode!=='source')){
    line.audio=null;line.warning='Speaker changed. Regenerate this voice take.';
  }
  preserveSource(line);
  line.speaker=target;line.start=Number(next.toFixed(3));line.end=Number((next+length).toFixed(3));
  return true;
}

export function reorderSpeaker(p,id,target,after=false){
  const source=p.speakers.findIndex(s=>s.id===id);
  if(source<0||id===target||!p.speakers.some(s=>s.id===target))return false;
  const [speaker]=p.speakers.splice(source,1);
  const index=p.speakers.findIndex(s=>s.id===target)+(after?1:0);
  p.speakers.splice(index,0,speaker);return true;
}

export function toggleTrack(p,track,id){
  if(track==='speaker'){
    const s=p.speakers.find(s=>s.id===id);if(!s)return false;
    s.muted=!s.muted;return true;
  }
  const keys={original:'original_muted',background:'background_muted',video:'video_visible',subtitles:'subtitles_visible'};
  const key=keys[track];if(!key)return false;
  p.settings[key]=!(p.settings[key]??(['video','subtitles'].includes(track)));return true;
}

export function frameRate(p){
  const fps=p.media?.streams.find(s=>s.index===p.settings.video_stream)?.fps??'24/1';
  const [num,den=1]=String(fps).split('/').map(Number),rate=num/den;
  return Number.isFinite(rate)&&rate>0&&rate<=240?rate:24;
}

export function createTimelineDrag(root,{project,locked,scale,commit,select}){
  let dragging=false;
  function start(e){
    if(locked()||e.button!==0||e.target.closest('[data-trim],[data-panel-resize]'))return false;
    const grip=e.target.closest('[data-reorder-speaker]'),clip=e.target.closest('.dialogue-clip');
    if(!grip&&!clip)return false;
    const p=project(),node=grip??clip,id=grip?.dataset.reorderSpeaker??clip.dataset.id;
    const line=clip?p.dialogue.find(l=>l.id===id):null,rate=frameRate(p),pixels=scale();
    const box=node.getBoundingClientRect(),x=e.clientX,y=e.clientY;
    let moved=false,target=null,next=line?.start,ghost=null;
    e.preventDefault();node.setPointerCapture(e.pointerId);dragging=true;
    function move(ev){
      const dx=ev.clientX-x,dy=ev.clientY-y;
      if(!moved&&Math.hypot(dx,dy)<5)return;
      moved=true;
      if(!ghost){ghost=node.cloneNode(true);ghost.classList.add('timeline-drag-ghost');Object.assign(ghost.style,{left:box.x+'px',top:box.y+'px',width:box.width+'px',height:box.height+'px'});document.body.append(ghost);node.classList.add('timeline-drag-source');}
      root.querySelectorAll('.timeline-drop-target').forEach(el=>el.classList.remove('timeline-drop-target'));
      target=document.elementFromPoint(ev.clientX,ev.clientY)?.closest('[data-speaker-lane]');
      target?.classList.add('timeline-drop-target');
      const header=target&&ev.clientX<target.getBoundingClientRect().x+186;
      if(line)next=ev.shiftKey||header||Math.abs(dx)<5?line.start:Math.round((line.start+dx/pixels)*rate)/rate;
      ghost.style.transform=`translate(${line?(next-line.start)*pixels:dx}px,${dy}px)`;
      const scroll=root.querySelector('.timeline-scroll');if(scroll){const area=scroll.getBoundingClientRect();if(ev.clientY>area.bottom-20)scroll.scrollTop+=8;else if(ev.clientY<area.top+20)scroll.scrollTop-=8;}
    }
    function finish(ev){
      node.removeEventListener('pointermove',move);node.removeEventListener('pointerup',finish);node.removeEventListener('pointercancel',cancel);node.removeEventListener('lostpointercapture',cancel);
      node.classList.remove('timeline-drag-source');ghost?.remove();root.querySelectorAll('.timeline-drop-target').forEach(el=>el.classList.remove('timeline-drop-target'));dragging=false;
      if(ev.type!=='pointerup')return;
      if(moved&&target){const targetId=target.dataset.speakerLane;commit(p=>grip?reorderSpeaker(p,id,targetId,ev.clientY>target.getBoundingClientRect().y+target.getBoundingClientRect().height/2):moveClip(p,id,targetId,next));}
      select(line?id:null,moved);
    }
    function cancel(ev){finish(ev);}
    node.addEventListener('pointermove',move);node.addEventListener('pointerup',finish);node.addEventListener('pointercancel',cancel);node.addEventListener('lostpointercapture',cancel);
    return true;
  }
  return {start,get dragging(){return dragging;}};
}
