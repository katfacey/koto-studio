module.exports = { run: [
  { method: 'shell.run', params: { venv: '.workers/piper', message: 'python -m pip install "piper-tts>=1.3,<2"' } },
  { method: 'notify', params: { html: 'Piper worker installed. Supply an English .onnx voice and matching .onnx.json file in Model manager.' } },
] };
