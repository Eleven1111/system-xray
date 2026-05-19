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
