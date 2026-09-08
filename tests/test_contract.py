"""
S1 统一契约层测试：claims / mechanisms / actions / coverage_audit / 依赖传播。

守住的是 S1 的退出条件：
  - 从一条行动可以追溯到机制、断言和摘录
  - 撤销载荷性断言能够标记依赖判断
  - 行动卡不得超出契约声明的用户权限
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.tools.evidence_lineage import (          # noqa: E402
    affected_by_contradiction, claim_support, normalize_url, source_families,
)
from agent.validation import validate_contract      # noqa: E402


def _src(url, role='supports', **kw):
    s = {'url': url, 'role': role, 'tier': 2, 'directness': 'direct'}
    s.update(kw)
    return s


def _base():
    """一份通过全部契约校验的最小 analysis。"""
    return {
        'completeness': 'partial',
        'output_mode': 'full',
        'dimension_scores': {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4, 'D7': 3},
        'analysis_contract': {'objective': '决定是否推进试点', 'user_authority': 'can_act',
                              'as_of': '2026-09-08'},
        'claims': [{
            'id': 'C1', 'statement': '扣奖规则于 5 月生效', 'status': 'supported',
            'loads': ['M1'],
            'sources': [_src('https://gov.example/rule', source_family='rule-notice'),
                        _src('https://news.example/report', source_family='indep-report')],
        }],
        'mechanisms': [{
            'id': 'M1', 'explains': '严重事故上报数下降但投诉未降',
            'chain': '扣奖规则 → 一线降级上报 → 管理层低估风险 → 修复资源不足',
            'alternatives': ['事故确实减少，投诉存在滞后', '事故定义变化，前后不可比'],
            'discriminating_predictions': ['同口径独立监控的故障数不随自报数下降'],
            'failure_conditions': ['统一口径后差异消失'],
            'supporting_claims': ['C1'],
            'causal_level': 'L1_explanatory',
        }],
        'actions': [{
            'id': 'A1', 'action': '在可比小组试行独立上报渠道',
            'mechanism_id': 'M1', 'executor_role': 'user_direct',
            'first_step': '固定事故定义与抽样审计方法，选定对照组',
            'verification': {'baseline': '试点前 8 周自报与独立监测差距',
                             'outcome_metric': '独立监测与自报事件的差距',
                             'observation_window': '一个业务周期'},
            'guardrails': {'stop_conditions': ['一线工作量增幅 >15% 即暂停'],
                           'rollback': '关闭独立渠道，恢复原流程'},
            'decision_triggers': ['口径统一后差异消失 → 撤下"隐瞒导致"的强判断'],
        }],
    }


# ── 追溯链 ──

def test_full_chain_passes():
    errors, _ = validate_contract(_base())
    assert errors == []


def test_action_without_mechanism_is_rejected():
    a = _base()
    del a['actions'][0]['mechanism_id']
    errors, _ = validate_contract(a)
    assert any('mechanism_id' in e for e in errors)


def test_action_referencing_unknown_mechanism_is_rejected():
    a = _base()
    a['actions'][0]['mechanism_id'] = 'M99'
    errors, _ = validate_contract(a)
    assert any('M99' in e for e in errors)


def test_action_without_verification_or_stop_condition_is_rejected():
    a = _base()
    del a['actions'][0]['verification']
    del a['actions'][0]['guardrails']
    errors, _ = validate_contract(a)
    assert any('outcome_metric' in e for e in errors)
    assert any('stop_conditions' in e for e in errors)


def test_mechanism_without_alternative_is_rejected():
    a = _base()
    a['mechanisms'][0]['alternatives'] = []
    errors, _ = validate_contract(a)
    assert any('alternatives' in e for e in errors)


def test_l3_claim_without_identification_is_rejected():
    a = _base()
    a['mechanisms'][0]['causal_level'] = 'L3_effect_estimate'
    errors, _ = validate_contract(a)
    assert any('L3_effect_estimate' in e and 'estimand' in e for e in errors)


def test_l2_claim_without_parameters_is_rejected():
    a = _base()
    a['mechanisms'][0]['causal_level'] = 'L2_parameterised'
    errors, _ = validate_contract(a)
    assert any('L2_parameterised' in e for e in errors)


def test_causal_readiness_lists_what_is_missing():
    from agent.validation import causal_readiness
    r = causal_readiness(_base()['mechanisms'][0])
    assert r['ready_for'] == 'L1_explanatory'
    assert 'time_step' in r['missing_for_L2']
    assert 'estimand' in r['missing_for_L3']
    assert r['overclaimed'] is False


def test_fully_specified_mechanism_may_claim_l3():
    a = _base()
    m = a['mechanisms'][0]
    m.update({
        'causal_level': 'L3_effect_estimate',
        'variables': [{'name': '上报延迟', 'unit_or_proxy': '小时'}],
        'time_step': '周', 'initial_values': {'上报延迟': 12}, 'delays': {'上报→修复': '2 周'},
        'parameter_ranges': {'扣奖弹性': [0.1, 0.4]}, 'boundary_conditions': '仅限该事业部',
        'sensitivity_plan': '对扣奖弹性做区间扫描',
        'estimand': '试点组与对照组的严重事故率差', 'identification': '可比小组 + 前后对照',
        'data_source': '内部工单系统', 'refutation_plan': '安慰剂期检验',
        'applicable_population': '该事业部一线班组', 'applicable_period': '2026H2',
    })
    errors, _ = validate_contract(a)
    assert not any('L3' in e for e in errors)


# ── 权限边界 ──

def test_action_cannot_exceed_declared_authority():
    a = _base()
    a['analysis_contract']['user_authority'] = 'can_only_monitor'
    errors, _ = validate_contract(a)
    assert any('超出契约声明的用户权限' in e for e in errors)


def test_monitor_only_reader_gets_monitoring_action():
    a = _base()
    a['analysis_contract']['user_authority'] = 'can_only_monitor'
    a['actions'][0]['executor_role'] = 'user_monitor_only'
    errors, _ = validate_contract(a)
    assert errors == []


# ── 反证传播 ──

def test_contradicted_claim_forces_needs_review_on_dependents():
    a = _base()
    a['claims'][0]['status'] = 'contradicted'
    errors, _ = validate_contract(a)
    assert any('needs_review' in e and 'M1' in e for e in errors)


def test_marking_needs_review_satisfies_propagation():
    a = _base()
    a['claims'][0]['status'] = 'contradicted'
    a['mechanisms'][0]['needs_review'] = True
    errors, _ = validate_contract(a)
    assert not any('needs_review' in e for e in errors)


def test_unreachable_source_does_not_propagate_as_refutation():
    # 链接打不开 ≠ 断言为假
    a = _base()
    a['claims'][0]['sources'][0]['reachability'] = 'unavailable'
    prop = affected_by_contradiction(a)
    assert prop['needs_review'] == {}


def test_unresolved_claim_does_not_propagate():
    a = _base()
    a['claims'][0]['status'] = 'unresolved'
    assert affected_by_contradiction(a)['needs_review'] == {}


def test_dangling_loads_are_reported():
    a = _base()
    a['claims'][0]['loads'] = ['M404']
    _, warnings = validate_contract(a)
    assert any('loads' in w for w in warnings)


# ── 来源家族 ──

def test_reprints_collapse_to_one_family():
    srcs = [_src(f'https://outlet{i}.example/story', source_family='gov-press-0517')
            for i in range(4)]
    fam = source_families(srcs)
    assert fam['independent_count'] == 1
    assert fam['collapsed'][0]['members'] == 4


def test_tracking_params_and_www_do_not_split_a_family():
    fam = source_families([
        _src('https://www.Example.com/a/?utm_source=x'),
        _src('https://example.com/a'),
    ])
    assert fam['independent_count'] == 1


def test_normalize_url_keeps_meaningful_query():
    assert normalize_url('https://e.com/p?id=7&utm_campaign=z') == 'https://e.com/p?id=7'


def test_background_link_is_not_support():
    c = {'id': 'C9', 'status': 'supported',
         'sources': [_src('https://e.com/bg', role='background')]}
    prof = claim_support(c)
    assert prof['supporting'] == 0
    assert any('背景链接' in n for n in prof['notes'])


def test_single_family_supported_claim_is_flagged():
    a = _base()
    a['claims'][0]['sources'] = [_src('https://gov.example/rule', source_family='rule-notice')]
    _, warnings = validate_contract(a)
    assert any('独立来源家族' in w for w in warnings)


def test_supported_status_requires_a_supporting_source():
    a = _base()
    for s in a['claims'][0]['sources']:
        s['role'] = 'background'
    errors, _ = validate_contract(a)
    assert any('supported' in e for e in errors)


# ── 覆盖审计 ──

def test_missing_coverage_audit_warns():
    _, warnings = validate_contract(_base())
    assert any('coverage_audit' in w for w in warnings)


def test_decision_relevant_unknown_must_surface():
    a = _base()
    a['coverage_audit'] = [{'element_group': 'information_and_measurement', 'status': 'unknown',
                            'evidence_or_reason': '未拿到上报规则版本',
                            'affects_current_decision': True}]
    _, warnings = validate_contract(a)
    assert any('实质影响' in w for w in warnings)


def test_illegal_element_group_is_rejected():
    a = _base()
    a['coverage_audit'] = [{'element_group': '随便编的组', 'status': 'covered',
                            'evidence_or_reason': 'x'}]
    errors, _ = validate_contract(a)
    assert any('element_group' in e for e in errors)


# ── id 契约 ──

def test_duplicate_ids_rejected():
    a = _base()
    a['mechanisms'].append(dict(a['mechanisms'][0]))
    errors, _ = validate_contract(a)
    assert any('重复' in e for e in errors)


def test_wrong_id_prefix_rejected():
    a = _base()
    a['actions'][0]['id'] = 'X1'
    errors, _ = validate_contract(a)
    assert any('`A` 开头' in e for e in errors)


# ── 完整性 ──

def test_cannot_declare_complete_without_process_evidence():
    from agent.store.db import validate_analysis
    a = _base()
    a['completeness'] = 'complete_with_uncertainty'
    assert any('complete_with_uncertainty' in e for e in validate_analysis(a))


def test_draft_can_still_be_saved(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    a = _base()
    a['completeness'] = 'draft'
    path = db.save_analysis('T', 'public_company', a, date_str='20260101')
    assert Path(path).exists()


def test_system_metadata_cannot_be_overridden_by_payload(tmp_path, monkeypatch):
    import json
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    a = _base()
    a['analysis_date'] = '19700101'
    a['system_name'] = '冒名系统'
    path = db.save_analysis('真实系统', 'public_company', a, date_str='20260101')
    saved = json.loads(Path(path).read_text())
    assert saved['system_name'] == '真实系统'
    assert saved['analysis_date'] == '20260101'
