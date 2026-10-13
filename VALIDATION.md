# Release validation · 2026-10-13

Environment: Linux, Python 3.12, FFmpeg 7.1.5, Node 24.

The following checks passed:

- Seven backend tests using HTTP requests through the real ASGI application and
  real FFmpeg media operations. They cover MKV import and track inspection,
  audio extraction, preview encoding, subtitles, imported voice takes, MKV and
  MP4 output, output duration, sample-level placement of voice clips, silent
  gaps, English track metadata, waveform peaks, HTTP range requests, project
  reopening, failed export validation, model worker protocol, subprocess
  cancellation, interrupted job history, revision conflicts, voice take
  invalidation, TTS-to-conversion ordering, speaker conversion overrides, and
  reuse of cached takes.
- Browser-module JavaScript syntax checks.
- Renderer/action smoke checks in a minimal DOM harness: editor and timeline
  rendering, escaped user content, dialogue edit/save, speaker creation, model
  dialog, and dialogue table. The HTTP fixtures in this harness are test data.
- Python compilation and Pinokio JavaScript syntax checks.
- Dependency-free frontend build.

Test-only model workers return deterministic fixture audio/text. No GPU model
output is represented as tested inference. Actual Demucs, Whisper, Pyannote,
Piper, XTTS, Ollama, and third-party RVC execution require their packages,
configured weights, and a compatible host. They were not installed/executed here.

Chromium launches failed because the execution sandbox denies its required
socket operations. Browser visual layout, video playback, Windows PowerShell
installation, native pywebview mode, Pinokio installation, and RTX 5090 inference
have not been validated. The archive includes setup instructions and a CUDA
architecture/matrix diagnostic for the target machine.

Run checks again on the target host:

```powershell
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python -m unittest discover -s backend/tests -v
# Optional Node checks:
node frontend/check-ui.mjs
```
