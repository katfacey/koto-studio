# Model adapter protocol

Built-in workers run outside the backend process in `.workers/audio`,
`.workers/whisper`, `.workers/piper`, and `.workers/xtts`. The local Ollama adapter
runs its cancellable HTTP client in a separate process and unloads the model
after each request. Only one processing job runs at a time.

To add an alternative separator, recognizer, TTS engine, translation engine, or
voice converter, create `models/adapters.json`. This is trusted, local application
configuration, not a project import format. Restart the backend to load it.

```json
[
  {
    "id": "my-rvc",
    "label": "My local RVC worker",
    "capability": "voice_conversion",
    "description": "Converts synthesized English speech using my installed RVC model.",
    "command": ["C:\\Tools\\RVC\\venv\\Scripts\\python.exe", "C:\\Tools\\RVC\\koto_worker.py"],
    "fields": [
      {"key": "model", "label": "RVC weights path", "type": "text", "default": ""},
      {"key": "index", "label": "Optional index path", "type": "text", "default": ""}
    ]
  }
]
```

`command` is an argument array. KOTO appends two arguments: a request JSON path
and a result JSON path. There is no shell interpolation. Your worker translates
this protocol into your chosen model's API; different RVC/UVR distributions have
different APIs and are not treated as interchangeable executables.

## Request

```json
{
  "adapter": "my-rvc",
  "capability": "voice_conversion",
  "settings": {"model": "C:\\Models\\voice.pth", "index": ""},
  "output_dir": "C:\\KOTO\\data\\projects\\...\\work_...",
  "audio": "C:\\KOTO\\data\\projects\\...\\speech.wav",
  "reference": null
}
```

Inputs vary by capability:

| Capability | Inputs | Result JSON |
| --- | --- | --- |
| `separation` | `audio` | `{"vocals":"absolute.wav","background":"absolute.wav"}` |
| `transcription` | `audio` | `{"lines":[{"start":1.2,"end":2.3,"source":"日本語"}]}` |
| `diarization` | `audio` | `{"turns":[{"start":1.2,"end":2.3,"speaker":"speaker-1"}]}` |
| `translation` | `lines` | `{"lines":[{"id":"existing-id","translation":"English"}]}` |
| `synthesis` | `text`, optional `reference` | `{"audio":"absolute.wav"}` |
| `voice_conversion` | synthesized `audio`, optional `reference` | `{"audio":"absolute.wav"}` |

All returned audio paths must point to files **inside `output_dir`**. Write the
result JSON to the second argument and exit with code 0. On failure, write a
useful error to stderr and exit nonzero. Never indicate success before saving
your files. Artifact paths are validated before use.

Optional progress is written to stdout, one JSON line at a time:

```text
KOTO_EVENT {"progress":0.4,"message":"Converting voice"}
```

Cancellation terminates the worker process tree. Completed line takes are
preserved; interrupted work can be retried. Model package dependencies and model
licenses belong to the adapter's environment.

Voice conversion runs **after TTS and before timing normalization**. It can be
selected at project level, or overridden for an individual speaker. KOTO does
not ship an RVC model or a universal RVC wrapper; supply the bridge for the RVC
distribution you use. UVR/BS-RoFormer models use the same separation protocol.
