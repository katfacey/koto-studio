module.exports = { run: [
  { method: 'shell.run', params: { venv: '.workers/audio', message: 'python -m pip install "torch==2.7.1" "torchaudio==2.7.1" --index-url https://download.pytorch.org/whl/cu128' } },
  { method: 'shell.run', params: { venv: '.workers/audio', message: 'python -m pip install "demucs>=4,<5" "pyannote.audio>=3.3,<4" -c scripts/torch-constraints.txt' } },
  { method: 'shell.run', params: { venv: '.workers/audio', message: 'python scripts/check_gpu.py' } },
] };
