"""Copy and verify immutable PDF storage; restore only into an empty destination."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def manifest(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlinks are not allowed in document backups")
        if path.is_file():
            if path.name == "backup-manifest.json":
                continue
            if path.suffix == ".upload":
                raise ValueError("Upload in progress: quiesce writes before backup")
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            files[path.relative_to(root).as_posix()] = digest.hexdigest()
    return files


def copy_verified(source: Path, target: Path, restore: bool = False) -> dict[str, str]:
    source = source.resolve()
    target = target.resolve()
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("Source and target must be separate directories")
    if not source.is_dir() or (target.exists() and any(target.iterdir())):
        raise ValueError("Source must exist and target must be empty")
    expected = manifest(source)
    if restore:
        saved = json.loads((source / "backup-manifest.json").read_text())
        if saved != expected:
            raise ValueError("Backup digest mismatch")
    shutil.copytree(source, target, dirs_exist_ok=True)
    if manifest(target) != expected:
        raise ValueError("Restored storage digest mismatch")
    (target / "backup-manifest.json").write_text(json.dumps(expected, sort_keys=True))
    return expected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore", "verify"])
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "verify":
        saved = json.loads((args.source / "backup-manifest.json").read_text())
        if saved != manifest(args.source):
            raise ValueError("Backup digest mismatch")
    else:
        if args.target is None:
            parser.error("target is required")
        copy_verified(args.source, args.target, restore=args.action == "restore")
    print("Storage digests verified")
