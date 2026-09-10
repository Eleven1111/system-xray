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
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tools.query_generator import generate_queries, format_for_claude, SYSTEM_TYPES
from agent.tools.causal_graph import analyze_graph
from agent.tools.ach_score import score_hypotheses
from agent.tools.history_compare import detect_danger_zones
from agent.tools.evidence_lineage import lineage_report
from agent.tools.causal_adapter import detect_backends, estimate_effect
from agent.tools.forecast_registry import due_predictions
from agent.tools.stock_flow import run_gated
from agent.tools.temporal import diff_analyses, staleness_report
from agent.validation import causal_readiness_report, completeness_report, validate_contract
from agent.store.db import (
    list_analyses, list_versions, load_latest, load_predictions, load_version,
    save_analysis, save_html_report, save_research_materials,
    save_to_obsidian, build_radar_svg, validate_analysis,
    process_warnings, build_source_audit_html, select_verification_sample,
    triage_claims_for_factcheck,
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
        'relational':        '关系系统（多行为体互动格局：冲突/对抗/联盟，如"伊朗-美国-以色列"）',
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
    """
    校验 analysis JSON（统一契约：存储 shape + 对象层 + 依赖一致性），不落盘。

    退出码 0=通过(可含告警)，1=有硬错误。
    """
    analysis = json.loads(_read_payload(args.input))
    errors, warnings = validate_contract(analysis)
    for w in warnings:
        print(w)
    comp = completeness_report(analysis)
    print(f'完整性：declared={comp["declared"]} / derived={comp["derived"]}'
          + (f'（缺口：{"；".join(comp["blockers"])}）' if comp['blockers'] else ''))
    if errors:
        print('❌ 校验失败：')
        for e in errors:
            print(f'  - {e}')
        sys.exit(1)
    print('✅ 校验通过' + ('（含上述非阻塞告警）' if warnings else ''))


def cmd_lineage(args):
    """从 analysis JSON 计算来源家族折叠、断言支撑画像与反证传播（受影响结论）。"""
    analysis = json.loads(_read_payload(args.input))
    print(json.dumps(lineage_report(analysis), ensure_ascii=False, indent=2))


def cmd_causal_readiness(args):
    """体检各机制卡够不够格升到 L2/L3；缺项非空 = 停在 L1 的方向性解释。"""
    analysis = json.loads(_read_payload(args.input))
    print(json.dumps(causal_readiness_report(analysis), ensure_ascii=False, indent=2))


def cmd_simulate(args):
    """L2 参数化局部模型：跑存量—流量并给出**稳健性判定**（入口门不过则拒绝出数）。"""
    payload = json.loads(_read_payload(args.input))
    result = run_gated(payload.get('mechanism', {}), payload.get('model', {}),
                       payload.get('verdict', {}))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('errors'):
        sys.exit(1)


def cmd_estimate_effect(args):
    """L3 因果效果估计：能力检测 + 入口门 + 反驳检验；条件不满足则拒绝出数。"""
    payload = json.loads(_read_payload(args.input))
    result = estimate_effect(payload.get('mechanism', {}), payload.get('spec', {}))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('errors'):
        sys.exit(1)


def cmd_backends(args):
    """列出可用的因果/仿真后端——不可用就如实说不可用。"""
    print(json.dumps(detect_backends(), ensure_ascii=False, indent=2))


def cmd_changes(args):
    """
    对比本期 analysis 与已存档的某一版，输出判断变更清单 + 口径可比性。

    --against 指定 analysis_id；省略则与最新版本比。
    """
    current = json.loads(_read_payload(args.input))
    previous = (load_version(args.system, args.against) if args.against
                else load_latest(args.system))
    if previous is None:
        print(f'未找到 [{args.system}] 的历史版本'
              + (f'（analysis_id={args.against}）' if args.against else ''), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(diff_analyses(current, previous), ensure_ascii=False, indent=2))


def cmd_staleness(args):
    """按断言类型（而非统一阈值）体检断言账本的时效，列出最该复查的条目。"""
    analysis = json.loads(_read_payload(args.input))
    claims = analysis.get('claims') or analysis.get('key_claims') or analysis
    as_of = args.date or (analysis.get('analysis_contract') or {}).get('as_of')
    print(json.dumps(staleness_report(claims, as_of=as_of), ensure_ascii=False, indent=2))


def cmd_predictions_due(args):
    """按 event_type 判定：在给定日期哪些预测可裁定、哪些只能等。"""
    payload = json.loads(_read_payload(args.input))
    registry = payload.get('predictions', payload) if isinstance(payload, dict) else payload
    as_of = args.date or datetime.now().strftime('%Y-%m-%d')
    print(json.dumps(due_predictions(registry, as_of), ensure_ascii=False, indent=2))


def cmd_versions(args):
    """列出某系统的全部不可变分析版本（含 analysis_id，可用于 --against / 精确重建）。"""
    versions = list_versions(args.system)
    if not versions:
        print(f'未找到 [{args.system}] 的分析版本')
        return
    print(f'\n{args.system} 的分析版本（共 {len(versions)} 个，升序）：\n')
    for v in versions:
        print(f"  {v['analysis_id']}  {v.get('completeness') or '完整性未记录':<26}"
              f"  总分 {v.get('overall_score') if v.get('overall_score') is not None else '—'}"
              f"  saved_at={v.get('saved_at')}")
    print(f"\n最新：{versions[-1]['analysis_id']}（latest 只是指针，历史版本不被覆盖）")


def cmd_save_analysis(args):
    """从文件/stdin 读取 analysis JSON 并持久化（落盘前走统一契约校验；流程告警非阻塞）。"""
    analysis = json.loads(_read_payload(args.input))
    errors, warnings = validate_contract(analysis)
    if errors:
        print('analysis 契约校验失败，已拒绝持久化：\n  - ' + '\n  - '.join(errors),
              file=sys.stderr)
        sys.exit(1)
    try:
        path = save_analysis(args.system, args.type, analysis, date_str=args.date)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    for w in warnings:
        print(w, file=sys.stderr)
    print(f'已保存到：{path}')


def cmd_build_audit(args):
    """从文件/stdin 读取 Research Brief JSON（含 sources[]），输出逐条 URL 的信源审计 HTML 片段。"""
    brief = json.loads(_read_payload(args.input))
    sources = brief.get('sources', brief) if isinstance(brief, dict) else brief
    verifications = brief.get('source_verification') if isinstance(brief, dict) else None
    print(build_source_audit_html(sources, verifications=verifications))


def cmd_triage_claims(args):
    """从 analysis JSON 的 claims 账本（兼容 key_claims）分诊独立 fact-check。"""
    analysis = json.loads(_read_payload(args.input))
    kc = ((analysis.get('claims') or analysis.get('key_claims'))
          if isinstance(analysis, dict) else analysis)
    n = args.sample if args.sample else 5
    triaged = triage_claims_for_factcheck(kc or [], max_n=n)
    if not triaged:
        print('# 无需独立复核的载荷性薄佐证断言（或无 key_claims 账本）')
        return
    print(f'# 待独立复核断言（{len(triaged)} 条）——对每条派 fact_check sub-agent 重新求证（勿假设原结论成立）：')
    for i, c in enumerate(triaged, 1):
        print(f'{i}. 「{c["claim"]}」\n   支撑：{c["loads"]} ｜ {c["reason"]}（{c["n_sources"]}源/最高T{c["best_tier"]}）')


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


def cmd_causal(args):
    """从交互边 JSON 计算反馈回路/杠杆点/处方交叉检查（Step 5.2/5.6 的确定性引擎）。"""
    payload = json.loads(_read_payload(args.input))
    result = analyze_graph(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('errors'):
        sys.exit(1)


def cmd_ach_score(args):
    """从 ACH 证据矩阵 JSON 计算假说加权排序与状态（Step 4.5 的定量引擎）。"""
    payload = json.loads(_read_payload(args.input))
    result = score_hypotheses(payload.get('hypotheses', []), payload.get('evidence', []))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('errors'):
        sys.exit(1)


def cmd_danger_zones(args):
    """从七维评分 JSON 自动比对危险区/生存区签名（机械化 scoring-calibration 交叉表）。"""
    scores = json.loads(_read_payload(args.input))
    print(json.dumps(detect_danger_zones(scores), ensure_ascii=False, indent=2))


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

跨期更新（S2）：
  python3 -m agent.agent --system "X" --versions                      # 列出不可变版本 + analysis_id
  python3 -m agent.agent --system "X" --changes --input new.json      # 判断变更 + 口径可比性
  python3 -m agent.agent --system "X" --changes --against 20260908-001 --input new.json
  python3 -m agent.agent --staleness --input analysis.json -d 2026-09-08
  python3 -m agent.agent --predictions-due --input analysis.json -d 2026-09-08
  python3 -m agent.agent --lineage --input analysis.json
  python3 -m agent.agent --causal-readiness --input analysis.json

能力分层（S4，条件不满足即拒绝出数）：
  python3 -m agent.agent --backends
  python3 -m agent.agent --simulate --input l2.json          # {mechanism, model, verdict}
  python3 -m agent.agent --estimate-effect --input l3.json   # {mechanism, spec}
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
    parser.add_argument('--causal',         action='store_true', help='读取交互边 JSON({edges,scores?,trajectories?,prescriptions?})，输出回路/杠杆点/处方交叉检查')
    parser.add_argument('--ach-score',      action='store_true', help='读取 ACH 矩阵 JSON({hypotheses,evidence})，输出假说加权排序与状态')
    parser.add_argument('--danger-zones',   action='store_true', help='读取七维评分 JSON，输出危险区/生存区签名命中')
    parser.add_argument('--build-audit',    action='store_true', help='读取 Brief JSON(含 sources[])，输出逐条 URL 信源审计 HTML 片段')
    parser.add_argument('--verify-plan',     action='store_true', help='从 Brief JSON 选出最该 WebFetch 抽查的信源，输出核验清单')
    parser.add_argument('--triage-claims',   action='store_true', help='从 analysis JSON 分诊出最该独立 fact_check 的载荷性薄佐证断言')
    parser.add_argument('--lineage',         action='store_true', help='读取 analysis JSON，输出来源家族折叠、断言支撑画像与反证传播（受影响结论）')
    parser.add_argument('--changes',         action='store_true', help='对比本期 analysis 与历史版本，输出判断变更清单 + 口径可比性')
    parser.add_argument('--against',         help='--changes 的对比目标 analysis_id；省略则与最新版本比')
    parser.add_argument('--staleness',       action='store_true', help='按断言类型体检时效，列出最该复查的断言')
    parser.add_argument('--causal-readiness', action='store_true', help='体检机制卡够不够格升到 L2/L3，列出缺失的入口条件')
    parser.add_argument('--simulate',        action='store_true', help='L2 存量—流量局部模型 + 参数区间稳健性判定（读 {mechanism, model, verdict}）')
    parser.add_argument('--estimate-effect', action='store_true', help='L3 因果效果估计 + 安慰剂/留一反驳（读 {mechanism, spec}）')
    parser.add_argument('--backends',        action='store_true', help='列出可用的因果/仿真后端')
    parser.add_argument('--predictions-due', action='store_true', help='按 event_type 判定：给定日期哪些预测可裁定、哪些只能等')
    parser.add_argument('--versions',        action='store_true', help='列出某系统的全部不可变分析版本（含 analysis_id）')
    parser.add_argument('--sample',          type=int, help='--verify-plan/--triage-claims 条数（默认 3/5）')
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

    if args.causal:
        cmd_causal(args)
        return

    if args.ach_score:
        cmd_ach_score(args)
        return

    if args.danger_zones:
        cmd_danger_zones(args)
        return

    if args.build_audit:
        cmd_build_audit(args)
        return

    if args.verify_plan:
        cmd_verify_plan(args)
        return

    if args.triage_claims:
        cmd_triage_claims(args)
        return

    if args.lineage:
        cmd_lineage(args)
        return

    if args.staleness:
        cmd_staleness(args)
        return

    if args.causal_readiness:
        cmd_causal_readiness(args)
        return

    if args.backends:
        cmd_backends(args)
        return

    if args.simulate:
        cmd_simulate(args)
        return

    if args.estimate_effect:
        cmd_estimate_effect(args)
        return

    if args.predictions_due:
        cmd_predictions_due(args)
        return

    if args.changes:
        if not args.system:
            parser.error('--changes 需要 --system 参数')
        cmd_changes(args)
        return

    if args.versions:
        if not args.system:
            parser.error('--versions 需要 --system 参数')
        cmd_versions(args)
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
