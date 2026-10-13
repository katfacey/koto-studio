# Release validation · v0.2.0 · 2026-10-13

Local checks: Linux, Python 3.12, FFmpeg 7.1.5, Node 24.
Windows checks: GitHub-hosted Windows, managed Python 3.11, bundled FFmpeg 9.0.2.

**[Windows standalone installation and real Piper synthesis passed](https://github.com/katfacey/koto-studio/actions/runs/38384120806).**

The following checks passed:

- Eighteen backend/runtime tests, including HTTP requests through the real ASGI application and
  real FFmpeg media operations. They cover MKV import and track inspection,
  audio extraction, preview encoding, subtitles, imported voice takes, MKV and
  MP4 output, output duration, sample-level placement of voice clips, silent
  gaps, English track metadata, waveform peaks, HTTP range requests, project
  reopening, failed export validation, model worker protocol, subprocess
  cancellation, interrupted job history, revision conflicts, voice take
  invalidation, TTS-to-conversion ordering, speaker conversion overrides, and
  reuse of cached takes. Image subtitle metadata is excluded from default track
  selection; explicit image-subtitle selection and empty track selection fail
  before a job starts. Retrying without subtitles produces real audio/preview
  assets, with FFmpeg progress captured.
- Managed Windows executable lookup with an empty PATH, rejection of system
  FFmpeg fallback, absolute driver/cancellation paths, app-owned caches and CUDA
  DLL directories, loopback-only translation endpoints, distribution manifests
  that exclude installed tools/user data, and translation process ownership.
- Browser-module JavaScript syntax checks.
- Renderer/action smoke checks in a minimal DOM harness: editor and timeline
  rendering, escaped user content, dialogue edit/save, speaker creation, model
  dialog, and dialogue table. Prepare checks cover the image-subtitle recovery
  button, queued/running/failed/completed jobs, visible failure messages, and
  immediate validation errors. The HTTP fixtures in this harness are test data.
- Python compilation.
- Dependency-free frontend build.
- Windows PowerShell 5.1 installation of Piper with the real downloaded Lessac
  voice and UTF-8, case-sensitive phoneme config validation through private Python.
  The actual isolated Piper worker generated 2.68 seconds of non-silent English
  speech on CPU with PATH limited to Windows System32.

Test-only model workers return deterministic fixture audio/text. No GPU model
output is represented as tested GPU inference. Actual Demucs, Whisper, Pyannote,
XTTS, Ollama, and third-party RVC execution require their packages,
configured weights, and a compatible host. They were not installed/executed here.

The passing Windows GitHub Actions workflow parses PowerShell installers, installs
the core with PATH restricted to Windows System32, asserts that Python/FFmpeg are
app-owned, runs the 18 tests, and starts the actual server/editor. The standalone
workflow installs into a path with spaces and reinstalls the core while checking
that a project-data fixture survives. It also installs and exercises the real
Piper worker, separately from deterministic protocol fixtures.

Chromium launches failed because the execution sandbox denies its required
socket operations. Browser visual layout/playback, native pywebview mode,
optional GPU package installation, and RTX 5090 inference
have not been validated. The archive includes setup instructions and a CUDA
architecture/matrix diagnostic for the target machine.

Run checks again on the target host:

```powershell
& ".\runtime\uv\uv.exe" --no-config pip install --python ".\.venv\Scripts\python.exe" -r backend/requirements-dev.txt
& ".\.venv\Scripts\python.exe" -m unittest discover -s backend/tests -v
# Optional Node checks:
node frontend/check-ui.mjs
```
