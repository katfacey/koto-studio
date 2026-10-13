"""Start and stop only services owned by this KOTO invocation."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from koto.runtime import executable, ollama_url, runtime_environment


def service_ready(url):
    try:
        request = urllib.request.Request(url + "/api/version")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=1) as response:
            return isinstance(json.load(response).get("version"), str)
    except (OSError, ValueError, AttributeError):
        return False


def stop_owned_process(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run([executable("taskkill"), "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        proc.wait(timeout=5)


@contextmanager
def managed_ollama(root=ROOT, required=False, timeout=45):
    root = Path(root)
    candidate = root / "runtime" / "ollama" / ("ollama.exe" if os.name == "nt" else "ollama")
    if not candidate.is_file():
        if required:
            raise RuntimeError("Run Install-Translation.cmd to install the app-owned translation runtime")
        yield None
        return
    env = runtime_environment(root=root)
    url = ollama_url(env)
    if service_ready(url):
        # Do not terminate a server started by another KOTO session or installer.
        yield None
        return
    env["OLLAMA_HOST"] = urlparse(url).netloc
    env["OLLAMA_KEEP_ALIVE"] = "0"
    Path(env["OLLAMA_MODELS"]).mkdir(parents=True, exist_ok=True)
    logs = root / "runtime" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / "ollama.log"
    with log.open("a", encoding="utf-8") as handle:
        proc = subprocess.Popen([str(candidate), "serve"], cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=os.name != "nt", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    try:
        deadline = time.monotonic() + timeout
        while not service_ready(url):
            if proc.poll() is not None:
                raise RuntimeError("Local translation server exited: " + log.read_text(encoding="utf-8", errors="replace")[-1200:])
            if time.monotonic() > deadline:
                raise RuntimeError("Local translation server did not start; see runtime/logs/ollama.log")
            time.sleep(.15)
        yield proc
    finally:
        stop_owned_process(proc)
