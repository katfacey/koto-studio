"""Shared local diarization paths, without importing GPU/model packages."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PIPELINE = "runtime/models/pyannote/pipeline.yaml"


def pipeline_path(settings=None, root=ROOT):
    path = Path((settings or {}).get("model") or DEFAULT_PIPELINE)
    return path.resolve() if path.is_absolute() else (Path(root) / path).resolve()


def require_pipeline(settings=None, root=ROOT):
    path = pipeline_path(settings, root)
    if not path.is_file():
        raise ValueError("Diarization model files are missing. Run Install-Diarization.cmd, accept the Hugging Face model access agreements, and enter a read token locally. Then retry Speakers. For existing model files, set Local pipeline YAML in Model manager > Speaker diarization.")
    return path
