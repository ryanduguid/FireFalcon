import json

import pytest

from pyfpa.memory.corrections import Correction, load_corrections, save_correction


@pytest.mark.parametrize("overwrite", [False, True])
@pytest.mark.parametrize("style", ["parent", "windows_parent", "absolute", "nested", "windows_nested"])
def test_correction_slug_cannot_choose_another_directory(tmp_path, style, overwrite):
    directory = tmp_path / "corrections"
    directory.mkdir()
    (directory / "nested").mkdir()
    slugs = {
        "parent": "../outside",
        "windows_parent": "..\\outside",
        "absolute": str(tmp_path / "outside"),
        "nested": "nested/outside",
        "windows_nested": "nested\\outside",
    }
    outside = tmp_path / "outside.md"
    if overwrite:
        outside.write_text("Preserve this fabricated record.", encoding="utf-8")
    before = {str(path.relative_to(tmp_path)): path.read_bytes()
              for path in tmp_path.rglob("*") if path.is_file()}
    correction = Correction(slug=slugs[style], type="context", target="demo", date="2026-09-29")

    with pytest.raises(ValueError, match="slug"):
        save_correction(correction, directory, overwrite=overwrite)

    after = {str(path.relative_to(tmp_path)): path.read_bytes()
             for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before


@pytest.mark.parametrize("slug", ["2026-09-29-revenue", "Revenue Review", "café", "_draft", "v1.2"])
def test_correction_keeps_existing_filename_spelling(tmp_path, slug):
    correction = Correction(slug=slug, type="context", target="demo", date="2026-09-29")
    save_correction(correction, tmp_path)
    assert [record.slug for record in load_corrections(tmp_path)] == [slug]


@pytest.mark.parametrize("style", ["parent", "windows_parent", "absolute"])
def test_correction_record_reports_path_errors_without_writing(tmp_path, run_cli, style):
    assert run_cli("init", str(tmp_path)).returncode == 0
    slugs = {
        "parent": "../../outside",
        "windows_parent": "..\\..\\outside",
        "absolute": str(tmp_path / "outside"),
    }
    result = run_cli("correction-record", str(tmp_path), "--slug", slugs[style],
                     "--type", "context", "--target", "demo", "--date", "2026-09-29")

    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["type"] == "invalid_correction"
    assert not (tmp_path / "outside.md").exists()
    assert load_corrections(tmp_path / ".fpa" / "corrections") == []
