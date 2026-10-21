"""이 영역의 모델만 읽는 백엔드 평가 서비스."""
from pathlib import Path
from .runtime.common import read
from .runtime.core import Core
from .runtime.input_schema import long_region_code, short_region_code
class ServiceBase:
    def __init__(self, package_dir=None):
        self.root = Path(package_dir or Path(__file__).resolve().parent).resolve()
        self.core = Core(self.root)
        self._cache = {}

    @staticmethod
    def records(frame):
        return Core.records(frame)

    def verify_integrity(self):
        self.core.verify_integrity()

    def _format(self, frame, future):
        d = frame.copy(deep=True)
        domain = self.DOMAIN
        out = d[['admin_code', 'admin_name', 'district']].rename(columns={
            'admin_code': 'region_code', 'admin_name': 'region_name', 'district': 'sigungu_name'})
        out['region_code'] = out.region_code.map(short_region_code)
        out[domain + '_score'] = d.score
        out[domain + '_grade'] = d.relative_grade
        status = ('validation_reason' if domain == 'energy' else 'forecast_status') if future else 'score_status'
        out[domain + '_status'] = d[status]
        out[domain + '_period'] = d.quarter if domain == 'energy' or future else d.as_of
        out['is_forecast'] = future
        out['production_approved'] = False
        out[domain + '_validation_passed'] = d.validation_passed if future else None
        if future:
            out[domain + '_validated_score'] = d.validated_score
            out[domain + '_score_lower'] = d.score_lower
            out[domain + '_score_upper'] = d.score_upper
        if domain == 'energy':
            for name in d.columns:
                if name.startswith(('electricity_MWh_', 'gas_1000m3_')) or name in ['source_group', 'horizon', 'origin']:
                    out[name] = d[name]
            if future:
                refit = self.core.metadata['additional_refit']
                out['energy_additional_refit_origins'] = refit['origins']
                out['energy_additional_refit_minimum_passed'] = refit['minimum_passed']
        else:
            mapping = {'medical_response': 'medical_response', 'aged_population_pct': 'elderly_population_pct',
                       'address_link_confirmed': 'address_link_confirmed', 'emergency_presence_score': 'emergency_presence_score',
                       '고령연령대_확인수': 'confirmed_elderly_age_band_count',
                       '고령연령대_미확인수': 'missing_elderly_age_band_count',
                       '고령비율_자료상태': 'elderly_ratio_data_status',
                       'air_input_imputed': 'health_air_input_imputed',
                       'air_imputation_sources': 'health_air_imputation_sources'}
            out['environment_score'] = d['exposure_score' if future else 'exposure_safety']
            for source, target in mapping.items():
                if source in d:
                    out[target] = d[source]
        return out.sort_values('region_code').reset_index(drop=True)

    def get_region_scores(self, region_code, mode='current'):
        code = short_region_code(long_region_code(region_code))
        if mode not in ['current', 'forecast']:
            raise ValueError('mode는 current 또는 forecast입니다.')
        if mode not in self._cache:
            self._cache[mode] = self.evaluate_latest() if mode == 'current' else self.forecast_latest()
        result = self._cache[mode]
        row = result.loc[result.region_code.eq(code)]
        if row.empty:
            raise KeyError('포함되지 않은 지역코드: ' + code)
        return self.records(row)[0]

class HealthScoringService(ServiceBase):
    DOMAIN = 'health'

    def score_health(self, medical, air_quarter):
        return self._format(self.core.score_health(medical, air_quarter), False)

    def forecast_health(self, medical, current_air_quarter, air_history, origin='2026-09'):
        result = self.core.forecast_health(medical, current_air_quarter, air_history, origin=origin)
        return {'scores': self._format(result['health'], True),
                'air_monthly': result['air_monthly'].rename(columns={'district': 'sigungu_name', 'district_code': 'sigungu_code'}),
                'air_quarter': result['air_quarter'].rename(columns={'district': 'sigungu_name', 'district_code': 'sigungu_code'})}

    def evaluate_latest(self):
        return self.score_health(read(self.root / 'data/health_snapshot.csv'), read(self.root / 'data/air_quarter.csv'))

    def forecast_latest(self):
        result = self.forecast_health(read(self.root / 'data/health_snapshot.csv'),
                                      read(self.root / 'data/air_quarter.csv'), read(self.root / 'data/air_history.csv'))
        return result['scores']
