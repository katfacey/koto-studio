from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from .store import ROOT
from .runtime import ollama_url, runtime_environment

BUILTINS = [
    {"id": "demucs", "label": "Demucs · HTDemucs", "capability": "separation", "module": "demucs", "environment": "audio", "description": "Local dialogue / accompaniment separation. Singing-oriented models may lose speech or effects.", "fields": [{"key":"model","label":"Model","type":"text","default":"htdemucs"},{"key":"device","label":"Device","type":"select","options":["cuda","cpu"],"default":"cuda"}]},
    {"id": "faster-whisper", "label": "Faster Whisper", "capability": "transcription", "module": "faster_whisper", "environment": "whisper", "description": "Japanese/Chinese speech recognition with timestamps. Models download on first use unless a local path is supplied.", "fields": [{"key":"model","label":"Model or local path","type":"text","default":"large-v3"},{"key":"language","label":"Source language","type":"select","options":["ja","zh","auto"],"default":"ja"},{"key":"device","label":"Device","type":"select","options":["cuda","cpu"],"default":"cuda"},{"key":"compute_type","label":"Precision","type":"select","options":["float16","int8_float16","int8","float32"],"default":"float16"}]},
    {"id": "pyannote", "label": "Pyannote · local pipeline", "capability": "diarization", "module": "pyannote.audio", "environment": "audio", "description": "Run Install-Diarization.cmd to download weights with your Hugging Face account. Accept both model access agreements first. Blank paths use the app-managed pipeline; inference stays local.", "fields": [{"key":"model","label":"Local pipeline YAML","type":"text","default":"runtime/models/pyannote/pipeline.yaml"},{"key":"device","label":"Device","type":"select","options":["cuda","cpu"],"default":"cuda"}]},
    {"id": "ollama", "label": "Ollama · local LLM", "capability": "translation", "module": None, "environment": None, "description": "App-managed Ollama on 127.0.0.1:11435. Run Install-Translation.cmd.", "fields": [{"key":"model","label":"Installed Ollama model","type":"text","default":"qwen3:14b"},{"key":"temperature","label":"Temperature","type":"number","default":0.2}]},
    {"id": "piper", "label": "Piper · English voices", "capability": "synthesis", "module": "piper", "environment": "piper", "description": "Fast local speech synthesis. Supply an English .onnx voice and matching .onnx.json file. Does not clone voices.", "fields": [{"key":"model","label":"Voice .onnx path","type":"text","default":"runtime/models/piper/en_US-lessac-medium.onnx"},{"key":"speaker_id","label":"Voice index","type":"number","default":0}]},
    {"id": "xtts", "supports_reference": True, "label": "XTTS v2 · reference voice", "capability": "synthesis", "module": "TTS", "environment": "xtts", "description": "Cross-language reference-conditioned speech. Run Install-Reference-Voices.cmd for app-owned XTTS weights and worker. Use original dialogue or an uploaded speaker sample.", "fields": [{"key":"model","label":"Local XTTS model directory","type":"text","default":"runtime/models/xtts"},{"key":"device","label":"Device","type":"select","options":["cuda","cpu"],"default":"cuda"}]},
]


def interpreter(adapter):
    env = adapter.get("environment")
    if not env:
        return sys.executable
    configured = os.environ.get("KOTO_WORKER_" + env.upper())
    if configured:
        return configured
    venv = ROOT / ".workers" / env
    path = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if os.name == "nt" and path.exists():
        config = venv / "pyvenv.cfg"
        text = config.read_text(encoding="utf-8-sig").replace("\\", "/").casefold() if config.exists() else ""
        managed = str(ROOT / "runtime" / "python").replace("\\", "/").casefold()
        if managed not in text:
            installer = {"piper": "Install-Piper.cmd", "xtts": "Install-Reference-Voices.cmd"}.get(env, "Install-Models.cmd")
            raise RuntimeError(f"The {env} worker points outside the current app folder, possibly because the app was moved. Close KOTO, run {installer} in this folder to repair it, then restart.")
    return str(path) if path.exists() else sys.executable


def module_available(adapter):
    module = adapter.get("module")
    if not module:
        return True
    try:
        py = interpreter(adapter)
        if py == sys.executable:
            return importlib.util.find_spec(module) is not None
        result = subprocess.run([py, "-c", "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)", module], capture_output=True, env=runtime_environment(python=py), timeout=15)
        return result.returncode == 0
    except (ImportError, ModuleNotFoundError, OSError, RuntimeError, subprocess.TimeoutExpired):
        return False


def local_json(path, payload=None, timeout=10):
    # Never send dialogue to a remote provider; local Ollama only.
    req = urllib.request.Request(ollama_url() + path, data=json.dumps(payload).encode() if payload is not None else None, headers={"Content-Type":"application/json"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
        return json.load(response)


class Registry:
    def __init__(self):
        self.adapters = {a["id"]: dict(a) for a in BUILTINS}
        manifest = ROOT / "models" / "adapters.json"
        if manifest.exists():
            for a in json.loads(manifest.read_text(encoding="utf-8")):
                if a.get("capability") not in {"separation","transcription","diarization","translation","synthesis","voice_conversion"}:
                    raise ValueError("Invalid adapter capability")
                if not a.get("command") or not all(isinstance(s,str) for s in a["command"]):
                    raise ValueError("Custom adapters need an argument-array command")
                a["custom"] = True
                self.adapters[a["id"]] = a

    def get(self, aid, capability=None):
        adapter = self.adapters.get(aid)
        if not adapter or (capability and adapter["capability"] != capability):
            raise ValueError("Model adapter does not support this stage")
        return adapter

    def list(self):
        result = []
        for adapter in self.adapters.values():
            a = dict(adapter)
            if a["id"] == "ollama":
                try:
                    a["local_models"] = [m["name"] for m in local_json("/api/tags", timeout=1).get("models",[])]
                    a["available"] = True
                except Exception:
                    a["available"] = False
            elif a.get("custom"):
                import shutil
                a["available"] = bool(shutil.which(a["command"][0]) or Path(a["command"][0]).is_file())
            else:
                a["available"] = module_available(a)
            a["status"] = "Worker installed; configure model weights" if a["available"] else "Worker not installed" if a["id"] != "ollama" else "Ollama is not running"
            result.append(a)
        return result
