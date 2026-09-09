"""Build a source-only archive from an explicit allowlist; exclude all local databases."""
from pathlib import Path
import hashlib
import json
import zipfile
import argparse

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=root / "dist" / "borrowbridge-source.zip")
destination = parser.parse_args().output.resolve()
destination.parent.mkdir(parents=True, exist_ok=True)
files = [root / n for n in (".gitignore", ".python-version", "pyproject.toml", "uv.lock", "LICENSE",
                            "README.md", "ARCHITECTURE.md", "TEST_REPORT.md", "domain.py", "worker.py",
                            "server.py", "test_domain.py", "verify_live.py", "package_release.py")]
files += sorted((root / "static").glob("*"))
files += sorted((root / "evidence").glob("*"))
assert all(p.is_file() and p.resolve().is_relative_to(root) for p in files)
assert all("private" not in p.relative_to(root).parts and ".venv" not in p.relative_to(root).parts for p in files)
with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, "borrowbridge/" + path.relative_to(root).as_posix())
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
print(json.dumps({"path": str(destination), "files": len(files), "bytes": destination.stat().st_size,
                  "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}))
