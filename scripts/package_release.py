"""Create a source release including built static assets, without local media/envs."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
target = ROOT.parent / "KOTO-Studio-v0.1.0.zip"
skip = {".venv",".workers","env","data","node_modules",".npm-cache","__pycache__",".pytest_cache",".git"}
with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in skip for part in relative.parts) or path.suffix in (".pyc",".log",".zip"):
            continue
        archive.write(path,Path("KOTO-Studio")/relative)
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert "KOTO-Studio/frontend/dist/index.html" in archive.namelist()
    assert "KOTO-Studio/Start.cmd" in archive.namelist()
    assert not any("/data/" in p or "/.venv/" in p for p in archive.namelist())
    print(f"Packaged {len(archive.namelist())} files: {target} ({target.stat().st_size:,} bytes)")
