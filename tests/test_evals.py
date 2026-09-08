"""
评估仪器自身的测试：合成案例套件、消融、决策增量评分器、案例库来源分离。

仪器出错比没有仪器更糟——它会给出看起来可信的错误结论。所以这里同样带负控。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.tools.history_compare import (                      # noqa: E402
    case_library_provenance, find_analogies,
)
from evals import synthetic                                    # noqa: E402
from evals.decision_increment import (                         # noqa: E402
    aggregate, blind_package, score_case,
)


# ── 合成案例 + 消融 ─────────────────────────────────────────────────────────

def test_all_synthetic_cases_pass_at_baseline():
    r = synthetic.run_ablation('none')
    failed = [c['id'] for c in r['cases'] if not c['passed']]
    assert failed == [], f'合成案例失败：{failed}'


def test_every_ablation_loses_at_least_one_case():
    """负控：如果关掉某模块什么都不变，那个模块要么没用、要么这批案例测不到它。"""
    report = synthetic.run()
    for name, r in report['ablations'].items():
        if name == 'none':
            continue
        assert r['delta_vs_baseline'] < 0, (
            f'消融 {name} 没有让任何案例失守——'
            f'该模块在这批案例上没有被检验到，消融数字无意义'
        )


def test_ablation_restores_module_state():
    """跑完消融必须还原，否则后面的测试全在被污染的状态下跑。"""
    from agent.tools import ach_score
    before = (ach_score._NON_DIAGNOSTIC_FACTOR, dict(ach_score._TIER_WEIGHT),
              ach_score.collapse_evidence_families)
    synthetic.run()
    after = (ach_score._NON_DIAGNOSTIC_FACTOR, dict(ach_score._TIER_WEIGHT),
             ach_score.collapse_evidence_families)
    assert before == after


def test_synthetic_library_declares_it_is_constructed():
    prov = synthetic.load_cases()['provenance']
    assert prov['coding'] == 'constructed'
    assert 'what_it_does_not_test' in prov


# ── 案例库来源分离 ──────────────────────────────────────────────────────────

def test_teaching_library_declares_post_hoc_coding():
    prov = case_library_provenance()
    assert prov['coding'] == 'post_hoc'
    assert prov['coder_blind_to_outcome'] is False
    assert prov['library_role'] == 'teaching'


def test_analogy_results_carry_coding_provenance():
    scores = {f'D{i}': 2 for i in range(1, 8)}
    r = find_analogies(scores, 'public_company', top_k=1)[0]
    assert r['outcome_is_hindsight'] is True
    assert r['coder_blind_to_outcome'] is False


def test_blind_mode_still_strips_outcome_after_migration():
    scores = {f'D{i}': 2 for i in range(1, 8)}
    r = find_analogies(scores, 'public_company', top_k=2, blind=True)
    assert all('outcome' not in x and 'key_lesson' not in x for x in r)


# ── 决策增量评分器 ──────────────────────────────────────────────────────────

def _rating(reviewer, score, why='理由'):
    return {'reviewer': reviewer, 'score': score, 'rationale': why}


def test_both_reviewers_two_qualifies():
    r = score_case('C1', 'A_current', [_rating('R1', 2), _rating('R2', 2)])
    assert r['qualified'] is True and r['resolution'] == 'agreed'


def test_both_reviewers_one_does_not_qualify():
    r = score_case('C1', 'A_current', [_rating('R1', 1), _rating('R2', 1)])
    assert r['qualified'] is False


def test_disagreement_without_arbitration_is_not_qualified():
    r = score_case('C1', 'A_current', [_rating('R1', 2), _rating('R2', 1)])
    assert r['qualified'] is False
    assert r['resolution'] == 'unarbitrated_disagreement'


def test_arbitration_decides_and_requires_rationale():
    ratings = [_rating('R1', 2), _rating('R2', 1)]
    ok = score_case('C1', 'A_current', ratings, _rating('R3', 2))
    assert ok['qualified'] is True and ok['resolution'] == 'arbitrated'
    no_reason = score_case('C1', 'A_current', ratings,
                           {'reviewer': 'R3', 'score': 2, 'rationale': ''})
    assert no_reason['qualified'] is False


def test_arbiter_cannot_be_an_original_reviewer():
    r = score_case('C1', 'A_current', [_rating('R1', 2), _rating('R2', 1)], _rating('R1', 2))
    assert r['qualified'] is False and '裁决人' in r['problems'][0]


def test_two_scores_from_one_reviewer_is_invalid():
    r = score_case('C1', 'A_current', [_rating('R1', 2), _rating('R1', 2)])
    assert r['qualified'] is False and r['resolution'] == 'invalid'


def test_rating_without_rationale_is_invalid():
    r = score_case('C1', 'A_current', [_rating('R1', 2, ''), _rating('R2', 2)])
    assert r['qualified'] is False


def test_aggregate_keeps_baselines_separate():
    cases = ([score_case(f'C{i}', 'A_current', [_rating('R1', 2), _rating('R2', 2)])
              for i in range(12)]
             + [score_case(f'C{i}', 'B_generic', [_rating('R1', 1), _rating('R2', 1)])
                for i in range(12)])
    agg = aggregate(cases)
    assert agg['by_baseline']['A_current']['meets_threshold'] is True
    assert agg['by_baseline']['B_generic']['meets_threshold'] is False


def test_incomplete_sample_cannot_claim_threshold():
    cases = [score_case(f'C{i}', 'A_current', [_rating('R1', 2), _rating('R2', 2)])
             for i in range(9)]
    agg = aggregate(cases)
    assert agg['by_baseline']['A_current']['meets_threshold'] is False
    assert any('样本不全' in f for f in agg['flags'])


def test_blind_package_hides_path_identity():
    outputs = {'C_new': 'system-xray 七维诊断：D3 信息与反馈恶化，机制卡显示……',
               'A_current': '旧版 ACH 分析结果……',
               'B_generic': '普通检索摘要……'}
    pkg = blind_package('CASE-01', outputs)
    joined = ' '.join(i['text'] for i in pkg['items'])
    for leak in ('system-xray', '七维', '机制卡', 'ACH', 'D3'):
        assert leak not in joined, f'盲评包泄漏了路径身份：{leak}'
    assert set(pkg['key'].values()) == set(outputs)


def test_blind_package_is_reproducible():
    outputs = {'a': 'x', 'b': 'y', 'c': 'z'}
    assert blind_package('CASE-02', outputs)['key'] == blind_package('CASE-02', outputs)['key']
