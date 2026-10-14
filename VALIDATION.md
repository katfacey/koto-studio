# Validation · KOTO Studio 0.2.5

**[Windows 0.2.5 validation passed](https://github.com/katfacey/koto-studio/actions/runs/38520342988).**
The run verifies the 0.2.5 health/launcher labels, standalone setup, all 37 backend
tests, real Piper/XTTS batches, and actual Chromium editing, playback and export.
Its [editor screenshot](https://github.com/katfacey/koto-studio/actions/runs/38520342988/artifacts/11873252917)
is included in the README. The final follow-up commit updates documentation and
the screenshot only; it does not change the runtime code that passed this run.

## Passed checks

- **37 backend tests** through the actual FastAPI/SQLite and FFmpeg paths: media
  import/prepare, text subtitles, source-track selection, timings, project reopen,
  asset invalidation, revision conflicts, manual/imported takes, translation
  alternatives, reference caching, worker protocol, cancellation, partial batches,
  model configuration, and local runtime isolation.
- **Real MKV and MP4 rendering** preserves overlong speech. Sample-level checks
  verify clip placement, overlaps, full tails beyond the source video's end,
  final output duration, and audible AAC tails in the muxed files.
- **Windows standalone bootstrap** with Python/FFmpeg under the app folder and
  PATH limited to Windows System32, including installer parsing, an actual server
  launch, installation in a path with spaces, and preserving data on reinstall.
- **Real Piper inference**, single-line and speaker batch, plus repair of a worker
  environment pointing at a moved installation.
- **Real XTTS inference on CPU**, using downloaded official weights and one loaded
  model/reference for a two-line batch. This is separate from worker-protocol fixtures.
- **Actual Chromium interaction on Windows**: panel resizing/persistence,
  clip reassignment/retiming/trimming, lane order, track mute/visibility, original
  reference selection, suggestion selection, live audio playback, delayed-save
  typing/trim races, real Piper generation, English-mix completion, keyboard
  deletion/undo, Render anyway, full-tail export/download, and the Cancel icon.
- **Frontend module checks** for rendering/actions, timing, timeline/monitor
  behavior, layout geometry, escaping, autosave failure recovery, and keyboard guards.

## Limits of that evidence

Protocol/provisioning tests use explicitly labeled fixtures. They do not establish
real Demucs, Whisper, gated pyannote, Ollama, or third-party conversion inference.
RTX 5090 execution, native pywebview mode, subjective voice similarity, separation
quality, translation quality, and a complete long episode still need evaluation
on the intended Windows PC. Local Linux browser launches are restricted by the
sandbox; actual browser evidence comes from the Windows runner.

## Reproduce

From an installed Windows app folder:

```powershell
& '.\runtime\uv\uv.exe' --no-config pip install --python '.\.venv\Scripts\python.exe' -r backend\requirements-dev.txt
& '.\.venv\Scripts\python.exe' -m unittest discover -s backend\tests -v
```

Optional frontend checks with Node:

```text
node frontend/check-ui.mjs
node frontend/check-timeline.mjs
node frontend/check-layout.mjs
```

The workflow in `.github/workflows/windows-bootstrap.yml` runs installer,
backend, real-model, and browser checks. Model scripts are
`scripts/check_piper.py`, `scripts/check_reference_voice.py`, and
`scripts/check_editor_browser.py`. Install their corresponding workers first;
browser checks also require `scripts/requirements-ui-checks.txt` and Chromium.
