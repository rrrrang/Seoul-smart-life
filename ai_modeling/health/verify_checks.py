"""각 영역 폴더 하나만 프로젝트 밖으로 복사한 상태에서 실행한다."""
import importlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DOMAIN = ROOT.name
sys.path.insert(0, str(ROOT.parent))
module = importlib.import_module(DOMAIN)
Service = getattr(module, 'EnergyScoringService' if DOMAIN == 'energy' else 'HealthScoringService')
schema = importlib.import_module(DOMAIN + '.runtime.input_schema')
common = importlib.import_module(DOMAIN + '.runtime.common')


def raw(relative):
    return pd.read_csv(ROOT / relative, dtype={'region_code': str, 'sigungu_code': str, 'source_group': str})


class DomainChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = Service()
        cls.current = cls.service.evaluate_latest()
        cls.future = cls.service.forecast_latest()

    def test_01_independent_domain_and_integrity(self):
        self.assertNotEqual(Path.cwd().resolve(), ROOT)
        self.assertFalse(any(k == 'src' or k.startswith('src.') for k in sys.modules))
        other = 'health' if DOMAIN == 'energy' else 'energy'
        self.assertFalse(any(k == other or k.startswith(other + '.') for k in sys.modules))
        self.assertFalse((ROOT.parent / other).exists())
        self.service.verify_integrity()
        self.assertEqual(len(list((ROOT / 'models').glob('*.joblib'))), 4 if DOMAIN == 'energy' else 3)

    def test_02_all_current_scores_and_grades_match(self):
        expected = raw('reference/current_scores.csv').set_index('region_code')
        result = self.current.set_index('region_code').loc[expected.index]
        self.assertEqual(len(result), 427)
        np.testing.assert_allclose(result[DOMAIN + '_score'], expected[DOMAIN + '_score'], atol=1e-9, rtol=1e-11)
        np.testing.assert_array_equal(result[DOMAIN + '_grade'], expected[DOMAIN + '_grade'])
        self.assertTrue(result[DOMAIN + '_score'].between(0, 100).all())
        other = 'health' if DOMAIN == 'energy' else 'energy'
        self.assertNotIn(other + '_score', result)

    def test_03_all_forecasts_match_and_keep_validation_holds(self):
        expected = raw('reference/forecast_scores.csv').set_index('region_code')
        result = self.future.set_index('region_code').loc[expected.index]
        self.assertEqual(len(result), 427)
        for name in expected.select_dtypes(include='number').columns:
            np.testing.assert_allclose(result[name], expected[name], atol=1e-8, rtol=1e-11)
        np.testing.assert_array_equal(result[DOMAIN + '_grade'], expected[DOMAIN + '_grade'])
        self.assertFalse(result.production_approved.any())
        self.assertFalse(result[DOMAIN + '_validation_passed'].any())
        self.assertTrue(result[DOMAIN + '_validated_score'].isna().all())
        if DOMAIN == 'health':
            self.assertEqual(int(result.health_air_input_imputed.sum()), 10)
            self.assertEqual(int(result.missing_elderly_age_band_count.gt(0).sum()), 27)

    def test_04_json_lookup_and_code_compatibility(self):
        code = self.current.region_code.iloc[0]
        row = self.service.get_region_scores(code)
        self.assertEqual(row['region_code'], code)
        self.assertEqual(row, self.service.get_region_scores('11' + code + '00'))
        self.assertTrue(self.service.get_region_scores(code, 'forecast')['is_forecast'])
        json.dumps(row, ensure_ascii=False, allow_nan=False)
        self.assertEqual(self.service.records(pd.DataFrame({'score': [np.nan]})), [{'score': None}])
        with self.assertRaises(ValueError):
            self.service.get_region_scores('11051')
        with self.assertRaises(KeyError):
            self.service.get_region_scores('999999')

    def test_05_raw_public_csv_inputs_missing_values_and_immutability(self):
        if DOMAIN == 'energy':
            frame = raw('examples/energy_input.csv')
            before = frame.copy(deep=True)
            result = self.service.score_energy(frame)
            self.assertTrue(result.energy_score.notna().all())
            pd.testing.assert_frame_equal(frame, before)
            frame.loc[0, 'electricity_MWh'] = np.nan
            self.assertTrue(np.isnan(self.service.score_energy(frame).energy_score.iloc[0]))
            with self.assertRaises(ValueError):
                self.service.score_energy(frame.drop(columns='households'))
        else:
            frame, air = raw('examples/health_input.csv'), raw('examples/air_quarter_input.csv')
            before = frame.copy(deep=True)
            self.assertTrue(self.service.score_health(frame, air).health_score.notna().all())
            pd.testing.assert_frame_equal(frame, before)
            frame.loc[0, 'physician_count'] = np.nan
            self.assertTrue(np.isnan(self.service.score_health(frame, air).health_score.iloc[0]))
            with self.assertRaises(ValueError):
                self.service.score_health(frame, pd.concat([air, air.iloc[[0]]]))

    def test_06_domain_rules_and_actual_numeric_inputs(self):
        if DOMAIN == 'energy':
            data = raw('data/energy_quarter.csv')
            fit = data.loc[data.quarter.eq('2025Q3')].head(2)
            self.assertTrue(self.service.score_energy(fit).energy_score.isna().all())
            data = data.loc[data.quarter.eq('2026Q2')].head(1).copy()
            before = self.service.score_energy(data).energy_score.iloc[0]
            data['electricity_MWh'] *= 2
            self.assertLess(self.service.score_energy(data).energy_score.iloc[0], before)
        else:
            data, air = raw('examples/health_input.csv').iloc[[0]].copy(), raw('examples/air_quarter_input.csv')
            columns = ['designated_emergency_institution_count', 'other_emergency_roster_institution_count',
                       'institutions_with_emergency_bed_records']
            data[columns] = 0
            before = self.service.score_health(data, air).health_score.iloc[0]
            data[columns[0]] = 1
            self.assertGreater(self.service.score_health(data, air).health_score.iloc[0], before)

    def test_07_future_values_do_not_leak_into_forecasts(self):
        if DOMAIN == 'energy':
            data = raw('data/energy_quarter.csv')
            data = data.loc[data.region_code.isin(data.region_code.unique()[:3])].copy()
            before = self.service.forecast_energy(data)
            data.loc[data.quarter.gt('2026Q2'), ['electricity_MWh', 'gas_1000m3', 'temperature_C', 'households']] = 987654321.
            pd.testing.assert_frame_equal(before, self.service.forecast_energy(data))
        else:
            h, air, history = raw('examples/health_input.csv'), raw('data/air_quarter.csv'), raw('data/air_history.csv')
            before = self.service.forecast_health(h, air, history)['scores']
            fake = history.loc[history.period.eq('2026-09')].copy()
            fake['period'], fake['actual'] = '2026-10', 987654321.
            history = pd.concat([history, fake], ignore_index=True)
            pd.testing.assert_frame_equal(before, self.service.forecast_health(h, air, history)['scores'])

    def test_08_fixed_five_grades_and_no_recommendation(self):
        config = self.service.core.energy_config if DOMAIN == 'energy' else self.service.core.health_config
        edges = config['grade_thresholds']
        np.testing.assert_array_equal(common.grades(edges, edges), ['아주나쁨', '나쁨', '기본', '좋음'])
        self.assertEqual(common.grades([100], edges)[0], '아주좋음')
        self.assertIsNone(common.grades([np.nan], edges)[0])
        self.assertFalse(any('rank' in c or '종합' in c for c in self.current.columns))


if __name__ == '__main__':
    from threadpoolctl import threadpool_limits
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    with threadpool_limits(limits=1):
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DomainChecks))
    print(json.dumps({'domain': DOMAIN, 'tests': result.testsRun, 'passed': result.wasSuccessful(),
                      'failures': len(result.failures), 'errors': len(result.errors)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
