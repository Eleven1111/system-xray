"""
对照运行记录器的测试——重点是**预算可比性是硬校验**这件事。

评估里最容易被糊弄的一环：给想验证的那条路径多跑几轮，然后把差异当成方法的功劳。
所以下面有负控：把容忍度放大，不可比的用例必须变成"可比"，证明这条校验真的在起作用。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evals import run_case                                   # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(run_case, 'RUNS_DIR', tmp_path / 'runs')


def _budget(searches=6, calls=10, seconds=120, tokens=8000):
    return {'searches': searches, 'tool_calls': calls,
            'wall_clock_seconds': seconds, 'tokens': tokens}


def _init(case_id='PILOT-00', cap=None):
    return run_case.init_case(case_id, subject='某系统', as_of='2026-09-08',
                              system_type='platform',
                              budget_cap=cap or {'searches': 8})


def _record_all(case_id='PILOT-00', round_name='fixed_material', budgets=None):
    budgets = budgets or {p: _budget() for p in run_case.PATHS}
    for path in run_case.PATHS:
        run_case.record_run(case_id, path, round_name,
                            output_text=f'{path} 的分析输出', budget_used=budgets[path])


# ── 基本记录 ────────────────────────────────────────────────────────────────

def test_init_creates_manifest_with_frozen_cap():
    m = _init()
    assert m['budget_cap'] == {'searches': 8}
    assert run_case.load_manifest('PILOT-00')['subject'] == '某系统'


def test_record_requires_full_budget_accounting():
    _init()
    r = run_case.record_run('PILOT-00', 'C_new', 'fixed_material', 'x',
                            budget_used={'searches': 5})
    assert r['errors'] and 'budget_used' in r['errors'][0]


def test_record_rejects_unknown_path_or_round():
    _init()
    assert run_case.record_run('PILOT-00', 'D_other', 'fixed_material', 'x', _budget())['errors']
    assert run_case.record_run('PILOT-00', 'C_new', 'whenever', 'x', _budget())['errors']


def test_output_is_written_to_disk():
    _init()
    _record_all()
    f = run_case.case_dir('PILOT-00') / 'outputs' / 'fixed_material__C_new.md'
    assert f.exists() and 'C_new' in f.read_text(encoding='utf-8')


# ── 预算可比性（核心）──────────────────────────────────────────────────────

def test_comparable_budgets_pass():
    _init()
    _record_all()
    assert run_case.check_comparability('PILOT-00', 'fixed_material')['comparable'] is True


def test_lopsided_search_budget_is_rejected():
    _init(cap={'searches': 100})
    _record_all(budgets={'A_current': _budget(searches=4), 'B_generic': _budget(searches=4),
                         'C_new': _budget(searches=12)})   # 新版多跑 3 倍
    r = run_case.check_comparability('PILOT-00', 'fixed_material')
    assert r['comparable'] is False
    assert any('C_new' in e and 'searches' in e for e in r['errors'])


def test_exceeding_pre_registered_cap_is_rejected():
    _init(cap={'searches': 5})
    _record_all(budgets={p: _budget(searches=6) for p in run_case.PATHS})
    r = run_case.check_comparability('PILOT-00', 'fixed_material')
    assert r['comparable'] is False
    assert any('超出预登记上限' in e for e in r['errors'])


def test_missing_path_blocks_comparison():
    _init()
    run_case.record_run('PILOT-00', 'C_new', 'fixed_material', 'x', _budget())
    r = run_case.check_comparability('PILOT-00', 'fixed_material')
    assert r['comparable'] is False
    assert any('缺少路径' in e for e in r['errors'])


def test_negative_control_loosening_tolerance_lets_it_through(monkeypatch):
    """负控：把容忍度放大，原本不可比的用例必须变可比——证明校验真的在起作用。"""
    _init(cap={'searches': 100})
    _record_all(budgets={'A_current': _budget(searches=4), 'B_generic': _budget(searches=4),
                         'C_new': _budget(searches=12)})
    assert run_case.check_comparability('PILOT-00', 'fixed_material')['comparable'] is False
    monkeypatch.setattr(run_case, 'BUDGET_TOLERANCE', 100.0)
    assert run_case.check_comparability('PILOT-00', 'fixed_material')['comparable'] is True


# ── 盲评打包 ────────────────────────────────────────────────────────────────

def test_incomparable_runs_are_not_packaged():
    _init(cap={'searches': 100})
    _record_all(budgets={'A_current': _budget(searches=4), 'B_generic': _budget(searches=4),
                         'C_new': _budget(searches=12)})
    r = run_case.package_for_review('PILOT-00', 'fixed_material')
    assert r['errors'], '不可比的输出不应被打包送评'


def test_package_separates_key_from_review_material():
    _init()
    _record_all()
    r = run_case.package_for_review('PILOT-00', 'fixed_material')
    assert not r['errors']
    review_dir = Path(r['review_dir'])
    files = {f.name for f in review_dir.iterdir()}
    assert len(files) == 3
    # 映射表不能出现在交给评审的目录里
    assert not any('key' in f for f in files)
    assert (run_case.case_dir('PILOT-00') / r['key_file']).exists()


def test_length_disparity_is_flagged_but_not_blocking():
    # 试点发现：篇幅差 3.28×。不阻断，但必须让评审组织者看见
    _init()
    for path, n in (('A_current', 1000), ('B_generic', 1000), ('C_new', 4000)):
        run_case.record_run('PILOT-00', path, 'fixed_material', 'x' * n, _budget())
    r = run_case.check_comparability('PILOT-00', 'fixed_material')
    assert r['comparable'] is True                       # 篇幅不阻断
    assert r['ratios']['output_length'] == 4.0
    assert any('篇幅' in w and '不得以长度' in w for w in r['warnings'])


def test_similar_lengths_produce_no_warning():
    _init()
    for path in run_case.PATHS:
        run_case.record_run('PILOT-00', path, 'fixed_material', 'x' * 1000, _budget())
    assert run_case.check_comparability('PILOT-00', 'fixed_material')['warnings'] == []


def test_blind_labels_do_not_share_letters_with_path_names():
    # 试点发现：标签 A/B/C 与路径名 A_current/B_generic/C_new 同字母，
    # 打乱后可能真撞上，评审白捡身份信息
    from evals.decision_increment import blind_package
    pkg = blind_package('X1', {p: f'{p} 输出' for p in run_case.PATHS})
    suffixes = {i['label'].rsplit('-', 1)[-1] for i in pkg['items']}
    path_initials = {p[0] for p in run_case.PATHS}
    assert not (suffixes & path_initials), f'标签字母与路径名首字母重叠：{suffixes & path_initials}'


def test_rounds_are_recorded_separately():
    _init()
    _record_all(round_name='fixed_material')
    _record_all(round_name='open_retrieval')
    st = run_case.status('PILOT-00')
    assert st['rounds']['fixed_material']['complete'] is True
    assert st['rounds']['open_retrieval']['complete'] is True
    files = {f.name for f in (run_case.case_dir('PILOT-00') / 'outputs').iterdir()}
    assert len(files) == 6      # 两轮 × 三路径，互不覆盖


def test_status_reports_incomplete_rounds_honestly():
    _init()
    run_case.record_run('PILOT-00', 'C_new', 'fixed_material', 'x', _budget())
    st = run_case.status('PILOT-00')
    assert st['rounds']['fixed_material']['complete'] is False
    assert st['rounds']['open_retrieval']['recorded_paths'] == []
