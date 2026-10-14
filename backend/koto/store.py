from __future__ import annotations

import copy
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("KOTO_DATA_DIR", ROOT / "data")).resolve()


class Store:
    def __init__(self, root: Path = DATA):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT, updated REAL, payload TEXT
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT, kind TEXT, status TEXT,
                    progress REAL, message TEXT, created REAL, updated REAL,
                    spec TEXT, result TEXT
                );
            """)
            db.execute("UPDATE jobs SET status='interrupted', message='Application stopped. Retry to resume from cached assets.' WHERE status IN ('queued','running')")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.root / "studio.sqlite", timeout=30)
        try:
            with connection:
                yield connection
        finally:
            # SQLite's own context manager commits/rolls back but does not close.
            # Explicit closure also releases Windows file locks immediately.
            connection.close()

    def project_dir(self, project_id: str) -> Path:
        # IDs are generated internally; never use user-supplied paths.
        uuid.UUID(project_id)
        path = self.root / "projects" / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def asset(self, project_id: str, name: str) -> Path:
        base = self.project_dir(project_id)
        path = (base / name).resolve()
        if not path.is_relative_to(base.resolve()) or name.startswith("."):
            raise ValueError("Invalid asset path")
        return path

    def create(self, name="Untitled project", demo=False):
        pid = str(uuid.uuid4())
        project = {
            "id": pid, "name": name[:120], "revision": 1, "demo": demo,
            "media": None, "assets": {}, "dialogue": [], "separations": [], "active_separation": None, "takes": {}, "voice_designs": [],
            "speakers": [{"id": "speaker-1", "name": "Speaker 01", "color": "#8b8aff", "voice": {}, "reference": None, "muted": False, "use_source_reference": False}],
            "models": {
                "separation": {"id": "demucs", "settings": {"model": "htdemucs", "device": "cuda"}},
                "transcription": {"id": "faster-whisper", "settings": {"model": "large-v3", "device": "cuda", "compute_type": "float16"}},
                "diarization": {"id": "pyannote", "settings": {"model": "runtime/models/pyannote/pipeline.yaml", "device": "cuda"}},
                "translation": {"id": "ollama", "settings": {"model": "qwen3:14b", "temperature": 0.2}},
                "synthesis": {"id": "piper", "settings": {"model": "runtime/models/piper/en_US-lessac-medium.onnx", "speaker_id": 0}},
            },
            "settings": {"audio_stream": None, "video_stream": None, "subtitle_stream": None, "background_gain": 0.8, "dialogue_gain": 1.0, "fit_duration": True, "output": "mkv", "background_mode": "separated", "original_muted": False, "background_muted": False, "video_visible": True, "subtitles_visible": True},
        }
        if demo:
            project["speakers"].append({"id": "speaker-2", "name": "Speaker 02", "color": "#e8a96b", "voice": {}, "reference": None, "muted": False, "use_source_reference": False})
            samples = [(1.0, 3.4, "speaker-1", "まだ雨が降っているね。", "It's still raining."), (4.0, 7.0, "speaker-2", "もうすぐ止むと思う。", "I think it'll stop soon."), (8.0, 10.6, "speaker-1", "次の電車を待とう。", "Let's wait for the next train."), (12.0, 15.0, "speaker-2", "ここで待っていよう。", "We'll wait right here.")]
            project["dialogue"] = [{"id": str(uuid.uuid4()), "start": a, "end": b, "speaker": s, "source": ja, "translation": en, "subtitle": en, "audio": None} for a,b,s,ja,en in samples]
            project["name"] = "After the rain · sample"
        self.save(project)
        return project

    def save(self, project):
        with self.lock, self.connect() as db:
            db.execute("INSERT OR REPLACE INTO projects VALUES(?,?,?,?)", (project["id"], project["name"], time.time(), json.dumps(project)))

    def get(self, pid):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise KeyError("Project not found")
        return json.loads(row[0])

    def update(self, pid, fn, revision=None):
        with self.lock:
            project = self.get(pid)
            if revision is not None and revision != project["revision"]:
                raise ValueError("Project changed. Reload and try again.")
            updated = fn(copy.deepcopy(project))
            updated["revision"] = project["revision"] + 1
            self.save(updated)
            return updated

    def list(self):
        with self.connect() as db:
            return [{"id": r[0], "name": r[1], "updated": r[2]} for r in db.execute("SELECT id,name,updated FROM projects ORDER BY updated DESC")]

    def job_create(self, pid, kind, spec):
        jid = str(uuid.uuid4())
        now = time.time()
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", (jid,pid,kind,"queued",0,"Waiting for worker",now,now,json.dumps(spec),"{}"))
        return jid

    def job_update(self, jid, **values):
        allowed = {"status", "progress", "message", "result"}
        fields = {k: json.dumps(v) if k == "result" else v for k,v in values.items() if k in allowed}
        fields["updated"] = time.time()
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in fields)} WHERE id=?", (*fields.values(),jid))

    def jobs(self, pid=None):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM jobs " + ("WHERE project_id=? " if pid else "") + "ORDER BY created DESC LIMIT 100", (pid,) if pid else ()).fetchall()
        return [{**dict(r), "spec": json.loads(r["spec"]), "result": json.loads(r["result"])} for r in rows]
