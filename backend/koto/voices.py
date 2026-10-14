"""Versioned voice assets, pure setting resolution, and non-destructive takes."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import shutil
import time
import uuid
from pathlib import Path
from .references import reference_signature


def resolve_voice(project, line):
    speaker = next(s for s in project['speakers'] if s['id'] == line['speaker'])
    binding = line.get('voice_profile') or speaker.get('voice_profile') or {}
    profile = binding.get('config', {})
    voice, clip = ({} if line.get('voice_profile') else speaker.get('voice', {})), line.get('voice', {})
    adapter = clip.get('adapter') or voice.get('adapter') or profile.get('adapter') or project['models']['synthesis']['id']
    default = project['models']['synthesis']
    settings = dict(default.get('settings', {})) if adapter == default['id'] else {}
    for config in (profile, voice, clip):
        if not config.get('adapter') or config['adapter'] == adapter:
            settings.update(config.get('settings', {}))
    source = bool(speaker.get('use_source_reference'))
    reference = speaker.get('reference')
    reference_text = speaker.get('reference_text', '')
    if line.get('voice_profile'):
        source, reference = False, binding.get('reference')
        reference_text = profile.get('reference_text', '')
    mode = clip.get('reference_mode', 'inherit')
    if mode != 'inherit':
        source, reference = mode == 'source', clip.get('reference') if mode == 'sample' else None
        reference_text = clip.get('reference_text', '')
    if 'reference_text' in clip: reference_text=clip['reference_text']
    conversion = None if clip.get('conversion_disabled', voice.get('conversion_disabled', False)) else clip.get('conversion') or voice.get('conversion') or profile.get('conversion') or project['models'].get('voice_conversion')
    return {'adapter': adapter, 'settings': settings, 'reference': reference, 'source': source,
            'reference_text': reference_text, 'delivery': clip.get('delivery', voice.get('delivery', profile.get('delivery', ''))),
            'seed': clip.get('seed', voice.get('seed', profile.get('seed'))), 'conversion': conversion,
            'profile': [binding.get('id'), binding.get('version')] if binding else None}


def signature(project, line):
    speaker = next((s for s in project['speakers'] if s['id'] == line['speaker']), {})
    if not line.get('voice') and not line.get('voice_profile') and not speaker.get('voice_profile'):
        # Existing project takes keep their original fingerprint until new features are used.
        reference = ['source', reference_signature(project, line['speaker'])] if speaker.get('use_source_reference', False) else speaker.get('reference')
        content = [line.get('translation', ''), line['speaker'], speaker.get('voice', {}), reference, project['models'].get('synthesis'), project['models'].get('voice_conversion')]
    else:
        resolved = resolve_voice(project, line)
        if resolved['source']:
            resolved['reference'] = ['source', reference_signature(project, line['speaker'])]
        content = [line.get('translation', ''), resolved]
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def current_take(project, line):
    audio = line.get('audio') or {}
    return audio.get('kind') != 'generated' or signature(project, line) in (audio.get('signature'), audio.get('accepted_signature'))


def remember_take(project, line):
    audio = line.get('audio')
    if not audio:
        return
    history = project.setdefault('takes', {}).setdefault(line['id'], [])
    if not any(t['audio']['asset'] == audio['asset'] for t in history):
        history.append({'id': str(uuid.uuid5(uuid.NAMESPACE_URL,project['id']+line['id']+audio['asset'])), 'created': time.time(), 'text': line.get('translation', ''), 'speaker': line['speaker'], 'voice': copy.deepcopy(line.get('voice', {})), 'audio': copy.deepcopy(audio)})


def validate_voice(voice, registry):
    if not isinstance(voice, dict):
        raise ValueError('Voice overrides must be an object')
    if voice.get('adapter'):
        registry.get(voice['adapter'], 'synthesis')
    if not isinstance(voice.get('settings', {}), dict):
        raise ValueError('Voice settings must be an object')
    for key in ('delivery', 'reference_text'):
        if not isinstance(voice.get(key, ''), str) or len(voice.get(key, '')) > 4000:
            raise ValueError(f'{key} must be text up to 4000 characters')
    seed = voice.get('seed')
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2147483647):
        raise ValueError('Seed must be an integer between 0 and 2147483647, or blank')
    if voice.get('reference_mode', 'inherit') not in ('inherit', 'source', 'sample', 'none'):
        raise ValueError('Unknown reference mode')
    if voice.get('reference') and not isinstance(voice['reference'], str):
        raise ValueError('Invalid reference audio')
    if voice.get('conversion'):
        registry.get(voice['conversion']['id'], 'voice_conversion')


class VoiceLibrary:
    def __init__(self, store, registry):
        self.store, self.registry = store, registry
        self.root = store.root / 'voices'
        self.root.mkdir(exist_ok=True)
        with store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS voice_profiles(id TEXT PRIMARY KEY,name TEXT,version INTEGER,archived INTEGER,updated REAL);
            CREATE TABLE IF NOT EXISTS voice_versions(profile_id TEXT,version INTEGER,payload TEXT,PRIMARY KEY(profile_id,version));''')

    def get(self, profile_id, version=None):
        uuid.UUID(profile_id)
        with self.store.connect() as db:
            row = db.execute('SELECT version FROM voice_profiles WHERE id=?', (profile_id,)).fetchone()
            if not row:
                raise KeyError('Voice profile not found')
            payload = db.execute('SELECT payload FROM voice_versions WHERE profile_id=? AND version=?', (profile_id, version or row[0])).fetchone()
            if not payload:
                raise KeyError('Voice profile version not found')
            return json.loads(payload[0])

    def list(self):
        with self.store.connect() as db:
            rows = db.execute('SELECT id,name,version,archived,updated FROM voice_profiles ORDER BY updated DESC').fetchall()
        return [{'id':r[0], 'name':r[1], 'version':r[2], 'archived':bool(r[3]), 'updated':r[4]} for r in rows]

    def asset(self, profile_id, version, name):
        uuid.UUID(profile_id)
        base = (self.root / profile_id / str(int(version))).resolve()
        target = (base / name).resolve()
        if not target.is_relative_to(base) or name.startswith('.'):
            raise ValueError('Invalid voice sample path')
        return target

    def save(self, name, description, config, sample=None, profile_id=None, expected_version=None):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError('Voice name must be 1–120 characters')
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError('Voice description must be at most 4000 characters')
        validate_voice(config, self.registry)
        adapter = self.registry.get(config['adapter'], 'synthesis')
        with self.store.lock:
            previous = self.get(profile_id) if profile_id else None
            if previous and expected_version != previous['version']:
                raise ValueError('Voice profile changed. Refresh the library before saving a new version.')
            if previous and not sample and previous.get('reference'):
                sample=self.asset(profile_id,previous['version'],previous['reference'])
            if adapter.get('supports_reference') and not sample:
                raise ValueError('This voice engine needs a saved reference sample')
            profile_id = profile_id or str(uuid.uuid4())
            version = previous['version'] + 1 if previous else 1
            reference = None
            if sample:
                source = Path(sample)
                reference = 'reference' + source.suffix.lower()
                dest = self.asset(profile_id, version, reference)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
            result = {'id':profile_id, 'version':version, 'name':name.strip(), 'description':description, 'config':copy.deepcopy(config), 'reference':reference, 'created':time.time()}
            with self.store.connect() as db:
                db.execute('INSERT INTO voice_versions VALUES(?,?,?)',(profile_id,version,json.dumps(result)))
                db.execute('INSERT OR REPLACE INTO voice_profiles VALUES(?,?,?,?,?)',(profile_id,name.strip(),version,0,time.time()))
            return result

    def bind(self, pid, profile_id, version=None):
        profile = self.get(profile_id, version)
        result = copy.deepcopy(profile)
        if profile['reference']:
            source = self.asset(profile_id, profile['version'], profile['reference'])
            target = self.store.asset(pid, str(uuid.uuid4()) + source.suffix)
            shutil.copyfile(source, target)
            result['reference'] = target.name
        # The snapshot and copied sample remain usable independently of the library.
        return result
