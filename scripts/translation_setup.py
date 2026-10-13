"""Download a chosen local model using this app's private Ollama executable."""
import argparse
import os
import subprocess
from pathlib import Path

from runtime_services import managed_ollama, runtime_environment

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:14b")
    args = parser.parse_args()
    if not args.model or args.model.startswith("-") or "cloud" in args.model.lower():
        raise SystemExit("Choose a local Ollama model name; cloud models are not supported by this installer")
    executable = ROOT / "runtime" / "ollama" / ("ollama.exe" if os.name == "nt" else "ollama")
    with managed_ollama(required=True):
        subprocess.run([str(executable), "pull", args.model], cwd=ROOT, env=runtime_environment(), check=True)
    print(f"Installed {args.model} inside runtime/models/ollama. Restart KOTO to start its managed translation server.")


if __name__ == "__main__":
    main()
