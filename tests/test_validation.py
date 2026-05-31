import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _valid_analysis():
    return {
        'dimension_scores': {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4, 'D7': 3},
        'overall_score': 3.4,
        'output_mode': 'full',
        'predictions': [
            {
                'prediction': '某事会发生',
                'falsification_condition': '若观察到 X 则失败',
                'time_horizon': '2026-12-31',
                'confidence': 0.7,
                'dimension_link': 'D2',
                'source_step': 'dimension_analysis',
            }
        ],
    }


# ── validate_analysis ──

def test_valid_analysis_passes():
    from agent.store.db import validate_analysis
    assert validate_analysis(_valid_analysis()) == []


def test_missing_dimension_scores():
    from agent.store.db import validate_analysis
    errors = validate_analysis({})
    assert any('dimension_scores' in e for e in errors)


def test_six_dimensions_legacy_shape_passes():
    # D7 是后增维度；历史上 6 维分析合法，不应被拒
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    del a['dimension_scores']['D7']
    assert validate_analysis(a) == []


def test_empty_dimension_scores_rejected():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['dimension_scores'] = {}
    errors = validate_analysis(a)
    assert any('不能为空' in e for e in errors)


def test_brief_mode_analysis_passes():
    # brief 模式仍内部完成七维评分，只是报告精简——持久化 shape 不变
    from agent.store.db import validate_analysis
    brief = {
        'dimension_scores': {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4, 'D7': 3},
        'overall_score': 3.4,
        'output_mode': 'brief',
        'risk_nodes': ['节点1', '节点2', '节点3'],
        # brief 模式按 SKILL.md 跳过 ACH，但维度评分齐全；预测可选
    }
    assert validate_analysis(brief) == []


def test_descriptive_dimension_keys_rejected():
    # D1_boundary_topology 这类描述性键会让 radar/analogy 工具失效，应拒绝
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['dimension_scores'] = {f'{k}_desc': v for k, v in a['dimension_scores'].items()}
    errors = validate_analysis(a)
    assert any('非法维度键' in e for e in errors)


def test_score_out_of_range():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['dimension_scores']['D1'] = 9
    errors = validate_analysis(a)
    assert any('D1' in e and '1-5' in e for e in errors)


def test_unknown_dimension_key():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['dimension_scores']['D8'] = 3
    errors = validate_analysis(a)
    assert any('D8' in e for e in errors)


def test_prediction_missing_required_field():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    del a['predictions'][0]['falsification_condition']
    errors = validate_analysis(a)
    assert any('falsification_condition' in e for e in errors)


def test_prediction_relative_date_rejected():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['predictions'][0]['time_horizon'] = '6 个月内'
    errors = validate_analysis(a)
    assert any('time_horizon' in e for e in errors)


def test_prediction_confidence_out_of_range():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['predictions'][0]['confidence'] = 1.5
    errors = validate_analysis(a)
    assert any('confidence' in e for e in errors)


def test_prediction_bad_dimension_link():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['predictions'][0]['dimension_link'] = 'D9'
    errors = validate_analysis(a)
    assert any('dimension_link' in e for e in errors)


def test_prediction_bad_source_step():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['predictions'][0]['source_step'] = 'made_up'
    errors = validate_analysis(a)
    assert any('source_step' in e for e in errors)


# ── save_analysis validation gate ──

def test_save_analysis_rejects_invalid(tmp_path):
    from agent.store.db import save_analysis
    with pytest.raises(ValueError):
        save_analysis('Test', 'public_company', {'dimension_scores': {'D1': 99}},
                      date_str='20260101')


def test_save_analysis_validate_false_bypasses(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    # patch the module-level helper used by save_analysis
    path = db.save_analysis('Test', 'public_company',
                            {'dimension_scores': {'D1': 99}},
                            date_str='20260101', validate=False)
    assert Path(path).exists()


def test_save_analysis_accepts_valid(tmp_path, monkeypatch):
    import agent.store.db as db
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    path = db.save_analysis('Test', 'public_company', _valid_analysis(),
                            date_str='20260101')
    assert Path(path).exists()
    saved = json.loads(Path(path).read_text())
    assert saved['dimension_scores']['D7'] == 3


# ── CLI persist via stdin (no inline interpolation) ──

def _run_cli(args, stdin_text=None):
    return subprocess.run(
        [sys.executable, '-m', 'agent.agent', *args],
        cwd=str(ROOT), input=stdin_text, capture_output=True, text=True,
    )


def test_cli_validate_passes_via_stdin():
    r = _run_cli(['--validate'], stdin_text=json.dumps(_valid_analysis()))
    assert r.returncode == 0
    assert '校验通过' in r.stdout


def test_cli_validate_fails_via_stdin():
    bad = {'dimension_scores': {'D1': 99}}
    r = _run_cli(['--validate'], stdin_text=json.dumps(bad))
    assert r.returncode == 1
    assert '校验失败' in r.stdout


def test_cli_radar_via_stdin():
    scores = {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4, 'D7': 3}
    r = _run_cli(['--radar'], stdin_text=json.dumps(scores))
    assert r.returncode == 0
    assert '<svg' in r.stdout
    assert '权力拓扑 3/5' in r.stdout


def test_cli_save_html_handles_tricky_payload(tmp_path):
    # 报告正文含中文引号、反引号、单双引号、三引号——内联 -c 会炸，CLI 不应炸
    tricky = (
        '<div class="exec-summary"><h2>摘要</h2>'
        "<p>它说\"X\"，又说'Y'，还有 `code` 和 '''triple'''，"
        '以及 $VAR 和 \\反斜杠。</p></div>'
    )
    out_dir = tmp_path / 'obsidian'
    # save_html_report 默认写 OBSIDIAN_DIR；这里直接调函数验证 payload 安全
    from agent.store.db import save_html_report
    path = save_html_report('诡异系统', 'public_company', tricky,
                            date_str='2026-01-01', output_dir=out_dir, title='测试标题')
    html = Path(path).read_text(encoding='utf-8')
    assert '它说"X"' in html
    assert '`code`' in html
    assert "'''triple'''" in html
