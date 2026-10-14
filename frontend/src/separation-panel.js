// A replaceable view over the separation API; result storage lives in the backend.
const H=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const off=v=>v?' disabled':'';
const opt=(v,label,selected)=>`<option value="${H(v)}"${selected?' selected':''}>${H(label)}</option>`;
const clock=v=>`${Math.floor(v/60).toString().padStart(2,'0')}:${(v%60).toFixed(1).padStart(4,'0')}`;
const action=(act,label,disabled=false,extra='')=>`<button class="secondary" data-act="${act}"${off(disabled)} ${extra}>${label}</button>`;
const field=(f,value)=>f.type==='checkbox'?`<label class="check-field"><input data-field="model.separation.${f.key}" type="checkbox"${value?' checked':''}>${H(f.label)}</label>`:`<label class="field-label">${H(f.label)}<input data-field="model.separation.${f.key}" type="number" min="${f.min}" max="${f.max}" step="${f.integer?1:.01}" value="${H(value)}"></label>`;

export function separationPanel({p,adapters,catalog,state,busy,jobs,player}){
  const selection=p.models.separation,adapter=adapters.find(a=>a.id===selection.id),uvr=selection.id==='audio-separator';
  const model=catalog?.models.find(m=>m.id===(selection.settings.model??'mdx-inst-hq3'));
  const results=[...(p.separations??[])].reverse();
  const selected=results.find(r=>r.id===state.resultId)??results[0];
  const pending=jobs.find(j=>['separate','download_separation_model'].includes(j.kind)&&['queued','running'].includes(j.status));
  return `<p class="modal-intro">Test a short source range, compare dialogue and background, then separate the full video. Previews keep the current project mix. Full results are saved and can be switched later.</p>
  <div class="separation-columns"><div><fieldset class="model-card"${off(busy)}>
  <div class="model-card-heading"><strong>Separation engine</strong><span class="${adapter?.available?'installed-badge':'missing-badge'}">${adapter?.available?'Worker installed':'Needs setup'}</span></div>
  <label class="field-label">Engine<select data-field="adapter.separation">${adapters.filter(a=>a.capability==='separation').map(a=>opt(a.id,a.label,a.id===selection.id)).join('')}</select></label>
  ${uvr?`<label class="field-label">Model<select data-field="model.separation.model">${(catalog?.models??[]).map(m=>opt(m.id,m.label,m.id===(model?.id))).join('')}</select></label><p>${H(model?.description)}</p><p class="inspector-note">${model?`${(model.size/1048576).toFixed(0)} MiB · ${model.architecture} · ${model.installed?'Weights installed':'Weights not downloaded'}`:''}</p>${action('download-separation-model',model?.installed?'Verify installed weights':'Download selected model',busy||!model)}<p class="inspector-note">${H(model?.terms)} <a href="${H(model?.source??'https://github.com/Anjok07/ultimatevocalremovergui')}" target="_blank" rel="noreferrer">Model source</a></p>`:adapter?.fields.filter(f=>f.key!=='device').map(f=>f.type==='select'?`<label class="field-label">${H(f.label)}<select data-field="model.separation.${f.key}">${f.options.map(v=>opt(v,v,v===(selection.settings[f.key]??f.default))).join('')}</select></label>`:`<label class="field-label">${H(f.label)}<input data-field="model.separation.${f.key}" value="${H(selection.settings[f.key]??f.default)}"></label>`).join('')??''}
  ${!adapter?.custom?`<label class="field-label">Device<select data-field="model.separation.device">${['cuda','cpu'].map(v=>opt(v,v.toUpperCase(),v===(selection.settings.device??'cuda'))).join('')}</select></label>`:''}
  ${!adapter?.available?`<p class="warning-box">Run ${uvr?'Install-Separation.cmd':'Install-Models.cmd'}, restart KOTO, then refresh worker status.</p>`:''}
  ${uvr&&model?`<details><summary>Advanced model controls</summary><div class="separation-advanced">${model.fields.map(f=>field(f,selection.settings[f.key]??f.default)).join('')}</div></details>`:''}
  </fieldset><fieldset class="model-card"${off(busy)}><strong>Preview source range</strong><div class="two-fields">${['start','end'].map(key=>`<label class="field-label">${key==='start'?'Start':'End'} · seconds<input data-separation-range="${key}" type="number" step=".1" min="0" max="${p.media?.duration??0}" value="${state[key]}"></label>`).join('')}</div><p class="inspector-note">Up to 120 seconds. Start with 30–60 seconds containing speech, music and effects.</p><div class="separation-actions">${action('separation-selection','Use selected clip',busy||!p.dialogue.some(l=>l.id===state.lineId))}${action('separation-playhead','From playhead',busy)}${action('separation-preview','Separate preview',busy||!p.assets.original_audio||!adapter?.available||uvr&&!model?.installed)}</div></fieldset>
  <div class="separation-actions">${action('refresh-separation','Refresh status',busy)}${action('separation-full','Separate full video',busy||!p.assets.original_audio||!adapter?.available||uvr&&!model?.installed)}</div>
  ${!p.assets.original_audio?'<p class="warning-box">Import video and run Prepare media first.</p>':''}
  ${pending?`<div class="running-card" role="status"><strong>${pending.kind==='separate'?'Separating audio':'Downloading weights'} · ${Math.round(pending.progress*100)}%</strong><div class="progress-bar"><i style="width:${pending.progress*100}%"></i></div><p>${H(pending.message)}</p>${action('cancel','Cancel job',false,`data-id="${pending.id}"`)}</div>`:''}</div>
  <div class="separation-results"><h3>Saved results</h3><p class="inspector-note">Listen for missing speech, dialogue leaking into the background, and lost effects. These models are trained mainly on music; quality varies with dialogue.</p>
  ${selected?`<div class="separation-comparison"><strong>${H(selected.selection.settings.model??selected.label)}</strong><small>${selected.preview?'Preview':'Full source'} · ${clock(selected.start)}–${clock(selected.end)}</small><div class="separation-actions">${[['original','Original'],['vocals','Dialogue'],['background','Background']].map(([key,label])=>`<button class="secondary${player.stem===key?' selected':''}" data-act="compare-separation" data-id="${selected.id}" data-stem="${key}" aria-pressed="${player.stem===key}">${label}</button>`).join('')}</div><div class="separation-actions">${action('play-separation',player.playing?'Pause':'Play',false,`data-id="${selected.id}"`)}${action('stop-separation','Stop')}</div><label class="field-label">Comparison position<input data-separation-seek type="range" min="0" max="${selected.duration}" step=".1" value="${player.resultId===selected.id?player.time:0}"></label><small id="separation-clock">${clock(selected.start+(player.resultId===selected.id?player.time:0))} / ${clock(selected.end)}</small></div>`:'<p class="inspector-note">Run a preview or full separation to save a result here.</p>'}
  <div class="separation-history">${results.map(r=>{const stale=r.source_asset!==p.assets.original_audio;return `<article class="separation-result${r.id===selected?.id?' selected':''}"><div><strong>${H(r.selection.settings.model??r.label)}</strong><small>${r.preview?'Preview':'Full source'} · ${clock(r.start)}–${clock(r.end)} · ${new Date(r.created*1000).toLocaleString()}</small><small>${r.id===p.active_separation?'Active project stems':stale?'Earlier prepared source':r.preview?'Preview only':'Saved full result'}</small></div><div>${action('select-separation','Compare',false,`data-id="${r.id}"`)}${!r.preview?action('activate-separation',r.id===p.active_separation?'Active':'Use in project',busy||stale||r.id===p.active_separation,`data-id="${r.id}"`):''}</div></article>`;}).join('')}</div>
  ${results.some(r=>!r.preview)?'<p class="inspector-note">Switching full results updates the background and vocal source. Generated takes using original speaker references need regeneration.</p>':''}</div></div>`;
}

export function createComparisonPlayer({url,onError,onUpdate,pauseMonitor,makeAudio=src=>new Audio(src)}){
  let audio=null,state={resultId:null,stem:'original',time:0,playing:false};
  const emit=()=>onUpdate({...state});
  const stop=()=>{audio?.pause();audio=null;state={...state,time:0,playing:false};emit();};
  function load(record,stem=state.stem){
    const offset=record.id===state.resultId?(audio?.currentTime??state.time):0;
    const wasPlaying=record.id===state.resultId&&state.playing;
    audio?.pause();state={resultId:record.id,stem,time:offset,playing:false};
    const current=makeAudio(url(record.assets[stem]));audio=current;
    current.addEventListener('loadedmetadata',()=>{if(audio===current)current.currentTime=Math.min(offset,current.duration||record.duration);});
    current.addEventListener('timeupdate',()=>{if(audio===current){state.time=current.currentTime;emit();}});
    current.addEventListener('ended',()=>{if(audio===current){state.playing=false;emit();}});
    current.addEventListener('error',()=>{if(audio===current){state.playing=false;onError('Could not load the saved separation audio');emit();}});
    emit();if(wasPlaying)void play();
  }
  async function play(){if(!audio)return;const current=audio;pauseMonitor();try{await current.play();if(audio===current){state.playing=true;emit();}}catch(error){if(audio===current){state.playing=false;onError(error.message);emit();}}}
  return {get state(){return {...state};},load,stop,seek(value){state.time=value;if(audio)audio.currentTime=value;emit();},toggle(record){if(state.resultId!==record.id||!audio)load(record);if(state.playing){audio.pause();state.playing=false;emit();}else void play();}};
}
