import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "storage_backup", Path(__file__).parents[1] / "scripts/storage_backup.py"
)
assert spec and spec.loader
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_restore_after_test_object_deletion_preserves_hashes(tmp_path):
    source = tmp_path / "source"
    (source / "project").mkdir(parents=True)
    pdf = source / "project" / "drawing.pdf"
    pdf.write_bytes(b"%PDF-example")
    expected = backup.copy_verified(source, tmp_path / "backup")
    pdf.unlink()
    restored = backup.copy_verified(tmp_path / "backup", tmp_path / "restored", restore=True)
    assert restored == expected
    assert (tmp_path / "restored/project/drawing.pdf").read_bytes() == b"%PDF-example"


def test_tampered_backup_and_nonempty_destination_are_rejected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "drawing.pdf").write_bytes(b"original")
    target = tmp_path / "backup"
    backup.copy_verified(source, target)
    (target / "drawing.pdf").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="digest mismatch"):
        backup.copy_verified(target, tmp_path / "restored", restore=True)
    with pytest.raises(ValueError, match="empty"):
        backup.copy_verified(source, target)
