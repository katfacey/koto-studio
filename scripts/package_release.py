"""Create a source release including built static assets, without local media/envs."""
from pathlib import Path
import zipfile
from release_files import refresh_source_manifest

ROOT = Path(__file__).resolve().parents[1]
target = ROOT.parent / "KOTO-Studio-v0.2.0.zip"
with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED) as archive:
    for path in refresh_source_manifest(ROOT):
        relative = path.relative_to(ROOT)
        archive.write(path,Path("KOTO-Studio")/relative)
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert "KOTO-Studio/frontend/dist/index.html" in archive.namelist()
    assert "KOTO-Studio/Start.cmd" in archive.namelist()
    for launcher in ("Install.cmd", "Install-Models.cmd", "Install-Translation.cmd"):
        assert f"KOTO-Studio/{launcher}" in archive.namelist()
    assert "KOTO-Studio/scripts/source-files.json" in archive.namelist()
    assert not any("/data/" in p or "/.venv/" in p or "/runtime/" in p for p in archive.namelist())
    print(f"Packaged {len(archive.namelist())} files: {target} ({target.stat().st_size:,} bytes)")
