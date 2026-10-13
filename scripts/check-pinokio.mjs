import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const app=require('../pinokio.js');
const exists=path=>['runtime/installed.json','.venv/Scripts/python.exe'].includes(path);
const info={exists,running:()=>false};
const empty=await app.menu({platform:'win32'},{exists:()=>false,running:()=>false});
assert.equal(empty[0].href,'install.js');
assert.ok(empty[0].text.includes('Python + FFmpeg'));
const installed=await app.menu({platform:'win32'},info);
assert.equal(installed[0].href,'start.js');
assert.ok(installed.some(item=>item.href==='install-translation.js'));
const active=await app.menu({platform:'win32'},{...info,running:p=>p==='install-whisper.js'});
assert.equal(active[0].href,'install-whisper.js');
const running=await app.menu({platform:'win32'},{...info,running:p=>p==='start.js'});
assert.equal(running[0].href,'http://127.0.0.1:8765');
for(const [file,profile] of [['install.js','core'],['install-audio.js','audio'],['install-whisper.js','whisper'],['install-piper.js','piper'],['install-xtts.js','xtts'],['install-translation.js','translation'],['install-models.js','models'],['install-all.js','all']]){
  const config=require('../'+file);
  const command=config.run[0].params.message;
  assert.ok(command.startsWith('"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"'));
  assert.ok(command.endsWith('-Profile '+profile));
  assert.equal(config.run[0].params.venv,undefined);
}
assert.equal(require('../start.js').run[0].params.message,'".venv\\Scripts\\python.exe" "scripts\\serve.py"');
console.log('Pinokio menu and all eight managed installer entry points passed.');
