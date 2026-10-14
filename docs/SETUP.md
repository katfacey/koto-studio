# Installation, models, and project storage

[Back to the README](../README.md) · KOTO Studio 0.2.5

## What stays inside the application folder

To edit and run the source on your PC, see [LOCAL-WORKSPACE.md](../LOCAL-WORKSPACE.md).

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

See [model adapter protocol](../models/README.md) for argument-array worker commands,
requests/results, progress events, and optional voice conversion. Add trusted
adapters locally and restart the backend. Model availability indicates a worker
package/executable is installed; it does not mean its weights are configured or
GPU inference has passed.
