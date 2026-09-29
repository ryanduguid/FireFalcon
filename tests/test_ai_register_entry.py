import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_register_entry_names_the_package_version() -> None:
    # docs/ai-register-entry.md is supplier information a firm uses in its AI
    # register, so the version it describes must move with the package.
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"$', project, re.M)
    entry = (ROOT / "docs" / "ai-register-entry.md").read_text(encoding="utf-8")

    assert version is not None
    assert f"| Name and version | au-fpa-pack {version.group(1)} (" in entry


def test_readme_links_the_register_entry() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "(docs/ai-register-entry.md)" in readme
