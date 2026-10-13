module.exports = {
  run: [
    { method: 'shell.run', params: { message: 'conda install -y -c conda-forge ffmpeg' } },
    { method: 'shell.run', params: { venv: 'env', message: 'pip install -r backend/requirements.txt' } },
    { method: 'shell.run', params: { venv: 'env', message: 'python scripts/build_frontend.py' } },
    { method: 'notify', params: { html: 'KOTO core installed. Start the studio; optional model workers have separate installers.' } },
  ],
};
