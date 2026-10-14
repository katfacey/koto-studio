"""Real FFmpeg + HTTP workflow checks. No GPU model inference is mocked as production output."""
import asyncio
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from koto.app import create_app
from koto.jobs import signature
from koto.media import binary, parse_subtitles, probe
from koto.store import Store


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            ffmpeg = binary("ffmpeg")
        except RuntimeError:
            raise unittest.SkipTest("FFmpeg is required for integration tests")
        cls.fixture = tempfile.TemporaryDirectory()
        cls.files = Path(cls.fixture.name)
        cls.sub = cls.files/"source.srt"
        cls.sub.write_text("1\n00:00:00,500 --> 00:00:01,500\nHello there.\n\n2\n00:00:02,000 --> 00:00:03,500\nLet's catch the train.\n",encoding="utf-8")
        cls.video = cls.files/"source.mkv"
        subprocess.run([ffmpeg,"-y","-v","error","-f","lavfi","-i","testsrc2=size=160x90:rate=24:duration=4","-f","lavfi","-i","sine=frequency=180:sample_rate=48000:duration=4","-i",str(cls.sub),"-map","0:v","-map","1:a","-map","2:s","-c:v","libx264","-preset","ultrafast","-c:a","pcm_s16le","-ac","2","-c:s","srt","-metadata:s:a:0","language=jpn","-metadata:s:s:0","language=eng","-t","4",str(cls.video)],check=True)
        cls.take = cls.files/"voice.wav"
        subprocess.run([ffmpeg,"-y","-v","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=0.8","-ac","2",str(cls.take)],check=True)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.temp.name))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url="http://testserver")
        # This sandbox suppresses asyncio's socket wake-up from other threads.
        # A heartbeat keeps the genuine threadpool and HTTP path running unchanged.
        async def heartbeat():
            while True:
                await asyncio.sleep(.01)
        self.beat = asyncio.create_task(heartbeat())
        self.p = (await self.client.post("/api/projects",json={"name":"Integration"})).json()
        self.pid = self.p["id"]

    async def asyncTearDown(self):
        self.app.state.jobs.closed.set()
        while self.app.state.jobs.thread.is_alive():
            await asyncio.sleep(.02)
        await self.client.aclose()
        self.beat.cancel()
        self.temp.cleanup()

    async def upload(self,route,path,fields=None):
        r = await self.client.post(f"/api/projects/{self.pid}/{route}",files={"file":(path.name,path.read_bytes())},data=fields)
        self.assertEqual(r.status_code,200,r.text)
        self.p = r.json()
        return self.p

    async def patch(self,**values):
        r = await self.client.patch(f"/api/projects/{self.pid}",json={"revision":self.p["revision"],**values})
        self.assertEqual(r.status_code,200,r.text)
        self.p = r.json()
        return self.p

    async def wait_job(self,jid,expected="completed"):
        for _ in range(400):
            jobs = (await self.client.get(f"/api/projects/{self.pid}/jobs")).json()
            job = next(j for j in jobs if j["id"]==jid)
            if job["status"] not in ("queued","running"):
                self.assertEqual(job["status"],expected,job["message"])
                self.p = (await self.client.get(f"/api/projects/{self.pid}")).json()
                return job
            await asyncio.sleep(.025)
        self.fail("Job timed out")

    async def run_job(self,kind):
        r = await self.client.post(f"/api/projects/{self.pid}/jobs",json={"kind":kind})
        self.assertEqual(r.status_code,200,r.text)
        return await self.wait_job(r.json()["id"])

    async def setup_separator_fixture(self, delay=0, video=None):
        await self.upload("media",video or self.video)
        await self.run_job("prepare")
        script=Path(self.temp.name)/"separator_fixture.py"
        script.write_text("import json,sys,shutil,time\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text())\ntime.sleep(r['settings'].get('delay',0))\nresult={}\nfor key in ('vocals','background'):\n p=Path(r['output_dir'])/(key+'.wav');shutil.copyfile(r['settings'].get('replacement') or r['audio'],p);result[key]=str(p)\nPath(sys.argv[2]).write_text(json.dumps(result))\n",encoding="utf-8")
        self.app.state.registry.adapters['separator-fixture']={'id':'separator-fixture','label':'Explicit test-only pass-through separator','capability':'separation','custom':True,'command':[sys.executable,str(script)]}
        await self.patch(models={**self.p['models'],'separation':{'id':'separator-fixture','settings':{'delay':delay}}})

    async def submit_separation(self,options=None,expected='completed'):
        response=await self.client.post(f'/api/projects/{self.pid}/jobs',json={'kind':'separate','options':options or {}})
        self.assertEqual(response.status_code,200,response.text)
        return await self.wait_job(response.json()['id'],expected)

    async def test_separation_preview_preserves_mix_full_history_switches_and_survives_reopen(self):
        await self.setup_separator_fixture()
        first=await self.submit_separation()
        active=self.p['active_separation']
        self.assertEqual(active,first['id'])
        stems={key:self.p['assets'][key] for key in ('vocals','background')}
        # A preview must preserve every downstream render asset, not just stems.
        self.p=self.app.state.store.update(self.pid,lambda p:{**p,'assets':{**p['assets'],'export':'saved-export.mkv'}})
        await self.patch(models={**self.p['models'],'separation':{'id':'separator-fixture','settings':{'delay':.01}}})
        self.assertEqual(self.p['assets']['export'],'saved-export.mkv')
        preview=await self.submit_separation({'preview':True,'start':1,'end':2.5})
        self.assertFalse(preview['result']['applied'])
        self.assertEqual(self.p['active_separation'],active)
        self.assertEqual(self.p['assets']['export'],'saved-export.mkv')
        self.assertEqual({key:self.p['assets'][key] for key in stems},stems)
        record=self.p['separations'][-1]
        for asset in record['assets'].values():
            path=self.app.state.store.asset(self.pid,asset)
            self.assertAlmostEqual(probe(path)['duration'],1.5,places=2)
            with wave.open(str(path)) as audio:
                self.assertEqual((audio.getframerate(),audio.getnchannels(),audio.getsampwidth()),(48000,2,2))
        rejected=await self.client.post(f'/api/projects/{self.pid}/separations/{preview["id"]}/activate',json={'revision':self.p['revision']})
        self.assertEqual(rejected.status_code,400)
        second=await self.submit_separation()
        self.assertEqual(self.p['active_separation'],second['id'])
        activated=await self.client.post(f'/api/projects/{self.pid}/separations/{active}/activate',json={'revision':self.p['revision']})
        self.assertEqual(activated.status_code,200,activated.text)
        self.p=activated.json()
        self.assertEqual(self.p['assets']['vocals'],stems['vocals'])
        stale_revision=await self.client.post(f'/api/projects/{self.pid}/separations/{second["id"]}/activate',json={'revision':self.p['revision']-1})
        self.assertEqual(stale_revision.status_code,409)
        reopened=Store(Path(self.temp.name)).get(self.pid)
        self.assertEqual(len(reopened['separations']),3)
        self.assertEqual(reopened['active_separation'],active)
        await self.patch(settings={**self.p['settings'],'audio_stream':None})
        stale=await self.client.post(f'/api/projects/{self.pid}/separations/{active}/activate',json={'revision':self.p['revision']})
        self.assertEqual(stale.status_code,400)
        self.assertIsNone(self.p['active_separation'])
        self.assertEqual(len(self.p['separations']),3)

    async def test_separation_bounds_bad_output_and_cancel_leave_history_unchanged(self):
        await self.setup_separator_fixture()
        for options in ({'preview':True,'start':-1,'end':2},{'preview':True,'start':1,'end':1},{'preview':True,'start':0,'end':5},{'preview':True,'start':True,'end':2},{'start':1}):
            response=await self.client.post(f'/api/projects/{self.pid}/jobs',json={'kind':'separate','options':options})
            self.assertEqual(response.status_code,400,response.text)
        await self.patch(models={**self.p['models'],'separation':{'id':'separator-fixture','settings':{'replacement':str(self.take)}}})
        failed=await self.submit_separation(expected='failed')
        self.assertIn('duration differs',failed['message'])
        self.assertEqual(self.p['separations'],[])
        await self.patch(models={**self.p['models'],'separation':{'id':'separator-fixture','settings':{'delay':2}}})
        response=await self.client.post(f'/api/projects/{self.pid}/jobs',json={'kind':'separate'})
        jid=response.json()['id']
        await asyncio.sleep(.2)
        await self.client.post(f'/api/jobs/{jid}/cancel')
        await self.wait_job(jid,'cancelled')
        self.assertEqual(self.p['separations'],[])
        self.assertNotIn('vocals',self.p['assets'])

    async def test_separation_pads_shorter_container_audio_without_shortening_video(self):
        short=Path(self.temp.name)/'short-audio.mkv'
        subprocess.run([binary('ffmpeg'),'-y','-v','error','-i',str(self.video),'-filter:a','atrim=duration=3.5','-c:v','copy','-c:a','pcm_s16le','-c:s','copy',str(short)],check=True)
        await self.setup_separator_fixture(video=short)
        original=self.app.state.store.asset(self.pid,self.p['assets']['original_audio'])
        self.assertAlmostEqual(probe(original)['duration'],3.5,places=2)
        full=await self.submit_separation()
        self.assertTrue(full['result']['applied'])
        for name in self.p['separations'][-1]['assets'].values():
            with wave.open(str(self.app.state.store.asset(self.pid,name))) as audio:
                self.assertAlmostEqual(audio.getnframes()/audio.getframerate(),4,places=2)
                audio.setpos(int(3.6*audio.getframerate()))
                self.assertEqual(set(audio.readframes(100)),{0})
        await self.submit_separation({'preview':True,'start':3,'end':self.p['media']['duration']})
        self.assertAlmostEqual(self.p['separations'][-1]['duration'],self.p['media']['duration']-3)
        await self.submit_separation({'preview':True,'start':3.6,'end':self.p['media']['duration']},expected='failed')

    async def test_separation_finishing_after_source_change_is_saved_without_applying(self):
        await self.setup_separator_fixture(delay=.6)
        response=await self.client.post(f'/api/projects/{self.pid}/jobs',json={'kind':'separate'})
        jid=response.json()['id']
        await asyncio.sleep(.15)
        blocked=await self.client.post(f'/api/projects/{self.pid}/separations/not-found/activate',json={})
        self.assertEqual(blocked.status_code,409)
        await self.patch(settings={**self.p['settings'],'audio_stream':None})
        completed=await self.wait_job(jid)
        self.assertFalse(completed['result']['applied'])
        self.assertNotIn('vocals',self.p['assets'])
        self.assertEqual(len(self.p['separations']),1)

    async def test_image_subtitles_are_not_auto_selected_and_prepare_errors_are_immediate(self):
        # Model image-subtitle metadata; media processing itself still uses real FFmpeg.
        metadata = probe(self.video)
        subtitle = next(s for s in metadata["streams"] if s["type"] == "subtitle")
        subtitle["codec"] = "hdmv_pgs_subtitle"
        with patch("koto.app.probe", return_value=metadata):
            await self.upload("media", self.video)
        self.assertIsNone(self.p["settings"]["subtitle_stream"])
        await self.patch(settings={**self.p["settings"], "subtitle_stream": subtitle["index"]})
        response = await self.client.post(f"/api/projects/{self.pid}/jobs", json={"kind": "prepare"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Set Subtitle track to None", response.json()["detail"])
        self.assertEqual(self.app.state.store.jobs(self.pid), [])
        await self.patch(settings={**self.p["settings"], "subtitle_stream": None, "audio_stream": None, "video_stream": None})
        response = await self.client.post(f"/api/projects/{self.pid}/jobs", json={"kind": "prepare"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Select at least one source track", response.json()["detail"])
        await self.patch(settings={**self.p["settings"], "video_stream": 0, "audio_stream": 1})
        runner = self.app.state.jobs
        with patch.object(runner, "progress", wraps=runner.progress) as progress:
            await self.run_job("prepare")
        self.assertIn("preview", self.p["assets"])
        self.assertIn("original_audio", self.p["assets"])
        self.assertNotIn("source_subtitles", self.p["assets"])
        self.assertTrue(any("preview ·" in call.args[2] and call.args[1] > .35 for call in progress.call_args_list))

    async def test_missing_diarization_weights_are_reported_before_queuing(self):
        await self.upload("media", self.video)
        models = dict(self.p["models"])
        models["diarization"] = {"id": "pyannote", "settings": {"model": str(Path(self.temp.name)/"missing.yaml"), "device": "cpu"}}
        await self.patch(models=models)
        response = await self.client.post(f"/api/projects/{self.pid}/jobs", json={"kind": "diarize"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Install-Diarization.cmd", response.json()["detail"])
        self.assertEqual(self.app.state.store.jobs(self.pid), [])

    async def test_import_prepare_manual_dub_export_and_reopen(self):
        await self.upload("media",self.video)
        self.assertEqual([s["type"] for s in self.p["media"]["streams"]],["video","audio","subtitle"])
        await self.run_job("prepare")
        self.assertTrue(self.p["assets"]["preview"])
        self.assertEqual(len(self.p["dialogue"]),2)
        await self.upload("subtitles",self.sub,{"language":"en"})
        self.assertEqual(self.p["dialogue"][0]["translation"],"Hello there.")
        for l in list(self.p["dialogue"]):
            await self.upload(f"dialogue/{l['id']}/audio",self.take)
        settings = dict(self.p["settings"],background_mode="silence")
        await self.patch(settings=settings)
        job = await self.run_job("export")
        target = self.app.state.store.asset(self.pid,job["result"]["export"])
        info = probe(target)
        self.assertAlmostEqual(info["duration"],4,delta=.08)
        self.assertEqual([s["type"] for s in info["streams"]],["video","audio","subtitle"])
        self.assertEqual(info["streams"][1]["language"],"eng")
        self.assertEqual(info["streams"][2]["language"],"eng")
        with wave.open(str(self.app.state.store.asset(self.pid,self.p["assets"]["dub_audio"])),"rb") as w:
            self.assertEqual(w.getnframes(),4*48000)
            self.assertEqual(set(w.readframes(int(.4*48000))),{0})
            w.setpos(int(.6*48000))
            self.assertNotEqual(set(w.readframes(2400)),{0})
            w.setpos(int(1.6*48000))
            self.assertEqual(set(w.readframes(2400)),{0})
        waveform = await self.client.get(f"/api/projects/{self.pid}/waveform/{self.p['assets']['original_audio']}")
        self.assertEqual(waveform.status_code,200)
        self.assertEqual(len(waveform.json()),360)
        self.assertGreater(max(waveform.json()),0)
        response = await self.client.get(f"/api/projects/{self.pid}/assets/{target.name}",headers={"Range":"bytes=0-99"})
        self.assertEqual(response.status_code,206)
        self.assertEqual(len(response.content),100)
        reopened = Store(Path(self.temp.name)).get(self.pid)
        self.assertEqual(reopened["dialogue"],self.p["dialogue"])
        self.assertTrue(reopened["assets"]["export"])
        await self.patch(settings={**self.p["settings"],"output":"mp4"})
        self.assertNotIn("export",self.p["assets"])
        mp4_job = await self.run_job("export")
        mp4_info = probe(self.app.state.store.asset(self.pid,mp4_job["result"]["export"]))
        self.assertAlmostEqual(mp4_info["duration"],4,delta=.08)
        self.assertEqual(mp4_info["streams"][0]["codec"],"h264")
        self.assertEqual(mp4_info["streams"][2]["codec"],"mov_text")

    async def test_track_mutes_black_video_and_hidden_subtitles_reach_actual_export(self):
        await self.upload("media", self.video)
        await self.run_job("prepare")
        await self.upload("subtitles", self.sub, {"language":"en"})
        await self.upload(f"dialogue/{self.p['dialogue'][0]['id']}/audio", self.take)
        self.p["speakers"].append({"id":"other", "name":"Other", "color":"#ff9900", "voice":{}, "muted":True})
        self.p["dialogue"][1]["speaker"] = "other"  # Missing take is allowed on a muted lane.
        await self.patch(speakers=self.p["speakers"], dialogue=self.p["dialogue"], settings={**self.p["settings"], "background_mode":"silence", "video_visible":False, "subtitles_visible":False})
        job = await self.run_job("export")
        target = self.app.state.store.asset(self.pid, job["result"]["export"])
        self.assertEqual([s["type"] for s in probe(target)["streams"]], ["video", "audio"])
        pixels = subprocess.run([binary("ffmpeg"),"-v","error","-i",str(target),"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"], capture_output=True, check=True).stdout
        self.assertEqual(set(pixels), {0})
        with wave.open(str(self.app.state.store.asset(self.pid,self.p["assets"]["dub_audio"])),"rb") as w:
            w.setpos(round(.6*48000)); self.assertNotEqual(set(w.readframes(2400)),{0})
            w.setpos(round(2.1*48000)); self.assertEqual(set(w.readframes(2400)),{0})
        self.p["speakers"][0]["muted"] = True
        await self.patch(speakers=self.p["speakers"], settings={**self.p["settings"], "background_mode":"original", "original_muted":True})
        await self.run_job("export")
        with wave.open(str(self.app.state.store.asset(self.pid,self.p["assets"]["dub_audio"])),"rb") as w:
            self.assertEqual(set(w.readframes(w.getnframes())), {0})
        # Muting the separated bed permits silence even if separation has not run.
        await self.patch(settings={**self.p["settings"], "background_mode":"separated", "background_muted":True})
        await self.run_job("export")
        await self.patch(settings={**self.p["settings"], "background_mode":"original", "original_muted":False})
        await self.run_job("export")
        with wave.open(str(self.app.state.store.asset(self.pid,self.p["assets"]["dub_audio"])),"rb") as w:
            self.assertNotEqual(set(w.readframes(2400)), {0})

    async def test_original_reference_extraction_synthesis_cache_and_uploaded_sample(self):
        await self.upload("media", self.video)
        await self.run_job("prepare")
        self.p["dialogue"] = [{"id":"voice-line", "speaker":"speaker-1", "start":1, "end":3, "source_start":0, "source_end":4, "source":"original", "translation":"English", "audio":None}]
        self.p["speakers"][0]["use_source_reference"] = True
        worker=Path(self.temp.name)/"reference_fixture.py"
        worker.write_text("import json,sys,wave,shutil\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text())\nwith wave.open(r['reference']) as w: assert w.getnframes()/w.getframerate() >= 3.9\np=Path(r['output_dir'])/'voice.wav'\nshutil.copyfile(r['settings']['fixture_audio'],p)\nPath(sys.argv[2]).write_text(json.dumps({'audio':str(p)}))\n", encoding="utf-8")
        self.app.state.registry.adapters["reference-fixture"]={"id":"reference-fixture", "capability":"synthesis", "custom":True, "supports_reference":True, "command":[sys.executable,str(worker)]}
        config = dict(self.p["models"], synthesis={"id":"reference-fixture", "settings":{"fixture_audio":str(self.take)}})
        await self.patch(speakers=self.p["speakers"],dialogue=self.p["dialogue"],models=config)
        await self.run_job("synthesize")
        ref = self.p["speakers"][0]["source_reference"]
        self.assertAlmostEqual(ref["duration"],4,delta=.02)
        self.assertTrue(self.p["dialogue"][0]["audio"])
        request = json.loads(next(self.app.state.store.project_dir(self.pid).glob("work_*/request.json")).read_text())
        self.assertEqual(request["reference"], str(self.app.state.store.asset(self.pid,ref["asset"])))
        self.p["dialogue"][0].update(start=1.5,end=3.5)
        await self.patch(dialogue=self.p["dialogue"])
        self.assertTrue(self.p["dialogue"][0]["audio"])  # Moving does not change the original voice.
        cached = await self.run_job("synthesize")
        self.assertEqual(cached["result"]["cached"],1)
        response = await self.client.post(f"/api/projects/{self.pid}/jobs",json={"kind":"reference", "options":{"speaker_id":"speaker-1"}})
        await self.wait_job(response.json()["id"])
        self.assertEqual(self.p["speakers"][0]["source_reference"]["asset"],ref["asset"])
        original = self.app.state.store.asset(self.pid,self.p["assets"]["original_audio"])
        await self.upload("speakers/speaker-1/reference",original)
        self.p["speakers"][0]["use_source_reference"] = False
        await self.patch(speakers=self.p["speakers"])
        self.assertIsNone(self.p["dialogue"][0]["audio"])
        await self.run_job("synthesize")
        requests=[json.loads(path.read_text()) for path in self.app.state.store.project_dir(self.pid).glob("work_*/request.json")]
        uploaded=str(self.app.state.store.asset(self.pid,self.p["speakers"][0]["reference"]))
        self.assertTrue(any(req["reference"]==uploaded for req in requests))
        self.assertEqual(self.p["speakers"][0]["source_reference"]["asset"],ref["asset"])

    async def test_chinese_source_subtitles_preserve_english_adaptation(self):
        await self.upload('media',self.video)
        await self.upload('subtitles',self.sub,{'language':'en'})
        original=[l['translation'] for l in self.p['dialogue']]
        source=Path(self.temp.name)/'chinese.srt'
        source.write_text('1\n00:00:00,500 --> 00:00:01,500\n在这里等候。\n\n2\n00:00:02,000 --> 00:00:03,500\n我们一起回家。\n',encoding='utf-8')
        await self.upload('subtitles',source,{'language':'zh'})
        self.assertEqual([l['translation'] for l in self.p['dialogue']],original)
        self.assertEqual(self.p['dialogue'][0]['source'],'在这里等候。')

    async def test_alternative_adaptations_run_only_for_requested_clip_and_do_not_replace_text(self):
        await self.upload("media",self.video)
        await self.upload("subtitles",self.sub,{"language":"en"})
        worker=Path(self.temp.name)/"adaptation_fixture.py"
        worker.write_text("import json,sys\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text())\nassert r['mode']=='alternatives' and r['line']['id']==r['settings']['line_id']\nassert r['target_seconds']==1 and r['approximate_word_budget']>0\nPath(sys.argv[2]).write_text(json.dumps({'alternatives':['Hello.','Hi there.','Hello, my friend.']}))\n",encoding="utf-8")
        lid=self.p['dialogue'][0]['id']
        self.app.state.registry.adapters['adaptation-fixture']={'id':'adaptation-fixture','capability':'translation','custom':True,'supports_alternatives':True,'command':[sys.executable,str(worker)]}
        models={**self.p['models'],'translation':{'id':'adaptation-fixture','settings':{'line_id':lid}}}
        await self.patch(models=models)
        before=[l['translation'] for l in self.p['dialogue']]
        r=await self.client.post(f"/api/projects/{self.pid}/jobs",json={'kind':'alternatives','options':{'line_id':lid}})
        self.assertEqual(r.status_code,200,r.text);await self.wait_job(r.json()['id'])
        self.assertEqual([l['translation'] for l in self.p['dialogue']],before)
        self.assertEqual(len(self.p['dialogue'][0]['alternatives']['suggestions']),3)
        self.assertNotIn('alternatives',self.p['dialogue'][1])
        self.assertGreater(self.p['dialogue'][0]['alternatives']['suggestions'][2]['estimated_seconds'],self.p['dialogue'][0]['alternatives']['suggestions'][0]['estimated_seconds'])

    async def test_manual_and_automatic_speed_apply_to_actual_audio_without_changing_take(self):
        await self.upload('media',self.video)
        await self.upload('subtitles',self.sub,{'language':'en'})
        self.p['dialogue']=self.p['dialogue'][:1]
        self.p['dialogue'][0].update(start=.5,end=1.2,auto_fit=False,playback_rate=1.2)
        await self.patch(dialogue=self.p['dialogue'],settings={**self.p['settings'],'background_mode':'silence'})
        await self.upload(f"dialogue/{self.p['dialogue'][0]['id']}/audio",self.take)
        original=self.p['dialogue'][0]['audio']['asset']
        await self.run_job('export')
        with wave.open(str(self.app.state.store.asset(self.pid,self.p['assets']['dub_audio'])), 'rb') as w:
            w.setpos(round(1.22*48000));self.assertEqual(set(w.readframes(2400)),{0})
        self.p['dialogue'][0].update(auto_fit=True,playback_rate=1)
        await self.patch(dialogue=self.p['dialogue']);await self.run_job('export')
        self.assertEqual(self.p['dialogue'][0]['audio']['asset'],original)
        self.assertAlmostEqual(probe(self.app.state.store.asset(self.pid,original))['duration'],.8,delta=.01)
        self.p['dialogue'][0].update(auto_fit=False,playback_rate=1)
        await self.patch(dialogue=self.p['dialogue'])
        job=await self.client.post(f"/api/projects/{self.pid}/jobs",json={'kind':'export'})
        completed=await self.wait_job(job.json()['id'])
        self.assertIn('exceeds its slot',completed['result']['warnings'][0])

    async def test_validation_conflicts_and_generated_take_invalidation(self):
        await self.upload("media",self.video)
        await self.upload("subtitles",self.sub,{"language":"en"})
        lid = self.p["dialogue"][0]["id"]
        await self.upload(f"dialogue/{lid}/audio",self.take)
        store = self.app.state.store
        def generated(p):
            l=p["dialogue"][0]
            l["audio"]["kind"]="generated"
            l["audio"]["signature"]=signature(p,l)
            return p
        self.p = store.update(self.pid,generated)
        stale = self.p["revision"]
        lines = self.p["dialogue"]
        original = lines[0]["audio"]["asset"]
        lines[0]["translation"]="A different English line."
        await self.patch(dialogue=lines)
        self.assertIsNone(self.p["dialogue"][0]["audio"])
        self.assertTrue(store.asset(self.pid,original).exists())
        r = await self.client.patch(f"/api/projects/{self.pid}",json={"revision":stale,"name":"Conflict"})
        self.assertEqual(r.status_code,409)
        lines = json.loads(json.dumps(self.p["dialogue"]))
        lines[0]["start"]=-1
        r = await self.client.patch(f"/api/projects/{self.pid}",json={"revision":self.p["revision"],"dialogue":lines})
        self.assertEqual(r.status_code,400)
        with self.assertRaises(ValueError):store.asset(self.pid,"../../studio.sqlite")
        r = await self.client.post("/api/projects",json={"name":"Cross origin"},headers={"Origin":"https://example.com"})
        self.assertEqual(r.status_code,403)
        self.assertEqual((await self.client.get("/api/projects",headers={"Host":"malicious.example"})).status_code,400)

    async def test_missing_takes_block_but_overlong_takes_render_with_warnings(self):
        await self.upload("media",self.video)
        await self.upload("subtitles",self.sub,{"language":"en"})
        r = await self.client.post(f"/api/projects/{self.pid}/jobs",json={"kind":"export"})
        j = await self.wait_job(r.json()["id"],"failed")
        self.assertIn("no replacement audio",j["message"])
        for l in list(self.p["dialogue"]):await self.upload(f"dialogue/{l['id']}/audio",self.take)
        self.p["dialogue"][0]["end"]=.6
        await self.patch(dialogue=self.p["dialogue"],settings={**self.p["settings"],"background_mode":"silence"})
        unchanged=json.loads(json.dumps(self.p["dialogue"]))
        j=await self.run_job("export")
        self.assertIn("Complete with timing warnings",j["message"])
        self.assertIn("Line 1 (Speaker 01, 0.50s)",j["result"]["warnings"][0])
        self.assertIn("0.80s speech at 1.00× / 0.10s slot (+0.70s)",j["result"]["warnings"][0])
        self.assertEqual(self.p["dialogue"],unchanged)
        with wave.open(str(self.app.state.store.asset(self.pid,self.p['assets']['dub_audio']))) as w:
            w.setpos(round(1.15*48000));self.assertTrue(any(w.readframes(2400)))
        # Filtering muted speakers preserves the editor's line numbers.
        second={**self.p["speakers"][0],"id":"speaker-2","name":"Other actor","muted":False}
        self.p["speakers"][0]["muted"]=True
        self.p["speakers"].append(second)
        self.p["dialogue"][1].update(speaker="speaker-2",end=2.1)
        await self.patch(dialogue=self.p["dialogue"],speakers=self.p["speakers"])
        j=await self.run_job("export")
        self.assertEqual(len(j['result']['warnings']),1)
        self.assertIn("Line 2 (Other actor, 2.00s)",j['result']['warnings'][0])
        # Extending a free slot removes the recommendation while retaining the take.
        asset=self.p["dialogue"][1]["audio"]["asset"]
        self.p["dialogue"][1].update(source_start=2,source_end=2.1,end=2.8)
        await self.patch(dialogue=self.p["dialogue"])
        j=await self.run_job("export")
        self.assertEqual(j['result']['warnings'],[])
        self.assertEqual(self.p["dialogue"][1]["audio"]["asset"],asset)
        self.assertEqual(self.p["dialogue"][1]["source_end"],2.1)

    async def test_overlong_takes_overlap_without_cutting_or_shifting_dialogue(self):
        await self.upload('media',self.video)
        await self.upload('subtitles',self.sub,{'language':'en'})
        self.p['dialogue'][0].update(start=.5,end=.6,auto_fit=False)
        self.p['dialogue'][1].update(start=1,end=1.1,auto_fit=False)
        await self.patch(dialogue=self.p['dialogue'],settings={**self.p['settings'],'background_mode':'silence'})
        for l in list(self.p['dialogue']):await self.upload(f"dialogue/{l['id']}/audio",self.take)
        unchanged=json.loads(json.dumps(self.p['dialogue']))
        j=await self.run_job('export')
        self.assertEqual(len(j['result']['warnings']),2)
        self.assertEqual(self.p['dialogue'],unchanged)
        import array
        with wave.open(str(self.app.state.store.asset(self.pid,j['result']['audio']))) as w:
            def energy(at):
                w.setpos(round(at*48000))
                return sum(abs(x) for x in array.array('h',w.readframes(2400)))
            single=energy(.8);overlap=energy(1.15);tail=energy(1.6)
            self.assertGreater(single,0)
            self.assertGreater(overlap,single*1.8)
            self.assertAlmostEqual(tail/single,1,delta=.02)

    async def test_dialogue_beyond_video_end_extends_full_audio_in_mkv_and_mp4(self):
        await self.upload('media',self.video)
        await self.upload('subtitles',self.sub,{'language':'en'})
        self.p['dialogue']=self.p['dialogue'][:1]
        self.p['dialogue'][0].update(start=3.7,end=3.9,auto_fit=False)
        await self.patch(dialogue=self.p['dialogue'],settings={**self.p['settings'],'background_mode':'silence'})
        await self.upload(f"dialogue/{self.p['dialogue'][0]['id']}/audio",self.take)
        for container in ('mkv','mp4'):
            with self.subTest(container=container):
                await self.patch(settings={**self.p['settings'],'output':container})
                unchanged=json.loads(json.dumps(self.p['dialogue']))
                j=await self.run_job('export')
                self.assertEqual(self.p['dialogue'],unchanged)
                self.assertAlmostEqual(j['result']['duration'],4.5,delta=.001)
                self.assertTrue(any('beyond the source video' in w for w in j['result']['warnings']))
                with wave.open(str(self.app.state.store.asset(self.pid,j['result']['audio']))) as w:
                    self.assertEqual(w.getnframes(),round(4.5*48000))
                    w.setpos(round(4.4*48000));self.assertTrue(any(w.readframes(2400)))
                rendered=self.app.state.store.asset(self.pid,j['result']['export'])
                self.assertGreaterEqual(probe(rendered)['duration'],4.49)
                # Check the muxed AAC too, rather than just the intermediate WAV.
                tail=self.files/f'export-tail-{container}.wav'
                subprocess.run([binary('ffmpeg'),'-v','error','-y','-ss','4.4','-i',str(rendered),'-map','0:a:0','-t','0.05',str(tail)],check=True)
                with wave.open(str(tail)) as w:self.assertTrue(any(w.readframes(2400)))

    async def test_custom_worker_protocol_and_cancel(self):
        await self.upload("media",self.video)
        await self.run_job("prepare")
        worker = Path(self.temp.name)/"fixture_worker.py"
        worker.write_text("import json,sys,time\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text())\ntime.sleep(float(r['settings'].get('delay',0)))\nPath(sys.argv[2]).write_text(json.dumps({'lines':[{'start':0.5,'end':1.5,'source':'こんにちは。'}]}))\n",encoding="utf-8")
        self.app.state.registry.adapters["fixture"]={"id":"fixture","label":"Test-only adapter","capability":"transcription","custom":True,"command":[sys.executable,str(worker)]}
        config=dict(self.p["models"])
        config["transcription"]={"id":"fixture","settings":{"delay":0}}
        await self.patch(models=config)
        await self.run_job("transcribe")
        self.assertEqual(self.p["dialogue"][0]["source"],"こんにちは。")
        self.assertEqual(self.p["dialogue"][0]["subtitle"],"Hello there.")
        config["transcription"]["settings"]["delay"]=20
        await self.patch(models=config)
        r = await self.client.post(f"/api/projects/{self.pid}/jobs",json={"kind":"transcribe"})
        jid=r.json()["id"]
        await asyncio.sleep(.25)
        await self.client.post(f"/api/jobs/{jid}/cancel")
        await self.wait_job(jid,"cancelled")
        self.assertEqual(self.p["dialogue"][0]["source"],"こんにちは。")

    async def test_restart_marks_unfinished_jobs_interrupted(self):
        store=self.app.state.store
        jid=store.job_create(self.pid,"prepare",{"project":self.p,"options":{}})
        reopened=Store(Path(self.temp.name))
        self.assertEqual(next(j for j in reopened.jobs() if j["id"]==jid)["status"],"interrupted")

    async def configure_batch_fixture(self, pause=False):
        await self.upload('media',self.video);await self.run_job('prepare')
        root=Path(self.temp.name);calls=root/'batch-calls.jsonl';flag=root/'pause.flag'
        if pause:flag.touch()
        script=root/'batch-fixture.py'
        script.write_text("import json,sys,time,shutil\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text());settings=r['settings']\nif r.get('reference'):\n import wave\n with wave.open(r['reference']) as w: assert w.getnframes()/w.getframerate()>=2.95\nlines=r.get('lines') or [{'id':'single','text':r['text']}]\nwith open(settings['calls'],'a') as f: f.write(json.dumps([l['id'] for l in lines])+'\\n')\ntakes=[]\nfor i,l in enumerate(lines):\n p=Path(r['output_dir'])/f'take_{i}.wav';shutil.copyfile(settings['audio'],p)\n take={'id':l['id'],'audio':str(p)};takes.append(take)\n if 'lines' in r: print('KOTO_EVENT '+json.dumps({'completed_take':take}),flush=True)\n if i==0 and Path(settings['pause']).exists(): time.sleep(5)\nPath(sys.argv[2]).write_text(json.dumps({'takes':takes} if 'lines' in r else {'audio':str(p)}))\n",encoding='utf-8')
        self.app.state.registry.adapters['batch-fixture']={'id':'batch-fixture','capability':'synthesis','custom':True,'supports_batch':True,'supports_reference':True,'command':[sys.executable,str(script)]}
        models={**self.p['models'],'synthesis':{'id':'batch-fixture','settings':{'audio':str(self.take),'calls':str(calls),'pause':str(flag)}}}
        lines=[{'id':'first','speaker':'speaker-1','start':.1,'end':1.1,'source':'source','translation':'First line.','audio':None},{'id':'second','speaker':'speaker-1','start':1.4,'end':2.4,'source':'source','translation':'Second line.','audio':None},{'id':'third','speaker':'speaker-1','start':2.8,'end':3.8,'source':'source','translation':'Third line.','audio':None}]
        self.p['speakers'][0]['reference']=self.p['assets']['original_audio']
        if pause:self.p['speakers'][0]['use_source_reference']=True
        await self.patch(models=models,dialogue=lines,speakers=self.p['speakers'])
        return calls,flag

    async def test_synthesis_groups_speaker_lines_and_preserves_cache_and_imported_takes(self):
        calls,_=await self.configure_batch_fixture()
        self.p['speakers'].append({'id':'other','name':'Other','color':'#ff9900','voice':{}})
        self.p['dialogue'][1]['speaker']='other'
        await self.patch(speakers=self.p['speakers'],dialogue=self.p['dialogue'])
        result=await self.run_job('synthesize')
        self.assertEqual(result['result'],{'lines':3,'speakers':2})
        requests=[json.loads(x) for x in calls.read_text().splitlines()]
        self.assertEqual(requests,[['first','third'],['single']])
        self.assertTrue(all(l['audio'] for l in self.p['dialogue']))
        cached=await self.run_job('synthesize');self.assertEqual(cached['result']['cached'],3)
        self.assertEqual(len(calls.read_text().splitlines()),2)
        await self.upload('dialogue/third/audio',self.take)
        self.p['dialogue'][0]['translation']='A revised first line.'
        other=self.p['dialogue'][1]['audio']['asset']
        await self.patch(dialogue=self.p['dialogue'])
        response=await self.client.post(f'/api/projects/{self.pid}/jobs',json={'kind':'synthesize','options':{'speaker_id':'speaker-1'}})
        job=await self.wait_job(response.json()['id']);self.assertEqual(job['result']['lines'],1)
        self.assertEqual(self.p['dialogue'][2]['audio']['kind'],'imported')
        self.assertEqual(self.p['dialogue'][1]['audio']['asset'],other)

    async def test_batch_rejects_artifacts_outside_the_worker_directory(self):
        calls,_=await self.configure_batch_fixture()
        script=Path(self.temp.name)/'bad-batch.py'
        script.write_text("import json,sys\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text());take={'id':r['lines'][0]['id'],'audio':r['settings']['audio']}\nprint('KOTO_EVENT '+json.dumps({'completed_take':take}),flush=True)\nPath(sys.argv[2]).write_text(json.dumps({'takes':[take]}))\n",encoding='utf-8')
        self.app.state.registry.adapters['batch-fixture']['command']=[sys.executable,str(script)]
        response=await self.client.post(f'/api/projects/{self.pid}/jobs',json={'kind':'synthesize'})
        job=await self.wait_job(response.json()['id'],expected='failed')
        self.assertIn('invalid batch artifact',job['message'])
        self.assertTrue(all(l['audio'] is None for l in self.p['dialogue']))

    async def test_cancelled_batch_keeps_completed_takes_and_retries_only_remaining_lines(self):
        calls,flag=await self.configure_batch_fixture(pause=True)
        response=await self.client.post(f'/api/projects/{self.pid}/jobs',json={'kind':'synthesize'})
        jid=response.json()['id']
        for _ in range(400):
            current=(await self.client.get(f'/api/projects/{self.pid}')).json()
            if current['dialogue'][0]['audio']:break
            await asyncio.sleep(.025)
        else:self.fail('Batch did not commit its first take before finishing')
        self.assertAlmostEqual(current['speakers'][0]['source_reference']['duration'],3,delta=.05)
        asset=current['dialogue'][0]['audio']['asset']
        await self.client.post(f'/api/jobs/{jid}/cancel');await self.wait_job(jid,expected='cancelled')
        self.assertEqual(self.p['dialogue'][0]['audio']['asset'],asset)
        self.assertIsNone(self.p['dialogue'][1]['audio'])
        flag.unlink();result=await self.run_job('synthesize');self.assertEqual(result['result']['lines'],2)
        self.assertEqual(self.p['dialogue'][0]['audio']['asset'],asset)
        self.assertEqual([json.loads(x) for x in calls.read_text().splitlines()],[['first','second','third'],['second','third']])

    async def test_synthesis_then_voice_conversion_and_speaker_override(self):
        await self.upload("media",self.video)
        await self.upload("subtitles",self.sub,{"language":"en"})
        worker=Path(self.temp.name)/"audio_fixture.py"
        worker.write_text("import json,sys,shutil\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text())\np=Path(r['output_dir'])/'voice.wav'\nshutil.copyfile(r.get('audio') or r['settings']['fixture_audio'],p)\nPath(sys.argv[2]).write_text(json.dumps({'audio':str(p)}))\n",encoding="utf-8")
        registry=self.app.state.registry
        for aid,cap in (("fixture-tts","synthesis"),("fixture-conversion","voice_conversion")):
            registry.adapters[aid]={"id":aid,"label":"Test-only audio worker","capability":cap,"custom":True,"command":[sys.executable,str(worker)]}
        config=dict(self.p["models"])
        config["synthesis"]={"id":"fixture-tts","settings":{"fixture_audio":str(self.take)}}
        config["voice_conversion"]={"id":"fixture-conversion","settings":{}}
        await self.patch(models=config)
        await self.run_job("synthesize")
        self.assertTrue(all(l["audio"] for l in self.p["dialogue"]))
        self.assertEqual(self.p["dialogue"][0]["audio"]["conversion"]["id"],"fixture-conversion")
        cached = await self.run_job("synthesize")
        self.assertEqual(cached["result"]["lines"],0)
        self.p["speakers"][0]["voice"]["conversion_disabled"]=True
        await self.patch(speakers=self.p["speakers"])
        self.assertTrue(all(l["audio"] is None for l in self.p["dialogue"]))
        await self.run_job("synthesize")
        self.assertIsNone(self.p["dialogue"][0]["audio"]["conversion"])


class SubtitleTests(unittest.TestCase):
    def test_multiline_vtt_and_hour_timestamps(self):
        lines=parse_subtitles("WEBVTT\n\n00:01.200 --> 00:02.300 align:center\n<i>One line</i>\nand another\n\n01:02:03.000 --> 01:02:04.100\nEnd.\n")
        self.assertEqual(len(lines),2)
        self.assertEqual(lines[0]["subtitle"],"One line\nand another")
        self.assertAlmostEqual(lines[1]["start"],3723)


if __name__=="__main__":unittest.main()
