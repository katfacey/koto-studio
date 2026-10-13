module.exports = { run: [
  { method: 'shell.run', params: { venv: '.workers/whisper', message: 'python -m pip install "faster-whisper>=1.1,<2" "ctranslate2>=4.6,<5"' } },
  { method: 'notify', params: { html: 'Whisper worker installed. Windows CUDA inference also needs compatible cuBLAS/cuDNN DLLs. Refresh Model manager; CPU mode is available.' } },
] };
