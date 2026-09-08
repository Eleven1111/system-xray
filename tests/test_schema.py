"""
diagnostic-schema.json 的契约测试。

重点守住 S0 修复的那个静默失效：Draft 7 下 `$ref` 的**同级关键字被忽略**，
维度专属枚举与 `definitions/dimension` 的 required 因此从未真正生效——
一个非法枚举值可以一路通过校验。改用 allOf 组合后，本文件用"应当报错"的实例把它钉住。
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

jsonschema = pytest.importorskip('jsonschema')

SCHEMA = json.loads((ROOT / 'references' / 'diagnostic-schema.json').read_text(encoding='utf-8'))

_DIMS = ['d1_boundary', 'd2_incentive', 'd3_information', 'd4_temporal',
         'd5_legitimacy', 'd6_coupling', 'd7_power']


def _errors(instance):
    return [e.message for e in jsonschema.Draft7Validator(SCHEMA).iter_errors(instance)]


def _minimal():
    return {
        'completeness': 'partial',
        'metadata': {
            'system_name': 'X', 'system_type': 'other', 'analysis_date': '2026-01-01',
            'analyst_confidence': 'medium', 'information_sources': [],
        },
        'cartography': {},
        'dimensions': {d: {'score': 3, 'trajectory': 'stable',
                           'key_findings': [], 'evidence': []} for d in _DIMS},
        'cross_dimensional': {}, 'risk_nodes': [], 'scenarios': [],
        'prescriptions': [], 'predictions': [],
    }


def test_schema_itself_is_valid_draft7():
    jsonschema.Draft7Validator.check_schema(SCHEMA)


def test_minimal_instance_passes():
    assert _errors(_minimal()) == []


def test_dimension_specific_enum_is_enforced():
    # 回归：Draft 7 的 $ref 同级扩展曾让这个非法值静默通过
    a = _minimal()
    a['dimensions']['d1_boundary']['soft_constraint_health'] = 'NOT_VALID'
    assert any('NOT_VALID' in e for e in _errors(a))


def test_dimension_required_fields_are_enforced():
    a = _minimal()
    del a['dimensions']['d3_information']['score']
    assert any('score' in e for e in _errors(a))


def test_score_accepts_unknown_and_not_applicable():
    a = _minimal()
    a['dimensions']['d4_temporal']['score'] = 'unknown'
    a['dimensions']['d5_legitimacy']['score'] = 'not_applicable'
    assert _errors(a) == []


def test_score_rejects_free_text_placeholder():
    a = _minimal()
    a['dimensions']['d4_temporal']['score'] = '大概三分'
    assert _errors(a)


def test_completeness_is_required_and_enumerated():
    a = _minimal()
    del a['completeness']
    assert any('completeness' in e for e in _errors(a))
    a['completeness'] = 'done'
    assert any('done' in e for e in _errors(a))


def test_prediction_requires_event_type():
    a = _minimal()
    a['predictions'] = [{
        'prediction': 'x', 'falsification_condition': 'y', 'time_horizon': '2026-12-31',
        'confidence': 0.6, 'dimension_link': 'D2', 'source_step': 'dimension_analysis',
    }]
    assert any('event_type' in e for e in _errors(a))


def test_scenario_probability_may_be_null():
    # 深不确定时"给不出概率"是合法输出，不再强制概率分布
    a = _minimal()
    a['scenarios'] = [{'name': 's', 'description': 'd', 'key_conditions': [],
                       'probability': None}]
    assert _errors(a) == []


def test_source_tier_capped_at_three():
    a = _minimal()
    a['metadata']['information_sources'] = [{'source': 's', 'tier': 4}]
    assert _errors(a)
