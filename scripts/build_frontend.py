"""Copy the dependency-free editor into the backend's static distribution."""
from pathlib import Path
import shutil
from release_files import refresh_source_manifest

ROOT = Path(__file__).resolve().parents[1]
frontend = ROOT / "frontend"
dist = frontend / "dist"
dist.mkdir(exist_ok=True)
shutil.copytree(frontend / "src", dist / "assets", dirs_exist_ok=True)
shutil.copy2(frontend / "index.html", dist / "index.html")
refresh_source_manifest()
print(f"Editor built: {dist}")
