"""CLI destinations are caller-selected; existing destinations must be refused.

B101 dispositions below apply only to pytest outcome assertions.
"""

import os.path
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module,basename", [("decisions", "decisions"), ("liquidity_grid", "liquidity")])
@pytest.mark.parametrize("relative", [False, True])
def test_new_selected_destination_produces_only_the_documented_files(tmp_path, module, basename, relative):
    destination = tmp_path / "new-output"
    selected = os.path.relpath(destination, ROOT) if relative else str(destination)
    result = subprocess.run([sys.executable, "-m", f"examples.ridgeline.{module}", "--output", selected],
                            cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr  # nosec B101
    assert {path.name for path in destination.iterdir()} == {f"{basename}.json", f"{basename}.md"}  # nosec B101


@pytest.mark.parametrize("module", ["decisions", "liquidity_grid"])
@pytest.mark.parametrize("directory", [False, True])
def test_existing_destination_and_its_content_are_preserved(tmp_path, module, directory):
    destination = tmp_path / "existing"
    if directory:
        destination.mkdir()
        sentinel = destination / "sentinel.txt"
    else:
        sentinel = destination
    sentinel.write_text("retain this content", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", f"examples.ridgeline.{module}", "--output", str(destination)],
                            cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode != 0  # nosec B101
    assert sentinel.read_text(encoding="utf-8") == "retain this content"  # nosec B101
    if directory:
        assert list(destination.iterdir()) == [sentinel]  # nosec B101


@pytest.mark.parametrize("module", ["decisions", "liquidity_grid"])
def test_output_destination_is_required(module):
    result = subprocess.run([sys.executable, "-m", f"examples.ridgeline.{module}"],
                            cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 2  # nosec B101
