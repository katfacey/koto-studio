module.exports = {
  version: '3.0',
  title: 'KOTO Studio',
  description: 'Self-contained local dubbing editor. Installs its own Python, FFmpeg, and optional model runtimes on Windows + NVIDIA.',
  icon: 'icon.svg',
  menu: async (kernel, info) => {
    const modelMenu = [
      { icon: 'fa-solid fa-wand-magic-sparkles', text: 'Install default dubbing workers (several GB)', href: 'install-models.js' },
      { icon: 'fa-solid fa-microphone', text: 'Install Whisper worker', href: 'install-whisper.js' },
      { icon: 'fa-solid fa-wave-square', text: 'Install audio workers', href: 'install-audio.js' },
      { icon: 'fa-solid fa-comment', text: 'Install Piper worker', href: 'install-piper.js' },
      { icon: 'fa-solid fa-comment', text: 'Install XTTS worker', href: 'install-xtts.js' },
      { icon: 'fa-solid fa-language', text: 'Install local translation (~12 GB)', href: 'install-translation.js' },
      { icon: 'fa-solid fa-layer-group', text: 'Install all runtimes (~20+ GB)', href: 'install-all.js' },
    ];
    if (kernel.platform && kernel.platform !== 'win32') return [{ icon: 'fa-solid fa-circle-info', text: 'This installer requires x64 Windows', href: 'PINOKIO.md' }];
    const installing = ['install.js','install-audio.js','install-whisper.js','install-piper.js','install-xtts.js','install-translation.js','install-models.js','install-all.js'].find(file => info.running(file));
    if (installing) return [{ icon: 'fa-solid fa-download', text: 'Installing app-owned runtime', href: installing }];
    if (info.running('start.js')) return [
      { icon: 'fa-solid fa-desktop', text: 'Open Studio', href: 'http://127.0.0.1:8765' },
      { icon: 'fa-solid fa-terminal', text: 'Server', href: 'start.js' },
      ...modelMenu,
    ];
    if (!info.exists('runtime/installed.json') || !info.exists('.venv/Scripts/python.exe')) return [{ icon: 'fa-solid fa-download', text: 'Install KOTO (Python + FFmpeg included)', href: 'install.js' }, { icon: 'fa-solid fa-book', text: 'Installation guide', href: 'PINOKIO.md' }];
    return [
      { icon: 'fa-solid fa-play', text: 'Start', href: 'start.js' },
      ...modelMenu,
      { icon: 'fa-solid fa-download', text: 'Reinstall core', href: 'install.js' },
    ];
  },
};
