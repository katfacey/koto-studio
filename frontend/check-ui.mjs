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
globalThis.document={querySelector(){return root;},addEventListener(){}};
globalThis.window={addEventListener(){}};
globalThis.localStorage={getItem(){return null;},setItem(){}};
if(!globalThis.crypto)Object.defineProperty(globalThis,'crypto',{value:webcrypto});
const timers=[];
globalThis.setInterval=(fn)=>{timers.push(fn);return timers.length;};
globalThis.setTimeout=()=>0;globalThis.clearTimeout=()=>{};

const p={id:'test-project',name:'Sample <img src=x onerror=alert(1)>',revision:1,demo:true,media:null,assets:{},speakers:[{id:'s1',name:'Speaker 01',color:'#8b8aff',voice:{},reference:null}],dialogue:[{id:'l1',start:1,end:3,speaker:'s1',source:'こんにちは',translation:'Hello there.',subtitle:'Hello.',audio:null}],models:{synthesis:{id:'piper',settings:{model:'',speaker_id:0}},translation:{id:'ollama',settings:{model:'qwen3:14b'}},separation:{id:'demucs',settings:{model:'htdemucs'}},transcription:{id:'faster-whisper',settings:{model:'large-v3'}},diarization:{id:'pyannote',settings:{model:''}}},settings:{audio_stream:null,video_stream:null,subtitle_stream:null,background_mode:'silence',background_gain:.8,dialogue_gain:1,fit_duration:true,output:'mkv'}};
let saved;
let jobs=[];
let nextJob=0;
let rejectJob='';
const models=Object.entries(p.models).map(([capability,s])=>({id:s.id,label:s.id,capability,available:false,description:'Test worker metadata',fields:[]}));
globalThis.fetch=async(path,init={})=>{
  let value;
  if(path==='/api/health')value={version:'0.2.0',local:true,gpu:null};
  else if(path==='/api/models')value=models;
  else if(path==='/api/projects'&&init.method==='POST')value=p;
  else if(path==='/api/projects')value=[];
  else if(path==='/api/projects/test-project'&&init.method==='PATCH'){saved=JSON.parse(init.body);Object.assign(p,saved,{revision:saved.revision+1});value=p;}
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
console.log('UI checks passed: editor/actions, escaped text, Prepare image-subtitle recovery, queued/running/failed/completed feedback, and immediate validation errors.');
