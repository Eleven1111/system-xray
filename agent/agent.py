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
from agent.store.db import list_analyses, load_latest


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

    mode_str = 'BRIEF（精简报告）' if args.brief else 'FULL（完整六维诊断）'
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
        """
    )
    parser.add_argument('--system',      '-s', help='系统名称')
    parser.add_argument('--type',        '-t', choices=SYSTEM_TYPES, help='系统类型')
    parser.add_argument('--date',        '-d', help='分析日期 YYYYMMDD（默认今天）')
    parser.add_argument('--brief',       action='store_true', help='精简输出模式')
    parser.add_argument('--queries-only',action='store_true', help='仅生成搜索查询集')
    parser.add_argument('--history',     action='store_true', help='查看历史分析记录')
    parser.add_argument('--list-types',  action='store_true', help='列出所有可用系统类型')

    args = parser.parse_args()

    if args.list_types:
        cmd_list_types()
        return

    if args.history:
        if not args.system:
            parser.error('--history 需要 --system 参数')
        cmd_history(args)
        return

    if not args.system or not args.type:
        parser.error('需要 --system 和 --type 参数（或使用 --list-types 查看可用类型）')

    if args.queries_only:
        cmd_queries_only(args)
    else:
        cmd_full_analysis(args)


if __name__ == '__main__':
    main()
