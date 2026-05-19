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
