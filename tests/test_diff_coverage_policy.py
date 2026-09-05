"""Repository contract for the risk-based changed-line coverage pilot."""

import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_changed_line_coverage_is_scoped_and_fail_closed() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow_path.is_file():
        if (ROOT / ".git").exists():
            pytest.fail("CI workflow is missing from the repository checkout")
        pytest.skip("CI workflow is not included in the source distribution")
    workflow = workflow_path.read_text(encoding="utf-8")

    assert re.search(r'"coverage==\d+\.\d+\.\d+"', pyproject)
    assert re.search(r'"diff-cover==\d+\.\d+\.\d+"', pyproject)
    assert "fetch-depth: 0" in workflow
    assert "--source=pyfpa/memory" in workflow
    assert '--include="pyfpa/memory/connectors.py,pyfpa/memory/workspace.py"' in workflow
    assert "--compare-branch=origin/main" in workflow
    assert "--branch-coverage" in workflow
    assert "--fail-under=100" in workflow


def test_no_tracked_file_is_covered_by_an_ignore_rule() -> None:
    """Generated artifacts stay out of the index.

    A committed file that .gitignore also claims is rewritten by every
    documented example run, so `git add -A` sweeps an unreviewable binary diff
    into the next commit.
    """
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--ignored", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.split() == []
