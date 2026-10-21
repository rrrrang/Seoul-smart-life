"""원래 계산식과 저장 모델의 직렬화 호환 클래스. 외부 프로젝트를 읽지 않는다."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.base import RegressorMixin, BaseEstimator

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'models'
SPEC = json.loads((ROOT / 'config/model_spec.json').read_text(encoding='utf-8'))
CORE = ['all_area_m2', 'all_weighted_age', 'nonresidential_mainuse_share_pct', 'households',
        'single_share_pct', 'temperature_C', 'quarter_sin', 'quarter_cos']
SUPPLY = ['인구1만명당_의과병원수', '인구1만명당_일반의원수', '인구1만명당_약국수',
          '인구1만명당_의과의사수', '인구1만명당_일반입원병상수', '인구1만명당_공공보건기관수']

def grades(values, bounds):
    a = np.asarray(values, float)
    edges = np.asarray(bounds, float)
    if edges.shape != (4,) or not np.isfinite(edges).all() or not np.all(np.diff(edges) > 0):
        raise ValueError('5단계 등급 경계가 잘못되었습니다.')
    result = np.full(len(a), None, dtype=object)
    valid = np.isfinite(a) & (a >= 0) & (a <= 100)
    labels = np.asarray(['아주나쁨', '나쁨', '기본', '좋음', '아주좋음'])
    result[valid] = labels[np.searchsorted(edges, a[valid], side='left')]
    return result

def read(path):
    from .input_schema import normalize_model_frame
    d = pd.read_csv(path, dtype={'admin_code': str, 'region_code': str, 'source_group': str,
                                'district_code': str, 'sigungu_code': str, '행정동코드': str})
    return normalize_model_frame(d)

def strict_sum(z, w):
    a = np.asarray(z, float)
    # 가중치가 0이어도 정의된 필수 항목의 누락을 무시하지 않는다.
    valid = np.isfinite(a).all(axis=1)
    output = np.full(len(a), np.nan)
    output[valid] = a[valid] @ np.asarray(w)
    return output

def fuel_score(expected, actual):
    e, a = np.asarray(expected, float), np.asarray(actual, float)
    result = np.full(len(e), np.nan)
    valid = np.isfinite(e) & (e > 0) & np.isfinite(a) & (a >= 0)
    result[valid] = 100 * e[valid] / (e[valid] + a[valid])
    return result

def interval(pred, radius):
    center = np.log1p(np.maximum(np.asarray(pred, float), 0))
    return np.maximum(0, np.expm1(center - radius)), np.expm1(center + radius)

class CalendarMedian(RegressorMixin, BaseEstimator):
    """행정동 ID를 쓰지 않는 훈련 분기별 가중 중앙값 기준모형."""
    def fit(self, X, y, sample_weight=None):
        y = np.asarray(y, float)
        sample_weight = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight)
        def median(mask):
            yy, ww = y[mask], sample_weight[mask]
            idx = np.argsort(yy)
            return float(yy[idx][np.searchsorted(np.cumsum(ww[idx]), ww.sum() / 2)])
        self.fallback_ = median(np.ones(len(y), bool))
        self.values_ = {tuple(key): median(np.all(X[['quarter_sin', 'quarter_cos']].to_numpy() == key, axis=1))
                        for key in np.unique(X[['quarter_sin', 'quarter_cos']].to_numpy(), axis=0)}
        return self

    def predict(self, X):
        return np.array([self.values_.get(tuple(k), self.fallback_) for k in X[['quarter_sin', 'quarter_cos']].to_numpy()])

class LagBaseline(RegressorMixin, BaseEstimator):
    def __init__(self, column='lag1'):
        self.column = column

    def fit(self, X, y, sample_weight=None):
        return self

    def predict(self, X):
        return X[self.column].to_numpy(float)

def core_valid(d):
    x = d[CORE].apply(pd.to_numeric, errors='coerce')
    valid = np.isfinite(x).all(axis=1)
    valid &= x.all_area_m2.gt(0) & x.households.gt(0) & x.all_weighted_age.ge(0)
    valid &= x.nonresidential_mainuse_share_pct.between(0, 100) & x.single_share_pct.between(0, 100)
    return valid

def feature_matrix(d):
    x = d[CORE].apply(pd.to_numeric, errors='coerce').copy()
    x['all_area_m2'] = np.log1p(x.all_area_m2.where(x.all_area_m2.gt(0)))
    x['households'] = np.log1p(x.households.where(x.households.gt(0)))
    return x

def normalize(frame, columns, bounds, cost=False):
    values = frame[columns].apply(pd.to_numeric, errors='coerce')
    z = pd.DataFrame(index=frame.index)
    for c in columns:
        lo, hi = bounds[c]
        if hi <= lo:
            z[c] = np.where(np.isfinite(values[c]), 0., np.nan)
        else:
            z[c] = ((hi - values[c]) if cost else (values[c] - lo)) / (hi - lo)
            z[c] = z[c].clip(0, 1)
    return z

def response_values(frame):
    """호출 때마다 원량·인구에서 재계산하여 오래된 비율·플래그를 신뢰하지 않는다."""
    h = frame.copy(deep=True)
    pop = pd.to_numeric(h['총인구'], errors='coerce')
    pop = pop.where(np.isfinite(pop) & pop.gt(0))
    counts = ['의과병원수', '일반의원수', '약국수', '의과의사수', '일반입원병상수', '공공보건기관수']
    for count, rate in zip(counts, SUPPLY):
        raw = pd.to_numeric(h[count], errors='coerce')
        h[rate] = raw.where(np.isfinite(raw) & raw.ge(0)) / pop * 10000
    for flag, rate in [('의과의사수_원본빈값수', '인구1만명당_의과의사수'),
                       ('일반입원병상수_원본빈값수', '인구1만명당_일반입원병상수')]:
        h.loc[~h[flag].eq(0), rate] = np.nan
    er_cols = ['공식지정응급기관수', '기타응급실운영병원_명단기관수', '응급실병상기록_기관수']
    er = h[er_cols].apply(pd.to_numeric, errors='coerce')
    recorded = er.gt(0).any(axis=1)
    complete = np.isfinite(er).all(axis=1) & er.ge(0).all(axis=1)
    h['emergency_presence_score'] = np.where(recorded, 100., np.where(complete, 0., np.nan))
    return h
