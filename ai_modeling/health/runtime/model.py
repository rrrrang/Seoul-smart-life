"""현재 건강여건 점수와 의료 유지 조건의 대기 전망. 학습·외부 다운로드 없음."""
import json
import joblib
import numpy as np
import pandas as pd
from .common import MODELS, normalize, response_values, strict_sum, grades, interval
from .input_schema import normalize_model_frame
FEATURES = ['lag1', 'lag2', 'lag3', 'lag12', 'past3_mean', 'month_sin', 'month_cos']
TARGETS = ['pm10', 'pm2.5', 'o3']
AIR_POLICY = 'geumcheon-202512-other24-median-v1'

class HealthContextScorer:
    def __init__(self, config=None):
        self.config = config if config is not None else json.loads((MODELS / 'health_context.json').read_text(encoding='utf-8'))

    def score(self, frame, air_quarter):
        h = response_values(normalize_model_frame(frame)).reset_index(drop=True)
        air_quarter = normalize_model_frame(air_quarter)
        cfg = self.config
        if h['행정동코드'].duplicated().any():
            raise ValueError('건강 입력 행정동 중복')
        latest = air_quarter.loc[air_quarter.quarter.eq('2026Q3')].copy()
        if latest.district_code.duplicated().any():
            raise ValueError('대기 자치구 원량 중복')
        out = h[['행정동코드', '자치구', '행정동명']].rename(columns={
            '행정동코드': 'admin_code', '자치구': 'district', '행정동명': 'admin_name'})
        out['district_code'] = h['행정동코드'].str[:5]
        out = out.merge(latest[['district_code'] + cfg['exposure_columns']], how='left', on='district_code', validate='many_to_one')
        rz = normalize(h, cfg['response_columns'], cfg['response_bounds'])
        ez = normalize(out, cfg['exposure_columns'], cfg['exposure_bounds'], cost=True)
        valid_med = np.isfinite(h[cfg['response_columns']]).all(axis=1) & h[cfg['response_columns']].ge(0).all(axis=1)
        valid_env = np.isfinite(out[cfg['exposure_columns']]).all(axis=1) & out[cfg['exposure_columns']].ge(0).all(axis=1)
        out['medical_response'] = 100 * strict_sum(rz, cfg['response_weights'])
        out['exposure_safety'] = 100 * strict_sum(ez, cfg['exposure_weights'])
        out.loc[~valid_med, 'medical_response'] = np.nan
        out.loc[~valid_env, 'exposure_safety'] = np.nan
        out['score'] = strict_sum(out[['exposure_safety', 'medical_response']], cfg['axis_weights'])
        age = pd.to_numeric(h['고령인구비율_pct'], errors='coerce')
        age_valid = np.isfinite(age) & age.between(0, 100)
        out.loc[~age_valid, 'score'] = np.nan
        dates_valid = h['의료자료기준'].eq('2026-06') & h['인구기준'].eq('2026Q2') & h['행정동주소DB기준'].eq('2026-09')
        out.loc[~dates_valid, 'score'] = np.nan
        out['aged_population_pct'] = age
        out['relative_grade'] = grades(out.score, cfg['grade_thresholds']) if cfg['grade_thresholds'] else None
        out['absolute_grade'] = None
        out['address_link_confirmed'] = h['기준자료_연결확인']
        out['score_status'] = np.where(out.score.isna(), '입력누락_계산보류',
                             np.where(out.address_link_confirmed, '상대참고_정식승인전', '주소불확실_잠정참고'))
        out['missing_fields'] = [';'.join((['고령인구비율_pct'] if not age_valid.iloc[i] else [])
                                         + (['의료대응입력'] if not valid_med.iloc[i] else [])
                                         + (['대기노출입력'] if not valid_env.iloc[i] else [])
                                         + (['지원하지않는_자료기준일'] if not dates_valid.iloc[i] else [])) for i in range(len(h))]
        out['score_kind'] = '건강여건_상대참고지수'
        out['as_of'] = cfg['as_of']
        out['component_dates'] = json.dumps(cfg['component_dates'], ensure_ascii=False)
        out['model_version'] = cfg['version']
        out['weights_version'] = cfg['version'] + ':snapshot'
        out['calibration_version'] = cfg['version'] + ':328-dong-reference'
        out['data_quality'] = '구 대기 참조·의료공급 대리·단위 미확인·기후 미반영·취약성 정량효과 미확정'
        out['source_geography'] = '대기:자치구; 의료:행정동'
        out['source_group_or_geography'] = out['source_geography']
        out['prediction_interval'] = None
        out['emergency_presence_score'] = h['emergency_presence_score']
        for c in ['공식지정응급기관수', '기타응급실운영병원_명단기관수', '응급실병상기록_기관수', '운영시간미확인_기관수']:
            out[c] = h[c]
        for c in cfg['response_columns']:
            out[c + '_normalized'] = rz[c] * 100
        for c in cfg['exposure_columns']:
            out[c + '_score'] = ez[c] * 100
        return out

def forecast_air(history, origin, bundles, months=3, override=None):
    if months != 3:
        raise ValueError('분기 비교를 위해 3개월 전망만 지원합니다.')
    origin = pd.Period(origin, freq='M')
    if origin.month not in [3, 6, 9, 12]:
        raise ValueError('분기 말에서 출발해야 분기 기준과 비교할 수 있습니다.')
    known = history.loc[history.period.le(str(origin))].copy()
    if known.duplicated(['district_code', 'target', 'period']).any():
        raise ValueError('대기 원량 자치구·물질·월 중복')
    frames = []
    for target in TARGETS:
        bundle = bundles[target]
        if bundle['fit_end'] > str(origin):
            raise ValueError('출발 이후 정답으로 학습한 대기 모델입니다.')
        if bundle.get('calibration_end', '2025-12') > str(origin):
            raise ValueError('출발 이후 오차로 보정한 대기 모델입니다.')
        source = known.loc[known.target.eq(target)].copy()
        source.actual = source.actual.where(np.isfinite(source.actual) & source.actual.ge(0))
        state = {(r.district_code, r.period): r.actual for r in source.itertuples()}
        lineage = {}
        if 'is_imputed' in source:
            flagged = source.loc[source.is_imputed.eq(True)]
            if flagged.imputation_available_month.gt(str(origin)).any():
                raise ValueError('출발 이후에야 이용 가능한 보완값입니다.')
            lineage = {(r.district_code, r.period): {r.imputation_source} for r in flagged.itertuples()}
        districts = source[['district_code', 'district']].drop_duplicates().sort_values('district_code')
        for h in range(1, months + 1):
            q = origin + h
            rows = []
            for code, district in districts.itertuples(index=False, name=None):
                row = {'district_code': code, 'district': district, 'target': target,
                       'origin': str(origin), 'period': str(q), 'horizon_months': h}
                sources = set()
                for lag in [1, 2, 3, 12]:
                    row['lag' + str(lag)] = state.get((code, str(q - lag)), np.nan)
                    sources.update(lineage.get((code, str(q - lag)), set()))
                row['input_contains_imputation'] = bool(sources)
                row['imputation_sources'] = ';'.join(sorted(sources))
                row['past3_mean'] = np.mean([row['lag1'], row['lag2'], row['lag3']])
                row['month_sin'], row['month_cos'] = np.sin(2 * np.pi * q.month / 12), np.cos(2 * np.pi * q.month / 12)
                rows.append(row)
            d = pd.DataFrame(rows)
            valid = np.isfinite(d[FEATURES]).all(axis=1) & d[['lag1', 'lag2', 'lag3', 'lag12']].ge(0).all(axis=1)
            d['predicted'] = np.nan
            method = override or bundle['selected']
            if method in ['previous_month', 'previous_year']:
                d.loc[valid, 'predicted'] = d.loc[valid, 'lag1' if method == 'previous_month' else 'lag12']
            elif valid.any():
                d.loc[valid, 'predicted'] = bundle['model'].predict(d.loc[valid, FEATURES])
            d.loc[d.predicted.lt(0) | ~np.isfinite(d.predicted), 'predicted'] = np.nan
            d['lower'], d['upper'] = interval(d.predicted, bundle['radius'] * np.sqrt(h))
            d['method'], d['observed_value'] = method, np.nan
            d['value_kind'] = '예측_관측값아님'
            d['recursive_prediction_used'] = h > 1
            d['missing_fields'] = [';'.join(col for col in FEATURES if not np.isfinite(row[col]))
                                     for _, row in d.iterrows()]
            for row in d.itertuples():
                state[row.district_code, row.period] = row.predicted
                lineage[row.district_code, row.period] = set(row.imputation_sources.split(';')) if row.imputation_sources else set()
            frames.append(d)
    return pd.concat(frames, ignore_index=True)

def quarter_air(monthly):
    d = monthly.copy()
    d['quarter'] = pd.PeriodIndex(d.period, freq='M').asfreq('Q').astype(str)
    rows = []
    for keys, part in d.groupby(['district_code', 'district', 'origin', 'quarter']):
        row = dict(zip(['district_code', 'district', 'origin', 'quarter'], keys))
        row['air_input_imputed'] = bool(part.input_contains_imputation.any())
        row['air_imputation_sources'] = ';'.join(sorted({key for text in part.imputation_sources for key in str(text).split(';') if key and key != 'nan'}))
        row['air_input_policy'] = AIR_POLICY if row['air_input_imputed'] else 'original_history'
        for target in TARGETS:
            p = part.loc[part.target.eq(target)]
            for value, suffix in [('predicted', ''), ('lower', '_lower'), ('upper', '_upper')]:
                valid = len(p) == 3 and p.period.nunique() == 3 and np.isfinite(p[value]).all()
                row[target + suffix] = float(p[value].mean()) if valid else np.nan
        rows.append(row)
    return pd.DataFrame(rows)

def exposure_score(frame, config):
    z = normalize(frame, TARGETS, config['exposure_bounds'], cost=True)
    result = 100 * strict_sum(z, config['exposure_weights'])
    valid = np.isfinite(frame[TARGETS]).all(axis=1) & frame[TARGETS].ge(0).all(axis=1)
    result[~valid] = np.nan
    return result

def score_quarter(quarter, config):
    d = quarter.copy()
    d['exposure_score'] = exposure_score(d, config)
    for suffix, label in [('_upper', 'exposure_lower'), ('_lower', 'exposure_upper')]:
        # Higher pollution gives a lower safety score; reverse the endpoints.
        endpoints = pd.DataFrame({t: d[t + suffix] for t in TARGETS})
        d[label] = exposure_score(endpoints, config)
    return d

def health_projection(current, predicted_quarter, config):
    """기존 보류를 유지하며 미래 의료 공급을 학습했다고 주장하지 않는다."""
    if predicted_quarter.district_code.duplicated().any():
        raise ValueError('전망 자치구 중복')
    out = current.copy(deep=True)
    # Never copy the current observed score into a future observed field.
    out = out.rename(columns={'score': 'current_score', 'relative_grade': 'current_grade',
                              'exposure_safety': 'current_exposure_safety',
                              **{t: 'current_' + t for t in TARGETS}})
    env = predicted_quarter[['district_code', 'quarter', 'exposure_score', 'exposure_lower', 'exposure_upper',
                             'air_input_imputed', 'air_imputation_sources', 'air_input_policy']]
    out = out.merge(env, how='left', on='district_code', validate='many_to_one')
    out['score'] = strict_sum(out[['exposure_score', 'medical_response']], config['axis_weights'])
    out['score_lower'] = strict_sum(out[['exposure_lower', 'medical_response']], config['axis_weights'])
    out['score_upper'] = strict_sum(out[['exposure_upper', 'medical_response']], config['axis_weights'])
    # Age, source-date and medical missingness holds are inherited unchanged.
    valid = out.current_score.notna()
    out.loc[~valid, ['score', 'score_lower', 'score_upper']] = np.nan
    out['relative_grade'] = grades(out.score, config['grade_thresholds'])
    out['value_kind'] = '예측_의료인구응급유지시나리오'
    out['observed_future_score'] = np.nan
    out['validation_passed'], out['validated_score'] = False, np.nan
    out['forecast_origin'] = '2026-09'
    out['forecast_status'] = np.where(out.score.isna(), '입력누락_계산보류',
                            np.where(out.address_link_confirmed, '시범예상_전체건강정답검증없음',
                                     '시범예상_주소불확실_전체건강정답검증없음'))
    out['future_missing_fields'] = out.missing_fields.fillna('')
    out.loc[out.exposure_score.isna(), 'future_missing_fields'] += ';미래대기입력'
    imputed = out.air_input_imputed.eq(True)
    out.loc[imputed & out.score.notna(), 'forecast_status'] += '_대기보완값사용'
    out.loc[imputed, 'data_quality'] += ';과거 대기 통계적 보완값 사용; 보완 오차는 점수 범위에 추가 보정하지 않음'
    return out
