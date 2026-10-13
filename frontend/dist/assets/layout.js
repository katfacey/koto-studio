const KEY='koto-panel-layout-v1';
const bounded=(value,min,max,fallback)=>Math.max(min,Math.min(Math.max(min,max),Number.isFinite(value)?value:fallback));

export function clampLayout(size,requested={},defaults={left:236,right:258,timeline:292}){
  const right=bounded(requested.right,210,size.width-180-420,defaults.right);
  const left=bounded(requested.left,180,size.width-right-420,defaults.left);
  const timeline=bounded(requested.timeline,180,size.height-320,defaults.timeline);
  const dialogue=Number.isFinite(requested.dialogue)?bounded(requested.dialogue,140,size.height-timeline-230,180):null;
  return {left,right,timeline,dialogue};
}

export function panelResizer(kind){
  const names={left:'media panel',right:'inspector',timeline:'timeline',dialogue:'dialogue editor'};
  const orientation=['left','right'].includes(kind)?'vertical':'horizontal';
  return `<div class="panel-resizer resizer-${kind}" data-panel-resize="${kind}" role="separator" aria-label="Resize ${names[kind]}" aria-orientation="${orientation}" tabindex="0" title="Drag to resize ${names[kind]}; double-click to reset"><span></span></div>`;
}

export function createPanelLayout(root,onChange){
  let requested={};let dragging=false;
  try{const stored=JSON.parse(localStorage.getItem(KEY));if(stored&&typeof stored==='object')requested=stored;}catch{/* Ignore damaged or unavailable preferences. */}
  function measure(){
    const workspace=root.querySelector('.workspace');if(!workspace)return null;
    const rect=workspace.getBoundingClientRect(),css=getComputedStyle(workspace);
    const defaults=Object.fromEntries(['left','right','timeline'].map(key=>[key,parseFloat(css.getPropertyValue('--panel-default-'+key))||{left:236,right:258,timeline:292}[key]]));
    return {workspace,rect,defaults,layout:clampLayout(rect,requested,defaults)};
  }
  function refresh(){
    const m=measure();if(!m)return;
    for(const key of ['left','right','timeline'])m.workspace.style.setProperty('--panel-'+key,m.layout[key]+'px');
    if(m.layout.dialogue===null)m.workspace.style.removeProperty('--panel-dialogue');else m.workspace.style.setProperty('--panel-dialogue',m.layout.dialogue+'px');
    for(const el of root.querySelectorAll('[data-panel-resize]')){
      const key=el.dataset.panelResize;el.setAttribute('aria-valuenow',Math.round(m.layout[key]??root.querySelector('.dialogue-editor')?.offsetHeight??180));
    }
  }
  function remember(){try{localStorage.setItem(KEY,JSON.stringify(requested));}catch{/* Resizing works without persistent storage. */}}
  function change(key,value){requested={...requested,[key]:value};refresh();onChange();}
  function start(event){
    const handle=event.target.closest('[data-panel-resize]');if(!handle||event.button!==0)return false;
    const m=measure();if(!m)return false;
    const key=handle.dataset.panelResize,x=event.clientX,y=event.clientY;
    const initial=m.layout[key]??root.querySelector('.dialogue-editor')?.offsetHeight??180;
    event.preventDefault();dragging=true;handle.setPointerCapture(event.pointerId);
    const move=ev=>change(key,initial+({left:ev.clientX-x,right:x-ev.clientX,timeline:y-ev.clientY,dialogue:y-ev.clientY}[key]));
    const finish=()=>{dragging=false;handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',finish);handle.removeEventListener('pointercancel',finish);handle.removeEventListener('lostpointercapture',finish);remember();};
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);handle.addEventListener('lostpointercapture',finish);
    return true;
  }
  function keydown(event){
    const handle=event.target.closest('[data-panel-resize]');if(!handle)return false;
    const key=handle.dataset.panelResize,keys=['left','right'].includes(key)?['ArrowLeft','ArrowRight']:['ArrowUp','ArrowDown'];
    if(!keys.includes(event.key)&&event.key!=='Home')return false;
    event.preventDefault();const m=measure();if(!m)return true;
    if(event.key==='Home')delete requested[key];else{
      const direction=(event.key===keys[0]?-1:1)*(['right','timeline','dialogue'].includes(key)?-1:1);
      requested[key]=(m.layout[key]??root.querySelector('.dialogue-editor')?.offsetHeight??180)+direction*(event.shiftKey?50:10);
    }
    refresh();onChange();remember();return true;
  }
  function reset(event){const handle=event.target.closest('[data-panel-resize]');if(!handle)return;delete requested[handle.dataset.panelResize];refresh();onChange();remember();}
  return {refresh,start,keydown,reset,get dragging(){return dragging;}};
}
