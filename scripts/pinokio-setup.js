// Shared Windows bootstrap, executed by Pinokio's own shell. No Python/conda/PATH lookup.
module.exports = (profile) => ({
  run: [{ method: 'shell.run', params: {
    message: `"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File scripts\\install.ps1 -Profile ${profile}`,
  } }],
});
