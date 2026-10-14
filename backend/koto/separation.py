"""UI-independent separation catalog, provisioning, and result selection.

Standard library only: the editor never imports Torch/ONNX. Model inference has
no downloader; only an explicit download job may contact the model host.
"""
from __future__ import annotations
import hashlib
import json
import math
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / 'models' / 'separation' / 'catalog.json'
MODEL_DIR = ROOT / 'runtime' / 'models' / 'separation'


def model_spec(model_id):
    for model in json.loads(CATALOG_PATH.read_text(encoding='utf-8'))['models']:
        if model['id'] == model_id:
            return model
    raise ValueError('Choose a supported separation model')


def model_path(spec, directory=MODEL_DIR):
    return Path(directory) / spec['filename']


def receipt_path(spec, directory=MODEL_DIR):
    return Path(directory) / (spec['id'] + '.installed.json')


def installed(spec, directory=MODEL_DIR, verify=False):
    path = model_path(spec, directory)
    try:
        receipt = json.loads(receipt_path(spec, directory).read_text(encoding='utf-8'))
        if path.stat().st_size != spec['size'] or receipt['filename'] != spec['filename']:
            return False
        expected = spec.get('sha256') or receipt['sha256']
        return receipt['sha256'] == expected and (not verify or file_hash(path) == expected)
    except (OSError, ValueError, KeyError):
        return False


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def uvr_hash(path):
    with Path(path).open('rb') as stream:
        stream.seek(max(0, Path(path).stat().st_size - 10000 * 1024))
        return hashlib.md5(stream.read()).hexdigest()


def metadata(spec, path):
    table = json.loads((CATALOG_PATH.parent / spec['metadata']).read_text(encoding='utf-8'))
    digest = uvr_hash(path)
    if digest not in table:
        raise ValueError('Model does not match the bundled UVR metadata; download it again')
    return table[digest]


def catalog(directory=MODEL_DIR):
    data = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    return {**data, 'models': [{**spec, 'installed': installed(spec, directory)} for spec in data['models']]}


def download(model_id, progress=lambda value, message: None, check=lambda: None, directory=MODEL_DIR):
    spec = model_spec(model_id)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if installed(spec, directory, verify=True):
        return json.loads(receipt_path(spec, directory).read_text(encoding='utf-8'))
    target = model_path(spec, directory)
    temporary = target.with_suffix(target.suffix + '.partial')
    try:
        progress(.01, 'Downloading ' + spec['label'])
        request = urllib.request.Request(spec['url'], headers={'User-Agent': 'KOTO-Studio'})
        count = 0
        digest = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as output:
            while True:
                check()
                block = response.read(1024 * 1024)
                if not block:
                    break
                count += len(block)
                if count > spec['size']:
                    raise ValueError('Model download exceeds its expected size')
                digest.update(block)
                output.write(block)
                progress(min(.95, count / spec['size'] * .95), f'Downloading {spec["label"]} · {count // 1048576} / {spec["size"] // 1048576} MiB')
        check()
        sha = digest.hexdigest()
        if count != spec['size'] or (spec.get('sha256') and sha != spec['sha256']):
            raise ValueError('Model download failed its size/checksum verification')
        if spec.get('metadata'):
            metadata(spec, temporary)
        temporary.replace(target)
        receipt = {'model_id': model_id, 'filename': spec['filename'], 'sha256': sha, 'size': count, 'installed': time.time(), 'url': spec['url']}
        receipt_path(spec, directory).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        progress(1, 'Model installed locally')
        return receipt
    finally:
        temporary.unlink(missing_ok=True)


def require_model(settings):
    spec = model_spec(settings.get('model', 'mdx-inst-hq3'))
    if not installed(spec, verify=True):
        raise ValueError('Download this separation model in Separate audio first')
    return spec, model_path(spec)


def validated_settings(settings):
    settings = dict(settings)
    spec = model_spec(settings.get('model', 'mdx-inst-hq3'))
    settings['model'] = spec['id']
    if settings.get('device', 'cuda') not in ('cuda', 'cpu'):
        raise ValueError('Separation device must be CUDA or CPU')
    for field in spec['fields']:
        key, value = field['key'], settings.get(field['key'], field['default'])
        if field['type'] == 'checkbox':
            if not isinstance(value, bool):
                raise ValueError(field['label'] + ' must be true or false')
        elif isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not field['min'] <= value <= field['max'] or (field.get('integer') and int(value) != value):
            raise ValueError(f'{field["label"]} must be between {field["min"]} and {field["max"]}')
        settings[key] = value
    # Only controls supported by the selected architecture enter the worker.
    return {k: settings[k] for k in ('model', 'device', *(f['key'] for f in spec['fields'])) if k in settings}


def separation_range(project, options):
    if not project['assets'].get('original_audio'):
        raise ValueError('Run Prepare media first')
    preview = options.get('preview', False)
    if not isinstance(preview, bool):
        raise ValueError('Preview must be true or false')
    duration = float(project['media']['duration'])
    if not preview:
        if 'start' in options or 'end' in options:
            raise ValueError('A full separation does not accept preview bounds')
        return False, 0., duration
    start, end = options.get('start'), options.get('end')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)):
        raise ValueError('Preview needs finite start and end times')
    if not 0 <= start < end <= duration or not .25 <= end - start <= 120:
        raise ValueError('Preview must be 0.25–120 seconds within the source video')
    return True, float(start), float(end)


def activate(project, result):
    if result['preview']:
        raise ValueError('A preview cannot replace the full project audio')
    if result['source_asset'] != project['assets'].get('original_audio'):
        raise ValueError('This result belongs to an earlier prepared source; separate the current source')
    if project.get('active_separation') == result['id'] and all(project['assets'].get(k) == result['assets'][k] for k in ('vocals', 'background')):
        return project
    project['assets'].update({k: result['assets'][k] for k in ('vocals', 'background')})
    project['active_separation'] = result['id']
    for key in ('export', 'dub_audio', 'english_subtitles'):
        project['assets'].pop(key, None)
    for speaker in project['speakers']:
        speaker.pop('source_reference', None)
        if speaker.get('use_source_reference'):
            for line in project['dialogue']:
                if line['speaker'] == speaker['id'] and (line.get('audio') or {}).get('kind') == 'generated':
                    line['audio'] = None
                    line['warning'] = 'Original voice reference changed. Regenerate this line.'
    return project
