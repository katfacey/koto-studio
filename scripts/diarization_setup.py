"""Download approved pyannote weights locally; prompt for a token without saving it."""
import copy
import getpass
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from koto.runtime import configure_process
from koto.diarization import DEFAULT_PIPELINE

REPOSITORIES = {
    "pipeline": ("pyannote/speaker-diarization-3.1", "config.yaml"),
    "segmentation": ("pyannote/segmentation-3.0", "pytorch_model.bin"),
    "embedding": ("pyannote/wespeaker-voxceleb-resnet34-LM", "pytorch_model.bin"),
}


def local_config(config, checkpoints):
    result = copy.deepcopy(config)
    if result.get("pipeline", {}).get("name") != "pyannote.audio.pipelines.SpeakerDiarization":
        raise ValueError("Unexpected pipeline configuration; no local config was installed")
    params = result["pipeline"].setdefault("params", {})
    for name in ("segmentation", "embedding"):
        path = Path(checkpoints[name]).resolve()
        if not path.is_file():
            raise ValueError(f"Missing local {name} checkpoint")
        params[name] = path.as_posix()
    params.pop("use_auth_token", None)
    result.pop("device", None)
    return result


def provision(token, api, download, destination):
    """Explicitly pin each download to its resolved model revision."""
    destination = Path(destination)
    files, revisions = {}, {}
    for name, (repository, filename) in REPOSITORIES.items():
        revision = api.model_info(repository, token=token).sha
        if not revision:
            raise ValueError(f"Could not resolve a revision for {repository}")
        print(f"Downloading {repository} at {revision}", flush=True)
        files[name] = Path(download(repo_id=repository, filename=filename, revision=revision, token=token, local_dir=destination / name))
        revisions[repository] = revision
    import yaml
    config = local_config(yaml.safe_load(files["pipeline"].read_text(encoding="utf-8")), files)
    # ASCII YAML also works with pyannote 3.x's Windows ANSI config reader.
    payload = yaml.safe_dump(config, allow_unicode=False, sort_keys=False)
    destination.mkdir(parents=True, exist_ok=True)
    temporary = destination / "pipeline.yaml.partial"
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(destination / "pipeline.yaml")
    (destination / "source.json").write_text(json.dumps({"revisions": revisions}, indent=2), encoding="utf-8")
    return destination / "pipeline.yaml"


def main():
    configure_process()
    print("Accept model access agreements in your browser with your Hugging Face account:")
    print("  https://huggingface.co/pyannote/speaker-diarization-3.1")
    print("  https://huggingface.co/pyannote/segmentation-3.0")
    print("Create a read token: https://huggingface.co/settings/tokens")
    print("Your token is used for downloads only and is not saved by KOTO.")
    token = os.environ.get("HF_TOKEN") or getpass.getpass("Hugging Face read token (hidden): ").strip()
    if not token:
        raise SystemExit("No token provided. Complete model access and rerun Install-Diarization.cmd.")
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.errors import HfHubHTTPError
    try:
        pipeline = provision(token, HfApi(), hf_hub_download, (ROOT / DEFAULT_PIPELINE).parent)
    except HfHubHTTPError as error:
        code = getattr(error.response, "status_code", None)
        raise SystemExit(f"Hugging Face download failed (HTTP {code}). Check your read token and accepted access agreements for both model pages above, then rerun Install-Diarization.cmd.") from None
    finally:
        token = None
    print(f"Local pipeline installed: {pipeline}")
    print("Restart KOTO. Blank diarization model paths automatically use this pipeline.")


if __name__ == "__main__":
    main()
