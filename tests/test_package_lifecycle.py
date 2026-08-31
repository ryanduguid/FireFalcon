from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_declares_the_source_only_package_lifecycle() -> None:
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())

    assert "**Package lifecycle:** source-only." in readme
    assert "not published to PyPI" in readme
    assert "pip install openfpa" not in readme
