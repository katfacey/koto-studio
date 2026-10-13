# Release validation · v0.2.0 · 2026-10-13

Local checks: Linux, Python 3.12, FFmpeg 7.1.5, Node 24.
Windows checks: GitHub-hosted Windows, managed Python 3.11, bundled FFmpeg 9.0.2.

**[Windows installation and Pinokio folder setup passed](https://github.com/katfacey/koto-studio/actions/runs/38351990802).**

The following checks passed:

- Seventeen backend/runtime tests, including HTTP requests through the real ASGI application and
  real FFmpeg media operations. They cover MKV import and track inspection,
  audio extraction, preview encoding, subtitles, imported voice takes, MKV and
  MP4 output, output duration, sample-level placement of voice clips, silent
  gaps, English track metadata, waveform peaks, HTTP range requests, project
  reopening, failed export validation, model worker protocol, subprocess
  cancellation, interrupted job history, revision conflicts, voice take
  invalidation, TTS-to-conversion ordering, speaker conversion overrides, and
  reuse of cached takes.
- Managed Windows executable lookup with an empty PATH, rejection of system
  FFmpeg fallback, absolute driver/cancellation paths, app-owned caches and CUDA
  DLL directories, loopback-only translation endpoints, distribution manifests
  that exclude installed tools/user data, and translation process ownership.
- Browser-module JavaScript syntax checks.
- Renderer/action smoke checks in a minimal DOM harness: editor and timeline
  rendering, escaped user content, dialogue edit/save, speaker creation, model
  dialog, and dialogue table. The HTTP fixtures in this harness are test data.
- Python compilation and Pinokio JavaScript syntax checks.
- Pinokio menu checks and all eight managed installer entry points.
- Dependency-free frontend build.

Test-only model workers return deterministic fixture audio/text. No GPU model
output is represented as tested inference. Actual Demucs, Whisper, Pyannote,
Piper, XTTS, Ollama, and third-party RVC execution require their packages,
configured weights, and a compatible host. They were not installed/executed here.

The passing Windows GitHub Actions workflow parses PowerShell installers, installs
the core with PATH restricted to Windows System32, asserts that Python/FFmpeg are
app-owned, runs the 17 tests, and starts the actual server/editor. It also executes
the Pinokio folder installer using a Home path with spaces, verifies that the
copied application is bootstrapped, and reinstalls it while preserving a project
data fixture. This tests the installer without requiring the Pinokio desktop UI.

Chromium launches failed because the execution sandbox denies its required
socket operations. Browser visual layout/playback, native pywebview mode,
the Pinokio desktop UI, optional GPU package installation, and RTX 5090 inference
have not been validated. The archive includes setup instructions and a CUDA
architecture/matrix diagnostic for the target machine.

Run checks again on the target host:

```powershell
& ".\runtime\uv\uv.exe" --no-config pip install --python ".\.venv\Scripts\python.exe" -r backend/requirements-dev.txt
& ".\.venv\Scripts\python.exe" -m unittest discover -s backend/tests -v
# Optional Node checks:
node frontend/check-ui.mjs
node scripts/check-pinokio.mjs
```
