"""Provision official XTTS weights in the app folder, without a system cache."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from koto.runtime import configure_process

REPOSITORY = 'coqui/XTTS-v2'
FILES = ('config.json', 'model.pth', 'vocab.json', 'speakers_xtts.pth')


def provision(api, download, destination):
    destination = Path(destination)
    revision = api.model_info(REPOSITORY, token=False).sha
    if not revision:
        raise ValueError('Could not resolve the official XTTS model revision')
    print(f'Downloading {REPOSITORY} at {revision} (several GB).', flush=True)
    for filename in FILES:
        path = Path(download(repo_id=REPOSITORY, filename=filename, revision=revision, token=False, local_dir=destination))
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f'Missing XTTS file: {filename}')
    for filename in ('config.json', 'vocab.json'):
        json.loads((destination / filename).read_text(encoding='utf-8'))
    (destination / 'source.json').write_text(json.dumps({'repository':REPOSITORY, 'revision':revision}, indent=2), encoding='utf-8')
    return destination


def main():
    configure_process()
    from huggingface_hub import HfApi, hf_hub_download
    path = provision(HfApi(), hf_hub_download, ROOT / 'runtime/models/xtts')
    print(f'XTTS ready at {path}. Restart KOTO and select an original reference or upload a sample.')


if __name__ == '__main__':
    main()
