# Validation · KOTO Studio

## 0.3.0 feature baseline: character voice library and Qwen

**[Windows voice-library validation passed](https://github.com/katfacey/koto-studio/actions/runs/38637758558).**
This validates runtime commit `7fa562985094081e86701fea97cfab40dfe68a06`.
Subsequent documentation/image updates and 0.3.0 version labels retain this feature
baseline. The release workflow also requires Windows validation to pass for the
exact release commit before creating its tag and uploading the ZIP.

- All **48 backend tests** passed locally and on Windows, covering versioned
  profile reuse across projects, copied sample independence, explicit version
  adoption, clip overrides/fingerprints, retained takes and approved older-take export.
- Chromium exercised real library creation/assignment, clip-only changes, saved
  take selection, and version 2 remaining independent of a project's version 1.
- **Real Qwen3-TTS Base CPU inference** generated a two-line reference-conditioned
  batch; **VoiceDesign** generated an audition, then Base cloned that recording.
  The installed-model path ran locally with Hugging Face offline mode and only
  Windows system executables on PATH. No system SoX or FlashAttention build was used.
- Real Piper/XTTS, all three separation models, standalone bootstrap/repair and
  the existing editor/media/export checks also passed.
- Local renderer/layout/timeline/comparison checks passed. A selected take made
  for different text/voice settings displays a listening warning while remaining exportable.

[Actual Windows library screenshot](docs/images/voice-library-windows.png) shows
library version 2 alongside a project pinned to version 1. Its browser check used
real Piper output; separate Qwen tests used the actual downloaded Qwen weights.

These are CPU integration tests. RTX 5090 performance, voice similarity and
Japanese/Chinese reference quality still require target-machine listening/testing.
DramaBox was evaluated from upstream sources; no DramaBox GPU inference or working
built-in adapter is claimed. See [voice setup and evaluation](docs/VOICES.md).

## Separation feature baseline

**[Windows separation validation passed](https://github.com/katfacey/koto-studio/actions/runs/38632810248).**
This run validated runtime commit `726edac07a99d95354e69b4dd05aca00164a4a47` with
only Windows System32 executables on PATH. The documentation follow-up does not
change that runtime code.

- All **45 backend tests** passed, including preview/export preservation, history
  switching/reopen, cancellation, source changes, invalid model outputs, and
  padding container audio that ends before its video.
- The isolated worker installed without system Python, FFmpeg, a CUDA toolkit,
  or a local C++ build. The selected dependency versions and all three weight
  SHA-256 values are pinned.
- **Real MDX-Net, VR and BS-RoFormer CPU inference** ran through download,
  preview and full-separation project APIs using real Piper speech mixed with
  a synthetic tone. Both stems were distinct, non-silent, aligned, and converted
  to 48 kHz stereo PCM16; previews preserved project audio, and the full result
  activated while retaining preview history.
- Real Piper/XTTS checks and Chromium editing/playback/export checks passed.
  Chromium also checked model selection, architecture controls, source-range
  shortcuts, and unavailable-worker states in the new panel.
- Local renderer, layout, timeline/monitor and comparison-player checks passed.
  Comparison tests cover matching playback position, stale play promises, and
  stopping playback on result changes.

[Actual Windows separation-panel screenshot](docs/images/separation-windows.png)
shows the setup state, before that browser-test workspace installed the optional
worker/weights. Inference was validated separately with real installed models.

RTX 5090 CUDA/ONNX provider activation, full-episode performance, and Japanese/
Chinese dialogue quality still need target-machine testing and listening. This
validation proves integration/timing, not separation quality on arbitrary media.

## Released 0.2.5 baseline

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
node frontend/check-separation.mjs
```

The workflow in `.github/workflows/windows-bootstrap.yml` runs installer,
backend, real-model, and browser checks. Model scripts are
`scripts/check_piper.py`, `scripts/check_reference_voice.py`, and
`scripts/check_editor_browser.py`. Install their corresponding workers first;
browser checks also require `scripts/requirements-ui-checks.txt` and Chromium.
