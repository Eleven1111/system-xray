"""
S2 跨期更新测试：不可变版本 / 双时间 / 按类型时效 / 口径可比性 / 判断变更 / 预测冻结。

守住的是 S2 的退出条件：
  - 新闻转载不改变独立证据数
  - 指标改口径不误判成状态改善
  - 到期预测按冻结规则裁定
  - 重大事实修正能影响相应行动状态
  - 同日两次保存保留两个不可变版本，可按分析 ID 重建当时输入、判断与预测
"""

import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.tools.forecast_registry import (          # noqa: E402
    due_predictions, freeze_predictions, select_versions, update_prediction,
)
from agent.tools.temporal import (                   # noqa: E402
    check_time_fields, comparability, diff_analyses, is_republication,
    staleness, staleness_report,
)


# ── 不可变版本 ──────────────────────────────────────────────────────────────

def _minimal(score=3):
    return {'dimension_scores': {'D1': score}, 'completeness': 'draft'}


def test_same_day_saves_keep_two_versions(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    p1 = db.save_analysis('S', 'public_company', _minimal(3), date_str='20260908')
    p2 = db.save_analysis('S', 'public_company', _minimal(4), date_str='20260908')
    assert p1 != p2
    assert Path(p1).exists() and Path(p2).exists()      # 前一版没有被覆盖
    versions = db.list_versions('S')
    assert len(versions) == 2
    assert versions[0]['analysis_id'] == '20260908-001'
    assert versions[1]['analysis_id'] == '20260908-002'


def test_concurrent_saves_reserve_distinct_immutable_versions(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    barrier = threading.Barrier(2)
    paths, failures = [], []

    def save(score):
        try:
            barrier.wait()
            paths.append(db.save_analysis('S', 'public_company', _minimal(score),
                                          date_str='20260908'))
        except Exception as exc:  # pragma: no cover - assertion exposes unexpected failure
            failures.append(exc)

    workers = [threading.Thread(target=save, args=(score,)) for score in (3, 4)]
    [w.start() for w in workers]
    [w.join() for w in workers]
    assert failures == []
    assert len(set(paths)) == 2
    assert len(db.list_versions('S')) == 2


def test_version_can_be_rebuilt_by_analysis_id(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    db.save_analysis('S', 'public_company', _minimal(3), date_str='20260908')
    db.save_analysis('S', 'public_company', _minimal(5), date_str='20260908')
    first = db.load_version('S', '20260908-001')
    assert first['dimension_scores']['D1'] == 3        # 当时的输入原样可重建
    assert db.load_latest('S')['dimension_scores']['D1'] == 5


def test_second_version_records_what_it_supersedes(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    db.save_analysis('S', 'public_company', _minimal(3), date_str='20260908')
    p2 = db.save_analysis('S', 'public_company', _minimal(4), date_str='20260909')
    assert json.loads(Path(p2).read_text())['supersedes'] == '20260908-001'


def test_index_is_derived_and_rebuildable(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    db.save_analysis('S', 'public_company', _minimal(3), date_str='20260908')
    index = tmp_path / 'S' / 'index.json'
    assert index.exists()
    index.unlink()                                     # 索引是派生物，删了应能重建
    assert len(db.list_versions('S')) == 1


def test_legacy_single_file_still_loads(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    legacy_dir = tmp_path / 'S'
    legacy_dir.mkdir(parents=True)
    (legacy_dir / '20260101.json').write_text(json.dumps(
        {'analysis_date': '20260101', 'dimension_scores': {'D1': 2}}), encoding='utf-8')
    assert db.load_latest('S')['dimension_scores']['D1'] == 2
    db.save_analysis('S', 'public_company', _minimal(4), date_str='20260101')
    ids = [v['analysis_id'] for v in db.list_versions('S')]
    assert ids == ['20260101', '20260101-001']         # 旧文件当作该日第 0 版，未被覆盖


# ── 双时间 ─────────────────────────────────────────────────────────────────

def test_retrieval_date_cannot_stand_in_for_event_date():
    problems = check_time_fields({'event_time': '2026-09-08', 'retrieved_at': '2026-09-08'})
    assert any('检索日期' in p for p in problems)


def test_event_cannot_postdate_publication():
    problems = check_time_fields({'event_time': '2026-09-08', 'published_at': '2026-09-01'})
    assert any('晚于 published_at' in p for p in problems)


def test_consistent_times_pass():
    assert check_time_fields({'event_time': '2026-05-01', 'published_at': '2026-05-02',
                              'retrieved_at': '2026-09-08'}) == []


def test_republication_of_old_event_is_detected():
    known = [{'source_family': 'gov-press-0517', 'event_time': '2026-05-17'}]
    hit = is_republication({'source_family': 'gov-press-0517', 'published_at': '2026-09-01'}, known)
    assert hit is not None                             # 只更新访问记录，不当新系统变化


# ── 按断言类型的时效 ────────────────────────────────────────────────────────

def test_officeholder_claim_goes_stale_in_days_not_months():
    r = staleness({'claim_type': 'officeholder', 'event_time': '2026-08-01'},
                  as_of='2026-09-08')
    assert r['status'] == 'stale'


def test_charter_claim_of_same_age_is_still_fresh():
    # 同样的 38 天，章程类断言不算过期——这正是统一阈值做不到的区分
    r = staleness({'claim_type': 'charter_rule', 'event_time': '2026-08-01'},
                  as_of='2026-09-08')
    assert r['status'] == 'fresh'


def test_historical_fact_is_not_time_bound():
    r = staleness({'claim_type': 'historical_fact', 'event_time': '1989-11-09'},
                  as_of='2026-09-08')
    assert r['status'] == 'not_time_bound'


def test_claim_without_anchor_is_not_assumed_fresh():
    r = staleness({'claim_type': 'crisis_status'}, as_of='2026-09-08')
    assert r['status'] == 'no_anchor'


def test_stale_loadbearing_claims_are_ranked_for_recheck():
    claims = [
        {'id': 'C1', 'claim_type': 'officeholder', 'event_time': '2026-01-01', 'loads': ['D7', 'M1']},
        {'id': 'C2', 'claim_type': 'officeholder', 'event_time': '2026-01-01', 'loads': ['D7']},
        {'id': 'C3', 'claim_type': 'charter_rule', 'event_time': '2026-08-01', 'loads': ['D1']},
    ]
    r = staleness_report(claims, as_of='2026-09-08')
    ids = [x['id'] for x in r['needs_recheck']]
    assert ids == ['C1', 'C2']                         # 载荷多的排前；C3 未过期不入列


# ── 口径可比性 ──────────────────────────────────────────────────────────────

def test_metric_redefinition_blocks_improvement_reading():
    prev = {'dimension_scores': {'D3': 2}, 'dimension_basis_version': {'D3': 'v1'}}
    cur = {'dimension_scores': {'D3': 4}, 'dimension_basis_version': {'D3': 'v2'}}
    r = comparability(cur, prev)
    assert r['comparable'] is False
    assert 'D3' in r['incomparable_dims']
    assert any('不得读作系统改善' in w for w in r['warnings'])


def test_same_basis_is_comparable():
    prev = {'dimension_scores': {'D3': 2}, 'dimension_basis_version': {'D3': 'v1'}}
    cur = {'dimension_scores': {'D3': 4}, 'dimension_basis_version': {'D3': 'v1'}}
    assert comparability(cur, prev)['comparable'] is True


def test_declared_measurement_change_marks_dimension_incomparable():
    prev = {'dimension_scores': {'D3': 2}}
    cur = {'dimension_scores': {'D3': 3},
           'measurement_changes': [{'metric': '事故上报数', 'dimension': 'D3',
                                    'change': '事故定义收窄', 'effective': '2026-06-01'}]}
    assert 'D3' in comparability(cur, prev)['incomparable_dims']


# ── 判断变更 ────────────────────────────────────────────────────────────────

def test_measurement_change_is_not_classified_as_system_change():
    prev = {'dimension_scores': {'D3': 2}, 'dimension_basis_version': {'D3': 'v1'}}
    cur = {'dimension_scores': {'D3': 4}, 'dimension_basis_version': {'D3': 'v2'}}
    d = diff_analyses(cur, prev)
    row = [c for c in d['judgement_changes'] if c['object_id'] == 'D3'][0]
    assert row['change_type'] == 'measurement'


def test_score_move_under_same_basis_is_a_system_change():
    prev = {'dimension_scores': {'D3': 2}, 'dimension_basis_version': {'D3': 'v1'}}
    cur = {'dimension_scores': {'D3': 4}, 'dimension_basis_version': {'D3': 'v1'}}
    row = [c for c in diff_analyses(cur, prev)['judgement_changes']
           if c['object_id'] == 'D3'][0]
    assert row['change_type'] == 'system_state'


def test_legacy_history_comparison_does_not_call_basis_change_improvement():
    from agent.tools.history_compare import compare_history
    prev = {'dimension_scores': {'D1': 2}, 'dimension_basis_version': {'D1': 'v1'}}
    cur = {'dimension_scores': {'D1': 4}, 'dimension_basis_version': {'D1': 'v2'}}
    result = compare_history('S', cur, prev)
    assert 'D1' not in result['improving']
    assert any('口径已变更' in warning for warning in result['trajectory_warnings'])


def test_withdrawal_driven_by_contradicted_claim_is_an_analysis_correction():
    prev = {'mechanisms': [{'id': 'M1', 'explains': 'x'}]}
    cur = {'mechanisms': [],
           'claims': [{'id': 'C1', 'status': 'contradicted', 'loads': ['M1']}]}
    row = [c for c in diff_analyses(cur, prev)['judgement_changes']
           if c['object_id'] == 'M1'][0]
    assert row['change'] == 'withdrawn'
    assert row['change_type'] == 'analysis_correction'


def test_unchanged_objects_are_reported_as_retained():
    m = {'id': 'M1', 'explains': 'x'}
    d = diff_analyses({'mechanisms': [m]}, {'mechanisms': [m]})
    assert d['counts'].get('retained') == 1


# ── 预测冻结与裁定 ──────────────────────────────────────────────────────────

def _pred(pid, conf=0.6, et='occurrence', horizon='2026-12-31'):
    return {'id': pid, 'prediction': 'x', 'falsification_condition': 'y',
            'time_horizon': horizon, 'event_type': et, 'confidence': conf,
            'dimension_link': 'D2', 'source_step': 'dimension_analysis'}


def test_freeze_rejects_prediction_without_event_type():
    p = _pred('P1'); del p['event_type']
    r = freeze_predictions([p], frozen_at='2026-09-08')
    assert r['errors'] and 'event_type' in r['errors'][0]


def test_freeze_refuses_to_overwrite_existing_id():
    r1 = freeze_predictions([_pred('P1', 0.4)], frozen_at='2026-09-08')
    r2 = freeze_predictions([_pred('P1', 0.9)], frozen_at='2026-10-01',
                            registry=r1['registry'])
    assert any('不得覆盖' in e for e in r2['errors'])
    assert len(r2['registry']) == 1


def test_save_path_freezes_predictions_and_preserves_initial_probability(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    first = _minimal(); first['predictions'] = [_pred('P1', 0.4)]
    db.save_analysis('S', 'public_company', first, date_str='20260908')
    second = _minimal(); second['prediction_updates'] = [
        {'id': 'P1', 'updates': {'confidence': 0.9}, 'reason': 'new evidence'}]
    db.save_analysis('S', 'public_company', second, date_str='20260909')
    saved = db.load_latest('S')['prediction_registry']
    assert [p['confidence'] for p in saved] == [0.4, 0.9]
    assert [p['confidence'] for p in db.load_predictions('S')] == [0.4]


def test_update_appends_version_and_keeps_initial_value():
    reg = freeze_predictions([_pred('P1', 0.4)], frozen_at='2026-09-08')['registry']
    reg = update_prediction(reg, 'P1', {'confidence': 0.9}, updated_at='2026-12-01',
                            reason='事件临近')['registry']
    assert [p['confidence'] for p in reg] == [0.4, 0.9]
    assert reg[1]['supersedes_version'] == 1


def test_update_cannot_change_frozen_event_definition():
    reg = freeze_predictions([_pred('P1')], frozen_at='2026-09-08')['registry']
    r = update_prediction(reg, 'P1', {'time_horizon': '2027-12-31'}, updated_at='2026-12-01')
    assert r['errors'] and 'time_horizon' in r['errors'][0]


def test_update_cannot_sneak_in_a_new_adjudication_rule():
    reg = freeze_predictions([_pred('P1')], frozen_at='2026-09-08')['registry']
    r = update_prediction(reg, 'P1', {'adjudication_sources': ['new source']},
                          updated_at='2026-12-01')
    assert r['errors'] and '允许更新列表' in r['errors'][0]


def test_freeze_rejects_invalid_confidence():
    r = freeze_predictions([_pred('P1', 1.1)], frozen_at='2026-09-08')
    assert r['errors'] and 'confidence' in r['errors'][0]


def test_review_policy_first_prevents_cherry_picking():
    reg = freeze_predictions([_pred('P1', 0.4)], frozen_at='2026-09-08')['registry']
    reg = update_prediction(reg, 'P1', {'confidence': 0.95}, updated_at='2026-12-30')['registry']
    sel = select_versions(reg, policy='first')['selected']
    assert [p['confidence'] for p in sel] == [0.4]     # 复盘用初始值，不是临到期那版


def test_lead_time_policy_excludes_last_minute_updates():
    reg = freeze_predictions([_pred('P1', 0.4)], frozen_at='2026-06-01')['registry']
    reg = update_prediction(reg, 'P1', {'confidence': 0.95}, updated_at='2026-12-30')['registry']
    sel = select_versions(reg, policy='lead_time', lead_time_days=30)['selected']
    assert [p['confidence'] for p in sel] == [0.4]


def test_unknown_review_policy_is_rejected():
    assert select_versions([], policy='whatever_looks_best')['errors']


def test_due_predictions_split_by_event_type():
    reg = [_pred('P1', et='occurrence'), _pred('P2', et='persistence'),
           _pred('P3', et='point_in_time'), _pred('P4', et='conditional')]
    r = due_predictions(reg, as_of='2026-06-01')
    early = {x['id']: x['adjudicable'] for x in r['early_only']}
    waiting = {x['id'] for x in r['waiting']}
    assert 'confirmed' in early['P1'] and 'falsified' not in early['P1'][0]
    assert 'falsified' in early['P2']
    assert 'P3' in waiting and 'P4' in waiting        # 时点型与条件型都只能等


def test_due_predictions_after_horizon_are_fully_adjudicable():
    r = due_predictions([_pred('P1', et='point_in_time')], as_of='2027-01-01')
    assert r['due'][0]['adjudicable'] == 'both_directions'
