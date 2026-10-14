from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]


def resolve_model(value):
    path=Path(value)
    if not path.is_absolute():path=ROOT/path
    if (path/'current.json').is_file():
        revision=json.loads((path/'current.json').read_text(encoding='utf-8'))['revision']
        if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):raise ValueError('Invalid Qwen model receipt')
        path=path/revision
    return path.resolve()
