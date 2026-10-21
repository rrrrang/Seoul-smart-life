import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from .common import CORE, read, grades
from .input_schema import normalize_model_frame
from .model import HealthContextScorer, forecast_air, quarter_air, score_quarter, health_projection

class Core:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.verify_integrity()
        self.metadata = self._json('config/deployment_metadata.json')
        policy = self._json('config/grade_policy.json')
        self.health_config = self._json('models/health_context.json')
        self.health_config['grade_thresholds'] = policy['health']['thresholds']
        self.health = HealthContextScorer(config=self.health_config)
        self.air = {t: joblib.load(self.root / 'models' / ('air_' + t.replace('.', '_') + '_deployment.joblib'))
                    for t in ['pm10', 'pm2.5', 'o3']}

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

    def score_health(self, medical, air_quarter):
        required = self.metadata['health_required_columns']
        h = self._frame(medical, required, ['행정동코드'])
        a = self._frame(air_quarter, ['district_code', 'quarter', 'pm10', 'pm2.5', 'o3'], ['district_code', 'quarter'])
        if not h['기준자료_연결확인'].map(lambda x: isinstance(x, (bool, np.bool_))).all():
            raise ValueError('기준자료_연결확인은 true/false 논리값이어야 합니다.')
        for c in self.metadata['health_numeric_columns']:
            h[c] = pd.to_numeric(h[c], errors='coerce')
        for c in ['pm10', 'pm2.5', 'o3']:
            a[c] = pd.to_numeric(a[c], errors='coerce')
        result = self.health.score(h, a)
        for c in ['고령인구_확인분합계', '고령연령대_확인수', '고령연령대_미확인수',
                  '고령연령대_미확인목록', '고령비율_자료상태', '고령비율_계산정책']:
            if c in h:
                result[c] = h[c].values
        partial = h['고령연령대_미확인수'].gt(0) if '고령연령대_미확인수' in h else pd.Series(False, index=h.index)
        result.loc[partial, 'data_quality'] += ';고령비율은 확인 연령대만 합산한 부분 비율'
        result.loc[partial & result.score.notna(), 'score_status'] += '_고령정보부분확인'
        result['input_policy_version'] = 'confirmed-elderly-age-bands-v2'
        return result

    def forecast_health(self, medical, current_air_quarter, air_history, origin='2026-09'):
        if origin != '2026-09':
            raise ValueError('이 버전은 2026-09 출발의 2026Q4 전망만 지원합니다.')
        history = self._frame(air_history, ['district_code', 'district', 'period', 'target', 'actual'],
                              ['district_code', 'target', 'period'])
        if not history.target.isin(['pm10', 'pm2.5', 'o3']).all():
            raise ValueError('지원하지 않는 대기 물질입니다.')
        current = self.score_health(medical, current_air_quarter)
        with threadpool_limits(limits=1):
            monthly = forecast_air(history, origin, self.air)
            quarter = score_quarter(quarter_air(monthly), self.health_config)
            result = health_projection(current, quarter, self.health_config)
        return {'health': result, 'air_monthly': monthly, 'air_quarter': quarter}
