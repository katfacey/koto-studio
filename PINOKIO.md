# Install KOTO Studio in Pinokio · Windows x64

**The Pinokio installer is `Install-Pinokio.cmd`.** The scripts used by Pinokio
itself are `pinokio.js` (menu), `install.js` (core install), and `start.js` (server).
They are all in the repository root.

## Private repository / downloaded ZIP

1. Sign into GitHub and [download the full source ZIP](https://github.com/katfacey/koto-studio/archive/refs/heads/main.zip).
2. Extract the whole folder. Do not download just the `.cmd` file; it needs the
   accompanying scripts and source manifest.
3. Close any running KOTO session, then double-click **Install-Pinokio.cmd**.
4. Select your **Pinokio Home** folder, the folder containing `api`. Its location
   is shown in Pinokio Settings. The installer copies the application into
   `<Pinokio Home>\api\koto-studio` and installs its own Python and FFmpeg there.
5. Open or restart Pinokio. In **Downloaded**, open **KOTO Studio → Start**.

This workflow uses the ZIP already downloaded through your browser. It does not
require GitHub credentials, Git, or `gh` inside Pinokio.

If you prefer a direct clone, use Pinokio's app download/import feature with
`https://github.com/katfacey/koto-studio`. A private clone requires working GitHub
authentication in Pinokio; the ZIP workflow above avoids that requirement.

## Pinokio menu

- **Install KOTO (Python + FFmpeg included)** bootstraps the core application.
- **Start** runs `.venv\Scripts\python.exe scripts\serve.py` explicitly.
- **Install default dubbing workers** installs separation, speech recognition,
  and Piper with a downloaded English voice.
- Individual **audio / Whisper / Piper / XTTS** installers let you choose what
  to install.
- **Install local translation** downloads the private Ollama runtime and Qwen3
  14B weights (roughly 12 GB).
- **Install all runtimes** installs all optional workers and local translation;
  it still requires provisioned XTTS and gated diarization model files.
- **Open Studio** opens `http://127.0.0.1:8765` after Start.

All menu installers call the same `scripts/install.ps1` bootstrap as the
standalone application. They do not use Pinokio's global conda environment or
look up Python, FFmpeg, pip, or Ollama on the system PATH.

To install into a known Home path without the folder picker:

```cmd
Install-Pinokio.cmd -PinokioHome "D:\Pinokio"
```

Pinokio itself, Windows, a browser, an up-to-date NVIDIA driver, and internet for
initial downloads are the host prerequisites. No system Python, FFmpeg, Node,
Ollama, CUDA toolkit, or manual PATH edit is required by KOTO's managed setup.
See [README.md](README.md) for disk requirements, model setup, and limitations.
