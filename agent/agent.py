"""
System Pathology Agent — CLI 入口

用法：
  python3 -m agent.agent --system "伊朗" --type geopolitical
  python3 -m agent.agent --system "ByteDance" --type public_company --brief
  python3 -m agent.agent --system "X" --type geopolitical --queries-only
  python3 -m agent.agent --system "X" --history
  python3 -m agent.agent --list-types
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tools.query_generator import generate_queries, format_for_claude, SYSTEM_TYPES
from agent.store.db import (
    list_analyses, load_latest, load_predictions,
    save_analysis, save_html_report, save_research_materials,
    save_to_obsidian, build_radar_svg, validate_analysis,
    process_warnings, build_source_audit_html, select_verification_sample,
)


def _read_payload(path: str | None) -> str:
    """从文件读取 payload；path 为 '-' 或 None 时从 stdin 读。"""
    if path and path != '-':
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return sys.stdin.read()


def cmd_list_types():
    print("可用系统类型：")
    descriptions = {
        'geopolitical':      '地缘政治/国家政权',
        'government_agency': '政府机构/监管机构',
        'public_company':    '上市公司',
        'private_company':   '私营企业',
        'dao':               'DAO/Web3 组织',
        'market':            '行业/市场',
        'platform':          '平台生态',
    }
    for t, desc in descriptions.items():
        print(f"  {t:<20} {desc}")


def cmd_queries_only(args):
    result = generate_queries(args.system, args.type, args.date)
    print(format_for_claude(result))
    print('\n--- JSON ---')
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_history(args):
    records = list_analyses(args.system)
    if not records:
        print(f"未找到 [{args.system}] 的历史分析记录")
        return
    print(f'\n{args.system} 的历史分析记录：\n')
    for r in records:
        score_str = f"总分 {r['overall_score']}" if r.get('overall_score') else '评分未记录'
        mode_str  = f"[{r['output_mode']}]" if r.get('output_mode') else ''
        print(f"  {r['date']}  {r['system_type']:<20}  {score_str}  {mode_str}")


def cmd_full_analysis(args):
    """生成研究任务清单，输出给 Claude 执行。"""
    result = generate_queries(args.system, args.type, args.date)

    print('=' * 60)
    print('SYSTEM PATHOLOGY AGENT — 研究阶段启动')
    print('=' * 60)
    print(format_for_claude(result))

    mode_str = 'BRIEF（精简报告）' if args.brief else 'FULL（完整七维诊断）'
    print(f'\n输出模式：{mode_str}')

    # 检查是否有历史分析
    latest = load_latest(args.system)
    if latest:
        print(f'\n历史记录：找到上期分析（{latest["analysis_date"]}），分析完成后将自动对比。')
    else:
        print(f'\n历史记录：首次分析，无历史对比数据。')

    # 输出结构化 JSON 供管道使用
    print('\n```json')
    print(json.dumps({
        'command':     'full_analysis',
        'system_name': args.system,
        'system_type': args.type,
        'output_mode': 'brief' if args.brief else 'full',
        'query_set':   result,
        'has_history': latest is not None,
        'previous_date': latest['analysis_date'] if latest else None,
    }, ensure_ascii=False, indent=2))
    print('```')


def cmd_validate(args):
    """仅校验 analysis JSON 结构，不落盘。退出码 0=通过(可含告警)，1=有硬错误。"""
    analysis = json.loads(_read_payload(args.input))
    errors = validate_analysis(analysis)
    warnings = process_warnings(analysis)
    for w in warnings:
        print(w)
    if errors:
        print('❌ 校验失败：')
        for e in errors:
            print(f'  - {e}')
        sys.exit(1)
    print('✅ 校验通过' + ('（含上述非阻塞告警）' if warnings else ''))


def cmd_save_analysis(args):
    """从文件/stdin 读取 analysis JSON 并持久化（落盘前自动校验；流程告警非阻塞）。"""
    analysis = json.loads(_read_payload(args.input))
    try:
        path = save_analysis(args.system, args.type, analysis, date_str=args.date)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    for w in process_warnings(analysis):
        print(w, file=sys.stderr)
    print(f'已保存到：{path}')


def cmd_build_audit(args):
    """从文件/stdin 读取 Research Brief JSON（含 sources[]），输出逐条 URL 的信源审计 HTML 片段。"""
    brief = json.loads(_read_payload(args.input))
    sources = brief.get('sources', brief) if isinstance(brief, dict) else brief
    verifications = brief.get('source_verification') if isinstance(brief, dict) else None
    print(build_source_audit_html(sources, verifications=verifications))


def cmd_verify_plan(args):
    """从 Brief JSON 选出最该 WebFetch 抽查的信源，输出核验清单（供 Orchestrator 执行）。"""
    brief = json.loads(_read_payload(args.input))
    sources = brief.get('sources', brief) if isinstance(brief, dict) else brief
    n = args.sample if args.sample else 3
    sample = select_verification_sample(sources, n=n)
    print(f'# 信源核验清单（{len(sample)} 条，请逐条 WebFetch 核验：URL 可达？标题/数字与所述一致？）')
    for i, s in enumerate(sample, 1):
        print(f'{i}. [T{s["tier"]}] {s["title"]}\n   {s["url"]}\n   原因：{s["reason"]}')
    print('\n# 核验后，把结果按 [{"url","status":"confirmed|dead|mismatch|unverifiable","note"}] '
          '写回 brief 的 source_verification 字段，并置 process_metadata.source_verification_done=true')


def cmd_save_materials(args):
    """从文件/stdin 读取 Research Brief JSON 并保存为 MD 素材。"""
    brief = json.loads(_read_payload(args.input))
    path = save_research_materials(args.system, args.type, brief, date_str=args.date)
    print(f'素材已保存到：{path}')


def cmd_save_html(args):
    """从文件/stdin 读取报告正文 HTML 并保存为智库风格 HTML 报告。"""
    body_html = _read_payload(args.input)
    path = save_html_report(
        args.system, args.type, body_html, date_str=args.date, title=args.title,
    )
    print(f'HTML 报告已保存到：{path}')


def cmd_save_md(args):
    """从文件/stdin 读取报告 Markdown 并保存为 Obsidian 备份。"""
    report = _read_payload(args.input)
    path = save_to_obsidian(args.system, args.type, report, date_str=args.date)
    print(f'MD 报告已保存到：{path}')


def cmd_radar(args):
    """从文件/stdin 读取七维评分 JSON，输出内联雷达图 SVG。"""
    scores = json.loads(_read_payload(args.input))
    print(build_radar_svg(scores))


def cmd_load_predictions(args):
    """输出指定系统上次分析的预测列表 JSON（无则 []）。"""
    print(json.dumps(load_predictions(args.system), ensure_ascii=False, indent=2))


def cmd_load_latest(args):
    """输出指定系统上次分析的完整记录 JSON（无则 null）。"""
    data = load_latest(args.system)
    print(json.dumps(data, ensure_ascii=False, indent=2) if data else 'null')


def main():
    parser = argparse.ArgumentParser(
        description='System Pathology Agent — 多视角系统诊断',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 -m agent.agent --system "伊朗" --type geopolitical
  python3 -m agent.agent --system "ByteDance" --type public_company --brief
  python3 -m agent.agent --system "DeFi" --type market --queries-only
  python3 -m agent.agent --system "ByteDance" --history
  python3 -m agent.agent --list-types

持久化（payload 从 --input 文件或 stdin 读取，避免内联 shell 转义问题）：
  python3 -m agent.agent --system "X" --type public_company --save-analysis --input analysis.json
  cat analysis.json | python3 -m agent.agent -s "X" -t public_company --save-analysis
  python3 -m agent.agent -s "X" -t public_company --save-html --title "标题" --input body.html
  python3 -m agent.agent -s "X" -t public_company --save-materials --input brief.json
  python3 -m agent.agent --validate --input analysis.json
  python3 -m agent.agent --radar --input scores.json
  python3 -m agent.agent --system "X" --load-predictions
        """
    )
    parser.add_argument('--system',      '-s', help='系统名称')
    parser.add_argument('--type',        '-t', choices=SYSTEM_TYPES, help='系统类型')
    parser.add_argument('--date',        '-d', help='分析日期（JSON 存储用 YYYYMMDD，Obsidian 文件用 YYYY-MM-DD；默认今天）')
    parser.add_argument('--brief',       action='store_true', help='精简输出模式')
    parser.add_argument('--queries-only',action='store_true', help='仅生成搜索查询集')
    parser.add_argument('--history',     action='store_true', help='查看历史分析记录')
    parser.add_argument('--list-types',  action='store_true', help='列出所有可用系统类型')
    # ── 持久化 / 校验子命令（payload 走文件或 stdin，不走内联插值）──
    parser.add_argument('--input',       '-i', help='payload 文件路径；省略或 "-" 则从 stdin 读取')
    parser.add_argument('--title',       help='--save-html 的报告标题')
    parser.add_argument('--save-analysis',  action='store_true', help='读取 analysis JSON 并持久化（落盘前校验）')
    parser.add_argument('--save-html',      action='store_true', help='读取报告正文 HTML 并保存为智库风格报告')
    parser.add_argument('--save-materials', action='store_true', help='读取 Research Brief JSON 并保存为 MD 素材')
    parser.add_argument('--save-md',        action='store_true', help='读取报告 Markdown 并保存为 Obsidian 备份')
    parser.add_argument('--validate',       action='store_true', help='仅校验 analysis JSON 结构，不落盘')
    parser.add_argument('--radar',          action='store_true', help='读取七维评分 JSON，输出雷达图 SVG')
    parser.add_argument('--build-audit',    action='store_true', help='读取 Brief JSON(含 sources[])，输出逐条 URL 信源审计 HTML 片段')
    parser.add_argument('--verify-plan',     action='store_true', help='从 Brief JSON 选出最该 WebFetch 抽查的信源，输出核验清单')
    parser.add_argument('--sample',          type=int, help='--verify-plan 抽查条数（默认 3）')
    parser.add_argument('--load-predictions', action='store_true', help='输出上次分析的预测列表 JSON')
    parser.add_argument('--load-latest',    action='store_true', help='输出上次分析的完整记录 JSON')

    args = parser.parse_args()

    if args.list_types:
        cmd_list_types()
        return

    if args.validate:
        cmd_validate(args)
        return

    if args.radar:
        cmd_radar(args)
        return

    if args.build_audit:
        cmd_build_audit(args)
        return

    if args.verify_plan:
        cmd_verify_plan(args)
        return

    if args.history:
        if not args.system:
            parser.error('--history 需要 --system 参数')
        cmd_history(args)
        return

    if args.load_predictions:
        if not args.system:
            parser.error('--load-predictions 需要 --system 参数')
        cmd_load_predictions(args)
        return

    if args.load_latest:
        if not args.system:
            parser.error('--load-latest 需要 --system 参数')
        cmd_load_latest(args)
        return

    # 持久化子命令需要 --system 和 --type
    if args.save_analysis or args.save_html or args.save_materials or args.save_md:
        if not args.system or not args.type:
            parser.error('持久化子命令需要 --system 和 --type 参数')
        if args.save_analysis:
            cmd_save_analysis(args)
        elif args.save_html:
            cmd_save_html(args)
        elif args.save_materials:
            cmd_save_materials(args)
        elif args.save_md:
            cmd_save_md(args)
        return

    if not args.system or not args.type:
        parser.error('需要 --system 和 --type 参数（或使用 --list-types 查看可用类型）')

    if args.queries_only:
        cmd_queries_only(args)
    else:
        cmd_full_analysis(args)


if __name__ == '__main__':
    main()
