"""Local browser launcher. Optional --desktop uses a native pywebview window."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from runtime_services import runtime_environment

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8765"


def health():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL + "/api/health",timeout=2) as response:
            result = json.load(response)
            return result.get("local") is True and result.get("version") == "0.2.5"
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--desktop", action="store_true", help="Requires pip install pywebview; browser mode has no native-window dependency")
    args = parser.parse_args()
    native = None
    if args.desktop:
        try:
            import webview
            native = webview
        except ImportError:
            raise SystemExit("Native window mode requires: .venv\\Scripts\\python -m pip install pywebview")
    if not (ROOT/"frontend"/"dist"/"index.html").exists():
        subprocess.run([sys.executable,str(ROOT/"scripts"/"build_frontend.py")],check=True)
    already = health()
    proc = None
    if not already:
        env = runtime_environment()
        proc = subprocess.Popen([sys.executable,str(ROOT/"scripts"/"serve.py")],cwd=ROOT,env=env)
        for _ in range(400):
            if proc.poll() is not None:
                raise SystemExit("Backend exited. Check its output above; port 8765 may already be in use.")
            if health():
                break
            time.sleep(0.15)
        else:
            proc.terminate()
            raise SystemExit("Backend did not start. Check dependency installation.")
    print(f"KOTO Studio: {URL}",flush=True)
    try:
        if native:
            native.create_window("KOTO Studio",URL,width=1440,height=960,min_size=(1040,740))
            native.start()
        else:
            webbrowser.open(URL)
            if proc:
                print("Keep this terminal open. Press Ctrl+C to stop.",flush=True)
                proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
