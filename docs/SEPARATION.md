# Separation architecture

Separation is independent of the browser layout. Any future desktop/browser GUI
can use these APIs; the current panel is a replaceable client.

- `backend/koto/separation.py`: catalog, downloads, validation, active-result changes.
- `backend/koto/separation_worker.py`: audio-separator integration; Torch/ONNX stay outside the editor.
- `backend/koto/jobs.py`: cancellation, preview extraction, duration validation, PCM normalization and result history.
- `frontend/src/separation-panel.js`: first-pass controls and comparison player.

## API

| Request | Meaning |
| --- | --- |
| `GET /api/separation/models` | Curated models, architecture-specific fields, size, source/terms, installed status |
| `PATCH /api/projects/{id}` | Save `models.separation: {id, settings}` through normal revision-checked project edits |
| `POST /api/projects/{id}/jobs` with `{kind:"download_separation_model",options:{model_id:"mdx-inst-hq3"}}` | Explicit cancellable app-owned download |
| Same endpoint with `{kind:"separate",options:{preview:true,start:12,end:42}}` | Separate only a source range; preserve project stems/exports |
| Same endpoint with `{kind:"separate"}` | Separate full prepared source and activate if that source is still current |
| `GET /api/projects/{id}` | Includes backend-owned `separations` history and `active_separation` ID |
| `POST /api/projects/{id}/separations/{result_id}/activate` with `{revision:123}` | Activate a saved full result for the current source; reject previews/stale results |

Preview bounds are source-media seconds, limited to 0.25–120 seconds. The selected
clip shortcut uses original `source_start/source_end`, preserving edits on the
English timeline. Results store selection/settings, timestamp, source asset,
range, duration, preview/full flag, and original/vocals/background paths.
History is not writable through project PATCH. Existing projects lazily acquire
history when separation runs; no database migration is required.

Workers must return both stems inside their assigned output directory. The backend
rejects a duration difference over 250 ms, then pads/trims rounding at the tail to
exact source duration and converts to 48 kHz stereo PCM16. It does not stretch
speech or repair model-introduced latency. Preview extraction uses exact FFmpeg
source bounds. Full-result switching clears export caches and original-reference
voice takes while preserving imported takes and fixed/uploaded-reference voices.

## Local models and dependencies

`Install-Separation.cmd` creates `.workers/separator` with app-owned Python 3.11,
Torch 2.7.1 cu128, torchvision 0.22.1, audio-separator 0.47.0 and ONNX Runtime GPU
1.22.0. NumPy 2 dependencies are isolated from Demucs/pyannote. A uv override uses
samplerate 0.2.2's Windows wheel instead of upstream's old 0.1.0 source build.
App-owned FFmpeg and worker DLL directories enter only the child process PATH.
Nothing is written to Windows' user/system PATH.

The catalog exposes three vocal/instrumental models. Bundled UVR metadata and the
RoFormer YAML come from TRvlvr/application_data commit
`3826b05b570dbd4fbedbc807758803b35348ba1b`. Download jobs use catalog-controlled
HTTPS URLs, atomic file replacement, expected sizes, pinned SHA-256 verification, UVR metadata identification for MDX/VR, and SHA-256 receipts. A repeat
request verifies the installed file. Inference verifies weights and overrides
upstream download/metadata lookup with these local resources.

CPU selection overrides automatic GPU detection. CUDA requires working Torch and,
for MDX, a successfully activated ONNX CUDA session; runtime fallback is disabled.
RoFormer and VR use Torch. Inference chunks long input at 60 seconds using upstream's
chunk handling. Overlap/denoise/TTA controls affect compute and quality; larger
batches consume more memory. No ensemble feature is included yet.

To extend the curated catalog, add trusted weights/configuration and model fields,
verify their hashes/terms, and validate stem names and timings in the actual worker.
For arbitrary external engines, use the existing trusted custom-adapter protocol.

## Validation and limits

The backend suite checks preview side effects, result switching/reopen, source-change
races, cancellation, invalid durations/bounds/settings and failed/corrupt downloads.
The comparison-player check covers aligned switching and old asynchronous play callbacks.
Windows CI installs with only System32 on PATH, runs actual MDX/VR/RoFormer CPU
inference through project APIs on real Piper speech mixed with a synthetic tone,
and tests first-pass controls in Chromium. These prove integration and timing;
they do not establish dialogue separation quality or RTX 5090 GPU performance.
Listen to representative Japanese/Chinese dialogue before committing to a full episode.

Model downloads require network access; ordinary installed-model separation is local.
Model weight terms are separate from KOTO's MIT license. Separation history uses
disk space and currently has no automatic cleanup. Future GUI work can change the
view without changing these endpoints or stored project fields.
