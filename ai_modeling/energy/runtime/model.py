"""학습 코드를 제외하고 원래 에너지 추론·점수 산식을 내보낸 모듈."""
import json
import joblib
import numpy as np
import pandas as pd
from .common import (ROOT, MODELS, SPEC, CORE, read, fuel_score, strict_sum, grades,
                     interval, core_valid, feature_matrix)
from .input_schema import normalize_model_frame
TARGETS = ['electricity_MWh', 'gas_1000m3']
FEATURES = CORE + ['log_lag1', 'log_lag2', 'log_lag4']

class ConditionalEnergyScorer:
    def __init__(self):
        self.config = __import__('json').loads((MODELS / 'energy_score.json').read_text(encoding='utf-8'))
        self.bundles = {t: joblib.load(MODELS / ('energy_' + t + '.joblib')) for t in SPEC['energy']['targets']}

    def score(self, frame):
        d = normalize_model_frame(frame).reset_index(drop=True)
        if d.duplicated(['admin_code', 'quarter']).any():
            raise ValueError('행정동·분기 중복')
        cfg = self.config
        out = d[['admin_code', 'district', 'admin_name', 'quarter', 'source_group']].copy()
        core_ok = core_valid(d)
        score_columns = []
        fit_ids = set()
        bounds = cfg['outlier_bounds']
        out['out_of_training_range'] = [
            ';'.join(c for c in bounds if pd.notna(row[c]) and (row[c] < bounds[c][0] or row[c] > bounds[c][1]))
            for _, row in d.iterrows()]
        for target, bundle in self.bundles.items():
            fit_ids.update(bundle['fit_row_ids'])
            out[target + '_actual'] = pd.to_numeric(d[target], errors='coerce')
            out[target + '_expected'] = np.nan
            out[target + '_lower'], out[target + '_upper'] = np.nan, np.nan
            pred = bundle['model'].predict(feature_matrix(d.loc[core_ok])) if core_ok.any() else np.array([])
            out.loc[core_ok, target + '_expected'] = pred
            lo, hi = interval(pred, bundle['radius'])
            out.loc[core_ok, target + '_lower'], out.loc[core_ok, target + '_upper'] = lo, hi
            valid = core_ok & d.months.eq(3) & d[target + '_observed_months'].eq(3) & d.quarter.le('2026Q3')
            # 학습에 포함된 행은 효율 비교에 사용하지 않는다.
            row_ids = d.admin_code.astype(str) + ':' + d.quarter
            valid &= ~row_ids.isin(bundle['fit_row_ids'])
            score_col = target + '_score'
            out[score_col] = fuel_score(out[target + '_expected'], out[target + '_actual'])
            out.loc[~valid, score_col] = np.nan
            score_columns.append(score_col)
        out['score'] = strict_sum(out[score_columns], cfg['weights'])
        out['relative_grade'] = grades(out.score, cfg['grade_thresholds'])
        out['absolute_grade'] = None
        out['score_kind'] = '주거상업혼합_조건별_상대비교_시범'
        out['score_status'] = np.where(out.score.notna(), '시범_정식승인전', '입력누락_학습행_계산보류')
        out['missing_fields'] = [';'.join(c for c in SPEC['energy']['required_core_columns'] + SPEC['energy']['targets']
                                         if pd.isna(row[c]) or not np.isfinite(pd.to_numeric(row[c], errors='coerce')))
                                  for _, row in d.iterrows()]
        out['data_quality'] = '상업포함·과거재구성·변환원량; 실측 주거효율 아님'
        out['model_version'] = cfg['version']
        out['weights_version'] = cfg['version'] + ':2025Q4'
        out['calibration_version'] = cfg['version'] + ':2025Q4'
        out['source_group_or_geography'] = out.source_group
        out['component_dates'] = out.quarter
        out['as_of'] = out.quarter
        return out

def clean_history(frame):
    d = normalize_model_frame(frame)
    if d.duplicated(['admin_code', 'quarter']).any():
        raise ValueError('에너지 행정동·분기 중복')
    for target in TARGETS:
        x = pd.to_numeric(d[target], errors='coerce')
        ok = np.isfinite(x) & x.ge(0) & d.months.eq(3) & d[target + '_observed_months'].eq(3)
        d[target] = x.where(ok)
    return d

def at(history, quarter):
    return history.loc[history.quarter.eq(str(quarter))].set_index('admin_code', drop=False).copy()

def conditions(history, origin, quarter):
    """출발 시점 이후의 실제 조건은 읽지 않는다. 기온은 전년 동분기 가정."""
    origin, quarter = pd.Period(origin, freq='Q'), pd.Period(quarter, freq='Q')
    if not origin < quarter <= origin + 2:
        raise ValueError('에너지는 출발 분기 이후 최대 2분기만 지원합니다.')
    known = history.loc[history.quarter.le(str(origin))]
    d = at(known, origin)
    if d.empty:
        raise ValueError('출발 분기의 조건 자료가 없습니다.')
    d = d[['admin_code', 'district', 'admin_name', 'source_group'] + CORE].copy()
    d['all_weighted_age'] += (quarter.ordinal - origin.ordinal) / 4
    prior = at(known, quarter - 4)
    d['temperature_C'] = prior.temperature_C.reindex(d.index)
    d['quarter_sin'] = np.sin(2 * np.pi * quarter.quarter / 4)
    d['quarter_cos'] = np.cos(2 * np.pi * quarter.quarter / 4)
    d['quarter'], d['origin'] = str(quarter), str(origin)
    return d.reset_index(drop=True)

def lag_features(history, cond, target):
    q = pd.Period(cond.quarter.iloc[0], freq='Q')
    x = feature_matrix(cond)
    for lag in [1, 2, 4]:
        values = at(history, q - lag)[target]
        raw = cond.admin_code.map(values)
        x['log_lag' + str(lag)] = np.log1p(raw.where(np.isfinite(raw) & raw.ge(0)))
    return x[FEATURES]

def usage_prediction(method, bundle, x):
    result = np.full(len(x), np.nan)
    valid = np.isfinite(x[FEATURES]).all(axis=1)
    if method == 'random_forest':
        result[valid] = np.maximum(0, np.expm1(bundle['random_forest'].predict(x.loc[valid, FEATURES])))
    else:
        lag = 'log_lag4' if method == 'previous_year' else 'log_lag1'
        result[valid] = np.expm1(x.loc[valid, lag])
    return result

class EnergyForecaster:
    def __init__(self, history, benchmark, config):
        self.history, self.benchmark, self.config = history, benchmark, config

    def forecast(self, origin, steps, bundles, selected):
        if steps not in (1, 2):
            raise ValueError('1~2분기 예측만 지원합니다.')
        history = self.history.loc[self.history.quarter.le(origin)].copy()
        frames = []
        for h in range(1, steps + 1):
            q = str(pd.Period(origin, freq='Q') + h)
            c = conditions(history, origin, q)
            out = c.copy()
            out['horizon'], out['value_kind'] = h, '예측_조건유지시나리오'
            generated = c.copy()
            for target in TARGETS:
                if bundles[target]['fit_end'] > origin:
                    raise ValueError('출발 시점 이후 정답으로 학습한 소비 전망기입니다.')
                if self.benchmark[target]['fit_end'] > origin:
                    raise ValueError('출발 시점 이후에 학습된 기준 모델입니다.')
                x = lag_features(history, c, target)
                forecast = usage_prediction(selected[target], bundles[target], x)
                forecast[~core_valid(c)] = np.nan
                expected = np.full(len(c), np.nan)
                valid = core_valid(c)
                if valid.any():
                    expected[valid] = self.benchmark[target]['model'].predict(feature_matrix(c.loc[valid]))
                out[target + '_forecast'], out[target + '_benchmark'] = forecast, expected
                out[target + '_actual'] = np.nan
                out[target + '_score'] = fuel_score(expected, forecast)
                out[target + '_method'] = selected[target]
                out[target + '_fit_end'] = bundles[target]['fit_end']
                generated[target] = forecast
            out['score'] = strict_sum(out[[t + '_score' for t in TARGETS]], self.config['weights'])
            out['relative_grade'] = grades(out.score, self.config['grade_thresholds'])
            out['recursive_prediction_used'] = h > 1
            out['condition_assumption'] = '출발 분기 규모·세대·비중 유지; 건령 경과; 전년 동분기 기온'
            out['missing_fields'] = [';'.join(col for col in CORE if not np.isfinite(row[col]))
                                     for _, row in c.iterrows()]
            for target in TARGETS:
                out.loc[out[target + '_forecast'].isna(), 'missing_fields'] += ';' + target + '_과거소비입력'
            frames.append(out)
            # Synthetic predictions go only to this private working copy; missing originals stay missing.
            history = pd.concat([history, generated], ignore_index=True)
        return pd.concat(frames, ignore_index=True)

    def observed_score(self, quarter):
        d = at(self.history, quarter).reset_index(drop=True)
        for target in TARGETS:
            expected = np.full(len(d), np.nan)
            valid = core_valid(d)
            if valid.any():
                expected[valid] = self.benchmark[target]['model'].predict(feature_matrix(d.loc[valid]))
            d[target + '_score'] = fuel_score(expected, d[target])
        d['observed_score'] = strict_sum(d[[t + '_score' for t in TARGETS]], self.config['weights'])
        return d.set_index('admin_code')

