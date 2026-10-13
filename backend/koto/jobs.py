from __future__ import annotations

import hashlib
import json
import os
import queue
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .media import IMAGE_SUBTITLE_CODECS, atempo_factor, binary, parse_subtitles, probe, write_srt
from .registry import interpreter, local_json
from .store import ROOT
from .runtime import executable, runtime_environment

CAPABILITIES = {"separate":"separation", "transcribe":"transcription", "diarize":"diarization", "translate":"translation", "synthesize":"synthesis"}


def signature(project, line):
    speaker = next((s for s in project["speakers"] if s["id"] == line["speaker"]), {})
    content = [line.get("translation", ""), line["speaker"], speaker.get("voice", {}), speaker.get("reference"), project["models"].get("synthesis"),project["models"].get("voice_conversion")]
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


class Cancelled(Exception):
    pass


class Jobs:
    def __init__(self, store, registry):
        self.store, self.registry = store, registry
        self.queue = queue.Queue()
        self.cancelled = set()
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def enqueue(self, pid, kind, options=None):
        if kind not in {*CAPABILITIES, "prepare", "export"}:
            raise ValueError("Unknown job type")
        project = self.store.get(pid)
        if not project["media"] and kind in ("prepare","separate","transcribe","diarize","export"):
            raise ValueError("Import source media first")
        if kind == "prepare":
            settings = project["settings"]
            if all(settings.get(key) is None for key in ("video_stream", "audio_stream", "subtitle_stream")):
                raise ValueError("Select at least one source track in the Clip inspector before Prepare.")
            sub = settings.get("subtitle_stream")
            if sub is not None:
                stream = next((s for s in project["media"]["streams"] if s["index"] == sub and s["type"] == "subtitle"), None)
                if stream is None:
                    raise ValueError("Selected subtitle track does not exist")
                if stream["codec"] in IMAGE_SUBTITLE_CODECS:
                    raise ValueError("Selected subtitles are images. Set Subtitle track to None in the Clip inspector, then Prepare. Import an SRT/ASS file separately; OCR is not included.")
        if kind in CAPABILITIES:
            cap = CAPABILITIES[kind]
            self.registry.get(project["models"][cap]["id"], cap)
        spec = {"project": project, "options": options or {}}
        jid = self.store.job_create(pid, kind, spec)
        self.queue.put((jid, pid, kind, spec))
        return jid

    def cancel(self, jid):
        job = next((j for j in self.store.jobs() if j["id"] == jid), None)
        if not job:
            raise KeyError("Job not found")
        if job["status"] in ("queued","running"):
            self.cancelled.add(jid)
            self.store.job_update(jid, message="Cancellation requested")

    def check(self, jid):
        if jid in self.cancelled or self.closed.is_set():
            raise Cancelled()

    def progress(self, jid, value, message):
        self.check(jid)
        self.store.job_update(jid, progress=value, message=message[:1000])

    def command(self, jid, args, log, progress_base=0, progress_span=1, duration=None, message="Processing media"):
        self.check(jid)
        position = Path(log).stat().st_size if Path(log).exists() else 0
        with open(log, "a", encoding="utf-8") as f:
            proc = subprocess.Popen([str(a) for a in args], stdout=f, stderr=subprocess.STDOUT, env=runtime_environment(python=str(args[0])), start_new_session=os.name != "nt", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        pending = ""
        try:
            while True:
                self.check(jid)
                with open(log, encoding="utf-8", errors="replace") as f:
                    f.seek(position)
                    chunk = f.read()
                    position = f.tell()
                lines = (pending + chunk).split("\n")
                pending = lines.pop()
                for line in lines:
                    if line.startswith("KOTO_EVENT "):
                        try:
                            event = json.loads(line[11:])
                            self.progress(jid, progress_base+float(event["progress"])*progress_span, event["message"])
                        except (ValueError, KeyError):
                            pass
                    elif duration and line.startswith("out_time_us="):
                        try:
                            fraction = max(0, min(0.99, int(line.split("=", 1)[1]) / 1_000_000 / duration))
                            self.progress(jid, progress_base + fraction * progress_span, f"{message} · {int(fraction * 100)}% processed")
                        except ValueError:
                            pass
                if proc.poll() is not None:
                    break
                time.sleep(0.15)
            self.check(jid)
            if proc.returncode:
                tail = Path(log).read_text(encoding="utf-8", errors="replace")[-1800:]
                raise RuntimeError(f"Worker exited with code {proc.returncode}. {tail}")
        except BaseException:
            if proc.poll() is None:
                if os.name == "nt":
                    subprocess.run([executable("taskkill"),"/PID",str(proc.pid),"/T","/F"], capture_output=True)
                else:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=10)
            raise

    def ffmpeg(self, jid, root, *args, duration=None, progress_base=0, progress_span=1, message="Processing media"):
        progress_args = ["-progress", "pipe:1", "-nostats", "-stats_period", "0.5"] if duration else []
        self.command(jid, [binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *progress_args, *args], root / f"{jid}.log", progress_base, progress_span, duration, message)

    def worker(self, jid, project, capability, request, base=0, span=1):
        selection = project["models"][capability]
        adapter = self.registry.get(selection["id"], capability)
        root = self.store.project_dir(project["id"])
        token = uuid.uuid4().hex
        work = root / f"work_{token}"
        work.mkdir()
        spec = {"adapter": adapter["id"], "capability": capability, "settings": selection.get("settings",{}), "output_dir": str(work), **request}
        req = work / "request.json"
        res = work / "result.json"
        req.write_text(json.dumps(spec), encoding="utf-8")
        command = adapter["command"] if adapter.get("custom") else [interpreter(adapter), str(ROOT / "backend" / "koto" / "worker.py")]
        self.command(jid, [*command, str(req), str(res)], root / f"{jid}.log", base, span)
        result = json.loads(res.read_text(encoding="utf-8"))
        # Workers may only return artifacts inside their assigned output directory.
        for key in ("audio", "vocals", "background"):
            if key in result:
                path = Path(result[key]).resolve()
                if not path.is_relative_to(work.resolve()) or not path.is_file():
                    raise ValueError("Worker returned an invalid artifact")
        return result

    def loop(self):
        while not self.closed.is_set():
            try:
                item = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            jid,pid,kind,spec = item
            try:
                self.check(jid)
                self.store.job_update(jid,status="running",progress=0.01,message="Starting " + kind)
                result = getattr(self, kind)(jid, spec["project"], spec["options"])
                self.check(jid)
                self.store.job_update(jid,status="completed",progress=1,message="Complete",result=result or {})
            except Cancelled:
                self.store.job_update(jid,status="cancelled",message="Cancelled; completed assets were preserved")
            except Exception as error:
                self.store.job_update(jid,status="failed",message=str(error)[-2200:])
            finally:
                self.cancelled.discard(jid)
                self.queue.task_done()

    def commit(self, jid, pid, fn, preserve_exports=False):
        self.check(jid)
        def merge(p):
            result = fn(p)
            if not preserve_exports:
                for key in ("export","dub_audio","english_subtitles"):
                    result["assets"].pop(key,None)
            return result
        return self.store.update(pid, merge)

    def prepare(self, jid, project, options):
        root = self.store.project_dir(project["id"])
        source = self.store.asset(project["id"], project["media"]["asset"])
        prefix = jid[:8]
        assets = {}
        audio = project["settings"]["audio_stream"]
        video = project["settings"]["video_stream"]
        if audio is not None:
            self.progress(jid,0.1,"Extracting selected audio track")
            path = root / f"{prefix}_original.wav"
            self.ffmpeg(jid,root,"-i",source,"-map",f"0:{audio}","-vn","-ar","48000","-ac","2","-c:a","pcm_s16le",path,duration=project["media"]["duration"],progress_base=.1,progress_span=.24,message="Extracting selected audio track")
            assets["original_audio"] = path.name
        if video is not None:
            self.progress(jid,0.35,"Creating browser-compatible preview")
            path = root / f"{prefix}_preview.mp4"
            args = ["-i",source,"-map",f"0:{video}"]
            if audio is not None:
                args += ["-map",f"0:{audio}","-c:a","aac","-b:a","128k"]
            args += ["-vf","scale=w='min(1280,iw)':h=-2","-c:v","libx264","-preset","veryfast","-crf","24","-pix_fmt","yuv420p","-movflags","+faststart",str(path)]
            self.ffmpeg(jid,root,*args,duration=project["media"]["duration"],progress_base=.35,progress_span=.49,message="Creating browser-compatible preview")
            assets["preview"] = path.name
        sub = project["settings"].get("subtitle_stream")
        subtitles = None
        if sub is not None:
            stream = next(s for s in project["media"]["streams"] if s["index"] == sub)
            if stream["codec"] in IMAGE_SUBTITLE_CODECS:
                raise ValueError("Selected subtitle track contains images. Import an SRT/ASS file instead; OCR is not included in this version.")
            self.progress(jid,0.85,"Extracting subtitle text")
            path = root / f"{prefix}_subtitles.srt"
            self.ffmpeg(jid,root,"-i",source,"-map",f"0:{sub}",path)
            subtitles = parse_subtitles(path.read_text(encoding="utf-8"))
            assets["source_subtitles"] = path.name
        def merge(p):
            # Re-preparation clears downstream stems; original media remains immutable.
            for key in ("vocals","background"):
                p["assets"].pop(key,None)
            p["assets"].update(assets)
            if subtitles is not None and not p["dialogue"]:
                p["dialogue"] = subtitles
            return p
        self.commit(jid,project["id"],merge)
        return {"assets": assets}

    def audio_source(self, p):
        audio = p["assets"].get("vocals") or p["assets"].get("original_audio")
        if not audio:
            raise ValueError("Run Prepare media first")
        return str(self.store.asset(p["id"],audio))

    def separate(self, jid, project, options):
        original = project["assets"].get("original_audio")
        if not original:
            raise ValueError("Run Prepare media first")
        result = self.worker(jid,project,"separation",{"audio":str(self.store.asset(project["id"],original))})
        root = self.store.project_dir(project["id"])
        assets = {k:str(Path(result[k]).relative_to(root)) for k in ("vocals","background")}
        def merge(p):
            p["assets"].update(assets)
            return p
        self.commit(jid,project["id"],merge)
        return {"assets":assets}

    def transcribe(self, jid, project, options):
        result = self.worker(jid,project,"transcription",{"audio":self.audio_source(project)})
        lines = []
        for item in result["lines"]:
            if not isinstance(item.get("source"),str) or not (0 <= float(item["start"]) < float(item["end"])):
                raise ValueError("Transcription worker returned invalid timestamps")
            overlaps = [(max(0,min(item["end"],s["end"])-max(item["start"],s["start"])),s) for s in project["dialogue"]]
            matched = max(overlaps,key=lambda t:t[0])[1] if overlaps and max(x[0] for x in overlaps)>0 else None
            subtitle = matched.get("subtitle", "") if matched else ""
            lines.append({"id":str(uuid.uuid4()), **item, "speaker":"speaker-1", "translation":"", "subtitle":subtitle, "audio":None})
        def merge(p):
            if p["dialogue"] != project["dialogue"]:
                raise ValueError("Dialogue changed during recognition. Retry after saving your edits.")
            p["dialogue"] = lines
            return p
        self.commit(jid,project["id"],merge)
        return {"lines":len(lines)}

    def diarize(self, jid, project, options):
        result = self.worker(jid,project,"diarization",{"audio":self.audio_source(project)})
        turns = result["turns"]
        tags = sorted({t["speaker"] for t in turns})
        colors = ["#8b8aff","#e8a96b","#62c8b5","#e181b0","#80b4f5"]
        speakers = [{"id":tag,"name":f"Speaker {i+1:02}","color":colors[i%len(colors)],"reference":None,"voice":{}} for i,tag in enumerate(tags)]
        def merge(p):
            if p["dialogue"] != project["dialogue"]:
                raise ValueError("Dialogue changed during diarization. Retry after saving your edits.")
            if speakers:
                p["speakers"] = speakers
                for line in p["dialogue"]:
                    scored = [(max(0,min(t["end"],line["end"])-max(t["start"],line["start"])),t["speaker"]) for t in turns]
                    best = max(scored,key=lambda t:t[0])
                    line["speaker"] = best[1]
                    line["audio"] = None
                    labels = {tag for overlap,tag in scored if overlap > 0.15}
                    line["warning"] = "Possible overlapping speakers; review assignment" if len(labels)>1 else "No matching speaker turn" if best[0]==0 else ""
            return p
        self.commit(jid,project["id"],merge)
        return {"speakers":len(speakers)}

    def translate(self, jid, project, options):
        selected = options.get("line_ids")
        lines = [l for l in project["dialogue"] if not selected or l["id"] in selected]
        if not lines:
            raise ValueError("No dialogue to translate")
        selection = project["models"]["translation"]
        if selection["id"] != "ollama":
            result = self.worker(jid,project,"translation",{"lines":lines})
            translated = {l["id"]:l["translation"] for l in result["lines"]}
        else:
            translated = {}
            for i,line in enumerate(lines):
                self.progress(jid,i/len(lines),f"Translating line {i+1} of {len(lines)}")
                index = project["dialogue"].index(line)
                context = [{"speaker":l["speaker"],"japanese":l.get("source",""),"subtitle":l.get("subtitle","")} for l in project["dialogue"][max(0,index-2):index+3]]
                prompt = json.dumps({"context":context,"line":{"japanese":line.get("source",""),"subtitle_reference":line.get("subtitle",""),"target_seconds":round(line["end"]-line["start"],2)}},ensure_ascii=False)
                if not line.get("source") and not line.get("subtitle"):
                    continue
                # Local requests run in a cancellable helper process as LLM responses can be slow.
                root = self.store.project_dir(project["id"])
                req = root / f"{jid}_{i}_translation_request.json"
                res = root / f"{jid}_{i}_translation_result.json"
                req.write_text(json.dumps({"model":selection["settings"].get("model","qwen3:14b"),"prompt":prompt,"temperature":float(selection["settings"].get("temperature",0.2))}),encoding="utf-8")
                import sys
                self.command(jid,[sys.executable,str(ROOT/"backend"/"koto"/"translate_worker.py"),str(req),str(res)],root/f"{jid}.log")
                translated[line["id"]] = json.loads(res.read_text(encoding="utf-8"))["translation"]
        def merge(p):
            old = {l["id"]:l for l in lines}
            for line in p["dialogue"]:
                if line["id"] in translated:
                    prior = old[line["id"]]
                    if any(line.get(k) != prior.get(k) for k in ("source","subtitle","translation","start","end")):
                        continue
                    line["translation"] = translated[line["id"]]
                    line["audio"] = None
            return p
        self.commit(jid,project["id"],merge)
        return {"lines":len(translated)}

    def synthesize(self, jid, project, options):
        selected = options.get("line_ids")
        candidates = [l for l in project["dialogue"] if l.get("translation","").strip() and (not selected or l["id"] in selected)]
        lines = [l for l in candidates if selected or not l.get("audio") or (l["audio"].get("kind")=="generated" and l["audio"].get("signature")!=signature(project,l))]
        if not lines:
            if candidates:
                return {"lines":0,"cached":len(candidates)}
            raise ValueError("Add an English translation first")
        root = self.store.project_dir(project["id"])
        generated = 0
        for i,line in enumerate(lines):
            self.progress(jid,i/len(lines),f"Generating line {i+1} of {len(lines)}")
            speaker = next(s for s in project["speakers"] if s["id"] == line["speaker"])
            config = json.loads(json.dumps(project))
            voice = speaker.get("voice",{})
            if voice.get("adapter"):
                config["models"]["synthesis"]["id"] = voice["adapter"]
            config["models"]["synthesis"]["settings"].update(voice.get("settings",{}))
            request = {"text":line["translation"], "reference":str(self.store.asset(project["id"],speaker["reference"])) if speaker.get("reference") else None}
            result = self.worker(jid,config,"synthesis",request,i/len(lines),1/len(lines))
            conversion = None if voice.get("conversion_disabled") else voice.get("conversion") or project["models"].get("voice_conversion")
            if conversion:
                config["models"]["voice_conversion"] = conversion
                self.progress(jid,i/len(lines),f"Converting voice for line {i+1}")
                result = self.worker(jid,config,"voice_conversion",{"audio":result["audio"],"reference":request["reference"]},i/len(lines),1/len(lines))
            generated_path = Path(result["audio"])
            raw_duration = probe(generated_path)["duration"]
            normalized = root / f"{jid[:8]}_{line['id']}_voice.wav"
            target = line["end"]-line["start"]
            factor = raw_duration/target
            fits = 0.8 <= factor <= 1.25
            filters = atempo_factor(factor) if project["settings"].get("fit_duration") and fits else "anull"
            self.ffmpeg(jid,root,"-i",generated_path,"-af",filters,"-ar","48000","-ac","2",normalized)
            audio = {"asset":normalized.name,"duration":probe(normalized)["duration"],"signature":signature(project,line),"kind":"generated","model":config["models"]["synthesis"],"conversion":conversion,"raw_duration":raw_duration}
            warning = "Timing needs review: rewrite or adjust the line before export" if raw_duration > target and not fits else ""
            def merge(p):
                current = next((l for l in p["dialogue"] if l["id"]==line["id"]),None)
                if current and signature(p,current)==audio["signature"] and current["start"]==line["start"] and current["end"]==line["end"] and current.get("audio")==line.get("audio"):
                    current["audio"] = audio
                    current["warning"] = warning
                return p
            self.commit(jid,project["id"],merge)
            generated += 1
        return {"lines":generated}

    def export(self, jid, project, options):
        root = self.store.project_dir(project["id"])
        lines = project["dialogue"]
        if not lines:
            raise ValueError("Add dialogue and replacement audio before rendering")
        missing = [l for l in lines if not l.get("audio")]
        if missing:
            raise ValueError(f"{len(missing)} dialogue lines have no replacement audio. Generate or import every line before rendering.")
        duration = project["media"]["duration"]
        mode = project["settings"].get("background_mode","separated")
        bed = project["assets"].get("background") if mode == "separated" else project["assets"].get("original_audio") if mode == "original" else None
        if mode == "separated" and not bed:
            raise ValueError("Separate audio first, or choose Silence / Original mix in Export settings")
        self.progress(jid,0.05,"Preparing synchronized dialogue clips")
        clips = []
        for i,line in enumerate(lines):
            self.check(jid)
            audio = line["audio"]
            if audio.get("kind")=="generated" and audio.get("signature") != signature(project,line):
                raise ValueError("A voice take is out of date. Regenerate the changed line.")
            target = line["end"]-line["start"]
            actual = probe(self.store.asset(project["id"],audio["asset"]))["duration"]
            factor = actual/target
            fit = project["settings"].get("fit_duration",True)
            if actual > target+0.08 and not (fit and factor <= 1.25):
                raise ValueError(f"Line {i+1} exceeds its slot. Edit wording or extend its timing; export will not cut off dialogue.")
            normalized = root / f"{jid[:8]}_mixclip_{i}.wav"
            filters = atempo_factor(factor) if fit and 0.8<=factor<=1.25 else "anull"
            self.ffmpeg(jid,root,"-i",self.store.asset(project["id"],audio["asset"]),"-af",filters,"-ar","48000","-ac","2",normalized)
            clips.append((line,normalized))
        self.progress(jid,0.25,"Mixing English dialogue and background")
        # Mix incrementally using PCM arrays to avoid FFmpeg's input limits on long episodes.
        import wave
        import array
        frames = round(duration*48000)
        mix_path = root / f"{jid[:8]}_dub.wav"
        # File-backed accumulation keeps memory bounded even for long episodes.
        import mmap
        accumulator = root / f"{jid[:8]}_mix.f32"
        with open(accumulator,"w+b") as f:
            f.truncate(frames*2*4)
            with mmap.mmap(f.fileno(),0) as mapped:
                floats = memoryview(mapped).cast("f")
                def add_wav(path, offset, gain):
                    with wave.open(str(path),"rb") as w:
                        if w.getframerate()!=48000 or w.getnchannels()!=2 or w.getsampwidth()!=2:
                            raise ValueError("Mix input must be stereo 48kHz PCM16")
                        at = offset*2
                        while data := w.readframes(48000):
                            self.check(jid)
                            values = array.array("h",data)
                            if sys_byteorder_big():
                                values.byteswap()
                            for j,v in enumerate(values):
                                if at+j<len(floats):
                                    floats[at+j] += v/32768*gain
                            at += len(values)
                try:
                    if bed:
                        normalized_bed = root / f"{jid[:8]}_bed.wav"
                        self.ffmpeg(jid,root,"-i",self.store.asset(project["id"],bed),"-ar","48000","-ac","2","-c:a","pcm_s16le",normalized_bed)
                        add_wav(normalized_bed,0,float(project["settings"].get("background_gain",0.8)))
                    for i,(line,path) in enumerate(clips):
                        add_wav(path,round(line["start"]*48000),float(project["settings"].get("dialogue_gain",1))*float(line.get("gain",1)))
                        self.progress(jid,0.25+0.35*(i+1)/len(clips),f"Mixing line {i+1} of {len(clips)}")
                    peak = max((abs(v) for v in floats),default=1)
                    scale = min(1,0.98/max(peak,0.0001))
                    with wave.open(str(mix_path),"wb") as w:
                        w.setparams((2,2,48000,0,"NONE","not compressed"))
                        for start in range(0,len(floats),96000):
                            self.check(jid)
                            pcm = array.array("h",(max(-32768,min(32767,round(v*scale*32767))) for v in floats[start:start+96000]))
                            if sys_byteorder_big():
                                pcm.byteswap()
                            w.writeframes(pcm.tobytes())
                finally:
                    floats.release()
        accumulator.unlink(missing_ok=True)
        self.progress(jid,0.7,"Muxing original video with English audio")
        subtitle = root / f"{jid[:8]}_english.srt"
        write_srt(lines,subtitle)
        container = project["settings"].get("output","mkv")
        target = root / f"{jid[:8]}_english.{container}"
        source = self.store.asset(project["id"],project["media"]["asset"])
        video_index = project["settings"]["video_stream"]
        args = ["-i",source,"-i",mix_path,"-i",subtitle]
        if video_index is not None:
            args += ["-map",f"0:{video_index}"]
        args += ["-map","1:a:0","-map","2:s:0","-c:v","copy" if container=="mkv" else "libx264","-c:a","aac","-b:a","256k","-c:s","srt" if container=="mkv" else "mov_text","-metadata:s:a:0","language=eng","-metadata:s:s:0","language=eng","-t",str(duration)]
        if container=="mp4":
            args += ["-preset","medium","-crf","18","-movflags","+faststart"]
        self.ffmpeg(jid,root,*args,target)
        def merge(p):
            p["assets"]["export"] = target.name
            p["assets"]["dub_audio"] = mix_path.name
            p["assets"]["english_subtitles"] = subtitle.name
            return p
        self.commit(jid,project["id"],merge,preserve_exports=True)
        return {"export":target.name,"audio":mix_path.name,"subtitles":subtitle.name,"project_revision":project["revision"]}


def sys_byteorder_big():
    import sys
    return sys.byteorder == "big"
