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
from .registry import interpreter, local_json, module_available
from .store import ROOT
from .runtime import executable, runtime_environment
from .diarization import require_pipeline
from .timing import estimate_seconds, playback_rate, adaptation_signature
from .references import reference_segments, reference_signature, source_bounds
from .separation import activate, download, installed, model_spec, separation_range, validated_settings

CAPABILITIES = {"separate":"separation", "transcribe":"transcription", "diarize":"diarization", "translate":"translation", "synthesize":"synthesis"}


def signature(project, line):
    speaker = next((s for s in project["speakers"] if s["id"] == line["speaker"]), {})
    reference = ["source", reference_signature(project, line["speaker"])] if speaker.get("use_source_reference", False) else speaker.get("reference")
    content = [line.get("translation", ""), line["speaker"], speaker.get("voice", {}), reference, project["models"].get("synthesis"),project["models"].get("voice_conversion")]
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
        if kind not in {*CAPABILITIES, "prepare", "export", "reference", "alternatives", "download_separation_model"}:
            raise ValueError("Unknown job type")
        project = self.store.get(pid)
        if kind=="synthesize" and (options or {}).get("speaker_id") and not any(s["id"]==(options or {})["speaker_id"] for s in project["speakers"]):
            raise ValueError("Unknown speaker for synthesis")
        if not project["media"] and kind in ("prepare","separate","transcribe","diarize","export"):
            raise ValueError("Import source media first")
        if kind == "download_separation_model":
            model_spec((options or {}).get("model_id"))
        if kind == "separate":
            separation_range(project, options or {})
            selection = project["models"]["separation"]
            adapter = self.registry.get(selection["id"], "separation")
            interpreter(adapter)
            if not adapter.get("custom") and not module_available(adapter):
                raise ValueError("Install the separation worker first: " + ("Install-Separation.cmd" if adapter["id"] == "audio-separator" else "Install-Models.cmd"))
            if adapter["id"] == "audio-separator":
                selection["settings"] = validated_settings(selection.get("settings", {}))
                if not installed(model_spec(selection["settings"]["model"])):
                    raise ValueError("Download the selected model in Separate audio first")
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
            if kind == "diarize" and project["models"][cap]["id"] == "pyannote":
                require_pipeline(project["models"][cap].get("settings"))
            if kind == "synthesize":
                selected = (options or {}).get("line_ids")
                ids = {l["speaker"] for l in project["dialogue"] if l.get("translation","").strip() and (not selected or l["id"] in selected) and (not (options or {}).get("speaker_id") or l["speaker"]==options["speaker_id"])}
                for speaker in project["speakers"]:
                    if speaker["id"] not in ids:
                        continue
                    adapter = self.registry.get(speaker.get("voice", {}).get("adapter") or project["models"][cap]["id"], cap)
                    # Validate moved/broken environments before launching a model process.
                    interpreter(adapter)
                    if not adapter.get("custom") and not module_available(adapter):
                        installer = "Install-Reference-Voices.cmd" if adapter["id"] == "xtts" else "Install-Piper.cmd" if adapter["id"] == "piper" else "Install-Models.cmd"
                        raise ValueError(f"The {adapter['label']} worker is missing or broken. Close KOTO, run {installer}, then restart.")
                    if speaker.get("use_source_reference") and not adapter.get("supports_reference", False):
                        raise ValueError("Original speaker references need XTTS or another reference-capable synthesis adapter. Piper uses fixed voices. Select XTTS in the speaker Voice tab and run Install-Reference-Voices.cmd.")
                    if speaker.get("use_source_reference"):
                        self.audio_source(project)
                        reference_segments(project, speaker["id"])
        if kind == "alternatives":
            line = next((l for l in project["dialogue"] if l["id"] == (options or {}).get("line_id")), None)
            if not line or not (line.get("source") or line.get("subtitle") or line.get("translation")):
                raise ValueError("Select a dialogue line with source text or an English translation")
            adapter = self.registry.get(project["models"]["translation"]["id"], "translation")
            if adapter["id"] != "ollama" and not adapter.get("supports_alternatives"):
                raise ValueError("This translation adapter does not support alternatives. Select local Ollama or a supports_alternatives adapter.")
        if kind == "reference":
            sid = (options or {}).get("speaker_id")
            if not any(s["id"] == sid for s in project["speakers"]):
                raise ValueError("Select a speaker before building an original reference")
            self.audio_source(project)
            reference_segments(project, sid)
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

    def command(self, jid, args, log, progress_base=0, progress_span=1, duration=None, message="Processing media", on_event=None):
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
                            if "progress" in event and "message" in event:
                                self.progress(jid, progress_base+float(event["progress"])*progress_span, event["message"])
                        except (ValueError, KeyError):
                            continue
                        if on_event:
                            on_event(event)
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

    def worker(self, jid, project, capability, request, base=0, span=1, on_take=None):
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
        expected={line["id"] for line in request.get("lines",[])} if on_take else set()
        def validate_take(take):
            if not isinstance(take,dict) or take.get("id") not in expected or not isinstance(take.get("audio"),str):
                raise ValueError("Worker returned an unknown or malformed batch take")
            path=Path(take["audio"]).resolve()
            if not path.is_relative_to(work.resolve()) or not path.is_file():
                raise ValueError("Worker returned an invalid batch artifact")
        def receive(event):
            if "completed_take" in event:
                validate_take(event["completed_take"])
                on_take(event["completed_take"])
        self.command(jid, [*command, str(req), str(res)], root / f"{jid}.log", base, span,on_event=receive if on_take else None)
        result = json.loads(res.read_text(encoding="utf-8"))
        # Workers may only return artifacts inside their assigned output directory.
        for key in ("audio", "vocals", "background"):
            if key in result:
                path = Path(result[key]).resolve()
                if not path.is_relative_to(work.resolve()) or not path.is_file():
                    raise ValueError("Worker returned an invalid artifact")
        if on_take:
            if not isinstance(result.get("takes"),list):
                raise ValueError("Batch worker returned no takes")
            for take in result["takes"]:
                validate_take(take)
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
                message = "Complete with timing warnings; recommended to fix audio before exporting" if kind=="export" and (result or {}).get("warnings") else "Complete"
                self.store.job_update(jid,status="completed",progress=1,message=message,result=result or {})
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
            p["active_separation"] = None
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

    def source_reference(self, jid, project, speaker):
        key = reference_signature(project, speaker["id"])
        cached = speaker.get("source_reference")
        if cached and cached.get("signature") == key and self.store.asset(project["id"], cached["asset"]).is_file():
            return cached
        source = self.audio_source(project)
        segments = reference_segments(project, speaker["id"])
        root = self.store.project_dir(project["id"])
        work = root / ("reference_" + uuid.uuid4().hex)
        work.mkdir()
        clips = []
        for i, (start, end) in enumerate(segments):
            self.progress(jid, .05 + .3*i/len(segments), f"Building original reference for {speaker['name']}")
            path = work / f"segment_{i}.wav"
            self.ffmpeg(jid, root, "-ss", str(start), "-i", source, "-t", str(end-start), "-vn", "-ar", "22050", "-ac", "1", "-c:a", "pcm_s16le", path)
            clips.append(path)
        path = work / "reference.wav"
        args = [item for clip in clips for item in ("-i", clip)]
        graph = "".join(f"[{i}:a]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=0:a=1[out]"
        self.ffmpeg(jid, root, *args, "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le", path)
        duration = probe(path)["duration"]
        if duration < 2.95:
            raise ValueError("Original reference is too short. Review source dialogue timestamps or upload a clean sample.")
        result = {"asset": path.relative_to(root).as_posix(), "duration": duration, "signature": key}
        speaker["source_reference"] = result
        def merge(p):
            current = next((s for s in p["speakers"] if s["id"] == speaker["id"]), None)
            if current and reference_signature(p, speaker["id"]) == key:
                current["source_reference"] = result
            return p
        self.commit(jid, project["id"], merge)
        return result

    def reference(self, jid, project, options):
        speaker = next(s for s in project["speakers"] if s["id"] == options["speaker_id"])
        return self.source_reference(jid, project, speaker)

    def download_separation_model(self, jid, project, options):
        return download(options["model_id"], lambda value, message: self.progress(jid, value, message), lambda: self.check(jid))

    def separate(self, jid, project, options):
        preview, start, end = separation_range(project, options)
        original = project["assets"]["original_audio"]
        root = self.store.project_dir(project["id"])
        source = self.store.asset(project["id"], original)
        comparison = original
        source_duration = probe(source)["duration"]
        if preview and start >= source_duration:
            raise ValueError("This preview begins after the prepared audio ends. Choose an earlier range.")
        # MKV audio tracks can end before the video. Pad that existing silence
        # before inference rather than mistaking it for a broken model output.
        if preview or abs(source_duration-(end-start)) > .001:
            clipped = root / f"{jid}_comparison.wav"
            self.ffmpeg(jid,root,"-ss",str(start),"-i",source,"-af",f"apad,atrim=duration={end-start}","-ar","48000","-ac","2","-c:a","pcm_s16le",clipped)
            source, comparison = clipped, clipped.name
        self.progress(jid,.05,"Separating preview range" if preview else "Separating full source")
        result = self.worker(jid,project,"separation",{"audio":str(source)},base=.05,span=.8)
        assets = {"original":comparison}
        for key in ("vocals","background"):
            if key not in result:
                raise ValueError("Separation worker returned no " + key)
            raw = Path(result[key])
            actual = probe(raw)["duration"]
            if not actual > 0 or abs(actual-(end-start)) > .25:
                raise ValueError(f"{key} duration differs from the source. The result was not applied.")
            # Maintain the same timeline and PCM format for every model. Only
            # rounding/padding at the tail is allowed; speech is never sped up.
            path = root / f"{jid}_{key}.wav"
            self.ffmpeg(jid,root,"-i",raw,"-af",f"apad,atrim=duration={end-start}","-ar","48000","-ac","2","-c:a","pcm_s16le",path)
            assets[key] = path.name
        selection = project["models"]["separation"]
        record = {"id":jid,"created":time.time(),"source_asset":original,"preview":preview,"start":start,"end":end,"duration":end-start,"selection":selection,"label":self.registry.get(selection["id"])["label"],"assets":assets}
        applied = False
        def merge(p):
            nonlocal applied
            p.setdefault("separations",[]).append(record)
            if not preview and p["assets"].get("original_audio") == original:
                activate(p,record)
                applied = True
            return p
        self.commit(jid,project["id"],merge,preserve_exports=True)
        return {"separation_id":jid,"preview":preview,"applied":applied,"assets":assets}

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
                    start,end = source_bounds(line)
                    scored = [(max(0,min(t["end"],end)-max(t["start"],start)),t["speaker"]) for t in turns]
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
                context = [{"speaker":l["speaker"],"source":l.get("source",""),"subtitle":l.get("subtitle","")} for l in project["dialogue"][max(0,index-2):index+3]]
                prompt = json.dumps({"context":context,"line":{"source":line.get("source",""),"subtitle_reference":line.get("subtitle",""),"target_seconds":round(line["end"]-line["start"],2)}},ensure_ascii=False)
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

    def alternatives(self,jid,project,options):
        line = next(l for l in project["dialogue"] if l["id"] == options["line_id"])
        selection = project["models"]["translation"]
        target = round(line["end"]-line["start"],2)
        index = project["dialogue"].index(line)
        context = [{"speaker":l["speaker"], "source":l.get("source",""), "translation":l.get("translation","")} for l in project["dialogue"][max(0,index-2):index+3]]
        prompt = {"context":context,"source":line.get("source",""),"subtitle_reference":line.get("subtitle",""),"current_translation":line.get("translation",""),"target_seconds":target,"approximate_word_budget":round(target*project["settings"].get("estimated_speech_wpm",150)/60)}
        self.progress(jid,.1,"Suggesting three timing-aware adaptations for one line")
        if selection["id"] == "ollama":
            root = self.store.project_dir(project["id"])
            req,res = root/f"{jid}_alternatives_request.json",root/f"{jid}_alternatives_result.json"
            req.write_text(json.dumps({"mode":"alternatives","model":selection["settings"].get("model","qwen3:14b"),"temperature":float(selection["settings"].get("temperature",.2)),"prompt":json.dumps(prompt,ensure_ascii=False)}),encoding="utf-8")
            import sys
            self.command(jid,[sys.executable,str(ROOT/"backend/koto/translate_worker.py"),str(req),str(res)],root/f"{jid}.log")
            result = json.loads(res.read_text(encoding="utf-8"))
        else:
            result = self.worker(jid,project,"translation",{"mode":"alternatives","line":line,**prompt})
        texts = result.get("alternatives")
        if not isinstance(texts,list) or not 1<=len(texts)<=5 or any(not isinstance(t,str) or not t.strip() or len(t)>20000 for t in texts):
            raise ValueError("Translation model returned invalid alternatives")
        suggestions=[{"text":t.strip(),"estimated_seconds":estimate_seconds(t,project["settings"].get("estimated_speech_wpm",150))} for t in dict.fromkeys(texts)]
        key=adaptation_signature(line)
        def merge(p):
            current=next((l for l in p["dialogue"] if l["id"]==line["id"]),None)
            if current and adaptation_signature(current)==key:
                current["alternatives"]={"signature":key,"basis":{k:line.get(k) for k in ("source","subtitle","translation","start","end")},"suggestions":suggestions}
            return p
        self.commit(jid,project["id"],merge)
        return {"line_id":line["id"],"suggestions":len(suggestions)}

    def synthesize(self, jid, project, options):
        selected=options.get("line_ids");sid=options.get("speaker_id")
        candidates=[l for l in project["dialogue"] if l.get("translation","").strip() and (not selected or l["id"] in selected) and (not sid or l["speaker"]==sid)]
        lines=[l for l in candidates if selected or not l.get("audio") or (l["audio"].get("kind")=="generated" and l["audio"].get("signature")!=signature(project,l))]
        if not lines:
            if candidates:return {"lines":0,"cached":len(candidates)}
            raise ValueError("Add an English translation first")
        root=self.store.project_dir(project["id"])
        generated=0;groups=[(s,[l for l in lines if l["speaker"]==s["id"]]) for s in project["speakers"]]
        groups=[g for g in groups if g[1]]
        self.progress(jid,.01,f"Planning {len(lines)} lines for {len(groups)} speakers; compatible voices will stay loaded per speaker")
        for speaker,group in groups:
            config=json.loads(json.dumps(project));voice=speaker.get("voice",{})
            if voice.get("adapter"):config["models"]["synthesis"]["id"]=voice["adapter"]
            config["models"]["synthesis"]["settings"].update(voice.get("settings",{}))
            reference=self.source_reference(jid,project,speaker)["asset"] if speaker.get("use_source_reference") else speaker.get("reference")
            reference=str(self.store.asset(project["id"],reference)) if reference else None
            conversion=None if voice.get("conversion_disabled") else voice.get("conversion") or project["models"].get("voice_conversion")
            def complete(line,path):
                nonlocal generated
                raw_duration=probe(Path(path))["duration"]
                normalized=root/f"{jid[:8]}_{line['id']}_voice.wav"
                self.ffmpeg(jid,root,"-i",path,"-af","anull","-ar","48000","-ac","2",normalized)
                audio={"asset":normalized.name,"duration":probe(normalized)["duration"],"signature":signature(project,line),"kind":"generated","model":config["models"]["synthesis"],"conversion":conversion,"raw_duration":raw_duration}
                target=line["end"]-line["start"];played=raw_duration/playback_rate(project,line,raw_duration)
                warning="Timing needs review: rewrite or adjust the line before export" if played>target+.08 else "Voice take is shorter than its slot. Consider a fuller adaptation or a slower speed." if played<target*.75 else ""
                def merge(p):
                    current=next((l for l in p["dialogue"] if l["id"]==line["id"]),None)
                    if current and signature(p,current)==audio["signature"] and current["start"]==line["start"] and current["end"]==line["end"] and current.get("audio")==line.get("audio"):
                        current["audio"]=audio;current["warning"]=warning
                    return p
                self.commit(jid,project["id"],merge);generated+=1
            adapter=self.registry.get(config["models"]["synthesis"]["id"],"synthesis")
            # GPU conversion bridges retain their existing per-line path so two large
            # models are never resident together unless the bridge explicitly owns that flow.
            if adapter.get("supports_batch") and len(group)>1 and not conversion:
                seen=set();by_id={l["id"]:l for l in group}
                def receive(take):
                    if take["id"] in seen:return
                    complete(by_id[take["id"]],take["audio"]);seen.add(take["id"])
                base=generated/len(lines)
                self.progress(jid,base,f"Loading {speaker['name']} once for {len(group)} lines")
                result=self.worker(jid,config,"synthesis",{"lines":[{"id":l["id"],"text":l["translation"]} for l in group],"reference":reference},base,len(group)/len(lines),on_take=receive)
                returned=[t["id"] for t in result["takes"]]
                if len(returned)!=len(set(returned)) or set(returned)!=set(by_id):
                    raise ValueError("Synthesis batch returned missing or duplicate dialogue takes")
                for take in result["takes"]:receive(take)
            else:
                for line in group:
                    self.progress(jid,generated/len(lines),f"Generating {speaker['name']} · line {generated+1} of {len(lines)}")
                    result=self.worker(jid,config,"synthesis",{"text":line["translation"],"reference":reference},generated/len(lines),1/len(lines))
                    if conversion:
                        config["models"]["voice_conversion"]=conversion
                        result=self.worker(jid,config,"voice_conversion",{"audio":result["audio"],"reference":reference},generated/len(lines),1/len(lines))
                    complete(line,result["audio"])
        return {"lines":generated,"speakers":len(groups)}

    def export(self, jid, project, options):
        root = self.store.project_dir(project["id"])
        all_lines = project["dialogue"]
        if not all_lines:
            raise ValueError("Add dialogue and replacement audio before rendering")
        muted = {s["id"] for s in project["speakers"] if s.get("muted", False)}
        lines = [l for l in all_lines if l["speaker"] not in muted]
        missing = [l for l in lines if not l.get("audio")]
        if missing:
            raise ValueError(f"{len(missing)} dialogue lines have no replacement audio. Generate or import every line before rendering.")
        duration = project["media"]["duration"]
        mode = project["settings"].get("background_mode","separated")
        bed = project["assets"].get("background") if mode == "separated" else project["assets"].get("original_audio") if mode == "original" else None
        bed_muted = project["settings"].get("background_muted", False) if mode == "separated" else project["settings"].get("original_muted", False)
        if bed_muted:
            bed = None
        if mode == "separated" and not bed and not bed_muted:
            raise ValueError("Separate audio first, or choose Silence / Original mix in Export settings")
        # Probe every take before normalization so a late failure wastes no render work.
        rates, issues = {}, []
        speakers = {s["id"]: s["name"] for s in project["speakers"]}
        for index,line in enumerate(all_lines):
            if line["speaker"] in muted:
                continue
            self.check(jid)
            audio = line["audio"]
            if audio.get("kind")=="generated" and audio.get("signature") != signature(project,line):
                raise ValueError(f"Line {index+1} has an out-of-date voice take. Regenerate the changed line.")
            target = line["end"]-line["start"]
            actual = probe(self.store.asset(project["id"],audio["asset"]))["duration"]
            rate = playback_rate(project,line,actual)
            rates[line["id"]] = rate
            if actual/rate > target+0.08:
                issues.append(f"Line {index+1} ({speakers.get(line['speaker'],line['speaker'])}, {line['start']:.2f}s) exceeds its slot: {actual/rate:.2f}s speech at {rate:.2f}× / {target:.2f}s slot (+{actual/rate-target:.2f}s).")
        self.progress(jid,0.05,"Preparing synchronized dialogue clips")
        clips = []
        import wave
        frames = round(duration*48000)
        source_frames = frames
        for i,line in enumerate(lines):
            self.check(jid)
            audio = line["audio"]
            rate = rates[line["id"]]
            normalized = root / f"{jid[:8]}_mixclip_{i}.wav"
            filters = atempo_factor(rate) if abs(rate-1)>.001 else "anull"
            self.ffmpeg(jid,root,"-i",self.store.asset(project["id"],audio["asset"]),"-af",filters,"-ar","48000","-ac","2",normalized)
            # Measure the normalized PCM itself: atempo can add a small tail.
            # Size the mix for all speech, including takes beyond the source video.
            with wave.open(str(normalized),"rb") as take:
                frames = max(frames,round(line["start"]*48000)+take.getnframes())
            clips.append((line,normalized))
        self.progress(jid,0.25,"Mixing English dialogue and background")
        # Mix incrementally using PCM arrays to avoid FFmpeg's input limits on long episodes.
        import array
        duration = frames/48000
        if frames>source_frames:
            issues.append(f"Export extended by {(frames-source_frames)/48000:.2f}s beyond the source video to keep the full dialogue audio.")
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
        visible = project["settings"].get("video_visible", True)
        subtitles_visible = project["settings"].get("subtitles_visible", True)
        self.progress(jid,0.7,"Muxing video with English audio" if visible else "Rendering black video with English audio")
        subtitle = root / f"{jid[:8]}_english.srt"
        write_srt(all_lines,subtitle)
        container = project["settings"].get("output","mkv")
        target = root / f"{jid[:8]}_english.{container}"
        source = self.store.asset(project["id"],project["media"]["asset"])
        video_index = project["settings"]["video_stream"]
        if visible:
            args = ["-i",source]
        else:
            stream = next((s for s in project["media"]["streams"] if s["type"]=="video" and (video_index is None or s["index"]==video_index)), {})
            width, height = int(stream.get("width") or 1280), int(stream.get("height") or 720)
            width, height = width + width % 2, height + height % 2
            numerator, denominator = (stream.get("fps") or "24/1").split("/")
            fps = float(numerator)/float(denominator) if float(denominator) else 24
            fps = fps if 0 < fps <= 240 else 24
            args = ["-f","lavfi","-i",f"color=c=black:s={width}x{height}:r={fps}"]
        args += ["-i",mix_path,"-i",subtitle]
        if not visible:
            args += ["-map","0:v:0"]
        elif video_index is not None:
            args += ["-map",f"0:{video_index}"]
        args += ["-map","1:a:0","-c:v","copy" if container=="mkv" and visible else "libx264","-c:a","aac","-b:a","256k","-metadata:s:a:0","language=eng","-t",str(duration)]
        if subtitles_visible:
            args += ["-map","2:s:0","-c:s","srt" if container=="mkv" else "mov_text","-metadata:s:s:0","language=eng"]
        if not visible:
            args += ["-pix_fmt","yuv420p"]
        if container=="mp4":
            args += ["-preset","medium","-crf","18","-movflags","+faststart"]
        self.ffmpeg(jid,root,*args,target)
        def merge(p):
            p["assets"]["export"] = target.name
            p["assets"]["dub_audio"] = mix_path.name
            p["assets"]["english_subtitles"] = subtitle.name
            return p
        self.commit(jid,project["id"],merge,preserve_exports=True)
        return {"export":target.name,"audio":mix_path.name,"subtitles":subtitle.name,"project_revision":project["revision"],"warnings":issues,"duration":duration}


def sys_byteorder_big():
    import sys
    return sys.byteorder == "big"
