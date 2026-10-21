"""Real delivered snapshots: no pickle/model loading and no external API."""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from services.ai_recommendation.snapshot_service import load_snapshot_dataset, recommend_snapshots

ROOT = Path(__file__).resolve().parents[2]
MODELING = ROOT / "ai_modeling"
if not (MODELING / "economy/results/economy_scores.json").exists():
    MODELING = ROOT / ".publish-repo/ai_modeling"


def test_economy_first_preserves_estimation_period_and_twenty_point_scale():
    dataset = load_snapshot_dataset(MODELING, target_month="2026-10", domains=["economy"])
    assert len(dataset.regions) == 427
    assert dataset.regions[0].region_code == "110515"
    assert dataset.regions[0].category_scores.economy == pytest.approx(26.269316679488888)
    assert dataset.regions[0].category_scores.comfort is None
    detail = dataset.regions[0].domain_metadata["economy"]
    assert detail.status == "estimated"
    assert detail.source_periods["employment"] == "2026-08"
    assert detail.details["target_month"] == "2026-10"
    result = recommend_snapshots(dataset, weights={"economy": 1})
    assert [r.region_code for r in result.items] == ["110615", "140520", "140540", "140550", "140605"]
    assert result.items[0].domain_points_20["economy"] == pytest.approx(20)
    assert result.selected_max_points == 20
    assert result.items[0].five_domain_total_points is None
    assert result.items[0].personalized_score_100 == pytest.approx(100)
    assert result.is_mock is False


def test_economy_month_must_be_explicit_and_match_delivery():
    with pytest.raises(ValueError, match="month"):
        load_snapshot_dataset(MODELING, target_month="2026-11", domains=["economy"])


def test_safety_context_requires_opt_in_and_original_units_are_preserved():
    with pytest.raises(ValueError, match="context"):
        load_snapshot_dataset(MODELING, target_month="2026-10", domains=["safety"])
    dataset = load_snapshot_dataset(MODELING, target_month="2026-10", domains=["safety"], allow_context_scores=True)
    first = dataset.regions[0].domain_metadata["safety"]
    assert first.status == "calculated_draft"
    assert set(first.original_spatial_units) == {"pooled_police_jurisdiction", "sigungu"}
    assert first.details["observed_dong_crime_count"] is None
    assert "not_427_independent_observations" in first.details["quality_flags"]
    assert first.reference_years == [2025, 2026]
    result = recommend_snapshots(dataset, weights={"safety": 1})
    assert result.items[0].region_code == "290525"
    assert "CONTEXT_ASSIGNED_SAFETY" in result.warnings


@pytest.mark.parametrize("domain", ["energy", "health"])
def test_pilot_domain_requires_explicit_opt_in(domain):
    with pytest.raises(ValueError, match="provisional"):
        load_snapshot_dataset(MODELING, target_month="2026-10", domains=[domain], allow_context_scores=True)


def test_energy_reference_is_labelled_snapshot_not_new_model_inference():
    dataset = load_snapshot_dataset(MODELING, target_month="2026-10", domains=["energy"], allow_provisional=True)
    row = dataset.regions[0]
    assert row.category_scores.energy == pytest.approx(49.85118978498229)
    detail = row.domain_metadata["energy"]
    assert detail.artifact_kind == "reference_snapshot"
    assert detail.source_periods["energy"] == "2026Q2"
    assert detail.production_approved is False
    result = recommend_snapshots(dataset, weights={"energy": 1})
    assert result.items[0].region_code == "680750"


def test_health_keeps_air_context_and_partial_age_flags():
    dataset = load_snapshot_dataset(MODELING, target_month="2026-10", domains=["health"],
        allow_provisional=True, allow_context_scores=True)
    first = dataset.regions[0].domain_metadata["health"]
    assert "sigungu" in first.original_spatial_units
    assert first.source_periods["observed_air"] == "2026Q3"
    assert first.details["source_units_confirmed"] is False
    assert first.details["row_context"]["elderly_ratio_data_status"] == "전체연령확인"
    assert any(r.domain_metadata["health"].details["row_context"]["missing_elderly_age_band_count"] != "0"
               for r in dataset.regions)


def test_all_available_domains_do_not_invent_comfort_or_full_hundred_point_total():
    dataset = load_snapshot_dataset(MODELING, target_month="2026-10", domains=["economy", "energy", "health", "safety"],
        allow_provisional=True, allow_context_scores=True)
    result = recommend_snapshots(dataset, weights={"economy": 1, "energy": 1, "health": 1, "safety": 1})
    assert len(result.items) == 5
    assert result.selected_max_points == 80
    assert result.unavailable_domains == ["comfort"]
    assert result.normalized_weights.comfort == 0
    for item in result.items:
        assert item.category_scores.comfort is None
        assert item.domain_points_20["comfort"] is None
        assert item.five_domain_total_points is None
        assert item.personalized_score_100 == pytest.approx(item.selected_total_points / 80 * 100, abs=1e-5)
    assert "PARTIAL_DOMAIN_RECOMMENDATION" in result.warnings
    with pytest.raises(ValueError, match="unavailable"):
        recommend_snapshots(dataset, weights={"comfort": 1})


def test_unavailable_comfort_is_not_substituted_with_health():
    with pytest.raises(ValueError, match="comfort"):
        load_snapshot_dataset(MODELING, target_month="2026-10", domains=["comfort"])


@pytest.fixture
def economy_copy(tmp_path):
    for relative in ["economy/results/economy_scores.json", "economy/data/regions.csv", "economy/model_config.json"]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MODELING / relative, target)
    return tmp_path


def test_duplicate_region_in_result_is_rejected(economy_copy):
    file = economy_copy / "economy/results/economy_scores.json"
    payload = json.loads(file.read_text(encoding="utf-8-sig"))
    payload["items"][1] = payload["items"][0]
    file.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_snapshot_dataset(economy_copy, target_month="2026-10", domains=["economy"])


def test_score_keys_and_region_identity_are_checked(economy_copy):
    file = economy_copy / "economy/results/economy_scores.json"
    payload = json.loads(file.read_text(encoding="utf-8-sig"))
    payload["items"][0]["region"]["region_code"] = "1111051500"
    file.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="region"):
        load_snapshot_dataset(economy_copy, target_month="2026-10", domains=["economy"])


@pytest.mark.parametrize("score", [True, -1, 101, "80"])
def test_invalid_supplied_scores_are_rejected(economy_copy, score):
    file = economy_copy / "economy/results/economy_scores.json"
    payload = json.loads(file.read_text(encoding="utf-8-sig"))
    payload["items"][0]["scores"]["economy"] = score
    file.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_snapshot_dataset(economy_copy, target_month="2026-10", domains=["economy"])


def test_raw_files_never_change_during_load_and_rank():
    path = MODELING / "economy/results/economy_scores.json"
    before = path.read_bytes()
    dataset = load_snapshot_dataset(MODELING, target_month="2026-10", domains=["economy"])
    recommend_snapshots(dataset, weights={"economy": 1})
    assert path.read_bytes() == before


def test_missing_economy_is_not_zero_and_selected_filter_uses_original_scale(economy_copy):
    file = economy_copy / "economy/results/economy_scores.json"
    payload = json.loads(file.read_text(encoding="utf-8-sig"))
    payload["items"][0]["scores"]["economy"] = None
    file.write_text(json.dumps(payload), encoding="utf-8")
    dataset = load_snapshot_dataset(economy_copy, target_month="2026-10", domains=["economy"])
    result = recommend_snapshots(dataset, weights={"economy": 1}, min_scores={"economy": 50})
    assert any(row.region_code == "110515" and row.reason == "missing_scores" for row in result.excluded)
    assert all(row.category_scores.economy >= 50 for row in result.items)
    assert all(row.domain_points_20["economy"] >= 10 for row in result.items)


def test_changed_energy_reference_is_rejected_before_use(economy_copy):
    for relative in ["energy/reference/current_scores.csv", "energy/MANIFEST.json"]:
        target = economy_copy / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MODELING / relative, target)
    file = economy_copy / "energy/reference/current_scores.csv"
    file.write_bytes(file.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="integrity"):
        load_snapshot_dataset(economy_copy, target_month="2026-10", domains=["energy"], allow_provisional=True)


def test_snapshot_cli_outputs_json_and_refuses_missing_comfort():
    command = [sys.executable, "-m", "examples.recommend_snapshot_demo", "--modeling-dir", str(MODELING),
               "--target-month", "2026-10"]
    success = subprocess.run(command + ["--domains", "economy"], cwd=ROOT, capture_output=True, encoding="utf-8")
    assert success.returncode == 0, success.stderr
    payload = json.loads(success.stdout)
    assert payload["items"][0]["region_code"] == "110615"
    failed = subprocess.run(command + ["--domains", "comfort"], cwd=ROOT, capture_output=True, encoding="utf-8")
    assert failed.returncode == 1
    assert "comfort unavailable" in json.loads(failed.stderr)["error"]


def test_cli_never_overwrites_an_existing_output(tmp_path):
    target = tmp_path / "existing.json"
    target.write_text("preserve-me", encoding="utf-8")
    command = [sys.executable, "-m", "examples.recommend_snapshot_demo", "--modeling-dir", str(MODELING),
               "--target-month", "2026-10", "--domains", "economy", "--output", str(target)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8")
    assert result.returncode == 1
    assert target.read_text(encoding="utf-8") == "preserve-me"


@pytest.mark.parametrize("flag", ["allow_provisional", "allow_context_scores"])
@pytest.mark.parametrize("value", ["false", "true", 1, None])
def test_snapshot_permission_flags_must_be_actual_booleans(flag, value):
    with pytest.raises(ValueError, match="boolean"):
        load_snapshot_dataset(MODELING, target_month="2026-10", domains=["economy"], **{flag: value})


def test_non_economy_snapshot_cannot_claim_future_release_month():
    with pytest.raises(ValueError, match="month"):
        load_snapshot_dataset(MODELING, target_month="2099-12", domains=["energy"], allow_provisional=True)
