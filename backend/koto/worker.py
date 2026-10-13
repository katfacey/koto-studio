"""Isolated model worker: python worker.py request.json result.json.

Only this file runs inside optional model environments. Protocol is documented in
models/README.md. GPU packages never load into the editor process.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from runtime import configure_process
configure_process()


def progress(value, message):
    print("KOTO_EVENT " + json.dumps({"progress": value, "message": message}), flush=True)


def run(request):
    adapter = request["adapter"]
    settings = request.get("settings", {})
    out = Path(request["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    device = settings.get("device", "cuda")
    if adapter == "demucs":
        cmd = [sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", settings.get("model", "htdemucs"), "-d", device, "-o", str(out), request["audio"]]
        progress(0.1, "Separating dialogue and accompaniment")
        subprocess.run(cmd, check=True)
        vocals = list(out.rglob("vocals.wav"))
        beds = list(out.rglob("no_vocals.wav"))
        if not vocals or not beds:
            raise RuntimeError("Separation produced no stems")
        return {"vocals": str(vocals[0]), "background": str(beds[0])}
    if adapter == "faster-whisper":
        from faster_whisper import WhisperModel
        progress(0.05, "Loading speech recognition model")
        precision = settings.get("compute_type", "float16")
        if device == "cpu" and precision in ("float16", "int8_float16"):
            precision = "int8"
        model = WhisperModel(settings.get("model", "large-v3"), device=device, compute_type=precision)
        segments, info = model.transcribe(request["audio"], language="ja", vad_filter=True, word_timestamps=True, beam_size=5)
        lines = []
        for s in segments:
            lines.append({"start": s.start, "end": s.end, "source": s.text.strip(), "words": [{"start": w.start, "end": w.end, "text": w.word, "probability": w.probability} for w in s.words or []], "confidence": 1-s.no_speech_prob})
            progress(min(0.95, s.end/max(info.duration, 1)), f"Recognized {s.end:.1f}s")
        return {"lines": lines, "language": info.language}
    if adapter == "pyannote":
        from diarization import require_pipeline
        model_path = require_pipeline(settings)
        # Pyannote 3.x uses Lightning checkpoints with model/task metadata.
        os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        import torch
        from pyannote.audio import Pipeline
        progress(0.1, "Loading local speaker pipeline")
        pipeline = Pipeline.from_pretrained(str(model_path))
        if pipeline is None:
            raise ValueError("Could not load the local pipeline. Rerun Install-Diarization.cmd or select a valid local pipeline in Model manager.")
        pipeline.to(torch.device(device))
        def report(step, artifact, **state):
            total = state.get("total") or 1
            fraction = min(1, state["completed"] / total) if state.get("completed") is not None else 1
            base, span = {"segmentation": (.15, .35), "embeddings": (.5, .35)}.get(step, (.85, .1))
            progress(base + fraction * span, f"Speaker diarization: {step}")
        result = pipeline(request["audio"], hook=report)
        annotation = getattr(result, "speaker_diarization", result)
        turns = [{"start": turn.start, "end": turn.end, "speaker": speaker} for turn, _, speaker in annotation.itertracks(yield_label=True)]
        return {"turns": turns}
    if adapter == "piper":
        from piper import PiperVoice
        import wave
        model_path = Path(settings.get("model", ""))
        if not model_path.is_file() or not Path(str(model_path) + ".json").is_file():
            raise ValueError("Configure an English .onnx voice and its .onnx.json config first")
        voice = PiperVoice.load(str(model_path))
        path = out / "speech.wav"
        progress(0.1, "Synthesizing English speech")
        with wave.open(str(path), "wb") as f:
            # Piper 1.3+ API; old piper packages need reinstalling in this environment.
            from piper.config import SynthesisConfig
            voice.synthesize_wav(request["text"], f, syn_config=SynthesisConfig(speaker_id=int(settings.get("speaker_id", 0))))
        return {"audio": str(path)}
    if adapter == "xtts":
        import os
        # Official XTTS checkpoints contain config classes predating Torch 2.6.
        os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
        import torch
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts
        import soundfile as sf
        directory = Path(settings.get("model") or "runtime/models/xtts")
        if not (directory / "config.json").is_file():
            raise ValueError("Run Install-Reference-Voices.cmd, or configure a local XTTS directory containing config.json, model.pth, and vocab.json")
        reference = request.get("reference")
        if not reference or not Path(reference).is_file():
            raise ValueError("This speaker needs a reference audio sample")
        progress(0.1, "Loading reference-conditioned voice")
        config = XttsConfig()
        config.load_json(str(directory / "config.json"))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(config, checkpoint_dir=str(directory), eval=True)
        model.to(torch.device(device))
        conditioning, embedding = model.get_conditioning_latents(audio_path=[reference])
        output = model.inference(request["text"], "en", conditioning, embedding)
        path = out / "speech.wav"
        sf.write(str(path), output["wav"], 24000)
        return {"audio": str(path)}
    raise ValueError(f"Unknown built-in worker: {adapter}")


if __name__ == "__main__":
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    output = run(request)
    Path(sys.argv[2]).write_text(json.dumps(output), encoding="utf-8")
    progress(1, "Worker complete")
