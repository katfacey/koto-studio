"""Cancellable process for local Ollama translation."""
import json
import sys
import urllib.request
from pathlib import Path

from runtime import configure_process, ollama_url
configure_process()

spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
alternatives = spec.get("mode") == "alternatives"
schema = {"type":"object","properties":{"alternatives":{"type":"array","items":{"type":"string"},"minItems":3,"maxItems":3}},"required":["alternatives"]} if alternatives else {"type":"object","properties":{"translation":{"type":"string"}},"required":["translation"]}
system = "Adapt the supplied Japanese or Chinese dialogue into spoken English. Preserve meaning, speaker intent and tone using the source and context. Suggest exactly three alternative phrasings: concise, closest to the supplied duration and slightly fuller. Aim for the supplied duration and word budget, without inventing information. Return JSON with an alternatives array of three nonempty strings. Do not include commentary." if alternatives else "You adapt Japanese or Chinese dialogue into natural spoken English. Use surrounding context and subtitle references, preserve meaning and tone, and aim for the supplied duration at a normal speaking pace. Translate only the requested line. Return JSON with one nonempty translation string. Never include reasoning or commentary."
payload = {
    "model": spec["model"], "stream": False, "think": False,
    "format": schema,
    "messages": [
        {"role":"system","content":system},
        {"role":"user","content":spec["prompt"]},
    ],
    "options": {"temperature":spec["temperature"]}, "keep_alive": 0,
}
req = urllib.request.Request(ollama_url()+"/api/chat",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=600) as response:
    body = json.load(response)
result = json.loads(body["message"]["content"])
if not alternatives and (not isinstance(result.get("translation"),str) or not result["translation"].strip()):
    raise ValueError("Translation model returned no English text")
Path(sys.argv[2]).write_text(json.dumps(result),encoding="utf-8")
