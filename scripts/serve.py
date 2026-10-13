"""Server entry used by both Start.cmd and Pinokio's Start menu."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from koto.runtime import configure_process
from runtime_services import managed_ollama


def main():
    os.chdir(ROOT)
    configure_process()
    import uvicorn
    with managed_ollama():
        uvicorn.run("koto.app:app", host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
