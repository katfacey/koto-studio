"""Provision immutable HF snapshots into app-owned directories for offline inference."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from koto.runtime import configure_process


def provision(api,download,design=False):
    repositories=[('base','Qwen/Qwen3-TTS-12Hz-0.6B-Base')]
    if design:repositories.append(('design','Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'))
    for name,repo in repositories:
        revision=api.model_info(repo,token=False).sha
        if not revision:raise ValueError('Could not resolve Qwen model revision')
        base=ROOT/'runtime/models/qwen'/name
        directory=base/revision
        print(f'Downloading {repo} at {revision}',flush=True)
        download(repo_id=repo,revision=revision,local_dir=directory,token=False,ignore_patterns=['*.md','.gitattributes','*.png','*.jpg'])
        if not (directory/'config.json').is_file():raise ValueError('Qwen model configuration is missing')
        (base/'current.json').write_text(json.dumps({'repository':repo,'revision':revision}),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--design',action='store_true');args=parser.parse_args()
    configure_process()
    from huggingface_hub import HfApi,snapshot_download
    provision(HfApi(),snapshot_download,args.design)
