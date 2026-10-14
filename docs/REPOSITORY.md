# Repository About and topics

The repository remains **private**. The intended metadata is recorded in
[repository-metadata.json](../.github/repository-metadata.json).
This is a prepared change: GitHub does not automatically apply this file as
repository settings. The connected file-writing tools cannot edit About/topics;
the local GitHub CLI credential was invalid when checked.

## Description

> Local AI dubbing studio for Windows + NVIDIA: JP/CN-to-English translation, speaker timelines, reference voices, model adapters, and MKV/MP4 export.

## Topics

```text
dubbing, video-translation, ai-translation, subtitle-translation, localization,
voice-cloning, text-to-speech, tts, speech-to-text, speech-recognition,
speaker-diarization, speech-synthesis, whisper, local-first, pytorch, python,
cuda, ollama
```

These 18 topics describe functionality or runtimes KOTO currently includes.
They are GitHub discovery topics, rather than release/version tags.
Image-inpainting, lip-sync, and unbundled model names are omitted because they
would suggest features this release does not provide.

## Research

Public GitHub repository metadata checked on **2026-10-14 UTC**:

| Related project | Stars at lookup | Relevant topics used there |
| --- | ---: | --- |
| [VideoLingo](https://github.com/Huanshere/VideoLingo) | 18,786 | dubbing, video-translation, ai-translation, localization, voice-cloning |
| [pyvideotrans](https://github.com/jianchang512/pyvideotrans) | 19,375 | speech-to-text, subtitle-translation, text-to-speech, tts |
| [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) | 62,770 | text-to-speech, tts, voice-cloning |
| [Coqui TTS](https://github.com/coqui-ai/TTS) | 46,115 | speech-synthesis, voice-cloning, pytorch, python |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 25,845 | speech-recognition, speech-to-text, whisper |
| [pyannote.audio](https://github.com/pyannote/pyannote-audio) | 10,641 | speaker-diarization, pytorch |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | 63,870 | local-first, cuda, dubbing, text-to-speech |
| [Ollama](https://github.com/ollama/ollama) | 183,072 | ollama |

Stars belong to repositories and do not transfer through topics. Private
repositories stay out of public topic listings; these choices prepare the About
section for authorized viewers and any later public release. Similar topics do
not imply affiliation, endorsement, or that every related project is integrated.

## Apply without changing visibility

On the [repository page](https://github.com/katfacey/koto-studio), open the gear
beside **About**, paste the description, add the topics, and save. Leave visibility
private. Alternatively, from your own authenticated GitHub CLI:

```powershell
gh repo edit katfacey/koto-studio --description "Local AI dubbing studio for Windows + NVIDIA: JP/CN-to-English translation, speaker timelines, reference voices, model adapters, and MKV/MP4 export." --add-topic "dubbing,video-translation,ai-translation,subtitle-translation,localization,voice-cloning,text-to-speech,tts,speech-to-text,speech-recognition,speaker-diarization,speech-synthesis,whisper,local-first,pytorch,python,cuda,ollama"
```

This command adds the researched topics and description; it has no visibility
change flag. GitHub CLI is optional repository maintenance tooling, not a KOTO
installation dependency. Do not put an access token into project files or chat.
