"""Cancellable process for local Ollama translation."""
import json
import sys
import urllib.request
from pathlib import Path

from runtime import configure_process, ollama_url
configure_process()

spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
payload = {
    "model": spec["model"], "stream": False, "think": False,
    "format": {"type":"object","properties":{"translation":{"type":"string"}},"required":["translation"]},
    "messages": [
        {"role":"system","content":"You adapt Japanese dialogue into natural spoken English. Use surrounding context and subtitle references, preserve meaning and tone, and aim for the supplied duration at a normal speaking pace. Translate only the requested line. Return JSON with one nonempty translation string. Never include reasoning or commentary."},
        {"role":"user","content":spec["prompt"]},
    ],
    "options": {"temperature":spec["temperature"]}, "keep_alive": 0,
}
req = urllib.request.Request(ollama_url()+"/api/chat",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=600) as response:
    body = json.load(response)
result = json.loads(body["message"]["content"])
if not isinstance(result.get("translation"),str) or not result["translation"].strip():
    raise ValueError("Translation model returned no English text")
Path(sys.argv[2]).write_text(json.dumps(result),encoding="utf-8")
