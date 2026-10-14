# Reusable character voices

Included in 0.3.0 Alpha. The earlier 0.2.5 ZIP remains an unchanged historical release.
The current controls are a first pass; library APIs and stored snapshots can serve
an upgraded voice interface later.

## Use a saved voice

1. Open a speaker's **Voices** inspector and configure its engine/reference.
2. Open **Voice library**, name the character, and **Save new voice**.
3. In any project, open the library and **Assign to speaker**.
4. Save revised settings with **Save version**. Existing projects stay on their
   pinned version. **Use latest version** explicitly updates an assignment.
5. Archive retired profiles; existing project snapshots and samples keep working.

The library owns a copy of its reference recording. Assignments also copy the
recording into the project and retain an immutable configuration snapshot. A
project does not need its original source project to use that voice.

## Per-clip controls and takes

The clip inspector allows a saved voice assignment, engine/model overrides,
reference mode/sample/transcript, and seed/delivery when supported by the engine.
Volume, manual speed, auto-fit, and timing controls continue to work independently.
**Reset clip overrides** restores inherited settings; selecting the empty library
voice option removes a clip's explicit profile binding.

Resolution is project defaults, speaker profile and overrides, then clip profile
and overrides. A clip profile supersedes the speaker voice. Clip settings remain
when its profile version is explicitly updated. Moving a clip with its own pinned
voice to another speaker lane preserves that voice/take unless it explicitly uses
the original speaker's dialogue as its reference.

Generated and imported takes are retained. Text/voice changes invalidate only the
selected generated take, not its history. Choose a **Saved take** to explicitly
approve an older result for the current clip; a changed-text/voice warning asks
for listening review. Further text/voice edits invalidate that approval. Imported
takes remain user-selected audio. The original waveform is preserved; timing,
speed, and gain are applied during playback/export. Long takes retain the existing
soft export warning and render-anyway behavior.

Compatible lines share one loaded model and reference conditioning. Seed and
supported delivery settings remain per-line. Different models/references form
separate groups. Existing voice-conversion bridges retain their per-line path to
avoid keeping two GPU models resident together.

## Qwen3-TTS

- **Install-Qwen-Voices.cmd** installs an isolated worker and Base 0.6B weights.
- **Install-Voice-Design.cmd** adds VoiceDesign 1.7B and the Base cloning model.
- Restart KOTO after installation. Choose CUDA or CPU explicitly.
- For cloning, attach clean speech or use the original speaker reference. Enter
  the exact reference transcript when known. Without one, the adapter uses the
  model's speaker-embedding-only mode.
- For a new voice, describe it in the library, generate audition recordings,
  listen, and **Save as voice**. The chosen recording becomes a reusable Base
  cloning reference. A description alone is not a stable identity anchor.

Cloning and voice design are separate model checkpoints. Base does not expose
arbitrary delivery instructions; those controls appear only for compatible
engines. Seeds help repeat generation but do not promise identical results across
hardware/runtime versions. Voice similarity and Japanese/Chinese reference quality
need listening checks. Timing is measured after synthesis; no engine is assumed
to match a dialogue slot perfectly.

Workers use SDPA and app-owned Torch/CUDA libraries; no FlashAttention build or
system SoX executable is required for the tested paths. Upstream's Python SoX
import may log a missing-SoX notice; cloning/design here use librosa and the model
codec, while KOTO timing/mixing uses its managed FFmpeg.

Weights are installed under `runtime/models/qwen/{base,design}/{revision}`.
`current.json` selects the installed default. Saving a Qwen library profile pins
its concrete model-revision directory. Upgrading the installed default leaves old
snapshots in place. Inference uses local files with Hugging Face offline mode.

## Storage and API

SQLite `voice_profiles` indexes the latest revision; `voice_versions` stores
immutable version payloads. Samples live in `data/voices/{id}/{version}`. Project
speaker/clip `voice_profile` bindings contain snapshots and project-owned sample
paths. `takes` is backend-owned history indexed by clip ID; `voice_designs` stores
project audition recordings. Existing projects acquire history as their takes
are edited/generated/selected. No existing media is moved.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/voices` | List saved/archived profiles and latest versions |
| `GET /api/voices/{id}?version=1` | Read a specific immutable version |
| `POST /api/voices/{id}/archive` | Archive/restore without deleting snapshots |
| `POST /api/projects/{id}/jobs`, kind `save_voice` | Save current speaker or chosen audition; optionally create a new profile version with `expected_version` |
| Same endpoint, kind `design_voice` | Generate a Qwen audition using `description`, `text`, device and optional seed |
| `POST .../speakers/{sid}/voice-profile` | Assign `{profile_id, version, revision}`; null removes binding |
| `POST .../dialogue/{lid}/voice-profile` | Assign an independent clip voice |
| `POST .../dialogue/{lid}/reference` | Upload a separate clip reference |
| `GET .../dialogue/{lid}/takes` | Read retained takes |
| `POST .../dialogue/{lid}/takes/{take_id}/select` | Explicitly select/approve a retained take |

Assignments and take selection check project revisions. Profile updates check the
latest version. Project PATCH cannot replace library binding snapshots or take
history. Archived profiles can be restored; there is no destructive deletion or
automatic storage cleanup in this first pass. Portable library ZIP import/export,
multiple named sample banks, training UI, and a richer voice editor remain future
work.

## DramaBox evaluation

[DramaBox](https://github.com/resemble-ai/DramaBox) is an expressive English TTS
model with reference cloning, prompt-directed acting, a warm inference server,
optional voice LoRA training, and an explicit duration target. Upstream reports
about 24 GB peak VRAM and its speed benchmark uses an H100; these are not RTX 5090
measurements. The downloaded model components total roughly 16–17 GB before the
worker runtime. This makes it a plausible optional candidate for the 32 GB card.

For a KOTO adapter, use a dedicated Torch 2.8/CUDA environment, pre-provision pinned
weights, disable compile initially on Windows, keep the model loaded within a
compatible batch, and pass individual clip directions/duration targets. Preserve
upstream watermarking. The optional RE-USE denoiser has Windows build dependencies
and separate non-commercial terms; it should not be a required setup component.
Use KOTO's existing reference preparation instead for the initial evaluation.

DramaBox is **not installed or exposed as a working built-in adapter yet**. It needs
Windows/NVIDIA inference, memory, language-reference and timing validation before
shipping. Its LTX-2 Community License is separate from KOTO's MIT license. Evaluation
here is based on upstream code/requirements; no DramaBox GPU benchmark was run.

## Sources

- [Voicebox profiles](https://github.com/jamiepine/voicebox/blob/main/backend/services/profiles.py) informed the library approach; KOTO does not require Voicebox to be installed.
- [Qwen3-TTS design then clone](https://github.com/QwenLM/Qwen3-TTS#voice-design-then-clone) and reusable conditioning APIs.
- [DramaBox inference server](https://github.com/resemble-ai/DramaBox/blob/master/src/inference_server.py) and [requirements](https://github.com/resemble-ai/DramaBox/blob/master/requirements.txt).

Qwen's code/weights and all other third-party components retain their own terms.
