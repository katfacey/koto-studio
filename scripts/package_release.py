"""Create a source release including built static assets, without local media/envs."""
from pathlib import Path
import json
import re
import zipfile
from release_files import refresh_source_manifest

ROOT = Path(__file__).resolve().parents[1]
version = json.loads((ROOT / "scripts/runtime-manifest.json").read_text(encoding="utf-8"))["version"]
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise ValueError("Release version must have the form major.minor.patch")
target = ROOT.parent / f"KOTO-Studio-v{version}.zip"
with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED) as archive:
    for path in refresh_source_manifest(ROOT):
        relative = path.relative_to(ROOT)
        # Stable metadata makes the same source snapshot reproducible on CI/local.
        entry = zipfile.ZipInfo((Path("KOTO-Studio") / relative).as_posix())
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.create_system = 3
        entry.external_attr = 0o100644 << 16
        archive.writestr(entry, path.read_bytes())
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert "KOTO-Studio/frontend/dist/index.html" in archive.namelist()
    assert "KOTO-Studio/Start.cmd" in archive.namelist()
    for launcher in ("Install.cmd", "Install-Models.cmd", "Install-Translation.cmd", "Install-Diarization.cmd", "Install-Piper.cmd", "Install-Reference-Voices.cmd", "Install-Separation.cmd", "Install-Qwen-Voices.cmd", "Install-Voice-Design.cmd"):
        assert f"KOTO-Studio/{launcher}" in archive.namelist()
    assert "KOTO-Studio/scripts/source-files.json" in archive.namelist()
    assert "KOTO-Studio/LICENSE" in archive.namelist()
    assert archive.read("KOTO-Studio/frontend/dist/assets/app.js") == archive.read("KOTO-Studio/frontend/src/app.js")
    assert not any("/data/" in p or "/.venv/" in p or "/.workers/" in p or "/runtime/" in p for p in archive.namelist())
    print(f"Packaged {len(archive.namelist())} files: {target} ({target.stat().st_size:,} bytes)")
