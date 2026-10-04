"""Require the reviewed component checks before a release can publish."""

import re
import tomllib
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = "ec6b0ee76446f11aefb7fa0c203f2e01b4c9a711"
# These are component jobs from successful main-branch runs, plus aggregates that
# require every job in their workflow to succeed; never a skip-tolerant aggregate
# gate. Review the list when a component's CI contract changes.
REQUIRED = {
    "release.yml": [
        ".github/workflows/no-ai-attribution.yml: Attribution policy / Attribution policy runner",
        ".github/workflows/ci.yml: connector-security-windows",
        ".github/workflows/ci.yml: lint",
        ".github/workflows/ci.yml: minimum-resolution (ubuntu-latest, 3.14)",
        ".github/workflows/ci.yml: minimum-resolution (windows-latest, 3.14)",
        ".github/workflows/ci.yml: test (3.14)",
        ".github/workflows/ci.yml: ci-gates",
        ".github/workflows/codeql.yml: Analyze (actions)",
        ".github/workflows/codeql.yml: Analyze (python)",
        ".github/workflows/codeql.yml: codeql-gates"
    ]
}


class ReleaseChecksTests(unittest.TestCase):
    def test_test_matrix_keeps_coverage_and_audit_on_the_release_interpreter(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        job = workflow["jobs"]["test"]
        versions = job["strategy"]["matrix"]["python-version"]
        self.assertEqual(versions, ["3.14"])
        self.assertEqual(
            {f".github/workflows/ci.yml: test ({version})" for version in versions},
            {selector for selector in REQUIRED["release.yml"] if ": test (" in selector},
        )
        for step in job["steps"]:
            if "coverage" in step.get("run", "") or "uv audit" in step.get("run", ""):
                self.assertEqual(step["if"], "matrix.python-version == '3.14'")

    def test_minimum_dependency_jobs_match_release_selectors(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        job = workflow["jobs"]["minimum-resolution"]
        self.assertEqual(
            job["name"], "minimum-resolution (${{ matrix.os }}, ${{ matrix.python-version }})"
        )
        matrix = job["strategy"]["matrix"]
        self.assertEqual(matrix, {
            "os": ["ubuntu-latest", "windows-latest"],
            "python-version": ["3.14"],
        })
        setup = next(step for step in job["steps"]
                     if step.get("uses", "").startswith("actions/setup-python@"))
        self.assertEqual(setup["with"]["python-version"], "${{ matrix.python-version }}")
        expected = {
            f".github/workflows/ci.yml: minimum-resolution ({os}, {version})"
            for os in matrix["os"] for version in matrix["python-version"]
        }
        self.assertEqual(expected, {
            selector for selector in REQUIRED["release.yml"] if ": minimum-resolution " in selector
        })

    def test_every_release_caller_requires_its_component_checks(self) -> None:
        workflows = ROOT / ".github" / "workflows"
        callers = sorted(
            path.name for path in workflows.glob("release*") if path.suffix in {".yml", ".yaml"}
        )
        self.assertEqual(callers, sorted(REQUIRED))
        for filename, expected in REQUIRED.items():
            with self.subTest(workflow=filename):
                text = (workflows / filename).read_text(encoding="utf-8")
                job = text.split("\n  release:\n", 1)[1].split("\n  pypi:", 1)[0]
                self.assertRegex(
                    job,
                    r"(?m)^    uses: ryanduguid/release-policy/\.github/workflows/"
                    r"release-(?:python|archive|skills)\.yml@" + POLICY + r"$",
                )
                permissions = job.split("    permissions:\n", 1)[1].split("    uses:", 1)[0]
                self.assertRegex(permissions, r"(?m)^      actions: read(?: #.*)?$")
                match = re.search(
                    r"^      required-checks: \|\n((?:        [^\n]*\n)+)", job, re.MULTILINE,
                )
                self.assertIsNotNone(match, "missing explicit component checks")
                assert match is not None
                actual = [line.strip() for line in match.group(1).splitlines()]
                self.assertCountEqual(actual, expected)
                self.assertEqual(len(actual), len(set(actual)), "duplicate check selector")
                for selector in actual:
                    path, name = selector.split(": ", 1)
                    self.assertTrue((ROOT / path).is_file(), path)
                    self.assertFalse(name.endswith(" / gates"), name)

    def test_dev_extra_pins_the_build_backend(self) -> None:
        # release-python builds without isolation, so the backend must come from
        # the locked dev extra, pinned exactly as [build-system] requires.
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requires = project["build-system"]["requires"]
        self.assertTrue(requires)
        for requirement in requires:
            self.assertIn(requirement, project["project"]["optional-dependencies"]["dev"])


if __name__ == "__main__":
    unittest.main()
