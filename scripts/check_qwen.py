"""Real local Qwen Base/VoiceDesign inference with system-only PATH."""
import array
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import wave
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from koto.runtime import runtime_environment


def main():
    with tempfile.TemporaryDirectory(prefix='KOTO Qwen voices ') as temp:
        work=Path(temp)
        def generate(adapter,text,reference=None,reference_text='',delivery='',lines=None):
            out=work/(adapter+str(len(list(work.iterdir()))));out.mkdir()
            envname='piper' if adapter=='piper' else 'qwen'
            python=ROOT/'.workers'/envname/'Scripts/python.exe'
            model='runtime/models/piper/en_US-lessac-medium.onnx' if adapter=='piper' else 'runtime/models/qwen/'+('design' if adapter=='qwen-design' else 'base')
            request={'adapter':adapter,'text':text,'reference':reference,'reference_text':reference_text,'delivery':delivery,'seed':31,'settings':{'model':model,'device':'cpu'},'output_dir':str(out)}
            if lines:request['lines']=lines
            req,res=out/'request.json',out/'result.json';req.write_text(json.dumps(request),encoding='utf-8')
            env=runtime_environment(python=python);env['OMP_NUM_THREADS']='2';env['MKL_NUM_THREADS']='2'
            subprocess.run([str(python),str(ROOT/'backend/koto/worker.py'),str(req),str(res)],env=env,cwd=ROOT,check=True,timeout=900)
            result=json.loads(res.read_text(encoding='utf-8'))
            paths=[t['audio'] for t in result['takes']] if 'takes' in result else [result['audio']]
            for path in paths:
                with wave.open(path) as wav:
                    duration=wav.getnframes()/wav.getframerate()
                    assert .2<duration<180,duration
                    samples=array.array('h',wav.readframes(wav.getnframes()));assert max(map(abs,samples))>50
            return paths
        text='The rain has stopped. Let us wait for the next train.'
        reference=generate('piper',text)[0]
        takes=generate('qwen','',reference,text,lines=[{'id':'a','text':'Hello there.','seed':11},{'id':'b','text':'Come with me.','seed':12}])
        assert len(takes)==2
        designed=generate('qwen-design','Hello there.',delivery='An adult woman with a warm clear voice and calm conversational delivery.')[0]
        generate('qwen','Good morning.',designed,'Hello there.')
        print('Real local Qwen Base batch, VoiceDesign audition, and design-then-clone passed on Windows CPU. No GPU performance or voice-similarity claim.')


if __name__=='__main__':main()
