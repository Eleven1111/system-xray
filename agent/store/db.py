"""
分析结果持久化存储

存储路径：~/.system_pathology/data/{safe_system_name}/{YYYYMMDD}.json
Obsidian 导出（MD 素材 + HTML 报告）：
  /Users/na/Library/Mobile Documents/iCloud~md~obsidian/Documents/System Pathology/
"""

import json
import math
from datetime import datetime
from pathlib import Path
from textwrap import dedent

DATA_DIR = Path.home() / '.system_pathology' / 'data'
OBSIDIAN_DIR = Path('/Users/na/Library/Mobile Documents/iCloud~md~obsidian/Documents/System Pathology')


def _system_dir(system_name: str) -> Path:
    safe = system_name.replace('/', '_').replace(' ', '_').replace(':', '_').replace('\\', '_')
    return DATA_DIR / safe


def save_analysis(system_name: str, system_type: str, analysis: dict, date_str: str | None = None) -> str:
    """
    保存分析结果，返回文件路径。

    analysis 应包含字段：
      dimension_scores: {D1: float, D2: float, ...}
      overall_score: float
      risk_nodes: [str]
      source_coverage: {perspective: bool}
      output_mode: 'full' | 'brief'
      predictions: [{prediction, falsification_condition, time_horizon, ...}]  （可选）
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    system_dir = _system_dir(system_name)
    system_dir.mkdir(parents=True, exist_ok=True)

    filepath = system_dir / f'{date_str}.json'
    record = {
        'system_name':   system_name,
        'system_type':   system_type,
        'analysis_date': date_str,
        'saved_at':      datetime.now().isoformat(),
        **analysis,
    }
    filepath.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    return str(filepath)


def load_latest(system_name: str) -> dict | None:
    """加载最近一次分析结果。"""
    system_dir = _system_dir(system_name)
    if not system_dir.exists():
        return None
    files = sorted(system_dir.glob('*.json'), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text())


def load_analysis(system_name: str, date_str: str) -> dict | None:
    """加载指定日期的分析结果。"""
    filepath = _system_dir(system_name) / f'{date_str}.json'
    if not filepath.exists():
        return None
    return json.loads(filepath.read_text())


def load_predictions(system_name: str) -> list[dict]:
    """
    加载最近一次分析中的预测列表。

    返回预测数组（可能为空）。向后兼容：旧 JSON 文件没有 predictions 字段时返回 []。
    """
    latest = load_latest(system_name)
    if latest is None:
        return []
    return latest.get('predictions', [])


def save_to_obsidian(
    system_name: str, system_type: str, report_markdown: str,
    date_str: str | None = None, output_dir: Path | None = None,
) -> str:
    """
    将诊断报告 Markdown 保存到 Obsidian 仓库。

    返回保存路径。report_markdown 应为完整的 Markdown 文本（含正文，不含 frontmatter）。
    output_dir: 可选，覆盖默认 OBSIDIAN_DIR（用于测试隔离）。
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    target_dir = output_dir or OBSIDIAN_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    safe = system_name.replace('/', '-').replace('\\', '-').replace(':', '-')
    filename = f'{date_str} {safe} 系统诊断.md'
    filepath = target_dir / filename

    frontmatter = f"""---
title: "{system_name} 系统诊断报告"
date: {date_str}
type: system-pathology
system: "{system_name}"
system_type: "{system_type}"
tags:
  - system-pathology
  - {system_type}
---

"""
    filepath.write_text(frontmatter + report_markdown, encoding='utf-8')
    return str(filepath)


def save_research_materials(
    system_name: str,
    system_type: str,
    research_brief: dict,
    date_str: str | None = None,
    output_dir: Path | None = None,
) -> str:
    """
    保存 Research Brief 原始素材为 MD 格式到 Obsidian。

    research_brief 应包含：
      sources: [{query, title, url, excerpt, tier, date}]
      contradictions: [{description, source_a, source_b, significance}]
      no_source_perspectives: [str]
      stale_perspectives: [str]
      confidence: str
      confidence_rationale: str
    output_dir: 可选，覆盖默认 OBSIDIAN_DIR（用于测试隔离）。
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    target_dir = output_dir or OBSIDIAN_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    safe = system_name.replace('/', '-').replace('\\', '-').replace(':', '-')
    filename = f'{date_str} {safe} 研究素材.md'
    filepath = target_dir / filename

    lines = [
        '---',
        f'title: "{system_name} 研究素材"',
        f'date: {date_str}',
        'type: research-materials',
        f'system: "{system_name}"',
        f'system_type: "{system_type}"',
        'tags:',
        '  - system-pathology',
        '  - research-materials',
        f'  - {system_type}',
        '---',
        '',
        f'# {system_name} — 研究素材',
        f'**采集日期：** {date_str}',
        '',
    ]

    sources = research_brief.get('sources', [])
    if sources:
        lines += ['## 信源清单', '']
        for s in sources:
            tier_tag = f'T{s.get("tier", "?")}'
            date_tag = s.get('date', '日期未知')
            lines.append(f'### [{tier_tag}] {s.get("title", "无标题")}')
            lines.append(f'- **查询：** `{s.get("query", "")}`')
            if s.get('url'):
                lines.append(f'- **URL：** {s["url"]}')
            lines.append(f'- **日期：** {date_tag}')
            if s.get('excerpt'):
                lines.append(f'- **摘录：** {s["excerpt"]}')
            lines.append('')

    contradictions = research_brief.get('contradictions', [])
    if contradictions:
        lines += ['## 矛盾信号', '']
        for c in contradictions:
            sig = c.get('significance', 'medium').upper()
            lines.append(f'### [{sig}] {c.get("description", "")}')
            lines.append(f'- 来源 A: {c.get("source_a", "")}')
            lines.append(f'- 来源 B: {c.get("source_b", "")}')
            lines.append('')

    no_src = research_brief.get('no_source_perspectives', [])
    if no_src:
        lines += ['## 未覆盖视角', '']
        for p in no_src:
            lines.append(f'- {p}')
        lines.append('')

    stale = research_brief.get('stale_perspectives', [])
    if stale:
        lines += ['## 过期视角', '']
        for p in stale:
            lines.append(f'- {p}')
        lines.append('')

    conf = research_brief.get('confidence', 'unknown')
    rationale = research_brief.get('confidence_rationale', '')
    lines += [
        '## 置信度评估',
        f'**等级：** {conf}',
        f'**理由：** {rationale}',
    ]

    filepath.write_text('\n'.join(lines), encoding='utf-8')
    return str(filepath)


# ── Brookings/CSIS 智库风格 HTML 模板 ──

_HTML_TEMPLATE = dedent("""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Source+Serif+4:ital,wght@0,400;0,600;0,700;1,400&display=swap');

  :root {{
    --blue-900: #0a2540;
    --blue-700: #1a3a5c;
    --blue-500: #2563eb;
    --blue-100: #dbeafe;
    --blue-50:  #eff6ff;
    --red-600:  #dc2626;
    --amber-500:#f59e0b;
    --green-600:#16a34a;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-300: #d1d5db;
    --gray-600: #4b5563;
    --gray-800: #1f2937;
    --font-serif: 'Source Serif 4', 'Noto Serif SC', 'Georgia', serif;
    --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: var(--font-serif);
    color: var(--gray-800);
    background: #fff;
    line-height: 1.7;
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 32px 80px;
  }}

  /* ── 顶部标识条 ── */
  .header-bar {{
    border-top: 4px solid var(--blue-900);
    padding-top: 24px;
    margin-bottom: 40px;
  }}
  .header-bar .institute {{
    font-family: var(--font-sans);
    font-size: 12px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--gray-600);
    margin-bottom: 8px;
  }}
  .header-bar h1 {{
    font-size: 28px;
    font-weight: 700;
    color: var(--blue-900);
    line-height: 1.3;
    margin-bottom: 8px;
  }}
  .header-bar .meta {{
    font-family: var(--font-sans);
    font-size: 13px;
    color: var(--gray-600);
  }}

  /* ── 执行摘要卡片 ── */
  .exec-summary {{
    background: var(--blue-50);
    border-left: 4px solid var(--blue-500);
    padding: 24px 28px;
    margin: 32px 0;
    border-radius: 0 8px 8px 0;
  }}
  .exec-summary h2 {{
    font-size: 16px;
    font-weight: 700;
    color: var(--blue-700);
    margin-bottom: 12px;
    font-family: var(--font-sans);
    text-transform: uppercase;
    letter-spacing: 1px;
  }}

  /* ── 章节 ── */
  h2 {{
    font-size: 20px;
    color: var(--blue-900);
    border-bottom: 2px solid var(--blue-900);
    padding-bottom: 6px;
    margin: 40px 0 16px;
  }}
  h3 {{
    font-size: 17px;
    color: var(--blue-700);
    margin: 24px 0 10px;
  }}
  h4 {{
    font-size: 15px;
    color: var(--gray-600);
    margin: 16px 0 8px;
    font-family: var(--font-sans);
  }}

  p {{ margin: 10px 0; }}
  ul, ol {{ margin: 8px 0 8px 24px; }}
  li {{ margin: 4px 0; }}

  /* ── 表格（zebra stripes） ── */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 14px;
  }}
  thead {{
    background: var(--blue-900);
    color: #fff;
  }}
  th {{
    padding: 10px 14px;
    text-align: left;
    font-family: var(--font-sans);
    font-weight: 600;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  td {{
    padding: 10px 14px;
    border-bottom: 1px solid var(--gray-200);
  }}
  tbody tr:nth-child(even) {{
    background: var(--gray-100);
  }}

  /* ── 风险 callout ── */
  .callout {{
    border-radius: 6px;
    padding: 16px 20px;
    margin: 16px 0;
    font-size: 14px;
  }}
  .callout-red {{
    background: #fef2f2;
    border-left: 4px solid var(--red-600);
  }}
  .callout-amber {{
    background: #fffbeb;
    border-left: 4px solid var(--amber-500);
  }}
  .callout-green {{
    background: #f0fdf4;
    border-left: 4px solid var(--green-600);
  }}
  .callout-title {{
    font-weight: 700;
    font-family: var(--font-sans);
    margin-bottom: 6px;
  }}

  /* ── 雷达图容器 ── */
  .radar-container {{
    text-align: center;
    margin: 24px 0;
  }}
  .radar-container svg {{
    max-width: 400px;
  }}

  /* ── 折叠信源审计 ── */
  details {{
    margin: 16px 0;
    border: 1px solid var(--gray-200);
    border-radius: 6px;
  }}
  summary {{
    padding: 12px 16px;
    background: var(--gray-100);
    cursor: pointer;
    font-family: var(--font-sans);
    font-weight: 600;
    font-size: 14px;
    border-radius: 6px;
  }}
  details[open] summary {{
    border-bottom: 1px solid var(--gray-200);
    border-radius: 6px 6px 0 0;
  }}
  details .content {{
    padding: 16px;
    font-size: 14px;
  }}

  /* ── 评分徽章 ── */
  .score-badge {{
    display: inline-block;
    font-family: var(--font-sans);
    font-weight: 700;
    font-size: 13px;
    padding: 2px 10px;
    border-radius: 12px;
    color: #fff;
  }}
  .score-1 {{ background: var(--red-600); }}
  .score-2 {{ background: #ea580c; }}
  .score-3 {{ background: var(--amber-500); color: var(--gray-800); }}
  .score-4 {{ background: var(--blue-500); }}
  .score-5 {{ background: var(--green-600); }}

  /* ── 预测卡片 ── */
  .prediction-review,
  .predictions {{
    margin: 32px 0;
  }}
  .prediction-card {{
    border: 1px solid var(--gray-200);
    border-left: 4px solid var(--blue-500);
    border-radius: 6px;
    padding: 16px 20px;
    margin: 12px 0;
    background: var(--gray-50);
  }}
  .prediction-title {{
    font-family: var(--font-sans);
    font-weight: 600;
    font-size: 15px;
    margin-bottom: 8px;
    color: var(--gray-800);
  }}
  .prediction-meta {{
    font-family: var(--font-sans);
    font-size: 13px;
    color: var(--gray-600);
    line-height: 1.6;
  }}
  .prediction-link {{
    font-family: var(--font-sans);
    font-size: 12px;
    color: var(--blue-500);
    margin-top: 6px;
  }}

  /* ── 页脚 ── */
  .footer {{
    margin-top: 60px;
    padding-top: 20px;
    border-top: 1px solid var(--gray-300);
    font-family: var(--font-sans);
    font-size: 12px;
    color: var(--gray-600);
    text-align: center;
  }}

  @media print {{
    body {{ padding: 20px; font-size: 11pt; }}
    .header-bar {{ border-top-width: 2px; }}
    details {{ page-break-inside: avoid; }}
    table {{ font-size: 10pt; }}
  }}
</style>
</head>
<body>

<div class="header-bar">
  <div class="institute">SYSTEM PATHOLOGY DIAGNOSTIC REPORT</div>
  <h1>{title}</h1>
  <div class="meta">{date} &nbsp;|&nbsp; System Type: {system_type} &nbsp;|&nbsp; Generated by System Pathology Framework</div>
</div>

{body}

<div class="footer">
  <p>System Pathology Framework &mdash; Cross-disciplinary diagnostic analysis</p>
  <p>This report is auto-generated. Source verification audit attached. Confidence levels noted per section.</p>
</div>

</body>
</html>
""")


_DIMENSION_LABELS = {
    'D1': '边界拓扑',
    'D2': '激励架构',
    'D3': '信息神经',
    'D4': '时间代谢',
    'D5': '合法性叙事',
    'D6': '耦合架构',
}


def build_radar_svg(scores: dict[str, int | float], size: int = 380) -> str:
    """
    从六维评分生成内联 SVG 雷达图。

    scores: {'D1': 3, 'D2': 4, 'D3': 2, 'D4': 5, 'D5': 3, 'D6': 4}
    返回可直接嵌入 <div class="radar-container"> 的 SVG 字符串。
    """
    cx, cy = size / 2, size / 2
    r_max = size / 2 - 50
    n = 6
    angle_offset = -math.pi / 2

    def polar(level: float, i: int) -> tuple[float, float]:
        theta = angle_offset + 2 * math.pi * i / n
        r = r_max * level / 5
        return cx + r * math.cos(theta), cy + r * math.sin(theta)

    lines: list[str] = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}">'
    )

    for level in range(1, 6):
        pts = ' '.join(f'{polar(level, i)[0]:.1f},{polar(level, i)[1]:.1f}' for i in range(n))
        opacity = '0.15' if level < 5 else '0.3'
        lines.append(
            f'  <polygon points="{pts}" fill="none" stroke="#94a3b8" '
            f'stroke-width="0.8" opacity="{opacity}" />'
        )

    for i in range(n):
        x, y = polar(5, i)
        lines.append(
            f'  <line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
            f'stroke="#94a3b8" stroke-width="0.5" opacity="0.3" />'
        )

    dim_keys = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6']
    data_pts = []
    for i, key in enumerate(dim_keys):
        val = scores.get(key, 0)
        val = max(0, min(5, val))
        data_pts.append(polar(val, i))

    pts_str = ' '.join(f'{x:.1f},{y:.1f}' for x, y in data_pts)
    lines.append(
        f'  <polygon points="{pts_str}" fill="rgba(37,99,235,0.2)" '
        f'stroke="#2563eb" stroke-width="2" />'
    )

    for i, (x, y) in enumerate(data_pts):
        lines.append(f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#2563eb" />')

    for i, key in enumerate(dim_keys):
        lx, ly = polar(5.8, i)
        val = scores.get(key, 0)
        label = _DIMENSION_LABELS.get(key, key)
        anchor = 'middle'
        if lx < cx - 10:
            anchor = 'end'
        elif lx > cx + 10:
            anchor = 'start'
        lines.append(
            f'  <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'dominant-baseline="central" '
            f'font-family="-apple-system,BlinkMacSystemFont,sans-serif" '
            f'font-size="12" fill="#1f2937">'
            f'{label} {val}/5</text>'
        )

    lines.append('</svg>')
    return '\n'.join(lines)


def save_html_report(
    system_name: str,
    system_type: str,
    report_body_html: str,
    date_str: str | None = None,
    output_dir: Path | None = None,
    title: str | None = None,
) -> str:
    """
    保存 Brookings/CSIS 智库风格 HTML 报告到 Obsidian 仓库。

    report_body_html: 报告正文的 HTML（不含 <html>/<head>/<body> 标签）。
    Orchestrator 负责将 Markdown 报告转换为 HTML 片段后调用此函数。

    HTML 使用内嵌 CSS，自包含无外部依赖（字体通过 Google Fonts CDN 加载，离线时降级到系统衬线字体）。
    output_dir: 可选，覆盖默认 OBSIDIAN_DIR（用于测试隔离）。

    CSS class 速查（供 Orchestrator 在转换报告时使用）：
      .exec-summary        — 执行摘要蓝色卡片
      .callout-red/amber/green — 风险等级 callout 块
      .score-badge .score-N — 评分徽章（N=1-5）
      .radar-container     — 雷达图 SVG 容器
      <details><summary>    — 折叠区域（用于信源审计）
      table (thead/tbody)   — zebra stripe 表格
      .prediction-review    — 上期预测复盘区块
      .predictions          — 可证伪预测区块
      .prediction-card      — 单条预测卡片（蓝色左边框）
      .prediction-title     — 预测内容标题
      .prediction-meta      — 证伪条件/时间窗口/置信度元信息
      .prediction-link      — 关联维度标签
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    target_dir = output_dir or OBSIDIAN_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    safe = system_name.replace('/', '-').replace('\\', '-').replace(':', '-')
    filename = f'{date_str} {safe} 诊断报告.html'
    filepath = target_dir / filename

    display_title = title or f'{system_name} — 系统诊断报告'
    html = _HTML_TEMPLATE.format(
        title=display_title,
        date=date_str,
        system_type=system_type,
        body=report_body_html,
    )
    filepath.write_text(html, encoding='utf-8')
    return str(filepath)


def list_analyses(system_name: str) -> list[dict]:
    """列出该系统的所有历史分析记录摘要（按日期倒序）。"""
    system_dir = _system_dir(system_name)
    if not system_dir.exists():
        return []
    records = []
    for f in sorted(system_dir.glob('*.json'), reverse=True):
        try:
            data = json.loads(f.read_text())
            records.append({
                'date':          data.get('analysis_date'),
                'system_type':   data.get('system_type'),
                'overall_score': data.get('overall_score'),
                'output_mode':   data.get('output_mode', 'full'),
                'file':          str(f),
            })
        except json.JSONDecodeError:
            continue
    return records
