"""Smoke-test the installed Piper voice through the actual isolated worker."""
import array
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from koto.runtime import runtime_environment


def main():
    model = ROOT / "runtime" / "models" / "piper" / "en_US-lessac-medium.onnx"
    python = ROOT / ".workers" / "piper" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    # Read the downloaded phoneme dictionary without changing Unicode or key case.
    config = json.loads(Path(str(model) + ".json").read_text(encoding="utf-8"))
    assert config["phoneme_id_map"], "Downloaded voice config has no phoneme mapping"
    with tempfile.TemporaryDirectory(prefix="KOTO Piper speech ") as tmp:
        work = Path(tmp)
        request = work / "request.json"
        result = work / "result.json"
        request.write_text(json.dumps({"adapter": "piper", "text": "The rain has stopped. Let's wait for the next train.", "settings": {"model": str(model), "speaker_id": 0}, "output_dir": str(work)}), encoding="utf-8")
        subprocess.run([str(python), str(ROOT / "backend" / "koto" / "worker.py"), str(request), str(result)], cwd=ROOT, env=runtime_environment(python=python), check=True, timeout=120)
        output = json.loads(result.read_text(encoding="utf-8"))
        with wave.open(output["audio"], "rb") as audio:
            assert audio.getsampwidth() == 2 and audio.getnchannels() == 1
            duration = audio.getnframes() / audio.getframerate()
            assert 1 < duration < 30, f"Unexpected synthesized duration: {duration}"
            samples = array.array("h", audio.readframes(audio.getnframes()))
            if sys.byteorder != "little":
                samples.byteswap()
            assert max(map(abs, samples)) > 100, "Synthesized speech is silent"
        print(f"Real Piper worker synthesized {duration:.2f}s of non-silent English speech.")


if __name__ == "__main__":
    main()
