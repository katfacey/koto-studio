import assert from 'node:assert/strict';
import {createComparisonPlayer,separationPanel} from './src/separation-panel.js';
const audios=[];let state;let paused=0;let errors=[];
function makeAudio(src){const listeners={};const a={src,currentTime:0,duration:2,paused:true,addEventListener(name,fn){listeners[name]=fn;},fire(name){listeners[name]?.();},pause(){this.paused=true;},async play(){this.paused=false;}};audios.push(a);return a;}
const player=createComparisonPlayer({url:p=>p,makeAudio,onError:e=>errors.push(e),onUpdate:s=>state=s,pauseMonitor:()=>paused++});
const record={id:'preview',assets:{original:'o.wav',vocals:'v.wav',background:'b.wav'}};
player.load(record,'original');audios[0].fire('loadedmetadata');
player.toggle(record);await Promise.resolve();assert.equal(state.playing,true);
audios[0].currentTime=.75;audios[0].fire('timeupdate');
player.load(record,'vocals');audios[1].fire('loadedmetadata');await Promise.resolve();
assert.equal(audios[1].currentTime,.75);assert.equal(state.playing,true);assert.equal(audios[0].paused,true);
audios[0].fire('ended');assert.equal(state.playing,true);
player.load({...record,id:'other'},'background');audios[2].fire('loadedmetadata');assert.equal(audios[2].currentTime,0);assert.equal(state.playing,false);
player.stop();assert.equal(state.time,0);assert.equal(state.playing,false);
assert.equal(errors.length,0);assert.ok(paused>=2);
// An obsolete play promise cannot mark a newly selected result as playing.
let resolve;player.load(record);audios.at(-1).play=()=>new Promise(r=>resolve=r);player.toggle(record);player.stop();resolve();await Promise.resolve();assert.equal(state.playing,false);
const html=separationPanel({p:{assets:{original_audio:'o.wav'},models:{separation:{id:'custom',settings:{model:'<img>'}}},separations:[{...record,created:0,preview:true,start:0,end:2,duration:2,source_asset:'o.wav',selection:{settings:{model:'<img>'}}}],dialogue:[],media:{duration:2}},adapters:[{id:'custom',capability:'separation',custom:true,available:true,fields:[]}],catalog:null,state:{start:0,end:2},busy:false,jobs:[],player:player.state});
assert.ok(html.includes('&lt;img&gt;'));assert.ok(!html.includes('<img>'));assert.ok(!html.includes('data-act="activate-separation"'));
console.log('Separation checks passed: aligned stem switching, preview-only selection, escaped history, playback stop and obsolete promise protection.');
