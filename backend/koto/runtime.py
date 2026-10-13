"""App-owned executables, caches, and child-process environments.

Windows production installs never need Python/FFmpeg/Ollama on the user's PATH.
Only standard-library imports are used so this module also runs in model workers.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]


def runtime_environment(root=ROOT, base=None, python=None, windows=None):
    env = dict(os.environ if base is None else base)
    root = Path(root).resolve()
    runtime = root / "runtime"
    env.update({
        "KOTO_APP_ROOT": str(root),
        "HF_HOME": str(runtime / "cache" / "huggingface"),
        "TORCH_HOME": str(runtime / "cache" / "torch"),
        "XDG_CACHE_HOME": str(runtime / "cache"),
        "UV_CACHE_DIR": str(runtime / "cache" / "uv"),
        "UV_PYTHON_INSTALL_DIR": str(runtime / "python"),
        "UV_PYTHON_BIN_DIR": str(runtime / "python" / "bin"),
        "OLLAMA_MODELS": str(runtime / "models" / "ollama"),
        "OLLAMA_HOST": "127.0.0.1:11435",
        "KOTO_OLLAMA_URL": env.get("KOTO_OLLAMA_URL", "http://127.0.0.1:11435"),
    })
    is_windows = os.name == "nt" if windows is None else windows
    search = [runtime / "ffmpeg" / "bin", runtime / "ollama"]
    if is_windows:
        executable = Path(python or sys.executable)
        worker = executable.parent.parent
        search.extend([
            worker / "Lib" / "site-packages" / "torch" / "lib",
            worker / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
            worker / "Lib" / "site-packages" / "nvidia" / "cudnn" / "bin",
        ])
        if env.get("SystemRoot"):
            search.append(Path(env["SystemRoot"]) / "System32")
    separator = ";" if is_windows else os.pathsep
    # Changes are process-local, never written to Windows' user/system PATH.
    env["PATH"] = separator.join([*(str(p) for p in search if p.is_dir()), env.get("PATH", "")])
    return env


_dll_handles = []


def configure_process():
    os.environ.update(runtime_environment(python=sys.executable))
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        for item in os.environ["PATH"].split(";"):
            path = Path(item)
            if path.is_dir() and ("torch" in path.parts or "nvidia" in path.parts):
                _dll_handles.append(os.add_dll_directory(str(path)))


def executable(name, root=ROOT, env=None, windows=None):
    env = os.environ if env is None else env
    is_windows = os.name == "nt" if windows is None else windows
    suffix = ".exe" if is_windows else ""
    root = Path(root).resolve()
    configured = env.get("KOTO_" + name.upper())
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute() or not candidate.is_file():
            raise RuntimeError(f"KOTO_{name.upper()} must point to an existing absolute executable path")
        return str(candidate)
    if name in ("ffmpeg", "ffprobe"):
        candidates = [root / "runtime" / "ffmpeg" / "bin" / (name + suffix)]
    elif name == "ollama":
        candidates = [root / "runtime" / "ollama" / (name + suffix)]
    elif name == "nvidia-smi":
        candidates = []
        if env.get("SystemRoot"):
            candidates.append(Path(env["SystemRoot"]) / "System32" / "nvidia-smi.exe")
        if env.get("ProgramFiles"):
            candidates.append(Path(env["ProgramFiles"]) / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe")
    elif name == "taskkill":
        candidates = [Path(env.get("SystemRoot", "C:/Windows")) / "System32" / "taskkill.exe"]
    else:
        raise ValueError("Unknown runtime executable")
    for path in candidates:
        if path.is_file():
            return str(path)
    # Linux development/test hosts can use explicit system tools. Windows
    # installs require their managed binaries, with no silent PATH fallback.
    if not is_windows or env.get("KOTO_ALLOW_SYSTEM_TOOLS") == "1":
        found = shutil.which(name, path=env.get("PATH", ""))
        if found:
            return str(Path(found).resolve())
    raise RuntimeError(f"Managed {name} is missing. Run Install.cmd (or the matching optional installer).")


def ollama_url(env=None):
    env = os.environ if env is None else env
    value = env.get("KOTO_OLLAMA_URL", "http://127.0.0.1:11435").rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Ollama must use a local loopback HTTP endpoint")
    return value
