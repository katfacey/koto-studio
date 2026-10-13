import assert from 'node:assert/strict';
import {clampLayout,createPanelLayout,panelResizer} from './src/layout.js';

for(const size of [{width:1040,height:500},{width:1400,height:800},{width:1920,height:980}]){
  for(const requested of [{},{left:9999,right:9999,timeline:9999,dialogue:9999},{left:-50,right:-50,timeline:-50},{left:'invalid',right:NaN,timeline:Infinity}]){
    const v=clampLayout(size,requested);
    assert.ok(v.left>=180&&v.right>=210&&size.width-v.left-v.right>=420);
    assert.ok(v.timeline>=180&&size.height-v.timeline>=320);
  }
}
const saved=new Map(),styles=new Map();
globalThis.localStorage={getItem:key=>saved.get(key)??null,setItem:(key,value)=>saved.set(key,value)};
globalThis.getComputedStyle=()=>({getPropertyValue:()=>''});
const workspace={getBoundingClientRect:()=>({width:1400,height:800}),style:{setProperty:(key,value)=>styles.set(key,value),removeProperty:key=>styles.delete(key)}};
const handles=Object.fromEntries(['left','right','timeline','dialogue'].map(key=>[key,{dataset:{panelResize:key},setAttribute(){},setPointerCapture(){},events:new Map(),addEventListener(type,fn){this.events.set(type,fn);},removeEventListener(type){this.events.delete(type);}}]));
const root={querySelector:key=>key==='.workspace'?workspace:key==='.dialogue-editor'?{offsetHeight:190}:null,querySelectorAll:()=>Object.values(handles)};
let changed=0;
const layout=createPanelLayout(root,()=>changed++);layout.refresh();
const event=(key,props={})=>({target:{closest:()=>handles[key]},preventDefault(){},button:0,pointerId:1,clientX:236,clientY:500,...props});
assert.equal(styles.get('--panel-left'),'236px');
assert.equal(layout.start(event('left')),true);
handles.left.events.get('pointermove')({clientX:350,clientY:500});
assert.equal(styles.get('--panel-left'),'350px');
assert.equal(layout.dragging,true);
handles.left.events.get('pointerup')();
assert.equal(layout.dragging,false);
assert.equal(JSON.parse(saved.get('koto-panel-layout-v1')).left,350);
createPanelLayout(root,()=>{}).refresh();
assert.equal(styles.get('--panel-left'),'350px');
layout.keydown(event('right',{key:'ArrowLeft',shiftKey:false}));
assert.equal(styles.get('--panel-right'),'268px');
layout.reset(event('left'));
assert.equal(styles.get('--panel-left'),'236px');
assert.ok(changed>=3);
assert.ok(panelResizer('timeline').includes('aria-orientation="horizontal"'));
saved.set('koto-panel-layout-v1','broken JSON');
createPanelLayout(root,()=>{}).refresh();
assert.equal(styles.get('--panel-right'),'258px');
console.log('Panel checks passed: bounds, pointer resizing, saved sizes, keyboard access, reset, and invalid preferences.');
