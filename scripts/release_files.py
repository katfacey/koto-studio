"""List distributable source files without installed tools, caches, or user media."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", ".workers", "env", "runtime", "data", "node_modules", ".npm-cache", "__pycache__", ".pytest_cache", ".git"}


def source_files(root=ROOT):
    root = Path(root)
    return sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink() and not any(part in SKIP for part in path.relative_to(root).parts) and path.suffix not in (".pyc", ".log", ".zip", ".bundle"))


def refresh_source_manifest(root=ROOT):
    root = Path(root)
    target = root / "scripts" / "source-files.json"
    names = {path.relative_to(root).as_posix() for path in source_files(root)}
    names.add("scripts/source-files.json")
    target.write_text(json.dumps(sorted(names), indent=2) + "\n", encoding="utf-8")
    return source_files(root)
