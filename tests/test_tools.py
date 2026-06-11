import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_dimension_labels_has_d7_in_db():
    from agent.store.db import _DIMENSION_LABELS
    assert 'D7' in _DIMENSION_LABELS
    assert _DIMENSION_LABELS['D7'] == '权力结构'


def test_dimension_labels_has_d7_in_compare():
    from agent.tools.history_compare import DIMENSION_LABELS
    assert 'D7' in DIMENSION_LABELS
    assert DIMENSION_LABELS['D7'] == '权力结构'


def test_radar_svg_seven_dimensions():
    from agent.store.db import build_radar_svg
    scores = {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4, 'D7': 3}
    svg = build_radar_svg(scores)
    assert '<svg' in svg
    assert '权力结构' in svg
    assert 'D7' not in svg or '权力结构 3/5' in svg


def test_radar_svg_six_dimensions_still_works():
    from agent.store.db import build_radar_svg
    scores = {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4}
    svg = build_radar_svg(scores)
    assert '<svg' in svg
    assert '权力结构' not in svg


def test_radar_svg_polygon_count():
    from agent.store.db import build_radar_svg
    scores = {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4, 'D7': 3}
    svg = build_radar_svg(scores)
    # 5 grid polygons + 1 data polygon = 6
    assert svg.count('<polygon') == 6


def test_find_analogies_returns_top_k():
    from agent.tools.history_compare import find_analogies
    scores = {'D1': 1, 'D2': 1, 'D3': 1, 'D4': 2, 'D5': 1, 'D6': 2, 'D7': 2}
    results = find_analogies(scores, top_k=3)
    assert len(results) == 3
    assert all('similarity' in r for r in results)
    assert all('name' in r for r in results)
    assert all('outcome' in r for r in results)
    assert results[0]['similarity'] > 0.8


def test_find_analogies_system_type_boost():
    from agent.tools.history_compare import find_analogies
    scores = {'D1': 1, 'D2': 2, 'D3': 1, 'D4': 3, 'D5': 2, 'D6': 1, 'D7': 4}
    results_no_type = find_analogies(scores, top_k=5)
    results_geo = find_analogies(scores, system_type='geopolitical', top_k=5)
    geo_count_no_type = sum(1 for r in results_no_type if r['system_type'] == 'geopolitical')
    geo_count_typed = sum(1 for r in results_geo if r['system_type'] == 'geopolitical')
    assert geo_count_typed >= geo_count_no_type


def test_find_analogies_includes_key_lesson():
    from agent.tools.history_compare import find_analogies
    scores = {'D1': 5, 'D2': 5, 'D3': 4, 'D4': 5, 'D5': 5, 'D6': 5, 'D7': 5}
    results = find_analogies(scores, top_k=1)
    assert 'key_lesson' in results[0]
    assert len(results[0]['key_lesson']) > 10


def test_metric_is_magnitude_aware_not_cosine():
    # 回归测试：危机向量(全低) 不应与健康系统(全高) 高度相似。
    # 余弦相似度的缺陷曾使两者同为 1.0；欧氏度量应明确区分。
    from agent.tools.history_compare import _distance_similarity
    crisis = [2, 2, 2, 2, 2, 1, 2]
    healthy = [5, 4, 4, 4, 5, 5, 5]
    assert _distance_similarity(crisis, crisis) == 1.0
    assert _distance_similarity(crisis, healthy) < 0.5  # cosine 会给 ~1.0


def test_find_analogies_crisis_vector_matches_distressed_not_healthy():
    # 危机向量的 top 类比应是受困/崩溃系统，而非瑞士/新加坡这类健康系统
    from agent.tools.history_compare import find_analogies
    scores = {'D1': 2, 'D2': 2, 'D3': 2, 'D4': 2, 'D5': 2, 'D6': 1, 'D7': 2}
    results = find_analogies(scores, system_type='geopolitical', top_k=5)
    names = {r['name'] for r in results}
    assert 'Switzerland (ongoing)' not in names
    assert 'Singapore (ongoing)' not in names
    # 至少一个公认的崩溃/危机案例进入 top 5
    assert names & {'Soviet Union (1989)', 'Venezuela (2024)', 'Lebanon (2020-2024)',
                    'Libya post-2011 (2020s)', 'WeWork (2019)'}


def test_same_type_bonus_is_additive_tiebreaker():
    # 同类型加性微调不应让松散匹配的同类型反超紧密匹配的跨类型
    from agent.tools.history_compare import find_analogies, _SAME_TYPE_BONUS
    assert _SAME_TYPE_BONUS <= 0.1  # tiebreaker 量级，非主导
    # 近乎完全匹配某 geopolitical case 时，加 bonus 后仍 ≤ 1.0
    scores = {'D1': 5, 'D2': 4, 'D3': 4, 'D4': 4, 'D5': 5, 'D6': 5, 'D7': 5}  # Switzerland
    results = find_analogies(scores, system_type='geopolitical', top_k=1)
    assert results[0]['similarity'] <= 1.0


# ── P6a: date-aware prediction calibration (no early-confirmed) ──

def _vr(result, horizon, conf):
    return {'verification_result': result, 'time_horizon': horizon,
            'original_prediction': {'confidence': conf, 'prediction': 'x'}}


def test_early_confirmed_reclassified_not_scored():
    from agent.tools.history_compare import calculate_prediction_accuracy
    vr = [_vr('confirmed', '2026-09-30', 0.78), _vr('confirmed', '2026-10-31', 0.64),
          _vr('confirmed', '2026-12-31', 0.66)]
    r = calculate_prediction_accuracy(vr, as_of_date='2026-06-01')
    assert r['confirmed_count'] == 0          # 未到期不算证实
    assert r['on_track_count'] == 3
    assert r['reclassified_early_confirmed'] == 3
    assert r['brier_score'] is None           # 无 resolved → 不刷假 Brier


def test_confirmed_after_horizon_is_scored():
    from agent.tools.history_compare import calculate_prediction_accuracy
    vr = [_vr('confirmed', '2026-09-30', 0.78), _vr('confirmed', '2026-10-31', 0.64),
          _vr('confirmed', '2026-12-31', 0.66)]
    r = calculate_prediction_accuracy(vr, as_of_date='2027-01-01')
    assert r['confirmed_count'] == 3
    assert r['brier_score'] is not None


def test_early_falsified_counts_immediately():
    from agent.tools.history_compare import calculate_prediction_accuracy
    # 提前证伪合法：条件已破，任何时候都算 resolved
    vr = [_vr('falsified', '2026-12-31', 0.8), _vr('falsified', '2026-12-31', 0.7),
          _vr('falsified', '2026-12-31', 0.6)]
    r = calculate_prediction_accuracy(vr, as_of_date='2026-06-01')
    assert r['falsified_count'] == 3
    assert r['brier_score'] is not None


# ── detect_danger_zones：危险区/生存区签名机械化 ──

def test_danger_zone_enron_signature():
    # D5≤2 + D2≤2 = 合法性-激励双崩塌（Enron/Theranos/FTX 签名）
    from agent.tools.history_compare import detect_danger_zones
    r = detect_danger_zones({'D1': 3, 'D2': 2, 'D3': 3, 'D4': 3, 'D5': 1, 'D6': 3, 'D7': 3})
    keys = {d['key'] for d in r['danger_zones']}
    assert 'legitimacy_incentive_collapse' in keys
    assert '🛑' in r['summary']


def test_danger_zone_multiple_hits():
    # 全面崩溃向量应命中多个签名
    from agent.tools.history_compare import detect_danger_zones
    r = detect_danger_zones({'D1': 1, 'D2': 1, 'D3': 1, 'D4': 1, 'D5': 1, 'D6': 1, 'D7': 1})
    assert len(r['danger_zones']) == 6


def test_survival_zone_healthy_signature():
    from agent.tools.history_compare import detect_danger_zones
    r = detect_danger_zones({'D1': 4, 'D2': 4, 'D3': 4, 'D4': 4, 'D5': 4, 'D6': 4, 'D7': 4})
    assert not r['danger_zones']
    assert len(r['survival_zones']) == 4
    assert '✅' in r['summary']


def test_no_zone_hit_in_middle_range():
    from agent.tools.history_compare import detect_danger_zones
    r = detect_danger_zones({'D1': 3, 'D2': 3, 'D3': 3, 'D4': 3, 'D5': 3, 'D6': 3, 'D7': 3})
    assert not r['danger_zones'] and not r['survival_zones']


def test_missing_dimension_not_hit():
    # 缺维不下判断（保守）：只有 D5 低、D2 缺失 → 不命中双崩塌
    from agent.tools.history_compare import detect_danger_zones
    r = detect_danger_zones({'D5': 1})
    assert not r['danger_zones']


# ── relational 系统类型 ──

def test_relational_in_system_types():
    from agent.tools.query_generator import SYSTEM_TYPES
    assert 'relational' in SYSTEM_TYPES


def test_relational_queries_generated():
    from agent.tools.query_generator import generate_queries
    r = generate_queries('Iran-US-Israel conflict', 'relational', date_str='20260611')
    keys = {p['perspective'] for p in r['perspectives']}
    # 关系系统核心视角：升级/缓和/红线/威慑/第三方
    assert {'escalation_events', 'deescalation_diplomacy', 'parties_official',
            'military_balance', 'third_party_mediators'} <= keys
    # 'iran' 关键词应触发波斯语本地视角（复用 geopolitical 的语言节）
    assert 'fa' in r['detected_languages']
    assert any(p['perspective'].startswith('fa_') for p in r['perspectives'])


def test_relational_escalation_deescalation_batched_together():
    # 升级与缓和是同一互动的两面，必须同批派发给同一 Researcher
    from agent.tools.query_generator import generate_queries, group_into_batches
    r = generate_queries('India Pakistan standoff', 'relational', date_str='20260611')
    batches = group_into_batches(r)
    for b in batches:
        keys = {p['perspective'] for p in b['perspectives']}
        if 'escalation_events' in keys:
            assert 'deescalation_diplomacy' in keys
            break
    else:
        raise AssertionError('escalation_events 未出现在任何批次')


def test_relational_chinese_perspectives_available():
    from agent.tools.query_generator import generate_queries
    r = generate_queries('中美战略竞争', 'relational', date_str='20260611')
    assert 'zh' in r['detected_languages']
    assert any(p['perspective'].startswith('zh_') and p['priority'] == 1
               for p in r['perspectives'])


def test_analogy_library_has_relational_cases():
    from agent.tools.history_compare import _load_cases
    cases = _load_cases()
    rel = [c for c in cases if c['system_type'] == 'relational']
    assert len(rel) >= 8
    assert all(set(c['scores']) == {'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7'} for c in rel)


def test_relational_prewar_vector_matches_collapse_cases():
    # 1914 式向量（刚性纠缠+先发激励+信号反转）的同类型 top 类比应是关系系统崩溃案例
    from agent.tools.history_compare import find_analogies
    scores = {'D1': 1, 'D2': 1, 'D3': 1, 'D4': 2, 'D5': 2, 'D6': 1, 'D7': 2}
    results = find_analogies(scores, system_type='relational', top_k=3)
    names = {r['name'] for r in results}
    assert names & {'July Crisis / European alliance system (1914)',
                    'Russia-NATO/Ukraine (2021 eve of war)'}


def test_relational_managed_rivalry_matches_detente_not_war():
    # 管理良好的对抗（红线清晰/渠道通畅）应匹配缓和期，而非 1914
    from agent.tools.history_compare import find_analogies
    scores = {'D1': 4, 'D2': 3, 'D3': 4, 'D4': 4, 'D5': 3, 'D6': 3, 'D7': 4}
    results = find_analogies(scores, system_type='relational', top_k=3)
    names = {r['name'] for r in results}
    assert 'US-USSR Détente (1972)' in names
    assert 'July Crisis / European alliance system (1914)' not in names


def test_chinese_exonym_triggers_local_language():
    # 用户以中文命名关系系统时，当事方本地语言必须被检测到
    from agent.tools.query_generator import detect_languages
    assert detect_languages('伊朗-美国-以色列冲突') >= {'zh', 'fa'}
    assert detect_languages('沙特-伊朗代理战争') >= {'zh', 'ar', 'fa'}
    assert detect_languages('俄乌战争') >= {'zh', 'ru'}
    assert detect_languages('朝鲜半岛局势') >= {'zh', 'ko'}
