import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import economy


class EconomyReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.data, cls.regions = economy.load_inputs(ROOT)
        cls.actual = economy.estimate('2026-10-21', '2026-10', ROOT)

    def assert_invalid_frames(self, data=None, regions=None):
        with self.assertRaises(economy.DataContractError):
            economy.validate_frames(self.data if data is None else data,
                                    self.regions if regions is None else regions, self.config)

    def test_all_427_estimates_replay_release_output(self):
        expected = json.loads((ROOT/'results/economy_scores.json').read_text(encoding='utf-8'))
        expected_scores = {x['region']['region_code']:x['scores']['economy'] for x in expected['items']}
        actual_scores = {x['region']['region_code']:x['scores']['economy'] for x in self.actual['items']}
        self.assertEqual(len(actual_scores),427)
        self.assertEqual(set(actual_scores),set(expected_scores))
        for code in expected_scores:
            self.assertAlmostEqual(actual_scores[code],expected_scores[code],places=8)

    def test_output_schema_and_semantics(self):
        for item in self.actual['items']:
            self.assertRegex(item['region']['region_code'],r'^\d{6}$')
            self.assertRegex(item['region']['sigungu_code'],r'^\d{5}$')
            self.assertGreaterEqual(item['scores']['economy'],0)
            self.assertLessEqual(item['scores']['economy'],100)
            self.assertEqual(item['metadata']['economy']['status'],'estimated')
            self.assertIsNone(item['scores']['safety'])
            self.assertNotIn('direction',item['metadata']['economy'])
            self.assertAlmostEqual(item['scores']['economy'],sum(
                x['score']*x['weight'] for x in item['metadata']['economy']['components'].values()))

    def test_ten_digit_code_rejected(self):
        regions=self.regions.copy(); regions.loc[0,'region_code']='1111051500'
        self.assert_invalid_frames(regions=regions)

    def test_numeric_code_rejected(self):
        regions=self.regions.copy(); regions['region_code']=regions.region_code.astype(int)
        self.assert_invalid_frames(regions=regions)

    def test_unknown_dong_rejected(self):
        data=self.data.copy(); data.loc[0,'region_code']='999999'
        self.assert_invalid_frames(data=data)

    def test_duplicate_dong_month_rejected(self):
        self.assert_invalid_frames(data=pd.concat([self.data,self.data.iloc[:1]],ignore_index=True))

    def test_missing_latest_is_not_zero(self):
        data=self.data.copy()
        index=data.index[data.month.eq('2026-08')][0]
        data.loc[index,'corporate_nps_members']=np.nan
        self.assert_invalid_frames(data=data)

    def test_observed_zero_is_allowed(self):
        data=self.data.copy()
        index=data.index[data.month.eq('2026-08')][0]
        data.loc[index,'corporate_nps_members']=0
        economy.validate_frames(data,self.regions,self.config)

    def test_infinite_and_negative_rejected(self):
        for bad in [-1,np.inf]:
            data=self.data.copy(); data.loc[0,'commute_weekday_daily_mean']=bad
            self.assert_invalid_frames(data=data)

    def test_invalid_area_rejected(self):
        regions=self.regions.copy(); regions.loc[0,'official_area_km2']=0
        self.assert_invalid_frames(regions=regions)

    def test_future_target_requires_new_release(self):
        with self.assertRaises(economy.DataContractError):
            economy.validate_request(self.config,'2026-11-01','2026-11')

    def test_past_snapshot_leakage_rejected(self):
        with self.assertRaises(economy.DataContractError):
            economy.validate_request(self.config,'2026-10-20','2026-10')

    def test_old_month_not_presented_as_current(self):
        with self.assertRaises(economy.DataContractError):
            economy.validate_request(self.config,'2026-11-01','2026-10')

    def test_stale_source_rejected(self):
        config=copy.deepcopy(self.config); config['source_months']['commute']='2026-08'
        with self.assertRaises(economy.DataContractError):
            economy.validate_request(config,'2026-10-21','2026-10')

    def test_unknown_future_observations_rejected(self):
        data=self.data.copy(); data.loc[data.month.eq('2026-09'),'corporate_nps_members']=1
        self.assert_invalid_frames(data=data)

    def test_fixed_normalization_boundaries(self):
        for axis in economy.AXES:
            c=self.config['normalization'][axis]
            values=np.array([0,np.expm1(c['log_density_p05']),np.expm1(c['log_density_p95']),np.inf])
            np.testing.assert_allclose(economy.normalized_score(values,axis,self.config),[0,0,100,100],atol=1e-10)

    def test_suspect_months_and_split_history_not_fabricated(self):
        panels=economy.panels_from_inputs(self.data,self.regions)
        self.assertTrue(panels['commute'].loc[['2025-03','2025-04']].isna().all().all())
        for panel in panels.values():
            self.assertTrue(panel.loc[panel.index<'2025-08',['230515','230533']].isna().all().all())

    def test_three_recent_valid_observations(self):
        panel=pd.DataFrame({'110515':[1,np.nan,5,9]},index=['2026-06','2026-07','2026-08','2026-09'])
        regions=self.regions[self.regions.region_code.eq('110515')]
        result=economy.feature_rows(panel,regions,'commute','2026-10',1)
        self.assertEqual(result.loc['110515','recent3'],5)

    def test_insufficient_history_falls_back_to_latest(self):
        panel=pd.DataFrame({'110515':[1,9]},index=['2026-08','2026-09'])
        regions=self.regions[self.regions.region_code.eq('110515')]
        result=economy.feature_rows(panel,regions,'commute','2026-10',1)
        self.assertEqual(result.loc['110515','recent3'],9)
        self.assertTrue(result.loc['110515','cold_start'])

    def test_config_method_cannot_misrepresent_implementation(self):
        config=copy.deepcopy(self.config)
        config['selected_methods']['commute']='ridge'
        with self.assertRaises(economy.DataContractError):
            economy.validate_config(config)

    def test_config_weights_and_calibration_validated(self):
        for changes in ['weight','normalization']:
            config=copy.deepcopy(self.config)
            if changes=='weight': config['weights']['commute']=.5
            else: config['normalization']['commute']['log_density_p95']=0
            with self.assertRaises(economy.DataContractError):
                economy.validate_config(config)


if __name__=='__main__':
    unittest.main()
