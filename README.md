# KOTO Studio · v0.1.0

A local Japanese-to-English dubbing editor for **Windows + NVIDIA**, designed
around an RTX 5090 with 32 GB VRAM. The first release includes a working media,
dialogue, voice, job, and export workflow. Its editor uses native browser modules
and needs no Node/npm installation. Python runs the local backend; optional AI
workers have separate environments.

## Start on Windows

1. Install **Python 3.11** from [python.org](https://www.python.org/downloads/),
   including the Windows Python launcher. Python 3.12 also works for the core.
2. Install FFmpeg, for example `winget install --id Gyan.FFmpeg -e`. Open a new
   terminal afterward and check that `ffmpeg -version` and `ffprobe -version`
   work. FFmpeg must include H.264/AAC encoding.
3. Extract the archive into a writable folder, such as `C:\KOTO Studio`.
4. Double-click **Install.cmd**, then **Start.cmd**.

The app opens at `http://127.0.0.1:8765`. Keep its terminal open; Ctrl+C stops it.
The service binds to loopback. Installation downloads core Python packages;
processing is local. Model weights are not bundled.

Optional native window:

```powershell
.venv\Scripts\python -m pip install pywebview
.venv\Scripts\python scripts\launch.py --desktop
```

This is a source-based application with launchers, not a signed standalone EXE.
Native window mode uses pywebview and may require Microsoft Edge WebView2.

## Pinokio

Import this local application folder using your Pinokio version's local-app or
developer workflow. `pinokio.js`, `install.js`, and `start.js` provide the menu,
core installation, and server startup. The installer uses Pinokio's conda
FFmpeg and its `env` Python environment. Optional worker installers appear in
the menu. The scripts are supplied and syntax-checked; they have not been run
inside Pinokio or on Windows in this build environment.

## Complete a project

1. **Import media.** MKV/MP4/MOV/WebM and other FFmpeg-readable files are
   inspected. Select video, audio, and subtitle streams in the Clip inspector.
   Importing another source into an existing media project creates a new project.
2. **Prepare.** Extract stereo 48 kHz audio and make a browser-compatible H.264
   proxy. The original video stays unchanged. Text subtitle streams become SRT.
   PGS/DVD image subtitle OCR is not included.
3. **Separate.** The Demucs adapter creates dialogue and background stems.
   Separation quality varies; review effects, breaths, and residual original
   dialogue. Demucs is a baseline, not a promise of clean dialogue isolation.
   Alternative separators can be added through the adapter protocol.
4. **Transcribe / diarize.** Whisper recognizes Japanese with timestamps.
   Subtitle references match by temporal overlap. Pyannote assigns the most
   overlapping speaker and flags possible overlaps; it does not isolate
   simultaneously speaking voices. You can assign speakers manually.
5. **Translate.** Local Ollama receives the line, nearby dialogue, subtitle
   reference, and target duration. English remains editable. Review meaning,
   pronouns, terminology, and timing; there is no guarantee that an LLM's line
   will fit until synthesized.
6. **Generate.** Assign project or speaker voices, attach clean reference audio
   if needed, and generate individual lines or the whole dialogue list.
   Synthesized lines are cached. An optional conversion adapter can process TTS
   output through a pretrained voice model before timing adjustment.
7. **Review.** Preview takes, edit line timestamps, drag trim handles, change
   levels, and regenerate. You can import replacement WAV/MP3/FLAC/M4A/OGG takes.
   Changing English text or voice configuration invalidates generated takes.
8. **Export.** Choose separated background, original audio (which retains
   original dialogue), or silence. Export requires a replacement take for every
   dialogue line. Modest time stretching is supported; overlong speech fails
   validation rather than being cut off. MKV copies source video; MP4 encodes
   H.264. Both include English AAC and an English subtitle track. Download the
   video, mixed WAV, and SRT from Export or completed Jobs.

The sample project is illustrative: it contains editable example dialogue and
clearly labeled artwork/waveforms. It has no source video or generated voice
takes. No inference is simulated. A complete manual dub is possible without AI
workers by importing subtitles and replacement takes.

## Install optional workers

From the application folder:

```powershell
powershell -File scripts/install-model.ps1 -Model whisper
powershell -File scripts/install-model.ps1 -Model audio
powershell -File scripts/install-model.ps1 -Model piper
powershell -File scripts/install-model.ps1 -Model xtts
```

Install only what you intend to use. These scripts use separate Python 3.11
environments. The audio/XTTS installers use CUDA 12.8 PyTorch wheels and run a
GPU architecture/matrix check. They do not download voice weights or gated
pyannote pipelines. Click **Refresh status** in Model manager after installation.
They pin PyTorch/torchaudio 2.7.1 and pyannote 3.x to avoid newer audio I/O
dependencies being introduced into the baseline worker environments.

| Adapter | Required setup |
| --- | --- |
| Demucs | Audio worker; defaults to `htdemucs`. First use downloads its weights. |
| Faster Whisper | Whisper worker; `large-v3`, another supported model, or a local model directory. First use of a model name downloads weights. |
| Pyannote | Audio worker; locally provisioned pipeline YAML and local weights. Obtain any gated models through their own setup process, then configure local paths. |
| Ollama | Install [Ollama](https://ollama.com/), run `ollama pull qwen3:14b`, and keep the local service running on port 11434. Choose an installed model in Model manager. |
| Piper | Piper worker; English `.onnx` voice plus matching `.onnx.json` from a compatible [Piper voice distribution](https://huggingface.co/rhasspy/piper-voices). Set the full local `.onnx` path. Does not clone voices. |
| XTTS v2 | XTTS worker; local model folder with `config.json`, `model.pth`, `vocab.json`, and required auxiliary files. Set its directory and attach a speaker reference. |
| RVC / other converters | Provide a distribution-specific worker through [models/README.md](models/README.md). RVC converts synthesized speech; it is not TTS. |

**GPU compatibility is not verified on an RTX 5090 here.** PyTorch must support
Blackwell `sm_120`; old wheels bundled with model projects may not. Faster
Whisper uses CTranslate2, not PyTorch, and CUDA execution on Windows needs
compatible CUDA 12 cuBLAS and cuDNN 9 DLLs available on PATH; inspect its current
installation requirements. Choose CPU/int8 while diagnosing that setup.

The single-worker queue releases model processes between stages. Ollama uses
`keep_alive: 0`. The 32 GB VRAM target provides room for substantial audio and
translation models but does not guarantee compatibility with every model.
Cloud inference adapters are not included in this release.

## Project data and extensibility

`data/studio.sqlite` stores projects and job history. Original media, preview
proxies, stems, references, takes, and renders live under
`data/projects/<project-id>/`. Save edits with Ctrl+S or the Save button; actions
that submit work also save first. Undo/redo is available for local edits.

Back up the **whole `data` folder**. Downloaded project JSON is metadata, not a
self-contained media bundle. There is no project JSON reimport UI yet. Cached
and abandoned artifacts are retained; automatic cache cleanup is not included.
Allow substantial disk space for PCM stems and render intermediates.

Jobs capture a project revision. Failed/interrupted jobs can be retried using
current settings; generated lines completed before cancellation are preserved.
The first release does not resume a model halfway through a single line.

See [models/README.md](models/README.md) for argument-array worker commands,
requests/results, progress events, and optional voice conversion. Add trusted
adapters locally and restart the backend. Model availability indicates a worker
package/executable is installed; it does not mean its weights are configured or
GPU inference has passed.

## Development and verification

```bash
python -m venv .venv
# Activate .venv using your platform's command.
python -m pip install -r backend/requirements-dev.txt
python scripts/build_frontend.py
python -m uvicorn koto.app:app --app-dir backend --host 127.0.0.1 --port 8765
python -m unittest discover -s backend/tests -v
```

Node is optional and can syntax-check browser modules with
`node --check frontend/src/app.js`. `node frontend/check-ui.mjs` runs renderer
and action smoke checks with a minimal DOM harness, including text escaping,
dialogue saving, speaker creation, and model configuration. It does not test
browser playback or visual layout. API documentation is at `/docs`.

Validated in Linux with real FFmpeg: import/extract/preview, subtitle alignment,
manual voice takes, rendered duration and audio placement, MKV/English stream
metadata, asset range requests, persistence, cancelled process trees, revision
conflicts, and generated-take invalidation. Test-only workers exercise the
extension protocol. GPU model inference, Windows installation, native-window
startup, and Pinokio execution remain unverified. Chromium visual validation was
blocked by this execution sandbox's socket restrictions.

## Scope of v0.1

This is a usable dubbing foundation, not a replacement for a mature NLE. It
does not include video inpainting, sexual-content uncensoring, lip sync,
automatic OCR, speaker-overlap source separation, a pretrained RVC bundle,
multi-channel spatial mixing, a signed installer, or hosted model processing.
Subtitles are matched by time overlap; dedicated forced alignment and automatic
translation repair loops remain later work.
