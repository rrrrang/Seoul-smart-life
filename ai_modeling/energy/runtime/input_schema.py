"""영어 열 이름·6자리 지역코드를 기존 저장 모델의 입력 형식으로 연결한다."""
import numpy as np
import pandas as pd

from .health_columns import HEALTH_COLUMN_NAMES

ENERGY_COLUMN_NAMES = {'admin_code': 'region_code', 'admin_name': 'region_name', 'district': 'sigungu_name'}
AIR_COLUMN_NAMES = {'district_code': 'sigungu_code', 'district': 'sigungu_name'}


def long_region_code(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise ValueError('region_code는 6자리 문자열이어야 합니다. 기존 10자리 코드도 지원합니다.')
    if len(value) == 6:
        return '11' + value + '00'
    if len(value) == 10 and value.startswith('11') and value.endswith('00'):
        return value
    raise ValueError('지원하지 않는 서울 행정동 코드 형식입니다: ' + value)


def short_region_code(value):
    return long_region_code(value)[2:-2]


def normalize_model_frame(frame):
    """공개 입력을 복사·변환한다. 필수값을 보충하거나 결측을 채우지는 않는다."""
    out = frame.copy(deep=True) if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)
    if not out.columns.is_unique:
        raise ValueError('입력 열 이름이 중복됩니다.')
    medical = any(c in out for c in ['medical_reference_period', '의료자료기준', 'medical_institution_count'])
    aliases = ({v: k for k, v in HEALTH_COLUMN_NAMES.items()} if medical else
               {v: k for k, v in ENERGY_COLUMN_NAMES.items()} if 'region_code' in out else
               {v: k for k, v in AIR_COLUMN_NAMES.items()})
    for public, internal in aliases.items():
        if public != internal and public in out and internal in out:
            raise ValueError('같은 항목의 새 이름과 기존 이름을 동시에 넣을 수 없습니다: ' + public)
    out = out.rename(columns=aliases)
    if medical:
        code = '행정동코드'
    else:
        code = 'admin_code'
    if code in out:
        out[code] = out[code].map(lambda v: long_region_code(v) if pd.notna(v) else v)
    return out


def energy_export_frame(frame):
    out = normalize_model_frame(frame).rename(columns=ENERGY_COLUMN_NAMES)
    out['region_code'] = out['region_code'].map(short_region_code)
    return out


def air_quarters(frame):
    """각 오염물질의 3개월 값이 모두 있을 때만 분기 평균을 계산한다."""
    d = normalize_model_frame(frame)
    if d.duplicated(['district_code', 'period']).any():
        raise ValueError('자치구·월 대기 입력이 중복됩니다.')
    d['quarter'] = pd.PeriodIndex(d.period, freq='M').asfreq('Q').astype(str)
    columns = ['pm10', 'pm2.5', 'o3']
    d[columns] = d[columns].apply(pd.to_numeric, errors='coerce')
    d[columns] = d[columns].where(np.isfinite(d[columns]) & d[columns].ge(0))
    grouped = d.groupby(['district_code', 'district', 'quarter'])
    values, counts = grouped[columns].mean(), grouped[columns].count()
    for column in columns:
        values.loc[counts[column].ne(3), column] = np.nan
    return values.reset_index()


def air_forecast_history(frame):
    """현재 월별 보완 CSV를 예측용 긴 표로 변환하며 보완 출처를 유지한다."""
    d = normalize_model_frame(frame)
    if d.duplicated(['district_code', 'period']).any():
        raise ValueError('자치구·월 대기 입력이 중복됩니다.')
    rows = []
    for target in ['pm10', 'pm2.5', 'o3']:
        part = d[['district_code', 'district', 'period', 'air_input_policy']].copy()
        part['target'] = target
        part['actual'] = d[target]
        part['actual_original'] = d[target + '_original']
        part['is_imputed'] = d[target + '_is_imputed'].eq(True)
        part['imputation_source'] = np.where(part.is_imputed,
            part.district_code + ':' + part.period + ':' + target, '')
        part['imputation_available_month'] = np.where(part.is_imputed, part.period, '')
        part['input_value_kind'] = np.where(part.is_imputed, '통계적보완_관측값아님', '원자료값')
        rows.append(part)
    columns = ['district_code', 'district', 'period', 'target', 'actual', 'actual_original',
               'is_imputed', 'imputation_source', 'imputation_available_month', 'input_value_kind', 'air_input_policy']
    return pd.concat(rows, ignore_index=True)[columns].sort_values(['target', 'district_code', 'period']).reset_index(drop=True)
