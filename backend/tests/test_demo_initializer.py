from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "init_demo.py"


def run_init(destination: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--destination", str(destination)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_initialization_is_independent_and_repeat_preserves_data(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert run_init(first).returncode == 0
    before = hashlib.sha256((first / "demo.sqlite3").read_bytes()).hexdigest()
    repeated = run_init(first)
    assert repeated.returncode == 0
    assert "existing state preserved" in repeated.stdout
    assert hashlib.sha256((first / "demo.sqlite3").read_bytes()).hexdigest() == before
    assert run_init(second).returncode == 0
    assert hashlib.sha256((second / "demo.sqlite3").read_bytes()).hexdigest() == before


def test_unrelated_existing_destination_is_not_modified(tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    result = run_init(destination)
    assert result.returncode != 0
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert sorted(p.name for p in destination.iterdir()) == ["keep.txt"]
