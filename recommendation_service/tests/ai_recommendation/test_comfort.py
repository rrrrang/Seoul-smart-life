"""District comfort context is never presented as observed dong data."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import pytest
from services.ai_recommendation.snapshot_service import load_snapshot_dataset, recommend_snapshots
from services.ai_recommendation.snapshot_llm import generate_snapshot_explanation

ROOT=Path(__file__).resolve().parents[2]
MODELING=ROOT/'ai_modeling'
if not (MODELING/'economy/results/economy_scores.json').exists():
    MODELING=ROOT/'.publish-repo/ai_modeling'
DOMAINS=['economy','energy','comfort','health','safety']


def load(root=MODELING, domains=DOMAINS):
    return load_snapshot_dataset(root,target_month='2026-10',domains=domains,
        allow_provisional=True,allow_context_scores=True)


def test_comfort_preserves_sigungu_period_relative_score_and_imputation():
    data=load()
    assert len(data.regions)==427
    assert data.available_domains==DOMAINS
    original=json.loads((MODELING/'comfort/results/comfort_scores.json').read_text(encoding='utf-8-sig'))
    districts={r['행정구코드']:r for r in original}
    for row in data.regions:
        assert row.category_scores.comfort==districts[row.sigungu_code]['점수']
        assert len(row.region_code)==6 and len(row.sigungu_code)==5
        evidence=row.domain_metadata['comfort']
        assert evidence.original_spatial_units==['sigungu']
        assert evidence.source_periods=={'evaluation_month':'2026-09','input_coverage':'2024-01~2026-09'}
        assert evidence.details['is_dong_observation'] is False
        assert evidence.details['score_mode']=='monthly_sigungu_relative'
        assert evidence.production_approved is False
        assert evidence.reference_years==[2024,2026]
    imputed=[r for r in data.regions if r.sigungu_code=='11410'][0]
    assert imputed.domain_metadata['comfort'].details['row_context']['temp_imputed']=='True'
    assert 'CONTEXT_ASSIGNED_COMFORT' in data.warnings
    assert 'COMFORT_PERIOD_DIFFERS_FROM_TARGET_MONTH' in data.warnings


def test_comfort_requires_explicit_context_opt_in():
    with pytest.raises(ValueError,match='context'):
        load_snapshot_dataset(MODELING,target_month='2026-10',domains=['comfort'],allow_provisional=True)


def test_five_domain_scores_and_independent_slider_scaling():
    dataset=load()
    low=recommend_snapshots(dataset,weights=dict.fromkeys(DOMAINS,10))
    high=recommend_snapshots(dataset,weights=dict.fromkeys(DOMAINS,100))
    assert low.model_dump()==high.model_dump()
    assert high.selected_max_points==100 and high.unavailable_domains==[]
    assert list(high.normalized_weights.model_dump().values())==pytest.approx([.2]*5)
    for row in high.items:
        assert row.personalized_score_100==pytest.approx(sum(row.category_scores.model_dump().values())/5,abs=1e-6)
        assert row.five_domain_total_points is not None
    safety=recommend_snapshots(dataset,weights={'safety':100})
    assert safety.normalized_weights.safety==1
    assert all(r.personalized_score_100==pytest.approx(r.category_scores.safety,abs=1e-6) for r in safety.items)
    with pytest.raises(ValueError):recommend_snapshots(dataset,weights=dict.fromkeys(DOMAINS,0))
    with pytest.raises(ValueError):recommend_snapshots(dataset,weights={**dict.fromkeys(DOMAINS,1),'comfort':-1})


def test_comfort_only_ties_use_region_code_and_scores_do_not_change_with_weights():
    dataset=load(domains=['comfort'])
    rec=recommend_snapshots(dataset,weights={'comfort':100})
    best=max(r.category_scores.comfort for r in dataset.regions)
    expected=sorted(r.region_code for r in dataset.regions if r.category_scores.comfort==best)[:5]
    assert [r.region_code for r in rec.items]==expected
    assert all(r.strengths==[] and r.weaknesses==[] for r in rec.items)


def test_five_domain_explanation_uses_only_hundred_point_display():
    rec=recommend_snapshots(load(),weights=dict.fromkeys(DOMAINS,1))
    explanation=asyncio.run(generate_snapshot_explanation(rec))
    assert explanation.unavailable_domains==[]
    for row in explanation.items:
        assert '/20' not in row.advantages+row.disadvantages
        assert '/100' in row.advantages+row.disadvantages
        assert not any('쾌적 자료는 미제공' in x for x in row.limitations)
        assert any('자치구' in x and '쾌적' in x for x in row.limitations)


@pytest.fixture
def changed_comfort(tmp_path):
    for name in ['economy/model_config.json','economy/data/regions.csv','economy/validation/release_checks.json']:
        out=tmp_path/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(MODELING/name,out)
    shutil.copytree(MODELING/'comfort',tmp_path/'comfort')
    return tmp_path


def approve_import(root):
    p=root/'comfort/validation/import_receipt.json';receipt=json.loads(p.read_text(encoding='utf-8'))
    for name in receipt['files_sha256']:
        receipt['files_sha256'][name]=hashlib.sha256((root/'comfort'/name).read_bytes()).hexdigest()
    p.write_text(json.dumps(receipt),encoding='utf-8')


def test_changed_comfort_fails_import_integrity(changed_comfort):
    p=changed_comfort/'comfort/results/comfort_scores.json'
    rows=json.loads(p.read_text(encoding='utf-8'));rows[0]['점수']=99
    p.write_text(json.dumps(rows),encoding='utf-8')
    with pytest.raises(ValueError,match='integrity'):load(changed_comfort,['comfort'])


@pytest.mark.parametrize('corruption',['duplicate','missing','wrong_code','bad_score','score_mismatch','future_month','period','status'])
def test_invalid_comfort_contract_rejected_after_integrity_passes(changed_comfort,corruption):
    p=changed_comfort/'comfort/results/comfort_scores.json';rows=json.loads(p.read_text(encoding='utf-8'))
    if corruption=='duplicate':rows.append(rows[0])
    if corruption=='missing':rows.pop()
    if corruption=='wrong_code':rows[0]['행정구코드']='111100'
    if corruption=='bad_score':rows[0]['점수']=True
    if corruption=='score_mismatch':rows[0]['점수']=99
    if corruption=='future_month':rows[0]['평가기준월']='2027-01'
    if corruption=='period':rows[0]['사용자료_기준기간']='2025-01~2026-09'
    if corruption=='status':rows[0]['계산상태']='불가'
    p.write_text(json.dumps(rows),encoding='utf-8');approve_import(changed_comfort)
    with pytest.raises(ValueError):load(changed_comfort,['comfort'])


@pytest.mark.parametrize("bad", [[], False, 0, ""])
def test_falsy_invalid_min_scores_are_not_discarded(bad):
    with pytest.raises((ValueError, TypeError)):
        recommend_snapshots(load(), weights={"safety": 1}, min_scores=bad)
