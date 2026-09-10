"""
把 §14.3 的对抗用例套件接进 pytest，并给它加**负控**。

负控是关键：一个从不失败的检查和没有检查，信息量相同。
下面的负控把某条防护关掉，断言对应用例**确实会红**——
证明这些用例测的是防护本身，而不是恒真的断言。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evals import adversarial                     # noqa: E402


def test_all_automated_adversarial_cases_pass():
    report = adversarial.run()
    failed = [r['case'] for r in report['results'] if r['passed'] is False]
    assert failed == [], f'对抗用例失败：{failed}'
    assert report['automated_total'] >= 11


def test_prompt_gated_cases_are_reported_not_hidden():
    # 提示词层防护不能被记成"通过"——那正是假绿
    report = adversarial.run()
    gated = [r for r in report['results'] if r['status'] == 'prompt_gated']
    assert gated, '至少有一条用例应当被诚实标为提示词层防护'
    assert all(r['passed'] is None for r in gated)


def test_negative_control_duplicate_evidence(monkeypatch):
    """关掉证据家族折叠 → 重复计数用例必须变红。"""
    import agent.tools.ach_score as ach

    def no_collapse(evidence):
        out = []
        for i, e in enumerate(evidence):
            fam = dict(e)
            fam['copies'] = 1
            fam['family_id'] = f'raw:{i}'
            out.append(fam)
        return out, []

    monkeypatch.setattr(ach, 'collapse_evidence_families', no_collapse)
    passed, _ = adversarial.case_duplicate_evidence()
    assert passed is False


def test_negative_control_authority_boundary(monkeypatch):
    """放开权限边界 → 越权行动用例必须变红。"""
    import agent.validation as validation

    monkeypatch.setitem(validation._AUTHORITY_ALLOWS, 'can_only_monitor',
                        {'user_direct', 'user_influence', 'user_monitor_only', 'third_party'})
    passed, _ = adversarial.case_reader_without_authority()
    assert passed is False


def test_negative_control_measurement_basis(monkeypatch):
    """让口径比较永远返回"可比" → 口径变更用例必须变红。"""
    import agent.tools.temporal as temporal

    monkeypatch.setattr(temporal, 'comparability',
                        lambda cur, prev: {'comparable': True, 'incomparable_dims': [],
                                           'basis_changed_dims': [],
                                           'declared_measurement_changes': [], 'warnings': []})
    monkeypatch.setattr(adversarial, 'comparability', temporal.comparability)
    passed, _ = adversarial.case_measurement_basis_change()
    assert passed is False


def test_negative_control_blind_replay(monkeypatch):
    """让回放模式忘记隔离结局字段 → 后见之明污染用例必须变红。"""
    import agent.tools.history_compare as hc

    real = hc.find_analogies
    monkeypatch.setattr(adversarial, 'find_analogies',
                        lambda *a, **kw: real(*a, **{**kw, 'blind': False}))
    passed, _ = adversarial.case_hindsight_contamination()
    assert passed is False
