# KOTO Studio · v0.2.0

A local Japanese-to-English dubbing editor for **Windows x64 + NVIDIA**, designed
around an RTX 5090 with 32 GB VRAM. KOTO installs and runs its own Python, FFmpeg,
model environments, and optional local translation runtime inside the app folder.

**[Download the complete ZIP](https://github.com/katfacey/koto-studio/archive/refs/heads/main.zip)**

[Windows validation passed](https://github.com/katfacey/koto-studio/actions/runs/38464491621): 35 backend tests, real Piper/XTTS speaker batches, moved-folder worker repair, and Chromium autosave, trim, delete/undo, generation and playback checks with only Windows System32 on PATH.

## Standalone installation

1. Download and extract the **whole ZIP** into a writable folder, such as
   `C:\KOTO Studio`. Close an older KOTO session before upgrading.
2. Double-click **Install.cmd**. It downloads verified UV and FFmpeg archives,
   installs private Python 3.11, and builds the core environment. It neither
   changes your system PATH nor registers Python as a system installation.
3. Double-click **Start.cmd**. Start also bootstraps the core if it is missing.
4. Use **Install-Models.cmd** to select optional voice/audio workers. For local
   translation, use **Install-Translation.cmd** or the translation choice in
   that menu. Use **Install-Piper.cmd** to install or repair default voices; use **Install-Reference-Voices.cmd** for original speaker voice matching with XTTS. Restart KOTO after adding optional runtimes.
5. For automatic speaker diarization, use **Install-Diarization.cmd** as described
   below. Installing the audio worker package alone does not download gated weights.

You do not need to install Python, FFmpeg, Node/npm, Ollama, or a CUDA toolkit
before running these installers. The host requirements are Windows 10/11 x64,
a browser, a compatible NVIDIA driver for GPU inference, internet for initial
package/model downloads, and enough disk space.

This is **self-contained after setup**, rather than an offline archive containing
all binaries and every model. The release ZIP includes source and built UI;
installation downloads the runtime files into the app directory. Basic voices
and freely downloadable weights can be installed/downloaded there. Gated models
require your Hugging Face account. Install-Reference-Voices.cmd downloads official XTTS checkpoints into the app folder.

The browser editor opens at `http://127.0.0.1:8765`. Keep the standalone terminal
open; Ctrl+C stops the server and its owned translation process. This is a
standalone Windows environment with a browser editor, not a signed EXE.

## What stays inside the application folder

To edit and run the source on your PC, see [LOCAL-WORKSPACE.md](LOCAL-WORKSPACE.md).

| Location | Contents |
| --- | --- |
| `runtime/uv/` | Pinned, checksum-verified bootstrap executable |
| `runtime/python/` | Private managed Python installation |
| `runtime/ffmpeg/bin/` | Private FFmpeg, ffprobe, and companion files |
| `.venv/` | Core backend packages |
| `.workers/<worker>/` | Isolated AI environments and CUDA runtime libraries |
| `runtime/models/pyannote/` | Downloaded segmentation/embedding checkpoints and local pipeline YAML |
| `runtime/cache/` | Python package, Hugging Face, and Torch caches |
| `runtime/models/xtts/` | Official XTTS reference-voice checkpoints |
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

## Streamlined editing and generation

Autosave is enabled by default. Edits save after a 1.2-second pause, without blocking
continued typing. The footer shows Saving, Saved, or a retained-edits error. Toggle
Autosave in the footer to use manual saves; Ctrl+S still saves immediately. Undo/redo
remain available after autosave. Unsaved changes still trigger a browser close warning.

Select a clip and press Delete or Backspace to remove it. Text fields keep their
normal editing shortcuts. Ctrl+Z restores a deleted clip. Selecting a timeline clip
moves keyboard focus out of the text editor; deletion is blocked during processing.

Successful generation selects **English mix** and shows a short review toast.
Playback does not start automatically. Failed/cancelled jobs do not change the mix,
and historical jobs do not repeatedly switch it back after you choose Original.

**Generate** groups missing/outdated lines by speaker. Piper and XTTS load a voice
once per speaker batch; XTTS also computes the shared sample conditioning once.
**Generate speaker** runs only the selected character's missing/outdated lines,
keeping cached and imported takes. **Generate line** still explicitly regenerates
one clip. Individual takes retain their own timing and are committed as they finish;
cancelling a batch preserves completed takes, and retry skips those cached lines.
Custom adapters can opt into batching. Pipelines with a separate conversion adapter
retain per-line processing to avoid keeping two unrelated GPU workers resident.

## Timeline editing and voice timing

Drag a dialogue clip into another speaker lane to correct attribution. Hold Shift
to keep its time fixed, or drop on a lane header. Horizontal dragging snaps to the
source frame rate. Drag a speaker's grip to reorder lanes; focused grips also
support Arrow Up/Down. Imported takes remain attached; changing an actor clears a
generated take so it can be regenerated with the correct voice. Undo/redo and Save
include these edits.

Volume buttons mute speaker, original-dialogue and background tracks. Eye buttons
hide video or subtitles. English mix previews play individual takes and the selected
background live, so mutes work immediately before export. Render uses the same mute
and visibility settings; hidden video renders black. In Original monitoring mode,
speaker mutes gate the raw vocal stem at that actor's original timestamps. Simultaneous
voices in one raw stem cannot be muted independently; without separation, original
mix dialogue and background cannot be controlled independently.

Small clip dots and the selected line show estimated or measured timing. Estimates
use English word count, punctuation and the adjustable words-per-minute pace; they
are hints, not predictions from the selected TTS model. Generate measures the actual
take. Automatic fit can adjust speed within 0.80–1.25×. Manual speech speed overrides
auto-fit for that clip; preview and export apply it without overwriting the take.
Export rejects speech that still exceeds its slot instead of cutting it off.

**Suggest alternatives** runs the selected local translation model for one clip.
It proposes concise, near-target and fuller phrasings; it leaves your adaptation
unchanged until you click **Use this**. Review meaning and synthesize the chosen
wording to measure its actual duration. No alternatives are generated for the entire
project automatically. Local Ollama supports this directly; custom adapters can
opt in to the alternatives protocol.

In a speaker's **Voices** inspector, check **Use this speaker's original dialogue
as voice reference**. KOTO selects XTTS if the current synthesis adapter cannot use
references. Generate builds and caches up to 12 seconds from non-overlapping source
lines, using separated vocals when available. At least 3 seconds is required.
Correct assignments first. Retiming English clips preserves the original reference
timestamps. Uncheck it to use an uploaded sample; the uploaded file is retained.
XTTS voice similarity is approximate. Piper uses fixed voices and cannot clone.
Official [XTTS-v2 weights](https://huggingface.co/coqui/XTTS-v2) use the Coqui Public
Model License; consult the model page for permitted uses.

If Generate reports a moved or external worker environment, close KOTO and rerun
Install-Piper.cmd (default Piper) or Install-Reference-Voices.cmd (XTTS) in the current
folder. This rebuilds the affected environment against app-owned Python and preserves
project data. **Use project default** inherits Model manager → Synthesis; new projects
default to Piper.

## Complete a project

1. **Import media.** MKV/MP4/MOV/WebM and other FFmpeg-readable files are
   inspected. Select video, audio, and subtitle streams in the Clip inspector.
   Importing another source into an existing media project creates a new project.
2. **Prepare.** Extract stereo 48 kHz audio and make a browser-compatible H.264
   proxy. The original video stays unchanged. Text subtitle streams become SRT.
   Image subtitle tracks (PGS/DVD/DVB) are skipped when selecting default tracks;
   OCR is not included. If an older project has one selected, choose **None** for
   Subtitle track in the Clip inspector, or use **Prepare without image subtitles**.
   Import text subtitles separately, or transcribe the extracted Japanese audio.
   Prepare opens Jobs and shows live encoding progress; failures also appear in
   the preview and an error alert.
3. **Separate.** The Demucs adapter creates dialogue and background stems.
   Separation quality varies; review effects, breaths, and residual original
   dialogue. Demucs is a baseline, not a promise of clean dialogue isolation.
   Alternative separators can be added through the adapter protocol.
4. **Transcribe / diarize.** Whisper recognizes Japanese or Chinese with timestamps; choose ja, zh or auto in Model manager → Transcription.
   Subtitle references match by temporal overlap. Pyannote assigns the most
   overlapping speaker and flags possible overlaps; it does not isolate
   simultaneously speaking voices. You can assign speakers manually.
   Missing diarization weights are reported before the job starts, with instructions
   to run the local setup launcher in the error message.
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
   unmuted dialogue line. Modest time stretching is supported; overlong speech fails
   validation rather than being cut off. MKV copies source video; MP4 encodes
   H.264. Both include English AAC and an optional English subtitle track. Download the
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
| XTTS | Reference-conditioned voice worker | Run Install-Reference-Voices.cmd; use original dialogue references or upload a clean sample. |
| Local translation | Private Ollama + Qwen3 14B | No system Ollama service needed. |
| All | All workers and local translation | Accept gated diarization access and run its weight setup separately. |
| Speaker diarization weights | Audio worker plus local pyannote pipeline/weights | Accept Hugging Face access agreements and enter a read token locally. |

### Set up speaker diarization

1. Sign in and accept access agreements for
   [speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   and [segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0).
2. Create a [Hugging Face read token](https://huggingface.co/settings/tokens).
3. Double-click **Install-Diarization.cmd** and paste the token into its hidden
   local prompt. KOTO uses it for model downloads and does not save it.
4. Restart KOTO and retry **Speakers**. Existing projects with an empty model
   path automatically use `runtime/models/pyannote/pipeline.yaml`. For an explicit
   custom path, change it in Model manager → Speaker diarization.

The installer pins each download to its resolved revision and writes a pipeline
with absolute local checkpoint paths. The diarization worker uses offline Hugging
Face mode during inference. Model access and GPU inference must be checked on your
PC; the automated provisioning checks use fixtures and do not approve access agreements.

### Resize the editor

Drag the dividers beside the media panel and inspector, above the timeline, or
above the dialogue editor. Sizes persist in the browser. Double-click a divider
to reset it; focused dividers also support arrow keys (Shift for larger steps)
and Home to reset. Dialogue text areas can be resized vertically as well.

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
`node frontend/check-ui.mjs` and `node frontend/check-layout.mjs`.
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

The latest actual Windows editor screenshot is available in the [validation artifact](https://github.com/katfacey/koto-studio/actions/runs/38464491621/artifacts/11848036610). It uses the labeled sample project and real Piper takes; GPU voice similarity must be evaluated on the target PC.
