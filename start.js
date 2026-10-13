module.exports = {
  daemon: true,
  run: [
    { method: 'shell.run', params: {
      message: '".venv\\Scripts\\python.exe" "scripts\\serve.py"',
      on: [{ event: '/http:\/\/127\.0\.0\.1:8765/', done: true }],
    } },
    { method: 'local.set', params: { url: 'http://127.0.0.1:8765' } },
  ],
};
