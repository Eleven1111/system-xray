import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _e(src, dst, sign='+', strength='strong'):
    return {'from': src, 'to': dst, 'sign': sign, 'strength': strength}


# ── validate_edges ──

def test_valid_edges_pass():
    from agent.tools.causal_graph import validate_edges
    assert validate_edges([_e('D1', 'D2'), _e('D2', 'D3', '-', 'weak')]) == []


def test_invalid_dim_rejected():
    from agent.tools.causal_graph import validate_edges
    errors = validate_edges([_e('D8', 'D2')])
    assert any('D1-D7' in e for e in errors)


def test_self_loop_rejected():
    from agent.tools.causal_graph import validate_edges
    errors = validate_edges([_e('D2', 'D2')])
    assert any('自环' in e for e in errors)


def test_bad_sign_and_strength_rejected():
    from agent.tools.causal_graph import validate_edges
    errors = validate_edges([{'from': 'D1', 'to': 'D2', 'sign': 'x', 'strength': 'huge'}])
    assert any('sign' in e for e in errors)
    assert any('strength' in e for e in errors)


# ── find_feedback_loops ──

def test_two_node_reinforcing_loop():
    # 信息-激励恶性循环：D2↔D3 同向闭环
    from agent.tools.causal_graph import find_feedback_loops
    loops = find_feedback_loops([_e('D2', 'D3'), _e('D3', 'D2')])
    assert len(loops) == 1
    assert loops[0]['polarity'] == 'reinforcing'
    assert set(loops[0]['dims']) == {'D2', 'D3'}


def test_balancing_loop_odd_negative_edges():
    from agent.tools.causal_graph import find_feedback_loops
    loops = find_feedback_loops([_e('D1', 'D2', '+'), _e('D2', 'D1', '-')])
    assert len(loops) == 1
    assert loops[0]['polarity'] == 'balancing'


def test_double_negative_is_reinforcing():
    # 两条负边乘积为正 = 自增强
    from agent.tools.causal_graph import find_feedback_loops
    loops = find_feedback_loops([_e('D5', 'D7', '-'), _e('D7', 'D5', '-')])
    assert loops[0]['polarity'] == 'reinforcing'


def test_no_duplicate_loops_from_rotations():
    # 三节点环只报告一次，不因起点不同重复
    from agent.tools.causal_graph import find_feedback_loops
    edges = [_e('D1', 'D2'), _e('D2', 'D3'), _e('D3', 'D1')]
    loops = find_feedback_loops(edges)
    assert len(loops) == 1
    assert len(loops[0]['dims']) == 3


def test_no_loop_in_dag():
    from agent.tools.causal_graph import find_feedback_loops
    assert find_feedback_loops([_e('D1', 'D2'), _e('D2', 'D3')]) == []


def test_min_strength_weakest_link():
    from agent.tools.causal_graph import find_feedback_loops
    loops = find_feedback_loops([_e('D2', 'D3', '+', 'strong'), _e('D3', 'D2', '+', 'weak')])
    assert loops[0]['min_strength'] == 'weak'


# ── classify_loops ──

def test_reinforcing_loop_with_low_scores_is_vicious():
    from agent.tools.causal_graph import find_feedback_loops, classify_loops
    loops = find_feedback_loops([_e('D2', 'D3'), _e('D3', 'D2')])
    out = classify_loops(loops, scores={'D2': 2, 'D3': 2})
    assert out[0]['diagnosis'] == 'vicious'


def test_reinforcing_loop_with_high_scores_is_virtuous():
    from agent.tools.causal_graph import find_feedback_loops, classify_loops
    loops = find_feedback_loops([_e('D2', 'D3'), _e('D3', 'D2')])
    out = classify_loops(loops, scores={'D2': 4, 'D3': 4})
    assert out[0]['diagnosis'] == 'virtuous'


def test_down_trajectory_forces_vicious():
    # 即使分数尚可，趋势向下的自增强回路也判恶性
    from agent.tools.causal_graph import find_feedback_loops, classify_loops
    loops = find_feedback_loops([_e('D2', 'D3'), _e('D3', 'D2')])
    out = classify_loops(loops, scores={'D2': 4, 'D3': 4}, trajectories={'D3': 'down'})
    assert out[0]['diagnosis'] == 'vicious'


def test_balancing_loop_is_antagonistic():
    from agent.tools.causal_graph import find_feedback_loops, classify_loops
    loops = find_feedback_loops([_e('D1', 'D2', '+'), _e('D2', 'D1', '-')])
    out = classify_loops(loops, scores={'D1': 3, 'D2': 3})
    assert out[0]['diagnosis'] == 'antagonistic'


# ── rank_leverage ──

def test_leverage_point_is_most_looped_dim():
    # D3 参与两个回路（D2↔D3、D3↔D7），应排第一 —— Meadows 杠杆点
    from agent.tools.causal_graph import rank_leverage
    edges = [_e('D2', 'D3'), _e('D3', 'D2'), _e('D3', 'D7'), _e('D7', 'D3')]
    ranked = rank_leverage(edges)
    assert ranked[0]['dim'] == 'D3'
    assert ranked[0]['loop_count'] == 2


# ── propagate_intervention ──

def test_propagation_follows_sign_and_strength():
    from agent.tools.causal_graph import propagate_intervention
    # D2 改善 → D3 改善(0.6) → D5 恶化(0.6 * -0.6 = -0.36)
    edges = [_e('D2', 'D3', '+', 'strong'), _e('D3', 'D5', '-', 'strong')]
    eff = propagate_intervention(edges, 'D2', 1.0)
    assert eff['D2'] == 1.0
    assert eff['D3'] == 0.6
    assert eff['D5'] == -0.36


def test_propagation_does_not_revisit_nodes():
    from agent.tools.causal_graph import propagate_intervention
    edges = [_e('D2', 'D3'), _e('D3', 'D2')]
    eff = propagate_intervention(edges, 'D2', 1.0)
    assert eff['D2'] == 1.0   # 回路不放大自身（单路径不重访）


# ── cross_check_prescriptions ──

def test_prescription_conflict_detected():
    from agent.tools.causal_graph import cross_check_prescriptions
    # 处方A 改善 D2 → 恶化 D4；处方B 直接改善 D4 → 方向冲突
    edges = [_e('D2', 'D4', '-', 'strong')]
    rx = [
        {'title': '改革激励', 'target_dimension': 'D2'},
        {'title': '投资长期', 'target_dimension': 'D4'},
    ]
    result = cross_check_prescriptions(rx, edges)
    assert any(c['dim'] == 'D4' for c in result['conflicts'])


def test_multi_worsened_dimension_flagged():
    from agent.tools.causal_graph import cross_check_prescriptions
    # 两条处方都通过负边压低 D6
    edges = [_e('D1', 'D6', '-', 'strong'), _e('D2', 'D6', '-', 'strong')]
    rx = [
        {'title': 'A', 'target_dimension': 'D1'},
        {'title': 'B', 'target_dimension': 'D2'},
    ]
    result = cross_check_prescriptions(rx, edges)
    assert 'D6' in result['multi_worsened']


# ── analyze_graph 一次性入口 ──

def test_analyze_graph_end_to_end():
    from agent.tools.causal_graph import analyze_graph
    payload = {
        'edges': [_e('D7', 'D3', '-', 'strong'), _e('D3', 'D7', '-', 'strong')],
        'scores': {'D7': 2, 'D3': 2},
        'prescriptions': [{'title': '分权', 'target_dimension': 'D7'}],
    }
    result = analyze_graph(payload)
    assert result['loops'][0]['polarity'] == 'reinforcing'   # 负负得正：权力-信息恶性循环
    assert result['loops'][0]['diagnosis'] == 'vicious'
    assert result['leverage_ranking'][0]['loop_count'] == 1
    assert 'prescription_check' in result


def test_analyze_graph_returns_errors_on_bad_edges():
    from agent.tools.causal_graph import analyze_graph
    result = analyze_graph({'edges': [{'from': 'D9', 'to': 'D1', 'sign': '+', 'strength': 'strong'}]})
    assert result['errors']
