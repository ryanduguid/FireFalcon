import pytest

from pyfpa.config.schemas import EntityConfig
from pyfpa.portfolio.approval import (
    ApprovalScope,
    ConfidentialityReview,
    PromotionApproval,
    PromotionDenied,
    attest_validation,
    candidate_digest,
    record_promotion_approval,
)
from pyfpa.portfolio.library import (
    load_library,
    promote_prior,
    promote_skill,
    seed_from_library,
)
from pyfpa.portfolio.mine import PriorCandidate, SkillCandidate
from pyfpa.portfolio.validate import ValidationResult


def _cfg(dio=30.0):
    return EntityConfig.model_validate({
        "name": "c", "start_month": "2026-01", "horizon_months": 12, "tax_rate": 0.0,
        "channels": [{"name": "C", "annual_revenue": 1_000_000.0, "growth_rate": 0.0,
                      "seasonality": [1.0] * 12, "cogs_pct": 0.5}],
        "opex": [], "debt": [],
        "working_capital": {"dso_days": 30.0, "dpo_days": 30.0, "dio_days": dio},
        "opening_balances": {"cash": 0.0},
    })


def _support(tmp_path):
    """Three fabricated client workspaces, each naming a different business.

    The promotion gate counts distinct clients by business-profile heading, so a
    bare directory establishes no client and cannot support a prior.
    """
    paths = []
    for folder, business in (("one", "Wattlebank Joinery"), ("two", "Coral Bay Cartage"),
                             ("three", "Emu Plains Dental")):
        root = tmp_path / "clients" / folder
        (root / ".fpa").mkdir(parents=True, exist_ok=True)
        (root / ".fpa" / "business-profile.md").write_text(
            f"# {business} Business Profile\n", encoding="utf-8")
        paths.append(str(root))
    return paths


def _approve(library, candidate, *, allowed_files=()):
    """Record the practitioner approval the promotion gate requires."""
    is_prior = isinstance(candidate, PriorCandidate)
    approval = PromotionApproval(
        purpose="Reuse what generalised across same-type engagements",
        scope=ApprovalScope(
            business_type=candidate.business_type,
            driver=candidate.driver if is_prior else None,
            skill=None if is_prior else candidate.name,
        ),
        contributing_workspaces=list(candidate.support),
        authorisation_reference="EL-2026-014 cl 8 and practitioner sign-off",
        candidate_digest=candidate_digest(candidate),
        confidentiality_review=ConfidentialityReview(
            reviewer="Marlo Quinn", reviewed_on="2026-09-20"
        ),
        approved_by="Marlo Quinn",
        approved_at="2026-09-20T09:30:00+10:00",
        allowed_files=list(allowed_files),
    )
    record_promotion_approval(library, approval)
    return approval


def _validation(candidate, *, mean_delta=-0.01, n_folds=3, validated=True):
    """A validation result standing in for validate_prior over these workspaces.

    The fabricated support directories hold no scored snapshots, so this attests
    the result the way validate_prior would. tests/test_portfolio_approval.py
    covers what happens without the attestation.
    """
    digest = candidate_digest(candidate)
    return ValidationResult(mean_delta=mean_delta, n_folds=n_folds, validated=validated,
                            candidate_digest=digest,
                            attestation=attest_validation(digest, n_folds, mean_delta))


def _prior(tmp_path, driver="working_capital.dio_days", value=45.0):
    return PriorCandidate(business_type="d2c", driver=driver, value=value,
                          support=_support(tmp_path), dispersion=0.02)


def test_promote_prior_and_seed(tmp_path):
    lib = tmp_path / "library"
    cand = _prior(tmp_path)
    _approve(lib, cand)
    promote_prior(lib, cand, _validation(cand))
    assert "working_capital.dio_days" in (lib / "library-log.md").read_text()
    seeded = seed_from_library(lib, "d2c", _cfg(dio=30.0),
                              company_root=tmp_path / "fourth", seeded_at="2026-09-20")
    assert seeded.working_capital.dio_days == 45.0
    assert _cfg(dio=30.0).working_capital.dio_days == 30.0     # base unmutated


def test_a_prior_the_config_cannot_take_is_refused_before_any_seed_is_recorded(tmp_path):
    # A dso_days prior cannot seed a client that collects by a profile: the two
    # are exclusive, so the seed is refused and neither side records it.
    lib = tmp_path / "library"
    cand = _prior(tmp_path, driver="working_capital.dso_days", value=40.0)
    _approve(lib, cand)
    promote_prior(lib, cand, _validation(cand))
    profile_client = EntityConfig.model_validate({
        **_cfg().model_dump(),
        "working_capital": {"collection_profile": [0.5, 0.5], "dpo_days": 30.0, "dio_days": 30.0},
    })
    with pytest.raises(ValueError, match="not both"):
        seed_from_library(lib, "d2c", profile_client,
                          company_root=tmp_path / "fourth", seeded_at="2026-09-20")
    assert not (tmp_path / "fourth" / ".fpa" / "library-seeds.yaml").exists()
    assert not (lib / "provenance" / "seeds.yaml").exists()


def test_seed_unknown_type_is_noop(tmp_path):
    lib = tmp_path / "library"
    out = seed_from_library(lib, "saas", _cfg(dio=30.0),
                            company_root=tmp_path / "fourth", seeded_at="2026-09-20")
    assert out.working_capital.dio_days == 30.0
    assert not (tmp_path / "fourth" / ".fpa" / "library-seeds.yaml").exists()


def test_promote_two_priors_same_type_appends(tmp_path):
    # a second prior for the same business-type must EXTEND the file, not overwrite
    lib = tmp_path / "library"
    for cand in (_prior(tmp_path), _prior(tmp_path, driver="tax_rate", value=0.25)):
        _approve(lib, cand)
        promote_prior(lib, cand, _validation(cand, mean_delta=0.0))
    drivers = {p["driver"] for p in load_library(lib)["priors"]["d2c"]}
    assert drivers == {"working_capital.dio_days", "tax_rate"}


def test_load_library_round_trip(tmp_path):
    lib = tmp_path / "library"
    cand = _prior(tmp_path, driver="tax_rate", value=0.25)
    _approve(lib, cand)
    promote_prior(lib, cand, _validation(cand, mean_delta=0.0))
    loaded = load_library(lib)
    assert any(p["driver"] == "tax_rate" and p["value"] == 0.25 for p in loaded["priors"]["d2c"])


def test_promote_skill_copies_and_logs(tmp_path):
    src = tmp_path / "src" / "arr-waterfall"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: arr-waterfall\ndescription: x\n---\n")
    lib = tmp_path / "library"
    cand = SkillCandidate(business_type="saas", name="arr-waterfall",
                          support=_support(tmp_path), source=str(src))
    _approve(lib, cand, allowed_files=["SKILL.md"])
    promote_skill(lib, cand)
    assert (lib / "skills" / "arr-waterfall" / "SKILL.md").exists()
    assert "arr-waterfall" in (lib / "library-log.md").read_text()
    original = (lib / "skills/arr-waterfall/SKILL.md").read_bytes()
    (src / "SKILL.md").write_text("replacement", encoding="utf-8")
    # The replaced tree digests differently, so the recorded approval no longer
    # covers it and the copy is refused before it can overwrite the library.
    with pytest.raises(PromotionDenied, match="no promotion approval recorded"):
        promote_skill(lib, cand)
    assert (lib / "skills/arr-waterfall/SKILL.md").read_bytes() == original


def test_promote_skill_refuses_to_overwrite_an_approved_tree(tmp_path):
    src = tmp_path / "src" / "arr-waterfall"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: arr-waterfall\ndescription: x\n---\n")
    lib = tmp_path / "library"
    cand = SkillCandidate(business_type="saas", name="arr-waterfall",
                          support=_support(tmp_path), source=str(src))
    _approve(lib, cand, allowed_files=["SKILL.md"])
    promote_skill(lib, cand)
    with pytest.raises(FileExistsError):
        promote_skill(lib, cand)


@pytest.mark.parametrize("folds,validated", [(1, True), (3, False)])
def test_invalid_prior_cannot_create_library(tmp_path, folds, validated):
    lib = tmp_path / "library"
    candidate = _prior(tmp_path, driver="tax_rate", value=0.25)
    with pytest.raises(ValueError, match="validation"):
        promote_prior(lib, candidate, _validation(
            candidate, mean_delta=0, n_folds=folds, validated=validated))
    assert not lib.exists()


# "." and ".." are not listed: the ".yaml" suffix makes them "..yaml" and "...yaml",
# odd but legitimate direct children, so only a separator or an absolute path escapes.
@pytest.mark.parametrize("business_type", ["../../settings", "nested/type", "/tmp/settings"])
def test_promote_prior_refuses_a_type_that_escapes_the_priors_directory(tmp_path, business_type):
    lib = tmp_path / "library"
    cand = PriorCandidate(business_type=business_type, driver="tax_rate", value=0.25,
                          support=["a", "b", "c"], dispersion=0.01)
    val = ValidationResult(mean_delta=0.0, n_folds=3, validated=True)

    with pytest.raises(ValueError, match="unsafe library name"):
        promote_prior(lib, cand, val)
    assert not list(tmp_path.glob("*.yaml"))
    assert not lib.exists()


@pytest.mark.parametrize("name", ["../escape", "nested/skill", ".."])
def test_promote_skill_refuses_a_name_that_escapes_the_skills_directory(tmp_path, name):
    lib = tmp_path / "library"
    source = tmp_path / "source"
    (source / "inner").mkdir(parents=True)
    (source / "inner" / "SKILL.md").write_text("skill\n", encoding="utf-8")
    cand = SkillCandidate(name=name, business_type="d2c", source=str(source), support=["a", "b"])

    with pytest.raises(ValueError, match="unsafe library name"):
        promote_skill(lib, cand)
    assert not list(tmp_path.glob("escape*"))
    assert not lib.exists()
