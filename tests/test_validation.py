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


# ── P1: build_source_audit_html ──

def test_build_audit_itemizes_urls_by_tier():
    from agent.store.db import build_source_audit_html
    sources = [
        {'title': '官方公告', 'url': 'https://gov.example/a', 'tier': 1, 'date': '2026-05-01'},
        {'title': '路透报道', 'url': 'https://reuters.com/b', 'tier': 'T2', 'date': '2026-05-02'},
        {'title': '推文', 'url': 'https://x.com/c', 'tier': 3, 'date': None},
    ]
    html = build_source_audit_html(sources)
    assert '<details>' in html and '</details>' in html
    assert 'https://gov.example/a' in html
    assert 'href="https://reuters.com/b"' in html
    assert 'T1' in html and 'T2' in html and 'T3' in html
    assert '信源审计（3 条' in html


def test_build_audit_dedupes_and_escapes():
    from agent.store.db import build_source_audit_html
    sources = [
        {'title': 'A & <b>', 'url': 'https://e/x', 'tier': 1, 'date': '2026-01-01'},
        {'title': '重复', 'url': 'https://e/x', 'tier': 1, 'date': '2026-01-01'},  # 同 URL 去重
    ]
    html = build_source_audit_html(sources)
    assert html.count('https://e/x') == 1       # 去重
    assert '&amp;' in html and '&lt;b&gt;' in html  # 转义


# ── P2: process_warnings (non-blocking) ──

def test_process_warnings_missing_metadata():
    from agent.store.db import process_warnings
    w = process_warnings(_valid_analysis())
    assert any('process_metadata' in x for x in w)


def test_process_warnings_flags_skipped_ach_and_round2():
    from agent.store.db import process_warnings
    a = _valid_analysis()
    a['process_metadata'] = {'ach_run': False, 'round2_triggered': True, 'round2_run': False,
                             'source_verification_done': True}
    w = process_warnings(a)
    assert any('ACH' in x for x in w)
    assert any('Round2' in x for x in w)


def test_process_warnings_confidence_ceiling():
    from agent.store.db import process_warnings
    a = _valid_analysis()
    a['process_metadata'] = {'ach_run': True, 'unresolved_high_contradictions': 2,
                             'confidence_label': 'high'}
    w = process_warnings(a)
    assert any('封顶' in x or 'partial' in x for x in w)


def test_process_warnings_clean_when_all_good():
    from agent.store.db import process_warnings
    a = _valid_analysis()
    a['process_metadata'] = {'ach_run': True, 'round2_triggered': False, 'round2_run': False,
                             'source_verification_done': True, 'unresolved_high_contradictions': 0}
    a['dimension_evidence'] = {d: [{'title': 't', 'url': f'https://e/{d}'}]
                               for d in ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']}
    a['source_verification'] = [{'url': 'https://e/D1', 'status': 'confirmed'}]
    a['key_claims'] = [{'claim': '良好佐证的断言', 'loads': ['D1'],
                        'sources': [{'url': 'https://a/1', 'tier': 1},
                                    {'url': 'https://b/2', 'tier': 2}]}]  # 多源高tier → 不触发
    assert process_warnings(a) == []


def test_process_warnings_flags_missing_dimension_evidence():
    # dimension_evidence 缺失须被点名；且两块都缺时，该警告不能被 pm 早返回吞掉
    from agent.store.db import process_warnings
    a = _valid_analysis()  # 无 dimension_evidence、无 process_metadata
    w = process_warnings(a)
    assert any('dimension_evidence' in x for x in w)
    assert any('process_metadata' in x for x in w)


# ── P3: dimension_evidence strict-when-present ──

def test_dimension_evidence_present_and_valid_passes():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['dimension_evidence'] = {
        d: [{'title': 't', 'url': f'https://e/{d}'}] for d in
        ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']
    }
    assert validate_analysis(a) == []


def test_dimension_evidence_missing_url_rejected():
    from agent.store.db import validate_analysis
    a = _valid_analysis()
    a['dimension_evidence'] = {
        d: [{'title': 't', 'url': f'https://e/{d}'}] for d in
        ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']
    }
    a['dimension_evidence']['D6'] = [{'title': '无链接'}]  # 缺 url
    errors = validate_analysis(a)
    assert any('D6' in e for e in errors)


def test_dimension_evidence_absent_is_not_error():
    from agent.store.db import validate_analysis
    assert validate_analysis(_valid_analysis()) == []  # 不带 dimension_evidence 仍通过


# ── CLI: --build-audit ──

def test_cli_build_audit_via_stdin():
    brief = {'sources': [{'title': 'X', 'url': 'https://e/1', 'tier': 1, 'date': '2026-05-01'}]}
    r = subprocess.run(
        [sys.executable, '-m', 'agent.agent', '--build-audit'],
        cwd=str(ROOT), input=json.dumps(brief), capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert 'https://e/1' in r.stdout and '<details>' in r.stdout


# ── P6b: freshness / staleness warnings ──

def test_process_warnings_staleness_gap():
    from agent.store.db import process_warnings
    a = _valid_analysis()
    a['dimension_evidence'] = {d: [{'title': 't', 'url': f'https://e/{d}'}]
                               for d in ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']}
    a['process_metadata'] = {'ach_run': True, 'source_verification_done': True,
                             'latest_source_date': '2026-05-20', 'as_of_date': '2026-06-01',
                             'breaking_event_sweep_done': True}
    w = process_warnings(a)
    assert any('信息滞后' in x for x in w)


def test_process_warnings_breaking_event_sweep_skipped():
    from agent.store.db import process_warnings
    a = _valid_analysis()
    a['dimension_evidence'] = {d: [{'title': 't', 'url': f'https://e/{d}'}]
                               for d in ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']}
    a['process_metadata'] = {'ach_run': True, 'source_verification_done': True,
                             'latest_source_date': '2026-06-01', 'as_of_date': '2026-06-01',
                             'breaking_event_sweep_done': False}
    w = process_warnings(a)
    assert any('突发事件扫描' in x for x in w)


# ── 内容可信度：source verification sampling + 强制记录 ──

def test_select_verification_sample_prioritizes_t1_and_numbers():
    from agent.store.db import select_verification_sample
    sources = [
        {'title': 'blog post', 'url': 'https://b/1', 'tier': 3, 'excerpt': '泛泛而谈'},
        {'title': 'gov report 39 executions', 'url': 'https://g/2', 'tier': 1, 'excerpt': '39 起'},
        {'title': 'news no number', 'url': 'https://n/3', 'tier': 2, 'excerpt': '无数字'},
    ]
    sample = select_verification_sample(sources, n=2)
    urls = [s['url'] for s in sample]
    assert 'https://g/2' == urls[0]      # T1 + 含数字 → 最优先
    assert 'https://b/1' not in urls     # T3 无数字 → 落选


def test_select_verification_sample_dedups_and_limits():
    from agent.store.db import select_verification_sample
    sources = [{'title': 'a', 'url': 'https://x/1', 'tier': 1}] * 3 + \
              [{'title': 'b', 'url': 'https://x/2', 'tier': 2}]
    sample = select_verification_sample(sources, n=5)
    assert len(sample) == 2  # 去重后只剩 2 个 url


def test_build_audit_annotates_verification_badges():
    from agent.store.db import build_source_audit_html
    sources = [{'title': 'A', 'url': 'https://e/1', 'tier': 1, 'date': '2026-05-01'},
               {'title': 'B', 'url': 'https://e/2', 'tier': 2, 'date': '2026-05-02'}]
    verifications = [{'url': 'https://e/1', 'status': 'confirmed'},
                     {'url': 'https://e/2', 'status': 'dead'}]
    html = build_source_audit_html(sources, verifications=verifications)
    assert '✓核实' in html
    assert '✗失效' in html
    assert '已抽查核验 2 条' in html


def test_process_warnings_verification_claimed_without_records():
    from agent.store.db import process_warnings
    a = _valid_analysis()
    a['dimension_evidence'] = {d: [{'title': 't', 'url': f'https://e/{d}'}]
                               for d in ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']}
    a['process_metadata'] = {'ach_run': True, 'source_verification_done': True}  # 声称做了但无记录
    w = process_warnings(a)
    assert any('缺 source_verification 记录' in x for x in w)


def test_process_warnings_surfaces_dead_sources():
    from agent.store.db import process_warnings
    a = _valid_analysis()
    a['dimension_evidence'] = {d: [{'title': 't', 'url': f'https://e/{d}'}]
                               for d in ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']}
    a['process_metadata'] = {'ach_run': True, 'source_verification_done': True}
    a['source_verification'] = [{'url': 'https://e/1', 'status': 'confirmed'},
                                {'url': 'https://e/2', 'status': 'mismatch'}]
    w = process_warnings(a)
    assert any('失效/不符' in x for x in w)


def test_process_warnings_verification_field_omitted_warns_not_run():
    # 关键回归：完全省略 source_verification_done 不能静默跳过门控
    from agent.store.db import process_warnings
    a = _valid_analysis()
    a['dimension_evidence'] = {d: [{'title': 't', 'url': f'https://e/{d}'}]
                               for d in ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']}
    a['process_metadata'] = {'ach_run': True}  # 无 source_verification_done 字段
    w = process_warnings(a)
    assert any('信源核验门控' in x and '未执行' in x for x in w)


# ── 综述类错误：claims ledger triage + 独立复核告警 ──

def _claim(claim, loads, sources, ic=None):
    c = {'claim': claim, 'loads': loads, 'sources': sources}
    if ic:
        c['independent_check'] = ic
    return c


def test_triage_flags_loadbearing_single_t3_claim():
    # Zolghadr 类：载荷性 + 单一 T3 源 → 必须进分诊
    from agent.store.db import triage_claims_for_factcheck
    claims = [
        _claim('SNSC 秘书长是 X', ['D7'], [{'url': 'https://t3/1', 'tier': 3}]),  # 载荷+单T3
        _claim('GDP -6.1%', ['D2'], [{'url': 'https://a/1', 'tier': 2}, {'url': 'https://b/2', 'tier': 1}]),  # 多源高tier
        _claim('无关琐事', [], [{'url': 'https://t3/9', 'tier': 3}]),  # 不载荷 → 噪音
    ]
    t = triage_claims_for_factcheck(claims)
    claims_out = [x['claim'] for x in t]
    assert 'SNSC 秘书长是 X' in claims_out      # 进分诊
    assert 'GDP -6.1%' not in claims_out         # 佐证充分，不进
    assert '无关琐事' not in claims_out           # 不载荷，不进


def test_triage_skips_already_checked_and_caps():
    from agent.store.db import triage_claims_for_factcheck
    claims = [_claim(f'c{i}', ['D1'], [{'url': f'https://t/{i}', 'tier': 3}]) for i in range(8)]
    claims[0]['independent_check'] = {'status': 'confirmed'}  # 已复核 → 跳过
    t = triage_claims_for_factcheck(claims, max_n=5)
    assert len(t) == 5
    assert 'c0' not in [x['claim'] for x in t]


def test_triage_orders_by_stakes():
    from agent.store.db import triage_claims_for_factcheck
    claims = [
        _claim('low', ['D1'], [{'url': 'https://t/1', 'tier': 3}]),
        _claim('high', ['D1', 'D7', 'risk_node:1'], [{'url': 'https://t/2', 'tier': 3}]),
    ]
    t = triage_claims_for_factcheck(claims)
    assert t[0]['claim'] == 'high'   # loads 多 → 优先


def test_process_warnings_contradicted_claim_is_strong():
    from agent.store.db import process_warnings
    a = _valid_analysis()
    a['dimension_evidence'] = {d: [{'title': 't', 'url': f'https://e/{d}'}]
                               for d in ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']}
    a['process_metadata'] = {'ach_run': True, 'source_verification_done': True}
    a['source_verification'] = [{'url': 'https://e/D1', 'status': 'confirmed'}]
    a['key_claims'] = [_claim('SNSC 秘书长是 BadName', ['D7'],
                              [{'url': 'https://t3/x', 'tier': 3}],
                              ic={'status': 'contradicted', 'note': '应为 Zolghadr'})]
    w = process_warnings(a)
    assert any('推翻' in x and 'D7' in x for x in w)


def test_process_warnings_missing_key_claims_nudge():
    from agent.store.db import process_warnings
    a = _valid_analysis()  # full 模式、无 key_claims
    w = process_warnings(a)
    assert any('key_claims' in x for x in w)
