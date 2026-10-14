from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool

from .separation import activate, catalog
from .jobs import Jobs, signature
from .media import IMAGE_SUBTITLE_CODECS, binary, parse_subtitles, probe
from .registry import Registry
from .store import DATA, ROOT, Store
from .runtime import executable


class NewProject(BaseModel):
    name: str = Field(default="Untitled project", min_length=1, max_length=120)
    demo: bool = False


class ProjectPatch(BaseModel):
    revision: int
    name: str | None = None
    dialogue: list[dict] | None = None
    speakers: list[dict] | None = None
    models: dict | None = None
    settings: dict | None = None


class NewJob(BaseModel):
    kind: str
    options: dict = Field(default_factory=dict)


def number(value, low, high, label):
    try:
        n = float(value)
        if not math.isfinite(n) or not low <= n <= high:
            raise ValueError()
        return n
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be between {low} and {high}")


def validate_project(p, registry):
    if not isinstance(p["name"],str) or not p["name"].strip() or len(p["name"])>120:
        raise ValueError("Project name must be 1–120 characters")
    if not p["speakers"] or len(p["speakers"])>100:
        raise ValueError("A project needs 1–100 speakers")
    speaker_ids = set()
    for s in p["speakers"]:
        if not isinstance(s.get("id"),str) or s["id"] in speaker_ids:
            raise ValueError("Speaker IDs must be unique")
        speaker_ids.add(s["id"])
        if not isinstance(s.get("muted", False), bool):
            raise ValueError("Speaker mute must be true or false")
        s.setdefault("muted", False)
        if not isinstance(s.get("use_source_reference", False), bool):
            raise ValueError("Original voice reference must be true or false")
        s.setdefault("use_source_reference", False)
        if s.get("source_reference") and (not isinstance(s["source_reference"], dict) or not isinstance(s["source_reference"].get("asset"), str)):
            raise ValueError("Invalid original voice reference")
        s["name"] = str(s.get("name","Speaker"))[:80]
        if not re.fullmatch(r"#[0-9a-fA-F]{6}",s.get("color","")):
            raise ValueError("Invalid speaker color")
        voice = s.get("voice",{})
        if voice.get("adapter"):
            registry.get(voice["adapter"],"synthesis")
        if voice.get("conversion"):
            registry.get(voice["conversion"]["id"],"voice_conversion")
        if s.get("reference") and not isinstance(s["reference"],str):
            raise ValueError("Invalid reference")
    ids = set()
    max_duration = p["media"]["duration"] if p["media"] else 86400
    if len(p["dialogue"])>30000:
        raise ValueError("Too many dialogue lines")
    for line in p["dialogue"]:
        if not isinstance(line.get("id"),str) or line["id"] in ids:
            raise ValueError("Dialogue IDs must be unique")
        ids.add(line["id"])
        line["start"] = number(line.get("start"),0,max_duration,"Start time")
        line["end"] = number(line.get("end"),line["start"]+0.02,max_duration+0.001,"End time")
        if "source_start" in line or "source_end" in line:
            line["source_start"] = number(line.get("source_start"),0,max_duration,"Original start time")
            line["source_end"] = number(line.get("source_end"),line["source_start"]+.02,max_duration+.001,"Original end time")
        if line.get("speaker") not in speaker_ids:
            raise ValueError("Dialogue refers to an unknown speaker")
        for key in ("source","translation","subtitle"):
            if not isinstance(line.get(key,""),str) or len(line.get(key,""))>20000:
                raise ValueError("Invalid dialogue text")
        if not isinstance(line.get("auto_fit",True),bool):
            raise ValueError("Automatic timing must be true or false")
        line["playback_rate"] = number(line.get("playback_rate",1),.8,1.25,"Speech speed")
        line["gain"] = number(line.get("gain",1),0,4,"Line gain")
        if line.get("audio") and not isinstance(line["audio"].get("asset"),str):
            raise ValueError("Invalid dialogue audio")
    for cap,selection in p["models"].items():
        registry.get(selection["id"],cap)
        if not isinstance(selection.get("settings",{}),dict):
            raise ValueError("Invalid model settings")
    settings = p["settings"]
    for key, default in (("original_muted", False), ("background_muted", False), ("video_visible", True), ("subtitles_visible", True)):
        if not isinstance(settings.get(key, default), bool):
            raise ValueError(f"{key} must be true or false")
        settings.setdefault(key, default)
    settings["estimated_speech_wpm"] = number(settings.get("estimated_speech_wpm",150),80,240,"Estimated speaking pace")
    for key in ("background_gain","dialogue_gain"):
        settings[key] = number(settings.get(key,1),0,2,key)
    if settings.get("output") not in ("mkv","mp4"):
        raise ValueError("Output must be MKV or MP4")
    if settings.get("background_mode") not in ("separated","original","silence"):
        raise ValueError("Invalid background mode")
    if p["media"]:
        for key,kind in (("video_stream","video"),("audio_stream","audio"),("subtitle_stream","subtitle")):
            index = settings.get(key)
            if index is not None and not any(s["index"]==index and s["type"]==kind for s in p["media"]["streams"]):
                raise ValueError("Selected media track does not exist")
    return p


def create_app(data_dir: Path = DATA, dist_dir: Path | None = None):
    store = Store(data_dir)
    registry = Registry()
    jobs = Jobs(store,registry)

    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.closed.set()
        await run_in_threadpool(jobs.thread.join, 15)

    app = FastAPI(title="KOTO Studio",version="0.2.5",lifespan=lifespan)
    app.state.store,app.state.jobs,app.state.registry = store,jobs,registry
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=["localhost","127.0.0.1","testserver","tauri.localhost"])
    app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173","http://localhost:8765","http://127.0.0.1:8765","tauri://localhost","http://tauri.localhost"],allow_methods=["GET","POST","PATCH"],allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in ("POST","PATCH","DELETE") and origin:
            if urlparse(origin).hostname not in ("127.0.0.1","localhost","tauri.localhost"):
                return JSONResponse({"detail":"Only the local editor may modify projects"},status_code=403)
        return await call_next(request)

    @app.exception_handler(KeyError)
    async def not_found(request,error):
        return JSONResponse({"detail":str(error)},status_code=404)

    @app.exception_handler(ValueError)
    async def bad_request(request,error):
        return JSONResponse({"detail":str(error)},status_code=400)

    @app.exception_handler(RuntimeError)
    async def runtime_error(request,error):
        return JSONResponse({"detail":str(error)},status_code=422)

    def project(pid):
        try:
            uuid.UUID(pid)
        except ValueError:
            raise HTTPException(404,"Project not found")
        return store.get(pid)

    async def upload(pid, file, allowed=None):
        project(pid)
        suffix = Path(file.filename or "upload").suffix.lower()
        if allowed and suffix not in allowed:
            raise ValueError("Unsupported file type")
        suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,10}",suffix) else ".bin"
        target = store.asset(pid,uuid.uuid4().hex+suffix)
        # Disk writes run off the event loop; large episodes don't block progress polling.
        def copy():
            with target.open("wb") as f:
                shutil.copyfileobj(file.file,f,length=4*1024*1024)
        await run_in_threadpool(copy)
        return target

    @app.get("/api/health")
    async def health():
        def inspect():
            gpu = None
            try:
                smi = executable("nvidia-smi")
            except RuntimeError:
                smi = None
            if smi:
                try:
                    result = subprocess.run([smi,"--query-gpu=name,memory.total,driver_version","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=4)
                    if result.returncode==0:
                        row = result.stdout.splitlines()[0].split(",")
                        gpu = {"name":row[0].strip(),"vram_mb":int(row[1]),"driver":row[2].strip()}
                except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):
                    pass
            available = {}
            for name in ("ffmpeg","ffprobe"):
                try:
                    executable(name)
                    available[name] = True
                except RuntimeError:
                    available[name] = False
            return {"version":"0.2.5","local":True,**available,"gpu":gpu}
        return await run_in_threadpool(inspect)

    @app.get("/api/models")
    async def models():
        return await run_in_threadpool(registry.list)

    @app.get("/api/separation/models")
    def separation_models():
        return catalog()

    @app.post("/api/projects/{pid}/separations/{result_id}/activate")
    def activate_separation(pid:str,result_id:str,body:dict):
        project(pid)
        if any(j["status"] in ("queued","running") for j in store.jobs(pid)):
            raise HTTPException(409,"Wait for active jobs or cancel them before switching separation results")
        def merge(p):
            record = next((r for r in p.get("separations",[]) if r["id"] == result_id), None)
            if record is None:
                raise KeyError("Separation result not found")
            if not all(store.asset(pid,record["assets"][key]).is_file() for key in ("vocals","background")):
                raise ValueError("Saved separation assets are missing")
            return activate(p,record)
        try:
            return store.update(pid,merge,body.get("revision"))
        except ValueError as error:
            if str(error).startswith("Project changed"):
                raise HTTPException(409,str(error))
            raise

    @app.get("/api/projects")
    def list_projects():
        return store.list()

    @app.post("/api/projects")
    def new_project(body: NewProject):
        return store.create(body.name,body.demo)

    @app.get("/api/projects/{pid}")
    def get_project(pid:str):
        return project(pid)

    @app.get("/api/projects/{pid}/download")
    def download_project(pid:str):
        p = project(pid)
        return JSONResponse(p,headers={"Content-Disposition":"attachment; filename=koto-project.json"})

    @app.patch("/api/projects/{pid}")
    def patch_project(pid:str,body:ProjectPatch):
        project(pid)
        changes = body.model_dump(exclude_none=True,exclude={"revision"})
        def merge(p):
            previous_settings = dict(p["settings"])
            previous_export = {k:p[k] for k in ("dialogue","speakers","models","settings")}
            old = {l["id"]:l for l in p["dialogue"]}
            p.update(changes)
            validate_project(p,registry)
            # UI cannot invent file paths or attach another project's audio.
            for s in p["speakers"]:
                if s.get("reference") and not store.asset(pid,s["reference"]).is_file():
                    raise ValueError("Speaker reference does not exist")
                if s.get("source_reference") and not store.asset(pid,s["source_reference"]["asset"]).is_file():
                    raise ValueError("Original voice reference does not exist")
            for line in p["dialogue"]:
                prior = old.get(line["id"])
                if line.get("audio") and (not prior or prior.get("audio")!=line["audio"]):
                    path = store.asset(pid,line["audio"]["asset"])
                    if not path.is_file() or path.suffix.lower() not in (".wav",".mp3",".flac",".m4a",".ogg"):
                        raise ValueError("Use the audio upload endpoint to attach a voice take")
                if line.get("audio") and line["audio"].get("kind")=="generated" and line["audio"].get("signature")!=signature(p,line):
                    line["audio"] = None
                    line["warning"] = "Text or voice changed. Regenerate this line."
            # Choosing a model for a prospective separation preview does not
            # change the active stems or any existing render.
            old_render_models = {k:v for k,v in previous_export['models'].items() if k != 'separation'}
            new_render_models = {k:v for k,v in p['models'].items() if k != 'separation'}
            if old_render_models != new_render_models or any(p[k]!=previous_export[k] for k in ('dialogue','speakers','settings')):
                for key in ("export","dub_audio","english_subtitles"):
                    p["assets"].pop(key,None)
            if any(p["settings"].get(k)!=previous_settings.get(k) for k in ("audio_stream","video_stream","subtitle_stream")):
                p["active_separation"] = None
                for key in ("preview","original_audio","vocals","background"):
                    p["assets"].pop(key,None)
            return p
        try:
            return store.update(pid,merge,body.revision)
        except ValueError as e:
            if str(e).startswith("Project changed"):
                raise HTTPException(409,str(e))
            raise

    @app.post("/api/projects/{pid}/media")
    async def import_media(pid:str,file:UploadFile=File(...)):
        p = project(pid)
        if any(j["status"] in ("queued","running") for j in store.jobs(pid)):
            raise HTTPException(409,"Wait for active jobs or cancel them before replacing media")
        target = await upload(pid,file)
        try:
            metadata = await run_in_threadpool(probe,target)
            if not 0 < metadata["duration"] <= 86400:
                raise ValueError("Media must have a known duration between 0 and 24 hours")
        except Exception:
            target.unlink(missing_ok=True)
            raise
        def merge(p):
            p["media"] = {"asset":target.name,"name":Path(file.filename or "Source").name,**metadata}
            p["active_separation"] = None
            p["assets"] = {}
            p["dialogue"] = []
            p["demo"] = False
            p["name"] = Path(file.filename or "Untitled").stem[:120]
            for kind,key in (("video","video_stream"),("audio","audio_stream"),("subtitle","subtitle_stream")):
                streams = [s for s in metadata["streams"] if s["type"]==kind and (kind != "subtitle" or s["codec"] not in IMAGE_SUBTITLE_CODECS)]
                p["settings"][key] = streams[0]["index"] if streams else None
            return p
        return store.update(pid,merge)

    @app.post("/api/projects/{pid}/subtitles")
    async def import_subtitles(pid:str,file:UploadFile=File(...),language:str=Form("en")):
        project(pid)
        if language not in ("en","ja","zh"):
            raise ValueError("Subtitle language must be en, ja or zh")
        path = await upload(pid,file,{".srt",".vtt",".ass",".ssa"})
        if path.suffix in (".ass",".ssa"):
            converted = path.with_suffix(".srt")
            def convert():
                result = subprocess.run([binary("ffmpeg"),"-y","-v","error","-i",str(path),str(converted)],capture_output=True,text=True,timeout=60)
                if result.returncode:
                    raise ValueError("Could not convert subtitle file: "+result.stderr[-500:])
            await run_in_threadpool(convert)
            path = converted
        if path.stat().st_size>10*1024*1024:
            raise ValueError("Subtitle file is too large")
        lines = parse_subtitles(path.read_text(encoding="utf-8-sig"))
        if not lines:
            raise ValueError("No readable subtitle lines found")
        for line in lines:
            line["source" if language!="en" else "translation"] = line["subtitle"]
        def merge(p):
            if not p["dialogue"]:
                p["dialogue"] = lines
            else:
                for line in p["dialogue"]:
                    matches = [(max(0,min(s["end"],line["end"])-max(s["start"],line["start"])),s) for s in lines]
                    overlap,best = max(matches,key=lambda m:m[0])
                    if overlap:
                        line["subtitle"] = best["subtitle"]
                        if language=="en" and not line.get("translation"):
                            line["translation"] = best["translation"]
                        if language!="en" and not line.get("source"):
                            line["source"] = best["source"]
            p["assets"]["source_subtitles"] = path.name
            for key in ("export","dub_audio","english_subtitles"):
                p["assets"].pop(key,None)
            validate_project(p,registry)
            return p
        return store.update(pid,merge)

    @app.post("/api/projects/{pid}/speakers/{sid}/reference")
    async def reference(pid:str,sid:str,file:UploadFile=File(...)):
        p = project(pid)
        if not any(s["id"]==sid for s in p["speakers"]):
            raise KeyError("Speaker not found")
        raw = await upload(pid,file,{".wav",".mp3",".flac",".m4a",".ogg"})
        metadata = await run_in_threadpool(probe,raw)
        if not 3 <= metadata["duration"] <= 120:
            raise ValueError("Reference audio must be 3–120 seconds; clean speech works best")
        def merge(p):
            speaker = next(s for s in p["speakers"] if s["id"]==sid)
            speaker["reference"] = raw.name
            for key in ("export","dub_audio","english_subtitles"):
                p["assets"].pop(key,None)
            for line in p["dialogue"]:
                if line["speaker"]==sid and line.get("audio",{} ) and line["audio"].get("kind")=="generated":
                    line["audio"] = None
            return p
        return store.update(pid,merge)

    @app.post("/api/projects/{pid}/dialogue/{lid}/audio")
    async def line_audio(pid:str,lid:str,file:UploadFile=File(...)):
        p = project(pid)
        if not any(l["id"]==lid for l in p["dialogue"]):
            raise KeyError("Dialogue line not found")
        path = await upload(pid,file,{".wav",".mp3",".flac",".m4a",".ogg"})
        metadata = await run_in_threadpool(probe,path)
        def merge(p):
            line = next(l for l in p["dialogue"] if l["id"]==lid)
            line["audio"] = {"asset":path.name,"duration":metadata["duration"],"kind":"imported"}
            for key in ("export","dub_audio","english_subtitles"):
                p["assets"].pop(key,None)
            line["warning"] = "Imported take exceeds slot; adjust timing or replace it" if metadata["duration"]>(line["end"]-line["start"])*1.25 else ""
            return p
        return store.update(pid,merge)

    @app.get("/api/projects/{pid}/assets/{asset:path}")
    def get_asset(pid:str,asset:str):
        project(pid)
        path = store.asset(pid,asset)
        if not path.is_file():
            raise KeyError("Asset not found")
        return FileResponse(path)

    @app.get("/api/projects/{pid}/waveform/{asset:path}")
    def waveform(pid:str,asset:str):
        import array
        import wave
        import sys
        project(pid)
        path = store.asset(pid,asset)
        if not path.is_file() or path.suffix.lower() != ".wav":
            raise ValueError("Waveform preview requires a WAV asset")
        cache = path.with_suffix(".peaks.json")
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        with wave.open(str(path),"rb") as w:
            if w.getsampwidth()!=2:
                raise ValueError("Waveform preview requires PCM16 audio")
            size = max(1,(w.getnframes()+359)//360)
            peaks = []
            for i in range(360):
                raw = w.readframes(size)
                samples = array.array("h",raw)
                if sys.byteorder=="big":
                    samples.byteswap()
                peaks.append(round(max((abs(v)/32768 for v in samples[::8]),default=0),4))
        cache.write_text(json.dumps(peaks),encoding="utf-8")
        return peaks

    @app.get("/api/projects/{pid}/jobs")
    def get_jobs(pid:str):
        project(pid)
        return store.jobs(pid)

    @app.post("/api/projects/{pid}/jobs")
    def new_job(pid:str,body:NewJob):
        project(pid)
        jid = jobs.enqueue(pid,body.kind,body.options)
        return {"id":jid}

    @app.post("/api/jobs/{jid}/cancel")
    def cancel_job(jid:str):
        jobs.cancel(jid)
        return {"ok":True}

    dist = dist_dir or ROOT / "frontend" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets",StaticFiles(directory=dist/"assets"),name="frontend-assets")

    @app.get("/")
    def index():
        if (dist/"index.html").is_file():
            return FileResponse(dist/"index.html")
        return JSONResponse({"message":"Frontend not built. Run python scripts/build_frontend.py from the project folder.","docs":"/docs"})

    return app


app = create_app()
