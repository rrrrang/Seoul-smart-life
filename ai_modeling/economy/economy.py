"""Monthly Seoul economic-activity estimates. All paths are package-relative.

This is a fixed October 2026 release, not a live feed or an increase/decrease
classifier. Never present its estimate as an observed current-month statistic.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
AXES = {
    "commute": "commute_weekday_daily_mean",
    "employment": "corporate_nps_members",
    "licensing": "registered_active_candidate_count",
}
FEATURES = [
    "base_log", "log_area", "history_count", "recent3_log", "seasonal_log",
    "sin_month", "cos_month", "lag1_log", "change1", "lag2_log", "change2",
    "lag3_log", "change3", "lag6_log", "change6", "lag12_log", "change12",
]
DOMAINS = ["economy", "energy", "comfort", "health", "safety"]


GRADE_RULES = {
    "method": "fixed_score_intervals",
    "best_grade": 1,
    "worst_grade": 5,
    "score_rounding_before_grading": False,
    "missing_score_grade": None,
    "bands": [
        {"grade": grade, "label": f"{grade}등급", "min_score": lower,
         "max_score": upper, "min_inclusive": True, "max_inclusive": grade == 1}
        for grade, lower, upper in ((1, 80, 100), (2, 60, 80), (3, 40, 60), (4, 20, 40), (5, 0, 20))
    ],
    "interpretation": "현재월 경제활동 집중도 추정점수의 고정 구간 등급. 1등급이 가장 높으며 주민 소득이나 집값 상승을 뜻하지 않음.",
}


class DataContractError(ValueError):
    """Invalid data, unavailable source vintage, or unsupported target month."""


def grade_from_score(score):
    """Grade the unrounded score; missing is not zero or grade 5."""
    if score is None:
        return None
    if (isinstance(score, bool) or not isinstance(score, (int, float))
            or not np.isfinite(score) or not 0 <= score <= 100):
        raise DataContractError("score must be a finite number in [0, 100] or null")
    for band in GRADE_RULES["bands"]:
        if score >= band["min_score"]:
            return band["grade"]
    raise AssertionError("Unreachable score")


def shift(month: str, count: int) -> str:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise DataContractError(f"Invalid month: {month!r}; expected YYYY-MM")
    return str(pd.Period(month, freq="M") + count)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_config(root: Path = ROOT) -> dict:
    config = json.loads((root / "model_config.json").read_text(encoding="utf-8"))
    validate_config(config)
    return config


def validate_config(config: dict) -> None:
    methods = {"commute": "median3", "employment": "last_known", "licensing": "xgb_depth3_shrink50"}
    if config["selected_methods"] != methods:
        raise DataContractError("Configured methods differ from this release implementation")
    weights = config["weights"]
    if set(weights) != set(AXES) or not all(isinstance(w, (int, float)) and np.isfinite(w) and w >= 0 for w in weights.values()):
        raise DataContractError("Weights must be three finite, non-negative numbers")
    if not np.isclose(sum(weights.values()), 1, atol=1e-12) or not all(np.isclose(w, 1/3, atol=1e-12) for w in weights.values()):
        raise DataContractError("This release uses fixed equal one-third weights")
    for axis in AXES:
        calibration = config["normalization"][axis]
        low, high = calibration["log_density_p05"], calibration["log_density_p95"]
        if not np.isfinite([low, high]).all() or high <= low:
            raise DataContractError(f"Invalid normalization range: {axis}")
    if config["source_lags_months"] != {"commute": 1, "employment": 2, "licensing": 1}:
        raise DataContractError("Source lag definition differs from the validated implementation")


def validate_request(config: dict, as_of: str, target_month: str) -> None:
    if not isinstance(as_of, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise DataContractError("as_of must use canonical YYYY-MM-DD")
    try:
        requested_date = date.fromisoformat(as_of)
    except ValueError as exc:
        raise DataContractError("as_of must be YYYY-MM-DD") from exc
    shift(target_month, 0)
    if target_month != config["target_month"]:
        raise DataContractError(
            f"This artifact supports {config['target_month']} only. "
            "A new month requires refreshed sources, retraining and validation."
        )
    if as_of < config["snapshot_available_as_of"]:
        raise DataContractError("Requested date predates this data snapshot; past-time availability is unproven.")
    if requested_date.strftime("%Y-%m") != target_month:
        raise DataContractError("Only a current-month estimate is served; old releases cannot represent a new month.")
    for axis, lag in config["source_lags_months"].items():
        if config["source_months"][axis] != shift(target_month, -lag):
            raise DataContractError(f"Stale or inconsistent {axis} source month")


def validate_frames(data: pd.DataFrame, regions: pd.DataFrame, config: dict) -> None:
    expected = config["expected_regions"]
    if "region_short_code" in data or "region_short_code" in regions:
        raise DataContractError("Public field must be region_code, with the same six-digit value.")
    for name, frame in [("regions", regions), ("monthly_inputs", data)]:
        if "region_code" not in frame or not frame.region_code.map(
                lambda value: isinstance(value, str) and bool(re.fullmatch(r"\d{6}", value))).all():
            raise DataContractError(f"{name}: region_code must be a six-digit string, not a 10-digit administrative code.")
    if len(regions) != expected or regions.region_code.nunique() != expected:
        raise DataContractError(f"Expected {expected} unique regions")
    if not regions.sigungu_code.map(lambda value: isinstance(value, str) and bool(re.fullmatch(r"\d{5}", value))).all():
        raise DataContractError("sigungu_code must be a five-digit string")
    if regions[["region_name", "sigungu_code", "official_area_km2"]].isna().any().any():
        raise DataContractError("Region metadata has missing values")
    if not np.isfinite(regions.official_area_km2).all() or not regions.official_area_km2.gt(0).all():
        raise DataContractError("Area must be a positive, finite km2 value")
    if data.duplicated(["month", "region_code"]).any():
        raise DataContractError("Duplicate month/region rows")
    if not data.month.map(lambda value: isinstance(value, str) and bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value))).all():
        raise DataContractError("Invalid input month")
    codes = set(regions.region_code)
    expected_months = set(pd.period_range(config["input_period"][0], config["input_period"][1], freq="M").astype(str))
    if set(data.month) != expected_months:
        raise DataContractError("Monthly input period is incomplete or differs from this release")
    if any(set(g.region_code) != codes for _, g in data.groupby("month")):
        raise DataContractError("Every input month must contain the same 427 region identifiers")
    for axis, column in AXES.items():
        if column not in data:
            raise DataContractError(f"Missing input column: {column}")
        values = data[column]
        if not pd.api.types.is_numeric_dtype(values):
            raise DataContractError(f"Non-numeric source values: {column}")
        if (values.dropna() < 0).any() or not np.isfinite(values.dropna()).all():
            raise DataContractError(f"Negative or infinite source values: {column}")
        latest = config["source_months"][axis]
        current = data[data.month.eq(latest)]
        if len(current) != expected or current[column].isna().any():
            raise DataContractError(f"{axis}: missing latest observations; null is not zero")
        if data.loc[data.month > latest, column].notna().any():
            raise DataContractError(f"{axis}: source contains observations after the declared availability cutoff")


def load_inputs(root: Path = ROOT) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    config = read_config(root)
    for relative, expected_hash in config["artifact_sha256"].items():
        path = root / relative
        if not path.is_file() or digest(path) != expected_hash:
            raise DataContractError(f"Release input/model changed: {relative}. Rebuild and validate a new release.")
    regions = pd.read_csv(root / "data/regions.csv", dtype={"region_code": str, "sigungu_code": str})
    data = pd.read_csv(root / "data/monthly_inputs.csv", dtype={"region_code": str, "month": str})
    validate_frames(data, regions, config)
    return config, data, regions


def panels_from_inputs(data: pd.DataFrame, regions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    area = regions.set_index("region_code").official_area_km2.sort_index()
    result = {}
    for axis, column in AXES.items():
        panel = data.pivot(index="month", columns="region_code", values=column).sort_index().sort_index(axis=1) / area
        if axis == "commute":
            panel.loc[panel.index.isin(["2025-03", "2025-04"])] = np.nan
        panel.loc[panel.index < "2025-08", panel.columns.isin(["230515", "230533"])] = np.nan
        result[axis] = panel
    return result


def feature_rows(panel: pd.DataFrame, regions: pd.DataFrame, axis: str, target: str, lag: int) -> pd.DataFrame:
    origin = shift(target, -lag)
    if origin not in panel.index:
        raise DataContractError(f"{axis} has no data for {origin}")
    history = panel.loc[panel.index <= origin]
    if axis == "employment" and origin >= "2025-12":
        history = history.loc[history.index >= "2025-12"]
    meta = regions.set_index("region_code")
    rows = []
    for code in panel.columns:
        base = history.loc[origin, code]
        if pd.isna(base):
            raise DataContractError(f"Missing latest {axis} value for {code} ({origin})")
        hist = history[code].dropna()
        row = {"region_code": code, "base": base, "base_log": np.log1p(base),
               "history_count": len(hist), "cold_start": len(hist) < 3,
               "log_area": np.log(meta.loc[code, "official_area_km2"]),
               "recent3": hist.tail(3).median() if len(hist) >= 3 else base}
        row["recent3_log"] = np.log1p(row["recent3"])
        season = shift(target, -12)
        row["seasonal_log"] = np.log1p(history.loc[season, code]) if season in history.index else np.nan
        row["sin_month"] = np.sin(2 * np.pi * int(target[-2:]) / 12)
        row["cos_month"] = np.cos(2 * np.pi * int(target[-2:]) / 12)
        for months in [1, 2, 3, 6, 12]:
            previous = shift(origin, -months)
            value = history.loc[previous, code] if previous in history.index else np.nan
            row[f"lag{months}_log"] = np.log1p(value)
            row[f"change{months}"] = row["base_log"] - row[f"lag{months}_log"]
        rows.append(row)
    return pd.DataFrame(rows).set_index("region_code")


def normalized_score(density: np.ndarray, axis: str, config: dict) -> np.ndarray:
    calibration = config["normalization"][axis]
    lower = calibration["log_density_p05"]
    upper = calibration["log_density_p95"]
    return 100 * np.clip((np.log1p(density) - lower) / (upper - lower), 0, 1)


def estimate(as_of: str, target_month: str, root: Path = ROOT) -> dict:
    """Return backend-compatible scores; invalid/stale releases raise DataContractError."""
    config, data, regions = load_inputs(root)
    validate_request(config, as_of, target_month)
    panels = panels_from_inputs(data, regions)
    artifact = joblib.load(root / "models/licensing.joblib")  # Hash-verified project artifact only.
    if artifact["features"] != FEATURES or artifact["axis"] != "licensing" or artifact["horizon"] != 1:
        raise DataContractError("Unexpected licensing model feature contract")
    if artifact["cutoff"] != config["source_months"]["licensing"] or artifact["target_month"] != target_month:
        raise DataContractError("Model was trained for a different source cutoff/target")
    values, features = {}, {}
    for axis in AXES:
        frame = feature_rows(panels[axis], regions, axis, target_month, config["source_lags_months"][axis])
        features[axis] = frame
        if axis == "commute":
            prediction = frame.recent3.to_numpy()
        elif axis == "employment":
            prediction = frame.base.to_numpy()
        else:
            delta = artifact["model"].predict(frame[FEATURES])
            prediction = np.maximum(0, np.expm1(frame.base_log.to_numpy() + delta))
            cold = frame.cold_start.to_numpy()
            prediction[cold] = frame.loc[cold, "base"]
            prediction = .5 * prediction + .5 * frame.base.to_numpy()
        if not np.isfinite(prediction).all() or (prediction < 0).any():
            raise DataContractError(f"Non-finite or negative model result: {axis}")
        values[axis] = pd.Series(normalized_score(prediction, axis, config), index=frame.index)
    records = []
    for row in regions.sort_values("region_code").itertuples():
        component_scores = {axis: float(values[axis].loc[row.region_code]) for axis in AXES}
        score = sum(config["weights"][axis] * component_scores[axis] for axis in AXES)
        grade = grade_from_score(score)
        records.append({
            "region": {"region_code": row.region_code, "name_ko": row.region_name,
                       "sigungu_code": row.sigungu_code, "spatial_unit": "dong"},
            "scores": {domain: float(score) if domain == "economy" else None for domain in DOMAINS},
            "metadata": {"economy": {
                "status": "estimated", "target_month": target_month, "as_of": as_of,
                "data_snapshot_as_of": config["snapshot_available_as_of"],
                "source_periods": config["source_months"],
                "components": {axis: {"score": component_scores[axis], "weight": config["weights"][axis],
                                      "source_period": config["source_months"][axis],
                                      "method": config["selected_methods"][axis]} for axis in AXES},
                "grade": grade, "grade_label": f"{grade}등급" if grade is not None else None,
                "cold_start_fallback": any(bool(features[axis].loc[row.region_code, "cold_start"]) for axis in AXES),
                "measurement": "economic_activity_concentration_estimate",
                "interpretation": "출근활동·공개 법인사업장 고용·5개 업종 영업기반의 면적 대비 집중도 추정",
            }},
        })
    return {"domains": DOMAINS, "items": records, "is_mock": False,
            "metadata": {"economy": {
                "status": "estimated", "target_month": target_month, "as_of": as_of,
                "data_snapshot_as_of": config["snapshot_available_as_of"],
                "source_periods": config["source_months"],
                "selected_methods": config["selected_methods"], "weights": config["weights"],
                "interpretation": "경제활동의 면적 대비 집중도 추정. 주민 소득·집값·상승하락 예측이 아님.",
                "validation_scope": "2026-06/08 reconstructed-data retrospective recheck, not prospective validation",
                "direction_prediction_available": False,
                "grade_rules": deepcopy(GRADE_RULES),
            }}}


def retrain_licensing(root: Path, destination: Path) -> dict:
    """Reproduce the shipped model with fixed hyperparameters, without model selection."""
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from xgboost import XGBRegressor
    config, data, regions = load_inputs(root)
    panel = panels_from_inputs(data, regions)["licensing"]
    cutoff = config["source_months"]["licensing"]
    training = []
    for target in pd.period_range(shift(panel.index.min(), 3), cutoff, freq="M").astype(str):
        # New separate dongs have no synthetic history before August 2025.
        valid_codes = panel.columns[panel.loc[shift(target, -1)].notna()]
        frame = feature_rows(panel[valid_codes], regions, "licensing", target, 1)
        actual = panel.loc[target, frame.index]
        frame["target_change"] = np.log1p(actual) - frame.base_log
        frame = frame[~frame.cold_start & frame.target_change.notna()]
        training.append(frame)
    train = pd.concat(training, ignore_index=True)
    model = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
        XGBRegressor(n_estimators=180, max_depth=3, learning_rate=.035,
                     min_child_weight=25, subsample=.9, colsample_bytree=.9, reg_lambda=20,
                     objective="reg:squarederror", tree_method="hist", n_jobs=2, random_state=20261021),
    )
    model.fit(train[FEATURES], train.target_change)
    artifact = {"model": model, "features": FEATURES, "axis": "licensing", "horizon": 1,
                "cutoff": cutoff, "target_month": config["target_month"],
                "source_sha256": digest(root / "data/monthly_inputs.csv"),
                "cold_start_policy": "latest known value when fewer than 3 valid monthly observations"}
    destination.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, destination)
    return {"training_rows": len(train), "label_cutoff": cutoff, "target_month": config["target_month"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["predict", "train"], nargs="?", default="predict")
    parser.add_argument("--as-of", default=datetime.now(timezone(timedelta(hours=9))).date().isoformat())
    parser.add_argument("--target-month", default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.command == "train":
        output = args.output or ROOT / "models/licensing_retrained.joblib"
        if output.resolve() == (ROOT / "models/licensing.joblib").resolve():
            parser.error("Training must write a separate candidate artifact; never replace a validated release silently.")
        print(json.dumps(retrain_licensing(ROOT, output), ensure_ascii=False))
    else:
        try:
            result = estimate(args.as_of, args.target_month or args.as_of[:7])
        except DataContractError as exc:
            parser.error(str(exc))
        output = args.output or ROOT / "results/economy_scores.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(f"Wrote {len(result['items'])} estimated scores to {output}")


if __name__ == "__main__":
    main()
