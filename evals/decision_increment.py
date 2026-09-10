"""
决策增量评分器 + 盲评打包（升级方案 §14.2）

这是评估的**仪器**，不是评估结果。它做三件人做起来容易出错的事：

1. **盲评打包**：把三条路径的输出去标识、打乱顺序，映射表单独存放。
   评审看不到哪份是新版——否则"新版更好"会变成自我实现。
2. **判据执行**：两名评审各自 0/1/2 打分，**均为 2** 才直接计合格；
   分歧交第三位评审依同一标准裁决；**无法裁决不计为合格**。
3. **汇总**：相对每条基线**分别**统计，对照预登记阈值给出结论。

它拒绝替人做判断：没有评审输入就没有分数。任何"自动打分"都会把
"我们的工具认为自己有增量"包装成评估结论。

判据（预登记，不得在看到结果后修改）：

| 分 | 含义 |
|---|---|
| 0 | 仅换措辞／无证据 |
| 1 | 有证据的新解释，但尚未改变调查或行动 |
| 2 | 有证据，且明确改变调查优先级、行动选择或行动条件，并能指出相对该基线新增的推理步骤 |
"""

import json
import random
import re
import secrets

VALID_RATINGS = (0, 1, 2)
QUALIFYING_RATING = 2

# 预登记阈值：相对每条基线，12 案中至少 8 案有合格新增洞察
DEFAULT_THRESHOLD = {'qualified_cases': 8, 'total_cases': 12}

# 会泄露路径身份的痕迹。盲评打包前必须清掉——留一个"由 system-xray 生成"
# 就足以让评审认出哪份是待证明的新版。
_IDENTIFYING_PATTERNS = [
    (re.compile(r'system[-_ ]?xray', re.I), '[TOOL]'),
    (re.compile(r'\bD[1-7]\b'), '[DIM]'),
    (re.compile(r'七维|seven[- ]dimension', re.I), '[FRAMEWORK]'),
    (re.compile(r'机制卡|行动卡|mechanism card|action card', re.I), '[ARTIFACT]'),
    (re.compile(r'ACH|竞争假说'), '[METHOD]'),
]


def blind_package(case_id: str, outputs: dict, seed: str | None = None) -> dict:
    """
    把 `{path_name: output_text}` 打成盲评包。

    返回 `{case_id, items: [{label, text}], key: {label: path_name}}`。
    **`key` 必须与 `items` 分开保管**——交给评审的只有 items。
    未显式传 seed 时使用私有随机 nonce；评审若知道 case_id 和路径集合，也不能
    从公开标签重建映射。需要可重复生成时，调用者必须自行私下保管显式 seed。
    """
    rng = random.Random(seed or secrets.token_hex(32))
    paths = sorted(outputs)
    # 标签刻意不用 A/B/C：路径名就叫 A_current/B_generic/C_new，
    # 同字母会诱使评审去做"标签 A = 路径 A"的映射猜测，而随机打乱迟早会撞上一次真对应。
    # 试点时就撞上了（label-C → C_new），所以改用与路径名无字母交集的记号。
    labels = [f'{case_id}-{c}' for c in 'PQRSTU'[:len(paths)]]
    rng.shuffle(paths)

    items, key = [], {}
    for label, path in zip(labels, paths):
        text = outputs[path]
        for pattern, repl in _IDENTIFYING_PATTERNS:
            text = pattern.sub(repl, text)
        items.append({'label': label, 'text': text})
        key[label] = path
    return {'case_id': case_id, 'items': items, 'key': key,
            'note': 'key 与 items 分开保管；评审只拿 items'}


def score_case(case_id: str, baseline: str, ratings: list[dict],
               arbitration: dict | None = None) -> dict:
    """
    对**一个案例相对一条基线**做判定。

    ratings: `[{reviewer, score, rationale}]`，需恰好两名独立评审。
    arbitration: `{reviewer, score, rationale}`，仅在两人分歧时使用。

    规则：均为 2 → 合格；分歧 → 交裁决；无裁决或裁决非 2 → **不合格**。
    "无法裁决不计为合格"是预登记规则，不是遗漏。
    """
    problems = []
    if len(ratings) != 2:
        problems.append(f'需要恰好 2 名独立评审，实际 {len(ratings)} 名')
    reviewers = [r.get('reviewer') for r in ratings]
    if len(set(reviewers)) != len(reviewers):
        problems.append('两条评分来自同一名评审——不构成独立评分')
    for r in ratings:
        if r.get('score') not in VALID_RATINGS:
            problems.append(f'评分必须是 {list(VALID_RATINGS)}，实际 {r.get("score")!r}')
        if not r.get('rationale'):
            problems.append(f'评审 {r.get("reviewer")} 未给理由——判据要求可复核')
    if problems:
        return {'case_id': case_id, 'baseline': baseline, 'qualified': False,
                'resolution': 'invalid', 'problems': problems}

    scores = [r['score'] for r in ratings]
    if scores[0] == scores[1]:
        qualified = scores[0] == QUALIFYING_RATING
        return {'case_id': case_id, 'baseline': baseline, 'qualified': qualified,
                'resolution': 'agreed', 'scores': scores, 'problems': []}

    if not arbitration:
        return {'case_id': case_id, 'baseline': baseline, 'qualified': False,
                'resolution': 'unarbitrated_disagreement', 'scores': scores,
                'problems': ['两名评审分歧且无第三方裁决——按预登记规则不计为合格']}

    if arbitration.get('reviewer') in reviewers:
        return {'case_id': case_id, 'baseline': baseline, 'qualified': False,
                'resolution': 'invalid', 'scores': scores,
                'problems': ['裁决人不能是原评审之一']}
    if arbitration.get('score') not in VALID_RATINGS or not arbitration.get('rationale'):
        return {'case_id': case_id, 'baseline': baseline, 'qualified': False,
                'resolution': 'invalid', 'scores': scores,
                'problems': ['裁决缺少合法评分或理由（理由须留存）']}

    return {'case_id': case_id, 'baseline': baseline,
            'qualified': arbitration['score'] == QUALIFYING_RATING,
            'resolution': 'arbitrated', 'scores': scores,
            'arbitrated_score': arbitration['score'], 'problems': []}


def unblind_ratings(blind_cases: list[dict], key: dict[str, str],
                    candidate_path: str = 'C_new') -> dict:
    """将收回且冻结的匿名有向比较转换为 C 对每条基线的评分。"""
    results, errors = [], []
    for i, row in enumerate(blind_cases or []):
        if not isinstance(row, dict):
            errors.append(f'blind_cases[{i}] 必须是对象')
            continue
        candidate, comparator = row.get('candidate_label'), row.get('comparator_label')
        if candidate not in key or comparator not in key:
            errors.append(f'blind_cases[{i}] 含未知匿名标签')
            continue
        if candidate == comparator:
            errors.append(f'blind_cases[{i}] 候选与比较对象不能相同')
            continue
        if key[candidate] != candidate_path:
            continue
        baseline = key[comparator]
        if baseline == candidate_path:
            errors.append(f'blind_cases[{i}] 解盲后比较对象仍是 {candidate_path}')
            continue
        results.append(score_case(row.get('case_id', ''), baseline,
                                  row.get('ratings') or [], row.get('arbitration')))
    return {'results': results, 'errors': errors, 'candidate_path': candidate_path,
            'note': '原始匿名评分与私有 key 均须保留；转换在评分冻结后执行'}


def aggregate(case_results: list[dict], threshold: dict | None = None) -> dict:
    """
    按基线分别汇总。**不合并不同基线**——相对现版和相对普通研究路径是两个问题。
    """
    th = threshold or DEFAULT_THRESHOLD
    by_baseline: dict[str, list[dict]] = {}
    duplicates: list[str] = []
    seen: set[tuple[str, str]] = set()
    for r in case_results:
        key = (r.get('baseline'), r.get('case_id'))
        if key in seen:
            duplicates.append(f'{key[0]}/{key[1]}')
            continue
        seen.add(key)
        by_baseline.setdefault(r['baseline'], []).append(r)

    summary = {}
    for baseline, rows in sorted(by_baseline.items()):
        qualified = [r['case_id'] for r in rows if r['qualified']]
        invalid = [r['case_id'] for r in rows if r['resolution'] == 'invalid']
        unarb = [r['case_id'] for r in rows
                 if r['resolution'] == 'unarbitrated_disagreement']
        summary[baseline] = {
            'cases_scored': len(rows),
            'qualified': len(qualified),
            'qualified_ids': qualified,
            'invalid_ratings': invalid,
            'unarbitrated_disagreements': unarb,
            'threshold': th['qualified_cases'],
            'meets_threshold': (len(qualified) >= th['qualified_cases']
                                and len(rows) >= th['total_cases']),
            'incomplete': len(rows) < th['total_cases'],
        }

    flags = []
    for baseline, s in summary.items():
        if s['incomplete']:
            flags.append(
                f'相对基线「{baseline}」只评了 {s["cases_scored"]}/{th["total_cases"]} 案——'
                f'样本不全，不得据此宣称达标或未达标'
            )
        if s['invalid_ratings']:
            flags.append(f'基线「{baseline}」有 {len(s["invalid_ratings"])} 案评分无效：'
                         f'{s["invalid_ratings"]}')
    if duplicates:
        flags.append(
            f'发现重复的「基线/案例」评分 {duplicates}：重复项未计入样本，'
            '须修正评分文件后才能据此作任何阈值结论'
        )
    return {'by_baseline': summary, 'flags': flags,
            'note': ('12 个案例仅是原型筛选，达标也不足以声称跨领域普遍有效；'
                     '未达标应如实报告，不以其他指标替代')}


def load_ratings(path) -> list[dict]:
    """从评分文件读取并逐案判定。文件格式见 evals/cases/ratings-template.json。"""
    data = json.loads(open(path, encoding='utf-8').read())
    return [
        score_case(row['case_id'], row['baseline'], row['ratings'], row.get('arbitration'))
        for row in data.get('cases', [])
    ]
