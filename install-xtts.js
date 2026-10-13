module.exports = { run: [
  { method: 'shell.run', params: { venv: '.workers/xtts', message: 'python -m pip install "torch==2.7.1" "torchaudio==2.7.1" --index-url https://download.pytorch.org/whl/cu128' } },
  { method: 'shell.run', params: { venv: '.workers/xtts', message: 'python -m pip install "coqui-tts>=0.27,<1" soundfile -c scripts/torch-constraints.txt' } },
  { method: 'shell.run', params: { venv: '.workers/xtts', message: 'python scripts/check_gpu.py' } },
  { method: 'notify', params: { html: 'Supply locally provisioned XTTS model files, select their directory, and attach a speaker reference in the editor.' } },
] };
