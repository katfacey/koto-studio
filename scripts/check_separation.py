"""Real Windows/CPU separation via queued downloads and the public project API.

The fixture mixes real Piper speech with a synthetic tone. This proves model
loading, stems, timing, history and offline reuse, not dialogue separation quality.
"""
import asyncio
import array
import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from koto.app import create_app
from koto.media import binary
from koto.runtime import runtime_environment


async def main():
    import httpx
    os.environ['OMP_NUM_THREADS']='2'
    os.environ['MKL_NUM_THREADS']='2'
    with tempfile.TemporaryDirectory(prefix='KOTO separation validation ') as temp:
        directory=Path(temp)
        req,res=directory/'request.json',directory/'result.json'
        piper=ROOT/'.workers/piper/Scripts/python.exe'
        req.write_text(json.dumps({'adapter':'piper','text':"The rain has stopped. Let's wait for the next train.",'settings':{'model':str(ROOT/'runtime/models/piper/en_US-lessac-medium.onnx')},'output_dir':str(directory)}),encoding='utf-8')
        subprocess.run([str(piper),str(ROOT/'backend/koto/worker.py'),str(req),str(res)],env=runtime_environment(python=piper),check=True,timeout=120)
        speech=json.loads(res.read_text())['audio']
        video=directory/'speech-and-tone.mkv'
        subprocess.run([binary('ffmpeg'),'-y','-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=24:d=4','-i',speech,'-f','lavfi','-i','sine=frequency=700:sample_rate=48000:duration=4','-filter_complex','[1:a]apad,atrim=duration=4[s];[s][2:a]amix=inputs=2:normalize=0[a]','-map','0:v','-map','[a]','-c:v','libx264','-preset','ultrafast','-c:a','pcm_s16le','-t','4',str(video)],check=True)
        app=create_app(directory/'data')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            p=(await client.post('/api/projects',json={'name':'Real separator validation'})).json();pid=p['id']
            response=await client.post(f'/api/projects/{pid}/media',files={'file':(video.name,video.read_bytes())});assert response.status_code==200,response.text
            async def job(kind,options=None):
                response=await client.post(f'/api/projects/{pid}/jobs',json={'kind':kind,'options':options or {}});assert response.status_code==200,response.text
                jid=response.json()['id']
                for _ in range(12000):
                    jobs=(await client.get(f'/api/projects/{pid}/jobs')).json();entry=next(j for j in jobs if j['id']==jid)
                    if entry['status'] not in ('queued','running'):
                        assert entry['status']=='completed',entry['message']
                        return entry
                    await asyncio.sleep(.05)
                raise AssertionError('Real separation timed out')
            try:
                await job('prepare')
                original=(await client.get(f'/api/projects/{pid}')).json()['assets']['original_audio']
                checks=[]
                models=(await client.get('/api/separation/models')).json()['models']
                for model in models:
                    download=await job('download_separation_model',{'model_id':model['id']})
                    print('MODEL_SHA256',model['id'],download['result']['sha256'],flush=True)
                    project=(await client.get(f'/api/projects/{pid}')).json()
                    response=await client.patch(f'/api/projects/{pid}',json={'revision':project['revision'],'models':{**project['models'],'separation':{'id':'audio-separator','settings':{'model':model['id'],'device':'cpu'}}}});assert response.status_code==200,response.text
                    preview=await job('separate',{'preview':True,'start':.5,'end':2.5})
                    project=(await client.get(f'/api/projects/{pid}')).json()
                    assert project['assets']['original_audio']==original and 'vocals' not in project['assets']
                    record=project['separations'][-1]
                    peaks={}
                    for key in ('vocals','background'):
                        path=app.state.store.asset(pid,record['assets'][key])
                        with wave.open(str(path)) as wav:
                            assert (wav.getframerate(),wav.getnchannels(),wav.getsampwidth())==(48000,2,2)
                            assert abs(wav.getnframes()/wav.getframerate()-2)<.001
                            samples=array.array('h',wav.readframes(wav.getnframes()));peaks[key]=max(map(abs,samples))
                    assert all(v>0 for v in peaks.values()),peaks
                    vocal=app.state.store.asset(pid,record['assets']['vocals']).read_bytes()
                    background=app.state.store.asset(pid,record['assets']['background']).read_bytes()
                    assert vocal!=background,'Model returned identical stems'
                    checks.append({'model':model['id'],'duration':record['duration'],'peaks':peaks,'sha256':download['result']['sha256']})
                project=(await client.get(f'/api/projects/{pid}')).json()
                response=await client.patch(f'/api/projects/{pid}',json={'revision':project['revision'],'models':{**project['models'],'separation':{'id':'audio-separator','settings':{'model':models[0]['id'],'device':'cpu'}}}});assert response.status_code==200,response.text
                full=await job('separate')
                project=(await client.get(f'/api/projects/{pid}')).json();assert project['active_separation']==full['id']
                assert len(project['separations'])==4
                output=ROOT/'runtime/validation';output.mkdir(parents=True,exist_ok=True)
                (output/'separation-validation.json').write_text(json.dumps({'models':checks,'full_result_applied':True,'preview_history_preserved':True},indent=2))
                print('Real model/CPU API checks passed for MDX, VR and BS-RoFormer; target-GPU and listening quality need Windows/NVIDIA testing.',flush=True)
            finally:
                app.state.jobs.closed.set()
                while app.state.jobs.thread.is_alive():await asyncio.sleep(.05)


if __name__=='__main__':asyncio.run(main())
