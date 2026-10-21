import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from .common import CORE, read, grades
from .input_schema import normalize_model_frame
from .model import ConditionalEnergyScorer, EnergyForecaster, clean_history

class Core:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.verify_integrity()
        self.metadata = self._json('config/deployment_metadata.json')
        policy = self._json('config/grade_policy.json')
        self.energy_config = self._json('models/energy_score.json')
        self.energy_config['grade_thresholds'] = policy['energy']['thresholds']
        self.forecast_config = self._json('models/forecast_config.json')
        self.energy = ConditionalEnergyScorer.__new__(ConditionalEnergyScorer)
        self.energy.config = self.energy_config
        self.energy.bundles = {t: joblib.load(self.root / 'models' / ('energy_' + t + '.joblib'))
                               for t in ['electricity_MWh', 'gas_1000m3']}
        self.usage = {t: joblib.load(self.root / 'models' / ('usage_' + t + '.joblib'))
                      for t in ['electricity_MWh', 'gas_1000m3']}

    def _json(self, relative):
        return json.loads((self.root / relative).read_text(encoding='utf-8'))

    def verify_integrity(self):
        manifest = self._json('MANIFEST.json')
        for relative, expected in manifest['files'].items():
            p = (self.root / relative).resolve()
            if not p.is_relative_to(self.root) or not p.is_file():
                raise ValueError('패키지 파일 누락 또는 잘못된 경로: ' + relative)
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            if h != expected:
                raise ValueError('패키지 파일이 변경되었습니다: ' + relative)

    @staticmethod
    def _frame(value, required, keys):
        d = normalize_model_frame(value)
        if not d.columns.is_unique:
            raise ValueError('입력 컬럼이 중복됩니다.')
        missing = sorted(set(required) - set(d.columns))
        if missing:
            raise ValueError('필수 입력 컬럼 누락: ' + ', '.join(missing))
        if d.empty:
            raise ValueError('입력 행이 없습니다.')
        if d[keys].isna().any().any() or d.duplicated(keys).any():
            raise ValueError('입력 키 누락·중복: ' + ', '.join(keys))
        code = 'admin_code' if 'admin_code' in keys else '행정동코드' if '행정동코드' in keys else 'district_code'
        width = 10 if code != 'district_code' else 5
        if not d[code].map(lambda x: isinstance(x, str) and len(x) == width and x.isascii() and x.isdigit()).all():
            raise ValueError(f'{code}는 {width}자리 문자열이어야 합니다.')
        return d.reset_index(drop=True)

    @staticmethod
    def records(frame):
        """API JSON용 변환. 계산 보류 NaN을 0으로 바꾸지 않고 null로 내보낸다."""
        return json.loads(frame.to_json(orient='records', force_ascii=False, double_precision=15))

    def score_energy(self, frame):
        required = ['admin_code', 'district', 'admin_name', 'source_group', 'quarter', 'months',
                    'electricity_MWh', 'gas_1000m3', 'electricity_MWh_observed_months', 'gas_1000m3_observed_months'] + CORE
        d = self._frame(frame, required, ['admin_code', 'quarter'])
        if not d.quarter.str.fullmatch(r'\d{4}Q[1-4]').all():
            raise ValueError('quarter 형식은 2026Q2와 같아야 합니다.')
        for col in CORE + ['electricity_MWh', 'gas_1000m3', 'months', 'electricity_MWh_observed_months', 'gas_1000m3_observed_months']:
            d[col] = pd.to_numeric(d[col], errors='coerce')
        with threadpool_limits(limits=1):
            return self.energy.score(d)

    def forecast_energy(self, history, origin='2026Q2', steps=2):
        if origin != '2026Q2' or steps not in (1, 2):
            raise ValueError('이 버전은 2026Q2 출발의 1~2분기 전망만 지원합니다.')
        d = self._frame(history, ['admin_code', 'quarter', 'source_group', 'months', 'district', 'admin_name',
                        'electricity_MWh', 'gas_1000m3', 'electricity_MWh_observed_months', 'gas_1000m3_observed_months'] + CORE,
                        ['admin_code', 'quarter'])
        # 입력에 이후 관측 행이 있어도 예측 계산에는 전달하지 않는다.
        d = d.loc[d.quarter.le(origin)].copy()
        f = EnergyForecaster(clean_history(d), self.energy.bundles, self.energy_config)
        selected = {t: bundle['selected'] for t, bundle in self.usage.items()}
        with threadpool_limits(limits=1):
            out = f.forecast(origin, steps, self.usage, selected)
        config = self.forecast_config['energy']
        radius = config['score_error_width'] * np.sqrt(out.horizon)
        out['score_lower'] = np.maximum(0, out.score - radius)
        out['score_upper'] = np.minimum(100, out.score + radius)
        out['validation_passed'] = out.horizon.map(lambda h: bool(config['gates'][str(h)]['passed']))
        out['validated_score'] = np.where(out.validation_passed, out.score, np.nan)
        out['validation_reason'] = out.horizon.map(lambda h: self.metadata['energy_validation_reasons'][str(h)])
        return out
