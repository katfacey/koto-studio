# KOTO Studio · v0.2.0

A local Japanese-to-English dubbing editor for **Windows x64 + NVIDIA**, designed
around an RTX 5090 with 32 GB VRAM. KOTO installs and runs its own Python, FFmpeg,
model environments, and optional local translation runtime inside the app folder.

**[Download the complete ZIP](https://github.com/katfacey/koto-studio/archive/refs/heads/main.zip)**

[Windows standalone bootstrap verified](https://github.com/katfacey/koto-studio/actions/runs/38351990802)
with only Windows System32 on PATH.

## Standalone installation

1. Download and extract the **whole ZIP** into a writable folder, such as
   `C:\KOTO Studio`. Close an older KOTO session before upgrading.
2. Double-click **Install.cmd**. It downloads verified UV and FFmpeg archives,
   installs private Python 3.11, and builds the core environment. It neither
   changes your system PATH nor registers Python as a system installation.
3. Double-click **Start.cmd**. Start also bootstraps the core if it is missing.
4. Use **Install-Models.cmd** to select optional voice/audio workers. For local
   translation, use **Install-Translation.cmd** or the translation choice in
   that menu. Restart KOTO after adding optional runtimes.

You do not need to install Python, FFmpeg, Node/npm, Ollama, or a CUDA toolkit
before running these installers. The host requirements are Windows 10/11 x64,
a browser, a compatible NVIDIA driver for GPU inference, internet for initial
package/model downloads, and enough disk space.

This is **self-contained after setup**, rather than an offline archive containing
all binaries and every model. The release ZIP includes source and built UI;
installation downloads the runtime files into the app directory. Basic voices
and freely downloadable weights can be installed/downloaded there. Gated models
and optional reference-voice checkpoints still need local provisioning.

The browser editor opens at `http://127.0.0.1:8765`. Keep the standalone terminal
open; Ctrl+C stops the server and its owned translation process. This is a
standalone Windows environment with a browser editor, not a signed EXE.

## What stays inside the application folder

| Location | Contents |
| --- | --- |
| `runtime/uv/` | Pinned, checksum-verified bootstrap executable |
| `runtime/python/` | Private managed Python installation |
| `runtime/ffmpeg/bin/` | Private FFmpeg, ffprobe, and companion files |
| `.venv/` | Core backend packages |
| `.workers/<worker>/` | Isolated AI environments and CUDA runtime libraries |
| `runtime/cache/` | Python package, Hugging Face, and Torch caches |
| `runtime/models/piper/` | Downloaded English voice and matching config |
| `runtime/ollama/` | Optional portable Ollama runtime |
| `runtime/models/ollama/` | Local translation weights |
| `runtime/logs/` | Translation server logs |
| `data/` | Projects, source media, takes, stems, and renders |

Application launches use explicit executable paths. FFmpeg lookups on Windows
require the managed binaries and do not silently use a system installation.
Model processes receive their own FFmpeg and CUDA library search directories;
no user/system PATH changes are made. NVIDIA tools and process cancellation use
known Windows system/driver locations. An external PATH fallback is available
only for Linux development or explicit developer opt-in.

Installers preserve project data. When migrating an older version, system-Python
virtual environments are recreated against the private Python. After moving the
installed folder, rerun Install.cmd and the optional profiles you use to repair
virtual-environment paths; installed environments are not assumed relocatable.

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

## Optional model installers

**Install-Models.cmd** presents these choices:

| Choice | Installs | Additional setup |
| --- | --- | --- |
| Default dubbing workers | Demucs, Pyannote package, Faster Whisper, Piper + English voice | Gated diarization pipeline still needs provisioning; recognition/separation weights download on first use. |
| XTTS | Reference-conditioned voice worker | Supply a local XTTS v2 model directory and a speaker reference. |
| Local translation | Private Ollama + Qwen3 14B | No system Ollama service needed. |
| All | All workers and local translation | Still provision gated/XTTS checkpoint files as needed. |

Torch 2.7.1/torchaudio 2.7.1 CUDA 12.8 wheels supply GPU libraries. The Whisper worker
also gets those local cuBLAS/cuDNN libraries; no separate CUDA toolkit or DLL
PATH setup is required by the managed installer. GPU compatibility is checked
with `scripts/check_gpu.py` during installation, but inference still depends on
model compatibility and your NVIDIA driver.

Piper setup downloads the English Lessac medium voice and config from one
immutable Hugging Face revision, verifies the ONNX LFS checksum, and selects
`runtime/models/piper/en_US-lessac-medium.onnx` by default for new projects.
Existing projects with an empty/old voice path can select that path in Model
manager. Piper does not clone voices. XTTS can use speaker reference samples.

Ollama runs at **127.0.0.1:11435**, separate from the conventional system Ollama
port. Start automatically launches the app-owned runtime when installed and
stops only the process it started. Installation stores weights under
`runtime/models/ollama`. To install another local translation model:

```powershell
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File scripts\install.ps1 -Profile translation -TranslationModel "qwen3:8b"
```

Set the same model name in Model manager. Local inference is the default; cloud
models are not installed by this setup. The queue runs one processing job at a
time and releases model workers between stages. Ollama uses `keep_alive: 0`.

Core downloads are a few hundred MB plus installed files. Default GPU workers
require several GB; local translation needs roughly 12 GB including its runtime
and Qwen3 14B. Allow roughly 20+ GB for all runtimes, plus source media, PCM stems,
and intermediate renders. Download sizes vary with upstream package versions.
Model files are not committed to GitHub.

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

On a managed Windows installation:

```powershell
& ".\runtime\uv\uv.exe" --no-config pip install --python ".\.venv\Scripts\python.exe" -r backend\requirements-dev.txt
& ".\.venv\Scripts\python.exe" -m unittest discover -s backend\tests -v
```

Linux development can use an explicit Python environment and installed FFmpeg:

```bash
python -m pip install -r backend/requirements-dev.txt
python scripts/build_frontend.py
python scripts/serve.py
python -m unittest discover -s backend/tests -v
```

Node is optional for development checks:
`node frontend/check-ui.mjs`.
API documentation is at `/docs`. The Windows GitHub Actions workflow exercises
core installation and the HTTP/media tests with PATH limited to Windows System32.
See [VALIDATION.md](VALIDATION.md) and the repository's Actions tab for results.
GPU inference and native-window behavior still need validation
on the actual target machine.

Optional native window uses pywebview and Windows WebView2. Install pywebview into
the private core environment using its UV executable, then launch
`.venv\Scripts\python.exe scripts\launch.py --desktop`. Browser mode has no
additional native-window dependency.

## Scope

This release is a dubbing foundation, not a mature NLE. It does not include
video inpainting, sexual-content uncensoring, automatic lip sync or OCR,
speaker-overlap source separation, a pretrained RVC bundle, multi-channel spatial
mixing, a signed installer, or hosted model processing. Subtitles match by time
overlap; dedicated forced alignment and automatic translation repair loops remain
later work. Custom model adapters, including RVC/UVR bridges, use the protocol in
[models/README.md](models/README.md).
