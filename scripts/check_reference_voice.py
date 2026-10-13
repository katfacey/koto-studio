"""Exercise real XTTS weights and conditioning using a real Piper speech reference."""
import array
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import wave
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from koto.runtime import runtime_environment


def main():
    with tempfile.TemporaryDirectory(prefix='KOTO reference voice ') as tmp:
        work=Path(tmp)
        def generate(adapter,text,reference=None):
            out=work/adapter;out.mkdir()
            python=ROOT/'.workers'/adapter/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
            settings={'model':str(ROOT/'runtime/models/piper/en_US-lessac-medium.onnx')} if adapter=='piper' else {'model':str(ROOT/'runtime/models/xtts'),'device':'cpu'}
            req,res=out/'request.json',out/'result.json'
            req.write_text(json.dumps({'adapter':adapter,'text':text,'settings':settings,'reference':reference,'output_dir':str(out)}),encoding='utf-8')
            env=runtime_environment(python=python);env['OMP_NUM_THREADS']='2';env['MKL_NUM_THREADS']='2'
            subprocess.run([str(python),str(ROOT/'backend/koto/worker.py'),str(req),str(res)],cwd=ROOT,env=env,check=True,timeout=600)
            return json.loads(res.read_text(encoding='utf-8'))['audio']
        reference=generate('piper',"The rain has stopped. Let's wait for the next train. We can walk home together.")
        path=generate('xtts','The next train will arrive soon.',reference)
        with wave.open(path,'rb') as audio:
            duration=audio.getnframes()/audio.getframerate()
            assert 1<duration<30, f'Unexpected XTTS duration {duration}'
            samples=array.array('h',audio.readframes(audio.getnframes()))
            assert max(map(abs,samples))>100,'XTTS output is silent'
        print(f'Real XTTS reference-conditioned worker synthesized {duration:.2f}s of non-silent English on CPU. Voice similarity and RTX 5090 inference require target-machine listening checks.')


if __name__=='__main__':main()
