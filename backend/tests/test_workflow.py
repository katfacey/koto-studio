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

    async def test_missing_takes_and_long_takes_fail_without_cutting_dialogue(self):
        await self.upload("media",self.video)
        await self.upload("subtitles",self.sub,{"language":"en"})
        r = await self.client.post(f"/api/projects/{self.pid}/jobs",json={"kind":"export"})
        j = await self.wait_job(r.json()["id"],"failed")
        self.assertIn("no replacement audio",j["message"])
        for l in list(self.p["dialogue"]):await self.upload(f"dialogue/{l['id']}/audio",self.take)
        self.p["dialogue"][0]["end"]=.6
        await self.patch(dialogue=self.p["dialogue"],settings={**self.p["settings"],"background_mode":"silence"})
        r = await self.client.post(f"/api/projects/{self.pid}/jobs",json={"kind":"export"})
        j = await self.wait_job(r.json()["id"],"failed")
        self.assertIn("will not cut off dialogue",j["message"])

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
