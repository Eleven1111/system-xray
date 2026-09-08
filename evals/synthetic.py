"""
合成机制案例评估 + 消融实验（升级方案 §14.1 合成部分 / §14.4）

**为什么是合成的。** 历史案例的模型训练知识污染无法仅靠材料截断消除，匿名化也只能减少
泄漏、不能证明消除。合成案例的真相由构造决定，不存在泄漏——代价是它只测**逻辑**：
确定性引擎在已知真相下能否得出正确结论。它测不出研究采集质量、机制判断是否贴近现实、
或决策增量，那些要真实材料与人类评审（`evals/protocol.md`）。

**消融怎么做。** 同一批案例分别在"全模块"与"关掉某个模块"下跑，比较正确率。
差值就是该模块在这批案例上的**检出增益**。注意这个数字的边界：

- 它衡量的是"**关掉后有多少案例判错**"，不是"该模块让分析变好了多少"；
- 案例是按这些失效模式**构造**的，所以增益天然偏高——这是设计出来的靶场，不是野外；
- 因此结论只能是"这个模块在它负责的失效模式上确实起作用"，
  **不能**推广成"该模块值得保留在真实分析里"。后者要 §14.4 的真实案例消融。

运行：
    python3 -m evals.synthetic              # 人读报告（含消融表）
    python3 -m evals.synthetic --json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools import ach_score                                    # noqa: E402
from agent.tools.ach_score import score_hypotheses                   # noqa: E402
from agent.tools.evidence_lineage import affected_by_contradiction   # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / 'cases' / 'synthetic-mechanism-cases.json'

# 消融：关掉某个模块的方式。值是一个 (patch, restore) 工厂。
# 只关**这批案例真正依赖**的模块——把无关模块也列进来会制造虚假的"零增益"对照。
ABLATIONS = {
    'none':            '全模块（对照组）',
    'no_family_collapse': '关掉独立证据家族折叠（转载按条计数）',
    'no_diagnosticity':   '关掉鉴别力降权（全 C / 全 I 证据按满权重计）',
    'no_tier_weight':     '关掉信源层级加权（T3 的 I 与 T1 等重）',
    'no_lineage':         '关掉反证依赖传播',
}


def load_cases() -> dict:
    return json.loads(CASES_PATH.read_text(encoding='utf-8'))


# ── 消融补丁 ───────────────────────────────────────────────────────────────

def _apply(ablation: str):
    """返回 restore 回调。补丁作用于模块级常量/函数，跑完必须还原。"""
    if ablation == 'none':
        return lambda: None

    if ablation == 'no_family_collapse':
        original = ach_score.collapse_evidence_families

        def no_collapse(evidence):
            out = []
            for i, e in enumerate(evidence):
                fam = dict(e)
                fam['copies'] = 1
                fam['family_id'] = f'raw:{i}'
                out.append(fam)
            return out, []

        ach_score.collapse_evidence_families = no_collapse
        return lambda: setattr(ach_score, 'collapse_evidence_families', original)

    if ablation == 'no_diagnosticity':
        original = ach_score._NON_DIAGNOSTIC_FACTOR
        ach_score._NON_DIAGNOSTIC_FACTOR = 1.0
        return lambda: setattr(ach_score, '_NON_DIAGNOSTIC_FACTOR', original)

    if ablation == 'no_tier_weight':
        original = dict(ach_score._TIER_WEIGHT)
        ach_score._TIER_WEIGHT.update({1: 3.0, 2: 3.0, 3: 3.0})
        return lambda: (ach_score._TIER_WEIGHT.clear(),
                        ach_score._TIER_WEIGHT.update(original))

    if ablation == 'no_lineage':
        return lambda: None            # 在 _check_case 里按标志跳过传播检查

    raise ValueError(f'未知消融：{ablation}')


# ── 判定 ───────────────────────────────────────────────────────────────────

def _check_ach_case(case: dict) -> tuple[bool, list[str]]:
    exp = case['expected']
    result = score_hypotheses(case['hypotheses'], case['evidence'])
    if result.get('errors'):
        return False, [f'引擎报错：{result["errors"]}']

    status = {r['id']: r['status'] for r in result['ranking']}
    problems = []

    if exp.get('all_untestable'):
        if set(status.values()) != {'untestable'}:
            problems.append(f'应全部 untestable，实际 {status}')
    else:
        for hid in exp.get('surviving', []):
            if status.get(hid) == 'eliminated':
                problems.append(f'{hid} 是真解释却被反驳（假阳性反驳）')
        for hid in exp.get('refuted', []):
            if status.get(hid) != 'eliminated':
                problems.append(f'{hid} 应被反驳，实际 {status.get(hid)}')

    if 'h1_status' in exp and status.get('H1') != exp['h1_status']:
        problems.append(f'H1 应为 {exp["h1_status"]}，实际 {status.get("H1")}')

    if 'must_collapse_to_families' in exp:
        got = result.get('evidence_families')
        if got != exp['must_collapse_to_families']:
            problems.append(f'应折叠为 {exp["must_collapse_to_families"]} 个独立家族，实际 {got}')

    if exp.get('must_report_sensitivity') and result['sensitivity']['robust']:
        problems.append('结论悬于单条证据却未报告留一敏感性')

    return not problems, problems


def _check_propagation_case(case: dict, ablation: str) -> tuple[bool, list[str]]:
    if ablation == 'no_lineage':
        return False, ['消融：传播被关闭，被反证断言不会拖动依赖对象']
    prop = affected_by_contradiction(case['analysis'])
    expected = set(case['expected']['needs_review_targets'])
    got = set(prop['needs_review'])
    if got != expected:
        return False, [f'应标 needs_review 的对象 {sorted(expected)}，实际 {sorted(got)}']
    return True, []


def _check_case(case: dict, ablation: str) -> tuple[bool, list[str]]:
    if 'analysis' in case:
        return _check_propagation_case(case, ablation)
    return _check_ach_case(case)


def run_ablation(ablation: str) -> dict:
    lib = load_cases()
    restore = _apply(ablation)
    try:
        rows = []
        for case in lib['cases']:
            ok, problems = _check_case(case, ablation)
            rows.append({'id': case['id'], 'title': case['title'],
                         'passed': ok, 'problems': problems})
    finally:
        restore()
    passed = sum(1 for r in rows if r['passed'])
    return {'ablation': ablation, 'label': ABLATIONS[ablation],
            'passed': passed, 'total': len(rows), 'cases': rows}


def run() -> dict:
    results = {name: run_ablation(name) for name in ABLATIONS}
    baseline = results['none']
    for name, r in results.items():
        r['delta_vs_baseline'] = r['passed'] - baseline['passed']
        r['newly_failed'] = [
            c['id'] for c in r['cases']
            if not c['passed'] and next(b['passed'] for b in baseline['cases']
                                        if b['id'] == c['id'])
        ]
    return {
        'baseline_passed': baseline['passed'],
        'total_cases': baseline['total'],
        'ablations': results,
        'provenance': load_cases()['provenance'],
        'scope_note': (
            '消融差值衡量的是"关掉该模块后有多少**构造出来的**失效案例被判错"，'
            '不是该模块在真实分析中的价值。案例按这些失效模式构造，增益天然偏高。'
            '真实案例消融见 evals/protocol.md §3，尚未执行。'
        ),
    }


def main():
    ap = argparse.ArgumentParser(description='合成机制案例 + 消融实验')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    report = run()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if report['baseline_passed'] == report['total_cases'] else 1)

    base = report['ablations']['none']
    print('合成机制案例（真相由构造决定）\n' + '=' * 66)
    for c in base['cases']:
        print(f'{"✅" if c["passed"] else "❌"} {c["id"]} {c["title"]}')
        for p in c['problems']:
            print(f'    ! {p}')
    print(f'\n对照组：{base["passed"]}/{base["total"]} 通过')

    print('\n消融实验（§14.4）\n' + '=' * 66)
    print(f'{"配置":<34}{"通过":>8}{"差值":>8}  新失守案例')
    for name, r in report['ablations'].items():
        print(f'{r["label"]:<34}{r["passed"]:>4}/{r["total"]:<3}{r["delta_vs_baseline"]:>+8}'
              f'  {", ".join(r["newly_failed"]) or "—"}')
    print('\n' + report['scope_note'])
    sys.exit(0 if report['baseline_passed'] == report['total_cases'] else 1)


if __name__ == '__main__':
    main()
