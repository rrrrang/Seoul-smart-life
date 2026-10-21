"""Regression tests for the six-digit project geography and unchanged statistics."""
from pathlib import Path
from copy import deepcopy
import csv
import hashlib
import json
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from evaluation_contract import load_region_master, validate_regions, validate_evaluation
from backend_contract import convert, validate_backend
from safety_scoring import score_safety, relative_scores, combine
from safety_grading import grade_from_score, forbidden_paths
from build_safety import build_payload, verify_saved

PRESERVED_STATISTICS_SHA256='4091b7959d33f02f9f64cc049b8e9f916bb78981aeee2845814387acb26ea73c'

def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

class SafetyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master=load_region_master()
        cls.raw=load(ROOT/'data/safety_scoring_input.json')
        cls.saved=load(ROOT/'results/safety_scores.json')
        cls.scores=score_safety(cls.raw)

    def test_master_has_427_unique_six_digit_codes_and_25_districts(self):
        self.assertEqual(len(self.master),427)
        self.assertEqual(len({r['sigungu_code'] for r in self.master.values()}),25)
        for code,row in self.master.items():
            self.assertRegex(code,r'^\d{6}$')
            self.assertRegex(row['sigungu_code'],r'^\d{5}$')
            self.assertEqual(set(row),{'region_code','region_name','sigungu_code','sigungu_name'})

    def test_input_and_output_have_exact_same_master_membership(self):
        validate_regions(self.raw['dongs'],require_all=True)
        actual={i['region']['region_code']:i['region'] for i in self.saved['items']}
        self.assertEqual(set(actual),set(self.master))
        for code,region in actual.items():
            self.assertEqual(region,{'region_code':code,'name_ko':self.master[code]['region_name'],
                'sigungu_code':self.master[code]['sigungu_code'],'spatial_unit':'dong'})

    def test_no_legacy_geography_fields_in_input_or_delivery(self):
        def visit(obj):
            if isinstance(obj,dict):
                self.assertFalse({'region_short_code','parent_region_code'}.intersection(obj))
                for value in obj.values(): visit(value)
            elif isinstance(obj,list):
                for value in obj: visit(value)
        visit(self.raw);visit(self.saved)

    def test_unknown_and_numeric_codes_are_rejected(self):
        for invalid in ('999999','1111051500',110515):
            row=deepcopy(self.raw['dongs'][0]);row['region_code']=invalid
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):validate_regions([row])

    def test_legacy_fields_are_rejected_even_with_valid_short_code(self):
        for key in ('region_short_code','parent_region_code'):
            row=deepcopy(self.raw['dongs'][0]);row[key]='unused'
            with self.subTest(key=key),self.assertRaises(ValueError):validate_regions([row])

    def test_name_district_duplicate_and_missing_dong_are_rejected(self):
        row=deepcopy(self.raw['dongs'][0])
        for key,value in (('region_name','잘못된동'),('sigungu_code','11680')):
            wrong=deepcopy(row);wrong[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_regions([wrong])
        with self.assertRaises(ValueError):validate_regions([row,row])
        with self.assertRaises(ValueError):validate_regions(self.raw['dongs'][:-1],require_all=True)

    def test_backend_roundtrip_and_legacy_region_rejection(self):
        backend=convert(self.scores,self.master)
        self.assertTrue(validate_backend(backend,self.scores,self.master))
        backend['items'][0]['region']['parent_region_code']='11110'
        with self.assertRaises(ValueError):validate_backend(backend,self.scores,self.master)

    def test_all_non_geography_results_match_pre_migration_fingerprint(self):
        obj=deepcopy(self.saved)
        for item in obj['items']: item.pop('region')
        actual=hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(actual,PRESERVED_STATISTICS_SHA256)

    def test_saved_result_reproduces_from_packaged_statistics(self):
        self.assertEqual(verify_saved(),self.saved)
        self.assertEqual(build_payload(),self.saved)

    def test_validation_csv_matches_json_row_by_row(self):
        with (ROOT/'validation/02_427행정동_점수등급.csv').open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),427)
        expected={i['region']['region_code']:i for i in self.saved['items']}
        self.assertEqual({r['region_code'] for r in rows},set(expected))
        for row in rows:
            item=expected[row['region_code']]
            self.assertNotIn('region_short_code',row)
            self.assertEqual(row['sigungu_code'],item['region']['sigungu_code'])
            self.assertEqual(float(row['safety_score']),item['scores']['safety'])
            self.assertEqual(int(row['grade']),item['metadata']['safety']['grade'])

    def test_fixed_grades_and_forecast_exclusion(self):
        distribution={g:sum(i['metadata']['safety']['grade']==g for i in self.saved['items']) for g in range(1,6)}
        self.assertEqual(distribution,{1:49,2:98,3:80,4:167,5:33})
        self.assertEqual(forbidden_paths(self.saved),[])
        for item in self.saved['items']:
            self.assertTrue(all(v is None for k,v in item['scores'].items() if k!='safety'))

    def test_grade_boundaries_missing_and_invalid(self):
        for score,grade in ((0,5),(19.999999,5),(20,4),(40,3),(60,2),(80,1),(100,1),(None,None)):
            self.assertEqual(grade_from_score(score),grade)
        for value in (True,-1,101,float('nan'),float('inf'),'50'):
            with self.subTest(value=value),self.assertRaises(ValueError):grade_from_score(value)

    def test_rank_ties_and_direction_and_weights(self):
        values={'a':1,'b':2,'c':2,'d':3}
        self.assertEqual(relative_scores(values),{'a':0.0,'b':50.0,'c':50.0,'d':100.0})
        self.assertEqual(relative_scores(values,False),{'a':100.0,'b':50.0,'c':50.0,'d':0.0})
        self.assertEqual(combine({'crime':100,'cctv':0,'police':0}),80)
        self.assertIsNone(combine({'crime':None,'cctv':0,'police':0}))

    def test_invalid_population_and_jurisdiction_cannot_be_scored(self):
        raw=deepcopy(self.raw);raw['regions'][0]['population_monthly_2025'][0]=0
        with self.assertRaises(ValueError):score_safety(raw)
        raw=deepcopy(self.raw);raw['dongs'][0]['jurisdiction_id']='UNKNOWN'
        with self.assertRaises(ValueError):score_safety(raw)

if __name__=='__main__':
    unittest.main(verbosity=2)
