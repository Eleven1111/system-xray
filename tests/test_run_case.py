"""
对照运行记录器的测试。

核心区分（真实运行才逼出来的）：
  - **授予的资源**不等量 → 硬阻断。给想验证的那条路径多喂证据，差异就说明不了任何事。
  - **消耗**不等量 → 报告成本，不阻断。一个方法读自己更长的规范、想得更久，
    那是它的成本，不是不公平的输入；但它同时是对"更好"这个结论的真实威胁，
    所以必须变成结论的限定条件。

两处都有负控：放宽容忍度后，原本该红的必须变绿。
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
    # searches 是**授予**的资源：多给一条路径检索次数 = 多给它证据 → 硬阻断
    _init(cap={'searches': 100})
    _record_all(budgets={'A_current': _budget(searches=4), 'B_generic': _budget(searches=4),
                         'C_new': _budget(searches=12)})   # 新版多跑 3 倍
    r = run_case.check_comparability('PILOT-00', 'fixed_material')
    assert r['comparable'] is False
    assert any('C_new' in e and 'searches' in e for e in r['errors'])


def test_higher_consumption_is_cost_not_invalidity():
    """真实运行发现：三条路径 tokens 差 2.5×、wall_clock 差 11×，但读的是同一份材料。

    按旧逻辑整轮判"不可比"，等于说"新方法只要更费就不能被评估"——
    那是把成本问题误当成效度问题。现在改为报告成本 + 强制限定，不阻断。
    """
    _init(cap={'searches': 0})
    _record_all(budgets={
        'A_current': _budget(searches=0, calls=3, seconds=620, tokens=104858),
        'B_generic': _budget(searches=0, calls=2, seconds=56, tokens=58316),
        'C_new':     _budget(searches=0, calls=12, seconds=604, tokens=143854)})
    r = run_case.check_comparability('PILOT-00', 'fixed_material')
    assert r['comparable'] is True, '证据访问等量（searches 全为 0）就不该阻断'
    assert r['cost']['tokens']['ratio'] > 2
    assert any('算力不等量' in w and '限定' in w for w in r['warnings'])


def test_zero_search_round_counts_as_exact_parity():
    _init(cap={'searches': 0})
    _record_all(budgets={p: _budget(searches=0) for p in run_case.PATHS})
    r = run_case.check_comparability('PILOT-00', 'fixed_material')
    assert r['comparable'] is True
    assert r['ratios']['searches'] == 1.0


def test_negative_control_consumption_warning_disappears_when_loosened(monkeypatch):
    """负控：放宽容忍度后，成本告警必须消失——证明它真的由比值驱动。"""
    _init(cap={'searches': 0})
    _record_all(budgets={
        'A_current': _budget(searches=0, tokens=100000),
        'B_generic': _budget(searches=0, tokens=50000),
        'C_new':     _budget(searches=0, tokens=150000)})
    assert any('算力不等量' in w
               for w in run_case.check_comparability('PILOT-00', 'fixed_material')['warnings'])
    monkeypatch.setattr(run_case, 'BUDGET_TOLERANCE', 100.0)
    assert not any('算力不等量' in w
                   for w in run_case.check_comparability('PILOT-00', 'fixed_material')['warnings'])


def test_exceeding_pre_registered_cap_is_rejected():
    # 上限只对授予类资源生效
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


def test_similar_lengths_and_costs_produce_no_warning():
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
