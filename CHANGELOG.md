# Changelog

## 0.2.5

This version names the current development baseline. The changes below were built
and validated across the recent source updates; no undocumented 0.2.1–0.2.4 releases
are implied.

### Editing

- Resize panels and dialogue areas; keep panel sizes across browser sessions.
- Drag clips between speaker tracks, retime/trim clips, and reorder speaker lanes.
- Mute speakers/original/background audio and hide video or subtitles.
- Delete selected clips with Delete/Backspace, protect normal text editing, and undo.
- Autosave edits without overwriting newer typing or an in-progress trim gesture.

### Voices and translation

- Use original speaker dialogue or uploaded samples as XTTS references.
- Cache clean source references while preserving original timestamps during retiming.
- Generate by speaker batch with shared Piper voice or XTTS reference conditioning.
- Preserve finished takes on cancellation and reuse current takes on retry.
- Select English mix and notify the user after successful generation.
- Show estimated/measured timing, reversible speed controls, and optional per-clip
  alternate translations.

### Export and installation

- Recommend timing fixes while allowing **Render anyway** for overlong speech.
- Preserve full takes at their existing starts, including overlapping dialogue and
  audio tails beyond the video track; retain timing warnings in Jobs.
- Show affected line numbers/speakers and offer clip review and safe timing fixes.
- Keep Python, FFmpeg, GPU libraries, workers, models, and caches inside the app folder.
- Repair moved/system-Python worker environments with the app-owned runtime.
- Handle Piper's case-sensitive UTF-8 voice configuration correctly.
- Skip image subtitles during default track selection and show Prepare progress/errors.

### Documentation and packaging

- Align the application, launcher, installer metadata, and package name to 0.2.5.
- Rewrite onboarding, model setup, troubleshooting, and validation documentation.
- Include an actual Windows editor screenshot.
- Prepare a researched repository description and topics for GitHub About.
- Keep the repository private; no Pinokio installer is included.
