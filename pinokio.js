module.exports = {
  version: '3.0',
  title: 'KOTO Studio',
  description: 'Local-first Japanese-to-English dubbing editor for Windows + NVIDIA.',
  icon: 'icon.svg',
  menu: async (kernel, info) => {
    const modelMenu = [
      { icon: 'fa-solid fa-microphone', text: 'Install Whisper worker', href: 'install-whisper.js' },
      { icon: 'fa-solid fa-wave-square', text: 'Install audio workers', href: 'install-audio.js' },
      { icon: 'fa-solid fa-comment', text: 'Install Piper worker', href: 'install-piper.js' },
      { icon: 'fa-solid fa-comment', text: 'Install XTTS worker', href: 'install-xtts.js' },
    ];
    if (info.running('install.js')) return [{ icon: 'fa-solid fa-download', text: 'Installing', href: 'install.js' }];
    if (info.running('start.js')) return [
      { icon: 'fa-solid fa-desktop', text: 'Open Studio', href: 'http://127.0.0.1:8765' },
      { icon: 'fa-solid fa-terminal', text: 'Server', href: 'start.js' },
      ...modelMenu,
    ];
    if (!info.exists('env')) return [{ icon: 'fa-solid fa-download', text: 'Install', href: 'install.js' }];
    return [
      { icon: 'fa-solid fa-play', text: 'Start', href: 'start.js' },
      ...modelMenu,
      { icon: 'fa-solid fa-download', text: 'Reinstall core', href: 'install.js' },
    ];
  },
};
