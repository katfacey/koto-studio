# Working on KOTO Studio on your Windows PC

Your existing installation is already an editable source workspace. Its folder
may still be named 0.2.0 after updating the contents to 0.2.5; keep the path unchanged:

```text
F:\ai\AI Vibe Code Projects and Output\Programs\koto-studio\KOTO-Studio-v0.2.0
```

Open that folder in the local Codex application or your code editor. Start a
coding session with that folder selected as its workspace. Downloading source
does not connect a cloud coding session to your PC's filesystem.

To use a fresh separate folder instead, extract the complete source package under
`F:\ai\AI Vibe Code Projects and Output\Programs`. The packaged ZIP contains a
`KOTO-Studio` folder. Run Install.cmd there, then the optional installers you need.
Keep the existing folder if you want to reuse its installed environments, model
downloads, and project data without setting up another copy.

For the Piper JSON fix, replace your existing `scripts\install.ps1` with the
updated file. In PowerShell, run only the Piper profile:

```powershell
Set-Location -LiteralPath 'F:\ai\AI Vibe Code Projects and Output\Programs\koto-studio\KOTO-Studio-v0.2.0'
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File scripts\install.ps1 -Profile piper
```

The verified voice download is reused, and project data is preserved.

Edit `frontend\src\app.js` and `frontend\src\styles.css` for the editor. Rebuild
using the app-owned Python, then refresh the browser:

```powershell
& '.\.venv\Scripts\python.exe' scripts\build_frontend.py
```

Edit `backend\koto` for the API, queue, media processing, and model adapters.
Stop the running KOTO terminal with Ctrl+C, then run Start.cmd after backend changes. No Node/npm or system Python is needed
to build or run the app. Tests and runtime details are in README.md and VALIDATION.md.
