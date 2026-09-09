"""
对照运行的记录与校验（§14.1 的执行侧）

**这个模块不做分析。** 三条路径的分析是由 agent 实际跑出来的，本模块负责把跑的过程
变成**可审计、可比、可盲评**的记录：

- 建立每个案例的运行目录与清单（manifest）
- 校验三条路径的预算是否可比——一条路径多花三倍检索，比出来的差异说明不了任何事
- 校验固定材料轮与开放检索轮**分开记录**，不许混在一起报
- 生成盲评包（去标识 + 打乱 + 映射表分离）

预算可比性是这里最容易被糊弄的一环：人总倾向于给自己想验证的那条路径多跑几轮。
所以它是**硬校验**，不是提醒。
"""

import json
from datetime import datetime
from pathlib import Path

from evals.decision_increment import blind_package

RUNS_DIR = Path(__file__).resolve().parent / 'cases' / 'runs'

PATHS = {
    'A_current': '升级前 system-xray（记下 commit）',
    'B_generic': '普通检索摘要 + 通用代理分析',
    'C_new': '新版协议（本次升级后）',
}

ROUNDS = ('fixed_material', 'open_retrieval')

# 预算差异容忍度：任一计量超过最省路径的这个倍数，即判定不可比。
# 1.5 是刻意收紧的——检索次数差 50% 已经足以解释"新版看到了更多东西"。
BUDGET_TOLERANCE = 1.5

BUDGET_KEYS = ('tool_calls', 'searches', 'wall_clock_seconds', 'tokens')

# 两类计量必须分开对待——把它们混成一个"预算可比性"数字是仪器的原始缺陷（见下）。
#
# GRANTED：**授予或扣留**的资源。一条路径拿到更多证据访问，对照就失效，
#          因为你分不清"分析更好"和"看到的更多"。这是**硬校验**。
# CONSUMED：**消耗**出来的量。一个方法读自己更长的规范、想得更久，那是它的成本，
#          不是不公平的输入。这是**成本发现**，要报告、要成为结论的限定条件，但**不阻断**。
#
# 为什么这个区分是必需的：试水轮实测三条路径 tokens 差 2.5×、wall_clock 差 11×，
# 而三条读的是同一份材料、searches 全为 0。按旧逻辑整轮判为"不可比"——
# 那等于说"新方法只要更费就不能被评估"，把成本问题误当成效度问题。
# 反过来若直接放宽阈值，又会掩盖一个**真实**的效度威胁：
# 算力差异本身可能就是输出差异的原因（"C 更好"也许只是"C 想得更久"）。
# 正确做法是两者都说：证据访问可比 → 可以送评；算力不可比 → 任何"C 更好"的结论
# 都必须带着这个限定，且成本要与增量一起报。
GRANTED_KEYS = ('searches',)
CONSUMED_KEYS = ('tool_calls', 'wall_clock_seconds', 'tokens')

# 篇幅差异容忍度。这不是预算，是**评审偏倚**：更长的报告天然显得更用心，
# 而方案 §14.4 明确说"报告更长"不得作为成功指标。
# 试点实测三条路径差到 3.3×——不提醒的话，盲评拿到的就是一场篇幅比赛。
LENGTH_TOLERANCE = 2.0


def case_dir(case_id: str) -> Path:
    return RUNS_DIR / case_id


def init_case(case_id: str, subject: str, as_of: str, system_type: str,
              budget_cap: dict, note: str = '') -> dict:
    """建立案例运行目录与 manifest。预算上限在**跑之前**写死。"""
    d = case_dir(case_id)
    (d / 'outputs').mkdir(parents=True, exist_ok=True)
    (d / 'materials').mkdir(parents=True, exist_ok=True)
    manifest = {
        'case_id': case_id,
        'subject': subject,
        'system_type': system_type,
        'as_of': as_of,
        'created_at': datetime.now().isoformat(),
        'budget_cap': budget_cap,
        'paths': PATHS,
        'rounds': list(ROUNDS),
        'runs': {},
        'note': note,
    }
    (d / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def load_manifest(case_id: str) -> dict | None:
    p = case_dir(case_id) / 'manifest.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def record_run(case_id: str, path: str, round_name: str, output_text: str,
               budget_used: dict, artifacts: dict | None = None) -> dict:
    """
    记录一条路径在一轮里的输出与实际花费。

    输出落盘为 `outputs/{round}__{path}.md`，花费写进 manifest。
    重复记录同一 (path, round) 会**覆盖**——运行记录不是版本库，
    要保留多次尝试请用不同 case_id。
    """
    manifest = load_manifest(case_id)
    if manifest is None:
        return {'errors': [f'案例 {case_id} 未初始化，先调 init_case()']}
    if path not in PATHS:
        return {'errors': [f'path 必须是 {list(PATHS)} 之一']}
    if round_name not in ROUNDS:
        return {'errors': [f'round 必须是 {list(ROUNDS)} 之一']}

    missing = [k for k in BUDGET_KEYS if k not in budget_used]
    if missing:
        return {'errors': [f'budget_used 缺 {missing}——没有花费记录就无法判断可比性']}

    fname = f'{round_name}__{path}.md'
    (case_dir(case_id) / 'outputs' / fname).write_text(output_text, encoding='utf-8')
    manifest['runs'].setdefault(round_name, {})[path] = {
        'output_file': f'outputs/{fname}',
        'budget_used': {k: budget_used[k] for k in BUDGET_KEYS},
        'artifacts': artifacts or {},
        'recorded_at': datetime.now().isoformat(),
    }
    (case_dir(case_id) / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'errors': [], 'manifest': manifest}


def check_comparability(case_id: str, round_name: str) -> dict:
    """
    三条路径在同一轮里是否可比。返回两个层次的判断，**不要混着看**：

    - `comparable`（硬）：**授予的资源**是否等量、是否超出预登记上限。
      不通过就不该拿去比，也不该打包送评。
    - `cost` + `warnings`（软）：**消耗**差异。不阻断，但任何"某条路径更好"的结论
      都必须带上这个限定——差异可能部分来自它算得更久。

    `budget_cap` 只对授予类资源生效。对消耗类设上限没有意义：
    没人能在跑之前控制一个方法要想多久，跑完再拿它当"超标"是在用事后数据判无效。
    """
    manifest = load_manifest(case_id)
    if manifest is None:
        return {'comparable': False, 'errors': [f'案例 {case_id} 未初始化']}
    runs = (manifest.get('runs') or {}).get(round_name) or {}

    missing_paths = [p for p in PATHS if p not in runs]
    if missing_paths:
        return {'comparable': False,
                'errors': [f'{round_name} 轮缺少路径 {missing_paths} 的输出——三条齐全才能比'],
                'recorded_paths': sorted(runs)}

    problems, ratios, warnings = [], {}, []
    cap = manifest.get('budget_cap') or {}

    def _ratio(key):
        values = {p: runs[p]['budget_used'][key] for p in PATHS}
        nonzero = [v for v in values.values() if v > 0]
        if not nonzero:
            return values, None
        lo, hi = min(nonzero), max(values.values())
        return values, (hi / lo if lo else float('inf'))

    # ── 硬校验：授予的资源必须等量，超出预登记上限同样不可用 ──
    for key in GRANTED_KEYS:
        values, ratio = _ratio(key)
        if ratio is None:
            ratios[key] = 1.0          # 三条都是 0，例如固定材料轮禁检索：完全等量
            continue
        ratios[key] = round(ratio, 3)
        if ratio > BUDGET_TOLERANCE:
            worst = max(values, key=values.get)
            problems.append(
                f'{key} 最高/最低 = {ratio:.2f}×（>{BUDGET_TOLERANCE}）：'
                f'「{worst}」拿到 {values[worst]}，最少的只有 {min(values.values())}——'
                f'证据访问不等量，分不清"分析更好"还是"看到的更多"'
            )
        if key in cap:
            over = [p for p, v in values.items() if v > cap[key]]
            if over:
                problems.append(f'{key} 超出预登记上限 {cap[key]}：{over}')

    # ── 成本发现：消耗差异不阻断，但必须成为结论的限定条件 ──
    cost = {}
    for key in CONSUMED_KEYS:
        values, ratio = _ratio(key)
        cost[key] = {'values': values, 'ratio': round(ratio, 3) if ratio else None}
        if ratio and ratio > BUDGET_TOLERANCE:
            worst = max(values, key=values.get)
            warnings.append(
                f'算力不等量：{key} 最高/最低 = {ratio:.2f}×，最费的是「{worst}」'
                f'（{values[worst]} vs {min(v for v in values.values() if v > 0)}）。'
                f'不阻断——这是方法的成本，不是不公平的输入。但**任何"该路径更好"的结论'
                f'都必须带上这个限定**：差异可能部分来自它算得更久，而不是方法本身'
            )

    # 篇幅偏倚：不阻断（篇幅差异本身可能就是方法差异的真实结果），但必须让评审组织者看见，
    # 并在评分说明里明确要求评审不得以长度作为增量依据。
    lengths = {}
    for p in PATHS:
        f = case_dir(case_id) / runs[p]['output_file']
        lengths[p] = len(f.read_text(encoding='utf-8')) if f.exists() else 0
    nonzero = [v for v in lengths.values() if v > 0]
    if nonzero:
        ratio = max(lengths.values()) / min(nonzero)
        ratios['output_length'] = round(ratio, 3)
        if ratio > LENGTH_TOLERANCE:
            longest = max(lengths, key=lengths.get)
            warnings.append(
                f'篇幅最高/最低 = {ratio:.2f}×（>{LENGTH_TOLERANCE}），最长的是「{longest}」。'
                f'不阻断，但评分说明里必须写明**不得以长度作为决策增量的依据**——'
                f'否则盲评会退化成篇幅比赛'
            )

    return {'comparable': not problems, 'ratios': ratios, 'cost': cost,
            'output_lengths': lengths, 'warnings': warnings, 'errors': problems,
            'note': ('comparable 只回答"授予的资源是否等量"；'
                     'cost 与 warnings 回答"谁更费"，后者不阻断但必须写进结论的限定条件')}


def package_for_review(case_id: str, round_name: str) -> dict:
    """
    生成盲评包。**不可比就不打包**——把不可比的输出送去盲评，
    评审给出的差异判断会被预算差异污染，而他们看不到这一点。
    """
    comp = check_comparability(case_id, round_name)
    if not comp['comparable']:
        return {'errors': comp['errors']}

    manifest = load_manifest(case_id)
    runs = manifest['runs'][round_name]
    outputs = {
        path: (case_dir(case_id) / runs[path]['output_file']).read_text(encoding='utf-8')
        for path in PATHS
    }
    pkg = blind_package(f'{case_id}-{round_name}', outputs)

    review_dir = case_dir(case_id) / 'review' / round_name
    review_dir.mkdir(parents=True, exist_ok=True)
    for item in pkg['items']:
        (review_dir / f'{item["label"]}.md').write_text(item['text'], encoding='utf-8')
    # 映射表单独存放，且**不放在交给评审的目录里**
    (case_dir(case_id) / f'.key__{round_name}.json').write_text(
        json.dumps(pkg['key'], ensure_ascii=False, indent=2), encoding='utf-8')

    return {'errors': [], 'review_dir': str(review_dir),
            'items': [i['label'] for i in pkg['items']],
            'key_file': f'.key__{round_name}.json',
            'note': '交给评审的是 review/ 目录；映射表在案例根目录的隐藏文件里，别一起发出去'}


def status(case_id: str) -> dict:
    """案例当前进度：哪几轮哪几条路径已记录、可比性如何。"""
    manifest = load_manifest(case_id)
    if manifest is None:
        return {'errors': [f'案例 {case_id} 未初始化']}
    out = {'case_id': case_id, 'subject': manifest['subject'],
           'as_of': manifest['as_of'], 'rounds': {}}
    for r in ROUNDS:
        recorded = sorted((manifest.get('runs') or {}).get(r, {}))
        out['rounds'][r] = {
            'recorded_paths': recorded,
            'complete': len(recorded) == len(PATHS),
            'comparability': check_comparability(case_id, r) if len(recorded) == len(PATHS)
            else {'comparable': False, 'errors': ['未跑齐三条路径']},
        }
    return out
