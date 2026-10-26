"""Narrative contract regression tests through the real HTTP parser and scoring path."""
import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest

from services.ai_recommendation.llm_service import OpenRouterClient
from services.ai_recommendation.snapshot_llm import generate_snapshot_explanation
from services.ai_recommendation.snapshot_service import load_snapshot_dataset, recommend_snapshots

ADVANTAGES = '중계4동에 연결된 자치구 기준 참고점수인 생활 쾌적도는 70.8점으로 선택 영역 안에서 상대적 강점입니다. 행정동의 직접 관측값은 아닙니다.'
DISADVANTAGES = '경제 활력도는 17.3점으로 선택 영역 안에서 상대적으로 낮습니다. 제공된 점수만으로 실제 경제 수준이나 원인을 단정할 수는 없습니다.'


@pytest.fixture(scope='module')
def dataset():
    data = load_snapshot_dataset(Path(__file__).resolve().parents[2] / 'ai_modeling',
        target_month='2026-10', domains=['economy','energy','comfort','health','safety'],
        allow_provisional=True, allow_context_scores=True)
    return data.model_copy(update={'regions':[r for r in data.regions if r.region_code == '350624']})


def plan():
    return {'items':[{'region_code':'350624', 'strength_domains':['comfort'],
        'weakness_domains':['economy'], 'evidence_ids':[],
        'advantages':ADVANTAGES, 'disadvantages':DISADVANTAGES}]}


def invoke(rec, output, observed=None, status=200):
    def handler(request):
        if observed is not None:
            observed.append(json.loads(json.loads(request.content)['messages'][1]['content']))
        return httpx.Response(status, json={'choices':[{'finish_reason':'tool_calls','message':{
            'tool_calls':[{'type':'function','function':{'name':'ExplanationPlan','arguments':json.dumps(output)}}]}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenRouterClient(api_key='test-secret',model='nvidia/nemotron-3-ultra-550b-a55b:free',http_client=http,max_retries=0)
            return await generate_snapshot_explanation(rec,client)
    return asyncio.run(run())


def test_llm_prose_reaches_output_without_replacing_it_with_templates(dataset):
    rec = recommend_snapshots(dataset,weights=dict.fromkeys(dataset.available_domains,20),top_k=1)
    before = rec.model_dump_json()
    result = invoke(rec,plan())
    assert result.generation_status == 'llm'
    assert result.items[0].advantages == ADVANTAGES
    assert result.items[0].disadvantages == DISADVANTAGES
    assert result.items[0].personalized_score_100 == pytest.approx(47.37851)
    assert result.items[0].category_scores == rec.items[0].category_scores
    assert result.items[0].category_scores.model_dump() == pytest.approx(dict(economy=17.3195,energy=41.8344,comfort=70.8,health=39.8553,safety=67.0833),abs=.00005)
    assert result.items[0].domain_metadata == rec.items[0].domain_metadata
    assert any('운영 승인' in s for s in result.items[0].limitations)
    assert any('자치구' in s for s in result.items[0].limitations)
    assert result.items[0].citations == []
    assert result.diagnostics == []
    assert rec.model_dump_json() == before


def test_changed_weights_region_name_and_provenance_reach_model(dataset):
    seen = []
    rec = recommend_snapshots(dataset,weights=dict(economy=10,energy=10,comfort=40,health=10,safety=30),top_k=1)
    invoke(rec,plan(),seen)
    payload = seen[0]['recommendation']
    assert payload['normalized_weights'] == dict(economy=.1,energy=.1,comfort=.4,health=.1,safety=.3)
    assert payload['items'][0]['region_name'] == '중계4동'
    assert payload['items'][0]['domain_metadata']['comfort']['is_dong_observation'] is False
    assert payload['items'][0]['domain_metadata']['comfort']['production_approved'] is False


@pytest.mark.parametrize('field,value',[
    ('region_code','999999'), ('strength_domains',['economy']), ('weakness_domains',['comfort']),
    ('strength_domains',['comfort','comfort']), ('evidence_ids',['invented']),
    ('advantages',''), ('advantages','   '), ('advantages',None), ('advantages','x'*1801),
    ('advantages','생활 쾌적도는 99.9점으로 높습니다.'),
    ('advantages','생활 쾌적도는 17.3점으로 높습니다.'),
    ('advantages','중계4동은 공기가 깨끗하고 범죄가 없어 안전합니다.'),
    ('advantages','생활 쾌적도는 70.8점으로 행정동에서 직접 관측한 실측값입니다.'),
    ('advantages','생활 쾌적도는 70.8점입니다. https://invented.example 에 따르면 좋습니다.'),
    ('advantages','자치구 기준 생활 쾌적도는 70.8점입니다. 서울시 보고서에 따르면 살기 좋습니다.'),
])
def test_invalid_narrative_falls_back_without_leaking_it(dataset,field,value):
    rec = recommend_snapshots(dataset,weights=dict.fromkeys(dataset.available_domains,20),top_k=1)
    output = plan(); output['items'][0][field] = value
    result = invoke(rec,output)
    assert result.generation_status == 'fallback'
    assert result.diagnostics[0]['code'] == 'invalid_output'
    assert result.items[0].personalized_score_100 == pytest.approx(47.37851)
    assert result.items[0].region_code == '350624'
    assert result.items[0].advantages != value
    assert 'test-secret' not in result.model_dump_json()


def test_missing_narrative_and_duplicate_regions_do_not_count_as_llm_success(dataset):
    rec = recommend_snapshots(dataset,weights=dict.fromkeys(dataset.available_domains,20),top_k=1)
    missing = plan(); del missing['items'][0]['advantages']
    duplicate = plan(); duplicate['items'].append(copy.deepcopy(duplicate['items'][0]))
    for output in (missing,duplicate):
        assert invoke(rec,output).generation_status == 'fallback'


def test_provider_failure_preserves_existing_fallback(dataset):
    rec = recommend_snapshots(dataset,weights=dict.fromkeys(dataset.available_domains,20),top_k=1)
    offline = asyncio.run(generate_snapshot_explanation(rec))
    failed = invoke(rec,{},status=401)
    assert failed.generation_status == 'fallback'
    assert failed.items == offline.items
    assert failed.diagnostics[0]['code'] == 'authentication'


@pytest.mark.parametrize('caveat',[
    '운영 승인된 데이터가 아닙니다.',
    '공기가 깨끗하다고 단정할 수 없습니다.',
    '범죄가 없다고 볼 수는 없습니다.',
])
def test_negative_limitations_are_not_mistaken_for_positive_claims(dataset,caveat):
    rec = recommend_snapshots(dataset,weights=dict.fromkeys(dataset.available_domains,20),top_k=1)
    output=plan(); output['items'][0]['advantages'] += ' '+caveat
    result=invoke(rec,output)
    assert result.generation_status=='llm'
    assert result.items[0].advantages==output['items'][0]['advantages']


def test_separate_negative_sentence_cannot_hide_positive_fabrication(dataset):
    rec = recommend_snapshots(dataset,weights=dict.fromkeys(dataset.available_domains,20),top_k=1)
    output=plan(); output['items'][0]['advantages'] += ' 범죄가 없습니다. 운영 승인된 데이터는 아닙니다.'
    assert invoke(rec,output).generation_status=='fallback'


def test_single_domain_must_not_claim_relative_strength(dataset):
    rec = recommend_snapshots(dataset,weights={'economy':1},top_k=1)
    output=plan(); output['items'][0].update(strength_domains=['economy'],weakness_domains=['economy'],
        advantages='경제 활력도는 17.3점으로 상대적 강점입니다.',disadvantages='선택 영역이 하나라 비교할 수 없습니다.')
    assert invoke(rec,output).generation_status=='fallback'
