import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _h(hid, statement='假说'):
    return {'id': hid, 'statement': statement}


def _ev(ratings, tier=2, description='某证据'):
    return {'description': description, 'tier': tier, 'ratings': ratings}


# ── validate_matrix ──

def test_empty_hypotheses_rejected():
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses([], [_ev({'H1': 'C'})])
    assert result['errors']


def test_unknown_hypothesis_in_ratings_rejected():
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses([_h('H1')], [_ev({'H9': 'C'})])
    assert any('H9' in e for e in result['errors'])


def test_invalid_rating_rejected():
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses([_h('H1')], [_ev({'H1': 'X'})])
    assert result['errors']


# ── 状态判定 ──

def test_t1_inconsistency_eliminates():
    # 一条满鉴别力的 T1 I 即达排除阈值
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses(
        [_h('H1'), _h('H2')],
        [_ev({'H1': 'I', 'H2': 'C'}, tier=1)],
    )
    by_id = {r['id']: r for r in result['ranking']}
    assert by_id['H1']['status'] == 'eliminated'
    assert by_id['H2']['status'] == 'active'


def test_t3_inconsistency_only_stresses():
    # "如果 I 全部来自 T3 信源，降低排除信心" —— T3 I 不足以排除
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses(
        [_h('H1'), _h('H2')],
        [_ev({'H1': 'I', 'H2': 'C'}, tier=3)],
    )
    by_id = {r['id']: r for r in result['ranking']}
    assert by_id['H1']['status'] == 'stressed'
    assert any('T3' in f for f in result['flags'])


def test_all_neutral_is_untestable():
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses(
        [_h('H1'), _h('H2')],
        [_ev({'H1': 'N', 'H2': 'C'}, tier=2)],
    )
    by_id = {r['id']: r for r in result['ranking']}
    assert by_id['H1']['status'] == 'untestable'
    assert any('不可检验' in f for f in result['flags'])


# ── "一条强 I 比十条 C 更有诊断力" ──

def test_one_strong_i_outweighs_many_cs():
    from agent.tools.ach_score import score_hypotheses
    # H1 有十条 C 但有一条 T1 I；H2 只有一条 C 无 I —— H2 应排前
    evidence = [_ev({'H1': 'C', 'H2': 'C'}, tier=2) for _ in range(10)]
    evidence[0] = _ev({'H1': 'C', 'H2': 'N'}, tier=2)  # 让 H2 至少有一条 C
    evidence.append(_ev({'H1': 'I', 'H2': 'C'}, tier=1))
    result = score_hypotheses([_h('H1'), _h('H2')], evidence)
    assert result['ranking'][0]['id'] == 'H2'


# ── 鉴别力降权 ──

def test_non_diagnostic_evidence_downweighted():
    # 对所有假说都是 C 的证据无区分力，权重应远低于有区分的证据
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses(
        [_h('H1'), _h('H2')],
        [_ev({'H1': 'C', 'H2': 'C'}, tier=1)],   # 全 C，无鉴别力
    )
    by_id = {r['id']: r for r in result['ranking']}
    assert by_id['H1']['weighted_consistency'] == 0.75   # 3.0 * 0.25
    assert by_id['H1']['status'] == 'active'


def test_all_i_non_diagnostic_does_not_eliminate():
    # 全 I（连续两条 T1）但无区分力 → 降权后不应轻易排除所有假说
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses(
        [_h('H1'), _h('H2')],
        [_ev({'H1': 'I', 'H2': 'I'}, tier=1)],
    )
    statuses = {r['status'] for r in result['ranking']}
    assert statuses == {'stressed'}   # 0.75 < 3.0 阈值


# ── 结构性 flags ──

def test_all_survive_flags_high_uncertainty():
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses(
        [_h('H1'), _h('H2'), _h('H3')],
        [_ev({'H1': 'C', 'H2': 'C', 'H3': 'N'}, tier=2),
         _ev({'H1': 'N', 'H2': 'C', 'H3': 'C'}, tier=2)],
    )
    assert any('高不确定' in f for f in result['flags'])


def test_all_eliminated_flags_reexamine():
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses(
        [_h('H1'), _h('H2')],
        [_ev({'H1': 'I', 'H2': 'C'}, tier=1),
         _ev({'H1': 'C', 'H2': 'I'}, tier=1)],
    )
    assert any('复查' in f for f in result['flags'])


def test_strongest_i_recorded():
    from agent.tools.ach_score import score_hypotheses
    result = score_hypotheses(
        [_h('H1'), _h('H2')],
        [_ev({'H1': 'I', 'H2': 'C'}, tier=3, description='弱证据'),
         _ev({'H1': 'I', 'H2': 'C'}, tier=1, description='强证据')],
    )
    by_id = {r['id']: r for r in result['ranking']}
    assert by_id['H1']['strongest_i']['tier'] == 1
    assert by_id['H1']['strongest_i']['description'] == '强证据'
