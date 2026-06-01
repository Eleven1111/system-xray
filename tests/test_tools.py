import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_dimension_labels_has_d7_in_db():
    from agent.store.db import _DIMENSION_LABELS
    assert 'D7' in _DIMENSION_LABELS
    assert _DIMENSION_LABELS['D7'] == '权力拓扑'


def test_dimension_labels_has_d7_in_compare():
    from agent.tools.history_compare import DIMENSION_LABELS
    assert 'D7' in DIMENSION_LABELS
    assert DIMENSION_LABELS['D7'] == '权力拓扑'


def test_radar_svg_seven_dimensions():
    from agent.store.db import build_radar_svg
    scores = {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4, 'D7': 3}
    svg = build_radar_svg(scores)
    assert '<svg' in svg
    assert '权力拓扑' in svg
    assert 'D7' not in svg or '权力拓扑 3/5' in svg


def test_radar_svg_six_dimensions_still_works():
    from agent.store.db import build_radar_svg
    scores = {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4}
    svg = build_radar_svg(scores)
    assert '<svg' in svg
    assert '权力拓扑' not in svg


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
