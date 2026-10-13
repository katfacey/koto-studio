module.exports = {
  daemon: true,
  run: [
    { method: 'shell.run', params: {
      venv: 'env',
      message: 'python -m uvicorn koto.app:app --app-dir backend --host 127.0.0.1 --port 8765',
      on: [{ event: '/http:\/\/127\.0\.0\.1:8765/', done: true }],
    } },
    { method: 'local.set', params: { url: 'http://127.0.0.1:8765' } },
  ],
};
