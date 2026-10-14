// Renderer/action smoke checks without downloading a DOM or browser package.
// This is not a substitute for browser playback/visual testing.
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';

const listeners={};
const nodes=new Map();
const fakeNode=()=>({innerHTML:'',textContent:'',style:{},value:'',clientWidth:1000,scrollLeft:0,disabled:false});
const root={innerHTML:'',querySelector(selector){
  if(['#modal-root','#toast-root','#timecode','#save-status','[data-act="save"]','[data-act="generate-line"]','[data-act="play"]'].includes(selector)||selector==='.timeline-scroll'&&this.innerHTML.includes('class="timeline-scroll"')||selector==='.timeline-content'&&this.innerHTML.includes('class="timeline-content"')||selector==='.preview-caption'){
    if(!nodes.has(selector))nodes.set(selector,fakeNode());return nodes.get(selector);
  }return null;
},querySelectorAll(){return [];},addEventListener(type,fn){listeners[type]=fn;}};
let keydown;
globalThis.document={querySelector(){return root;},addEventListener(type,fn){if(type==='keydown')keydown=fn;}};
globalThis.window={addEventListener(){}};
globalThis.localStorage={getItem(){return null;},setItem(){}};
if(!globalThis.crypto)Object.defineProperty(globalThis,'crypto',{value:webcrypto});
const timers=[];
globalThis.setInterval=(fn)=>{timers.push(fn);return timers.length;};
let nextTimeout=0;const delayed=new Map();
globalThis.setTimeout=(fn,ms)=>{const id=++nextTimeout;delayed.set(id,{fn,ms});return id;};globalThis.clearTimeout=id=>delayed.delete(id);

const p={id:'test-project',name:'Sample <img src=x onerror=alert(1)>',revision:1,demo:true,media:null,assets:{},speakers:[{id:'s1',name:'Speaker 01',color:'#8b8aff',voice:{},reference:null}],dialogue:[{id:'l1',start:1,end:3,speaker:'s1',source:'こんにちは',translation:'Hello there.',subtitle:'Hello.',audio:null}],models:{synthesis:{id:'piper',settings:{model:'',speaker_id:0}},translation:{id:'ollama',settings:{model:'qwen3:14b'}},separation:{id:'demucs',settings:{model:'htdemucs'}},transcription:{id:'faster-whisper',settings:{model:'large-v3'}},diarization:{id:'pyannote',settings:{model:''}}},settings:{audio_stream:null,video_stream:null,subtitle_stream:null,background_mode:'silence',background_gain:.8,dialogue_gain:1,fit_duration:true,output:'mkv'}};
let saved;
let jobs=[];
let nextJob=0;
let rejectJob='';let patchGate=null,patchFailure='';
const models=Object.entries(p.models).map(([capability,s])=>({id:s.id,label:s.id,capability,available:false,description:'Test worker metadata',fields:[]}));
globalThis.fetch=async(path,init={})=>{
  let value;
  if(path==='/api/separation/models')value={models:[{id:'mdx-inst-hq3',label:'MDX fixture',installed:false,size:66759214,architecture:'MDX',fields:[{key:'batch_size',label:'Batch size',type:'number',default:1,min:1,max:16,integer:true}]}]};
  else if(path==='/api/health')value={version:'0.2.5',local:true,gpu:null};
  else if(path==='/api/models')value=models;
  else if(path==='/api/projects'&&init.method==='POST')value=p;
  else if(path==='/api/projects')value=[];
  else if(path==='/api/projects/test-project'&&init.method==='PATCH'){const snapshot=JSON.parse(init.body);if(patchGate)await patchGate;if(patchFailure)return {ok:false,json:async()=>({detail:patchFailure})};saved=snapshot;Object.assign(p,saved,{revision:saved.revision+1});value=p;}
  else if(path==='/api/projects/test-project')value=p;
  else if(path==='/api/projects/test-project/jobs'&&init.method==='POST'){
    if(rejectJob)return {ok:false,json:async()=>({detail:rejectJob})};
    const submitted={id:'job-'+(++nextJob),kind:JSON.parse(init.body).kind,status:'queued',progress:0,message:'Waiting for worker',result:{}};
    jobs.unshift(submitted);value={id:submitted.id};
  }
  else if(path==='/api/projects/test-project/jobs')value=jobs;
  else throw new Error('Unexpected request '+path);
  return {ok:true,json:async()=>structuredClone(value)};
};
await import('./src/app.js');
// Let initialization's promise chain finish.
for(let i=0;i<15;i++)await Promise.resolve();
assert.ok(root.innerHTML.includes('DUBBING PIPELINE'));
assert.ok(root.innerHTML.includes('PROGRAM MONITOR'));
assert.ok(root.innerHTML.includes('data-panel-resize="left"'));
assert.ok(root.innerHTML.includes('data-panel-resize="right"'));
assert.ok(root.innerHTML.includes('data-panel-resize="timeline"'));
assert.ok(root.innerHTML.includes('data-panel-resize="dialogue"'));
assert.ok(root.innerHTML.includes('Sample &lt;img'));
assert.ok(!root.innerHTML.includes('<img src=x onerror='));
assert.ok(nodes.get('.timeline-content').innerHTML.includes('Hello there.'));

const input={dataset:{field:'line.translation'},type:'textarea',value:'An edited English line.',closest(){return null;}};
listeners.input({target:input});
const click=async(act,data={})=>{
  const el={dataset:{act,...data},disabled:false};
  await listeners.click({target:{closest(selector){return selector==='[data-act]'?el:null;}}});
};
await click('save');
assert.equal(saved.dialogue[0].translation,'An edited English line.');
assert.ok(root.innerHTML.includes('Saved'));
await click('add-speaker');
assert.ok(root.innerHTML.includes('Speaker 02'));
assert.ok(root.innerHTML.includes('SPEAKER VOICE'));
await click('models');
assert.ok(nodes.get('#modal-root').innerHTML.includes('Voice conversion · optional'));
await click('close-modal');
await click('tab',{tab:'Dialogue'});
assert.ok(root.innerHTML.includes('An edited English line.'));

// Exercise the user-visible queue and polling path, including an image-subtitle retry.
await click('save');
p.demo=false;p.media={name:'Episode.mkv',duration:18,streams:[{index:0,type:'video',codec:'h264',language:'und'},{index:1,type:'audio',codec:'aac',language:'jpn'},{index:2,type:'subtitle',codec:'hdmv_pgs_subtitle',language:'eng'}]};
p.settings={...p.settings,video_stream:0,audio_stream:1,subtitle_stream:2};
await click('open-project',{id:p.id});
assert.ok(root.innerHTML.includes('Prepare without image subtitles'));
await click('prepare-no-subtitles');
assert.equal(saved.settings.subtitle_stream,null);
assert.ok(root.innerHTML.includes('Prepare queued'));
assert.ok(root.innerHTML.includes('jobs-list'));
assert.ok(!root.innerHTML.includes('Source is ready'));
jobs[0]={...jobs[0],status:'running',progress:.51,message:'Creating browser-compatible preview · 32% processed'};
await timers[1]();
assert.ok(root.innerHTML.includes('Preparing media · 51%'));
assert.ok(root.innerHTML.includes('32% processed'));
assert.ok(root.innerHTML.includes('m6 6 12 12M6 18 18 6'));
jobs[0]={...jobs[0],status:'failed',message:'Selected subtitle track contains images. <img src=x>'};
await timers[1]();
assert.ok(root.innerHTML.includes('Prepare failed'));
assert.ok(nodes.get('#toast-root').innerHTML.includes('Selected subtitle track contains images. &lt;img'));
assert.ok(!nodes.get('#toast-root').innerHTML.includes('<img src=x>'));
await click('dismiss-error');
await click('job',{kind:'prepare'});
jobs[0]={...jobs[0],status:'completed',progress:1,message:'Complete'};
p.assets={preview:'preview.mp4',original_audio:'original.wav'};p.revision++;
await timers[1]();
assert.ok(root.innerHTML.includes('preview.mp4'));
assert.ok(!root.innerHTML.includes('Prepare failed'));
assert.ok(nodes.get('#toast-root').innerHTML.includes('Prepare complete'));
rejectJob='Select at least one source track in the Clip inspector before Prepare.';
await click('job',{kind:'prepare'});
assert.ok(nodes.get('#toast-root').innerHTML.includes(rejectJob));
// Successful completion changes monitor mode exactly once; failure does not.
rejectJob='';await click('original');await click('job',{kind:'synthesize'});
jobs[0]={...jobs[0],status:'failed',message:'Test-only worker failure'};await timers[1]();
assert.ok(root.innerHTML.includes('data-act="original" class="active"'));
await click('dismiss-error');await click('job',{kind:'synthesize'});
jobs[0]={...jobs[0],status:'completed',progress:1,message:'Complete'};await timers[1]();
assert.ok(root.innerHTML.includes('data-act="dub" class="active"'));
assert.ok(nodes.get('#toast-root').innerHTML.includes('English mix selected'));
await click('original');await timers[1]();assert.ok(root.innerHTML.includes('data-act="original" class="active"'));
await click('tab',{tab:'Timeline'});await click('select-line',{id:'l1'});
// An overlong take warns but allows rendering and offers a reversible, explicit fix.
p.dialogue[0].audio={asset:'timing.wav',duration:3,kind:'imported'};p.revision++;
await click('open-project',{id:p.id});await click('export');
assert.ok(nodes.get('#modal-root').innerHTML.includes('Line 1 · Speaker 01'));
assert.ok(nodes.get('#modal-root').innerHTML.includes('Review clip'));
assert.ok(nodes.get('#modal-root').innerHTML.includes('Extend slot to 3.00s'));
assert.doesNotMatch(nodes.get('#modal-root').innerHTML,/data-act="render"[^>]* disabled/);
assert.ok(nodes.get('#modal-root').innerHTML.includes('Recommended: fix audio timing'));
assert.ok(nodes.get('#modal-root').innerHTML.includes('Render anyway'));
await click('render');assert.equal(jobs[0].kind,'export');assert.equal(jobs[0].status,'queued');
jobs[0]={...jobs[0],status:'completed',progress:1,message:'Complete with timing warnings',result:{warnings:['Line 1 exceeds its slot <img src=x>'],export:'dub.mkv'}};
await timers[1]();assert.ok(nodes.get('#toast-root').innerHTML.includes('Export complete with timing warnings'));
assert.ok(root.innerHTML.includes('Timing warnings (1)'));assert.ok(root.innerHTML.includes('&lt;img src=x&gt;'));
await click('export');
await click('review-timing',{id:'l1'});assert.equal(nodes.get('#modal-root').innerHTML,'');
assert.ok(root.innerHTML.includes('Extend slot to 3.00s'));
await click('fix-timing',{id:'l1'});await click('save');
assert.equal(p.dialogue[0].end,4);assert.equal(p.dialogue[0].source_end,3);
assert.equal(p.dialogue[0].audio.asset,'timing.wav');
await click('export');assert.ok(!nodes.get('#modal-root').innerHTML.includes('export-issue'));
await click('close-modal');await click('undo');await click('save');
assert.equal(p.dialogue[0].end,3);assert.equal(p.dialogue[0].audio.asset,'timing.wav');
// Missing takes remain a separate requirement; timing alone does not block.
await click('add-line');await click('export');
assert.match(nodes.get('#modal-root').innerHTML,/data-act="render"[^>]* disabled/);
assert.ok(nodes.get('#modal-root').innerHTML.includes('needs replacement audio'));
await click('close-modal');await click('undo');await click('save');
await click('select-line',{id:'l1'});
const press=(key,target={dataset:{},closest(){return null;}})=>{let prevented=false;keydown({key,target,preventDefault(){prevented=true;}});return prevented;};
assert.equal(press('Delete',{dataset:{},closest(sel){return sel.includes('input,textarea')?{}:null;}}),false);
assert.equal(press('Backspace',{dataset:{},isContentEditable:true,closest(){return null;}}),false);
assert.equal(press('Delete'),true);assert.ok(root.innerHTML.includes('add your first line'));await click('save');assert.equal(p.dialogue.length,0);
await click('undo');await click('save');assert.equal(p.dialogue.length,1);
assert.equal(press('Backspace'),true);await click('undo');await click('save');
await click('select-line',{id:'l1'});
const change=text=>listeners.input({...{target:{dataset:{field:'line.translation'},type:'textarea',value:text,closest(){return null;}}}});
const autosave=async()=>{const entry=[...delayed].find(([,v])=>v.ms===1200);assert(entry,'Autosave was not scheduled');delayed.delete(entry[0]);await entry[1].fn();};
change('Autosaved text.');await autosave();assert.equal(p.dialogue[0].translation,'Autosaved text.');
let release;patchGate=new Promise(resolve=>{release=resolve;});change('Snapshot before more typing.');const inFlight=autosave();
for(let i=0;i<4;i++)await Promise.resolve();change('Newer text entered while saving.');release();await inFlight;patchGate=null;
assert.equal(p.dialogue[0].translation,'Snapshot before more typing.');await autosave();assert.equal(p.dialogue[0].translation,'Newer text entered while saving.');
patchFailure='Test-only disk error';change('Keep this edit if saving fails.');await autosave();assert.ok(nodes.get('#save-status').textContent.includes('changes retained'));
assert.notEqual(p.dialogue[0].translation,'Keep this edit if saving fails.');patchFailure='';await click('save');assert.equal(p.dialogue[0].translation,'Keep this edit if saving fails.');
listeners.input({target:{dataset:{field:'autosave'},type:'checkbox',checked:false}});change('Manual-only edit.');assert(![...delayed.values()].some(v=>v.ms===1200));await click('save');
// The pipeline button opens a replaceable separation panel instead of queuing full inference.
models.push({id:'audio-separator',capability:'separation',available:false,label:'UVR fixture',fields:[{key:'model',default:'mdx-inst-hq3'},{key:'device',default:'cuda'}]});
await click('refresh-models');await click('job',{kind:'separate'});
assert.ok(nodes.get('#modal-root').innerHTML.includes('Separate dialogue and background.'));
assert.ok(nodes.get('#modal-root').innerHTML.includes('Saved results'));
listeners.input({target:{dataset:{field:'adapter.separation'},type:'select',value:'audio-separator',closest(){return null;}}});
assert.ok(nodes.get('#modal-root').innerHTML.includes('Install-Separation.cmd'));
assert.match(nodes.get('#modal-root').innerHTML,/data-act="separation-preview"[^>]* disabled/);
listeners.input({target:{dataset:{field:'model.separation.model'},type:'select',value:'mdx-inst-hq3',closest(){return null;}}});
await click('separation-selection');
assert.ok(nodes.get('#modal-root').innerHTML.includes('data-separation-range="start"'));
await click('save');assert.equal(saved.models.separation.settings.batch_size,1);
await click('close-modal');
// Explicit saved-take approval remains visible even when audio is ready.
p.dialogue[0].audio={asset:'approved.wav',kind:'generated',duration:1,accepted_signature:'fixture'};
p.dialogue[0].warning='Saved take selected for changed text/voice. Listen before exporting.';
p.revision++;await click('open-project',{id:p.id});await click('timeline-tab');
assert.ok(root.innerHTML.includes('Saved take selected for changed text/voice. Listen before exporting.'));
console.log('UI checks passed: completion mode/toast, keyboard deletion/undo, protected typing, debounced autosave, in-flight edits, save failure recovery, and existing editor/queue flows.');
