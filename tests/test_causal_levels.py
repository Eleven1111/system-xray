"""
S4 能力分层测试：L2 参数化局部模型 / L3 效果估计 / 入口门。

守住的是方案 §6.2 的核心约束：
  - 条件不满足 → 拒绝出数，停在 L1，而不是"先跑了再补条件"
  - L2 的关键输出是**稳健性判定**，不是曲线
  - L3 的数字永远与识别假设、适用群体、时间范围、反驳结果一起出现
  - 后端不可用时如实说明，不静默降级后假装用了它
"""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.tools.causal_adapter import (                     # noqa: E402
    check_data_shape, detect_backends, estimate_effect,
)
from agent.tools.stock_flow import (                          # noqa: E402
    run_gated, run_with_sensitivity, simulate, validate_model,
)
from agent.validation import causal_readiness                 # noqa: E402


# ── 入口门 ─────────────────────────────────────────────────────────────────

def _l2_ready():
    return {'id': 'M1', 'explains': 'x', 'chain': 'y',
            'variables': [{'name': '积压', 'unit_or_proxy': '单'}],
            'time_step': '天', 'initial_values': {'积压': 100}, 'delays': {'处理': 3},
            'parameter_ranges': {'处理系数': [0.1, 0.3]}, 'boundary_conditions': '仅该产线',
            'sensitivity_plan': '区间扫描'}


def _l3_ready():
    return {'id': 'M2', 'explains': 'x', 'chain': 'y',
            'estimand': '试点组与对照组事故率差', 'identification': '可比小组前后对照',
            'data_source': '工单系统', 'refutation_plan': '安慰剂 + 留一',
            'applicable_population': '一线班组', 'applicable_period': '2026H2'}


def test_l2_and_l3_are_parallel_not_a_ladder():
    # 效果估计不需要先有参数化仿真模型；反之亦然
    r3 = causal_readiness(_l3_ready())
    assert r3['ready_for_L3'] is True
    assert r3['ready_for_L2'] is False
    r2 = causal_readiness(_l2_ready())
    assert r2['ready_for_L2'] is True
    assert r2['ready_for_L3'] is False


def test_explicitly_empty_field_counts_as_declared():
    # delays={} 表示"本机制无延迟"，是交代过了，不是没交代
    m = _l2_ready(); m['delays'] = {}
    assert causal_readiness(m)['ready_for_L2'] is True


def test_missing_field_is_not_declared():
    m = _l2_ready(); del m['delays']
    r = causal_readiness(m)
    assert r['ready_for_L2'] is False
    assert 'delays' in r['missing_for_L2']


# ── L2 存量—流量 ────────────────────────────────────────────────────────────

def _model(coefficient=0.2, ranges=None):
    return {
        'stocks': {'backlog': 100.0}, 'time_step': 1.0, 'horizon': 20,
        'flows': [
            {'name': 'inflow', 'to': 'backlog', 'rate': {'kind': 'const', 'value': 10.0}},
            {'name': 'outflow', 'from': 'backlog',
             'rate': {'kind': 'proportional_to', 'stock': 'backlog',
                      'coefficient': coefficient}, 'delay': 3},
        ],
        'parameter_ranges': ranges if ranges is not None else {'outflow.coefficient': [0.08, 0.30]},
    }


def test_model_validation_catches_missing_time_step():
    m = _model(); del m['time_step']
    assert any('time_step' in e for e in validate_model(m))


def test_model_validation_rejects_unknown_stock_reference():
    m = _model()
    m['flows'][0]['to'] = 'nonexistent'
    assert any('nonexistent' in e for e in validate_model(m))


def test_simulation_reaches_expected_equilibrium():
    # 常量流入 10、比例流出 0.2 → 平衡态 50
    m = _model(coefficient=0.2)
    m['horizon'] = 400
    assert abs(simulate(m)['final']['backlog'] - 50.0) < 0.5


def test_stock_never_goes_negative():
    m = {'stocks': {'buffer': 5.0}, 'time_step': 1.0, 'horizon': 10,
         'flows': [{'name': 'drain', 'from': 'buffer',
                    'rate': {'kind': 'const', 'value': 100.0}}],
         'parameter_ranges': {}}
    assert min(simulate(m)['series']['buffer']) >= 0.0


def test_multiple_outflows_share_one_source_stock_without_creating_resource():
    # 回归：原实现逐条按初始库存截断，10 的库存可同时流出 8 + 8。
    m = {'stocks': {'source': 10.0, 'left': 0.0, 'right': 0.0},
         'time_step': 1.0, 'horizon': 1.0,
         'flows': [
             {'name': 'to_left', 'from': 'source', 'to': 'left',
              'rate': {'kind': 'const', 'value': 8.0}},
             {'name': 'to_right', 'from': 'source', 'to': 'right',
              'rate': {'kind': 'const', 'value': 8.0}},
         ]}
    result = simulate(m)
    assert result['final'] == {'source': 0.0, 'left': 5.0, 'right': 5.0}
    assert sum(result['final'].values()) == 10.0


def test_wide_parameter_range_flips_verdict_and_is_reported():
    r = run_with_sensitivity(_model(), {'stock': 'backlog', 'test': 'above', 'threshold': 50})
    assert r['robust'] is False
    assert 'outflow.coefficient' in r['flipping_parameters']
    assert '不稳健' in r['conclusion']


def test_narrow_defensible_range_is_robust():
    m = _model(ranges={'outflow.coefficient': [0.08, 0.12]})
    r = run_with_sensitivity(m, {'stock': 'backlog', 'test': 'above', 'threshold': 50})
    assert r['robust'] is True


def test_one_at_a_time_scan_does_not_claim_full_interval_robustness():
    m = {'stocks': {'x': 0.0}, 'time_step': 1.0, 'horizon': 1.0,
         'flows': [
             {'name': f'f{i}', 'to': 'x', 'rate': {'kind': 'const', 'value': 1.0}}
             for i in range(4)
         ],
         'parameter_ranges': {f'f{i}.value': [0.0, 2.0] for i in range(4)}}
    result = run_with_sensitivity(m, {'stock': 'x', 'test': 'below', 'threshold': 6.0})
    assert result['coverage'] == 'one_at_a_time'
    assert result['robust'] is None
    assert '未证明' in result['conclusion']


def test_baseline_runs_at_range_midpoint_not_declared_point():
    # 回归：基线曾跑在模型写死的点值上，点值落在区间外时会制造伪翻转
    m = _model(coefficient=0.2, ranges={'outflow.coefficient': [0.08, 0.12]})
    r = run_with_sensitivity(m, {'stock': 'backlog', 'test': 'above', 'threshold': 50})
    assert r['baseline_overrides']['outflow.coefficient'] == 0.1
    assert any('不在声明区间' in w for w in r['spec_warnings'])


def test_no_parameter_ranges_refuses_to_conclude():
    m = _model(ranges={})
    r = run_with_sensitivity(m, {'stock': 'backlog', 'test': 'above', 'threshold': 50})
    assert r['errors'] and 'parameter_ranges' in r['errors'][0]


def test_l2_gate_blocks_underspecified_mechanism():
    r = run_gated({'id': 'M9', 'explains': 'x'}, _model(),
                  {'stock': 'backlog', 'test': 'above', 'threshold': 50})
    assert r['errors'] and 'L2' in r['errors'][0]


def test_l2_gate_allows_fully_specified_mechanism():
    r = run_gated(_l2_ready(), _model(),
                  {'stock': 'backlog', 'test': 'above', 'threshold': 50})
    assert not r.get('errors')
    assert 'robust' in r


# ── L3 效果估计 ─────────────────────────────────────────────────────────────

def _panel(effect=-4.0, n_units=20, noise=0.0, seed=7):
    rng = random.Random(seed)
    rows = []
    for u in range(1, n_units + 1):
        g = 'treated' if u <= n_units // 2 else 'control'
        base = 20 + rng.gauss(0, noise) if noise else 20 + u
        rows.append({'unit': f'U{u}', 'group': g, 'period': 'pre', 'outcome': base})
        delta = effect if g == 'treated' else 0.0
        rows.append({'unit': f'U{u}', 'group': g, 'period': 'post',
                     'outcome': base + delta + (rng.gauss(0, noise) if noise else 0.0)})
    return rows


def test_l3_gate_blocks_mechanism_without_identification():
    r = estimate_effect({'id': 'M9', 'explains': 'x'},
                        {'strategy': 'difference_in_differences', 'data': _panel()})
    assert r['errors'] and 'L3' in r['errors'][0]


def test_did_recovers_known_effect():
    r = estimate_effect(_l3_ready(),
                        {'strategy': 'difference_in_differences', 'data': _panel(effect=-4.0)})
    assert abs(r['estimate'] - (-4.0)) < 0.01
    assert r['refutations']['leave_one_out']['sign_stable'] is True


def test_pure_noise_is_flagged_as_indistinguishable():
    rng = random.Random(1)
    noise = [{'unit': f'N{u}', 'group': 'treated' if u <= 4 else 'control',
              'period': p, 'outcome': rng.gauss(10, 3)}
             for u in range(1, 9) for p in ('pre', 'post')]
    r = estimate_effect(_l3_ready(), {'strategy': 'difference_in_differences', 'data': noise})
    assert r['refutations']['placebo']['fraction'] > 0.1
    assert any('噪声' in f for f in r['flags'])


def test_missing_control_group_is_rejected():
    treated_only = [d for d in _panel() if d['group'] == 'treated']
    r = estimate_effect(_l3_ready(),
                        {'strategy': 'difference_in_differences', 'data': treated_only})
    assert r['errors'] and any('control' in e for e in r['errors'])


def test_unsupported_strategy_is_refused_not_approximated():
    assert any('只支持' in e for e in check_data_shape(_panel(), 'instrumental_variable'))


def test_estimate_always_ships_with_assumptions_and_scope():
    r = estimate_effect(_l3_ready(), {'strategy': 'difference_in_differences', 'data': _panel()})
    assert r['applicable_population'] and r['applicable_period']
    assert r['identification'] and r['assumptions_are_the_analysts']


def test_backend_absence_is_reported_not_hidden():
    backends = detect_backends()
    assert 'dowhy' in backends and 'available' in backends['dowhy']
    r = estimate_effect(_l3_ready(), {'strategy': 'difference_in_differences', 'data': _panel()})
    if not backends['dowhy']['available']:
        assert r['backend_used'] == 'builtin_did'
        assert any('没有执行 DoWhy' in f for f in r['flags'])


def test_installed_dowhy_is_never_reported_as_used(monkeypatch):
    import agent.tools.causal_adapter as adapter
    real = adapter.detect_backends
    monkeypatch.setattr(adapter, 'detect_backends', lambda: {
        **real(), 'dowhy': {'available': True, 'version': 'test'}
    })
    r = estimate_effect(_l3_ready(), {'strategy': 'difference_in_differences', 'data': _panel()})
    assert r['backend_used'] == 'builtin_did'
    assert any('没有执行 DoWhy' in f for f in r['flags'])
