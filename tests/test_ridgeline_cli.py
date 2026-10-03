"""CLI destinations are caller-selected; existing destinations must be refused.

B101 dispositions below apply only to pytest outcome assertions.
"""

import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def example_source_path(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))


@pytest.mark.parametrize("module,basename", [("decisions", "decisions"), ("liquidity_grid", "liquidity")])
@pytest.mark.parametrize("relative", [False, True])
def test_new_selected_destination_produces_only_the_documented_files(tmp_path, monkeypatch, module, basename, relative):
    destination = tmp_path / "new-output"
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    selected = "../new-output" if relative else str(destination)
    monkeypatch.setattr(sys, "argv", [module, "--output", selected])
    runpy.run_module(f"examples.ridgeline.{module}", run_name="__main__")
    assert {path.name for path in destination.iterdir()} == {f"{basename}.json", f"{basename}.md"}  # nosec B101


@pytest.mark.parametrize("module", ["decisions", "liquidity_grid"])
@pytest.mark.parametrize("directory", [False, True])
def test_existing_destination_and_its_content_are_preserved(tmp_path, monkeypatch, module, directory):
    destination = tmp_path / "existing"
    if directory:
        destination.mkdir()
        sentinel = destination / "sentinel.txt"
    else:
        sentinel = destination
    sentinel.write_text("retain this content", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [module, "--output", str(destination)])
    with pytest.raises(FileExistsError):
        runpy.run_module(f"examples.ridgeline.{module}", run_name="__main__")
    assert sentinel.read_text(encoding="utf-8") == "retain this content"  # nosec B101
    if directory:
        assert list(destination.iterdir()) == [sentinel]  # nosec B101


@pytest.mark.parametrize("module", ["decisions", "liquidity_grid"])
def test_output_destination_is_required(monkeypatch, module):
    monkeypatch.setattr(sys, "argv", [module])
    with pytest.raises(SystemExit) as raised:
        runpy.run_module(f"examples.ridgeline.{module}", run_name="__main__")
    assert raised.value.code == 2  # nosec B101
