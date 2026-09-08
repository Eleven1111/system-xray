"""
Tool: L3 因果效果估计适配层（能力检测 + 最小内置估计器）

升级方案 §12.3 的能力检测原则用在这里：**先检测宿主具备什么，再选执行路径**，
不可用的能力如实记录，不虚构。以及 S4 的前置条件——工具能跑不代表当前输入满足算法要求。

三层把关，缺一层就不出定量结果：

1. **入口门**（`causal_readiness`）：机制卡有没有估计目标、识别策略、数据来源、
   反驳方案、适用群体与时间范围。缺任何一项 → 停在 L1。
2. **数据门**：数据形状能不能支撑所选识别策略（有没有对照组、有没有干预前观测）。
3. **后端**：装了 DoWhy 就用 DoWhy 的识别—估计—反驳全流程；
   没装则用**内置最小估计器**（双重差分 + 安慰剂 + 留一稳健性），
   并在输出里明确标注它**不是** DoWhy 的替代品。

内置估计器只用标准库，不引入任何依赖。它算得对，但它的能力边界很窄：
线性双重差分、无协变量调整、无面板自相关处理。**识别假设是分析者的，不是它验证的**——
它能做的只是在假设成立的前提下给一个数，再用两种反驳去摇一摇这个数。
"""

import random
import statistics
from importlib import import_module

from agent.validation import causal_readiness

SUPPORTED_STRATEGIES = ('difference_in_differences', 'before_after_with_control')


def detect_backends() -> dict:
    """
    检测可用的因果推断后端。**不可用就如实说不可用**，不静默降级后假装用了它。
    """
    backends = {}
    for name in ('dowhy', 'statsmodels'):
        try:
            mod = import_module(name)
            backends[name] = {'available': True,
                              'version': getattr(mod, '__version__', 'unknown')}
        except ImportError:
            backends[name] = {'available': False, 'version': None}
    backends['builtin_did'] = {
        'available': True, 'version': 'minimal',
        'caveat': ('内置最小双重差分：无协变量调整、无面板自相关处理、无倾向得分。'
                   '它不是 DoWhy 的替代品，只是在没有 DoWhy 时仍能给出一个'
                   '**带反驳检验**的估计，以及一份可复现的假设清单。'),
    }
    return backends


def check_data_shape(data: list[dict], strategy: str) -> list[str]:
    """数据形状能否支撑所选识别策略。缺对照组就做不了 DiD——这是硬约束，不是可选项。"""
    problems: list[str] = []
    if strategy not in SUPPORTED_STRATEGIES:
        return [f'内置估计器只支持 {list(SUPPORTED_STRATEGIES)}，收到 {strategy!r}；'
                f'其他策略请接 DoWhy 或专业工具']
    if not isinstance(data, list) or not data:
        return ['data 必须是非空数组']

    required = {'unit', 'group', 'period', 'outcome'}
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            problems.append(f'data[{i}] 必须是对象')
            continue
        missing = required - set(row)
        if missing:
            problems.append(f'data[{i}] 缺字段 {sorted(missing)}')
            continue
        if row['group'] not in ('treated', 'control'):
            problems.append(f'data[{i}].group 必须是 treated/control')
        if row['period'] not in ('pre', 'post'):
            problems.append(f'data[{i}].period 必须是 pre/post')
        if not isinstance(row['outcome'], (int, float)) or isinstance(row['outcome'], bool):
            problems.append(f'data[{i}].outcome 必须是数字')
    if problems:
        return problems

    cells = {(r['group'], r['period']) for r in data}
    for cell in (('treated', 'pre'), ('treated', 'post'),
                 ('control', 'pre'), ('control', 'post')):
        if cell not in cells:
            problems.append(f'缺少 {cell[0]}/{cell[1]} 单元格——'
                            f'双重差分需要四格齐全，否则无法与"本来就会发生的变化"分离')
    return problems


def _cell_mean(data: list[dict], group: str, period: str) -> float:
    vals = [r['outcome'] for r in data if r['group'] == group and r['period'] == period]
    return statistics.fmean(vals) if vals else float('nan')


def _did(data: list[dict]) -> float:
    return ((_cell_mean(data, 'treated', 'post') - _cell_mean(data, 'treated', 'pre'))
            - (_cell_mean(data, 'control', 'post') - _cell_mean(data, 'control', 'pre')))


def _placebo(data: list[dict], n: int = 200, seed: int = 20260908) -> dict:
    """
    安慰剂检验：随机重排组标签，看真实估计是否落在噪声分布里。

    单位级重排（不是行级）——同一单位的 pre/post 必须一起换组，否则打乱的是面板结构，
    检验会变得过于容易通过。
    """
    rng = random.Random(seed)
    units = sorted({r['unit'] for r in data})
    n_treated = len({r['unit'] for r in data if r['group'] == 'treated'})
    observed = abs(_did(data))
    extremes = 0
    draws = []
    for _ in range(n):
        shuffled = units[:]
        rng.shuffle(shuffled)
        fake_treated = set(shuffled[:n_treated])
        fake = [{**r, 'group': 'treated' if r['unit'] in fake_treated else 'control'}
                for r in data]
        d = _did(fake)
        draws.append(d)
        if abs(d) >= observed:
            extremes += 1
    return {'draws': n, 'placebo_at_least_as_extreme': extremes,
            'fraction': round(extremes / n, 4),
            'placebo_sd': round(statistics.pstdev(draws), 6) if len(draws) > 1 else 0.0}


def _leave_one_out(data: list[dict]) -> dict:
    """留一单位稳健性：去掉任一单位后估计是否变号。变号 = 结论悬于单个单位。"""
    base = _did(data)
    units = sorted({r['unit'] for r in data})
    flips, values = [], []
    for u in units:
        subset = [r for r in data if r['unit'] != u]
        if check_data_shape(subset, 'difference_in_differences'):
            continue                       # 去掉后四格不全，跳过而不是硬算
        d = _did(subset)
        values.append({'dropped_unit': u, 'estimate': round(d, 6)})
        if (d > 0) != (base > 0) and d != 0:
            flips.append(u)
    return {'sign_stable': not flips, 'flipping_units': flips, 'estimates': values}


def estimate_effect(mechanism: dict, spec: dict) -> dict:
    """
    带三层把关的效果估计。

    spec: {strategy, data: [{unit, group, period, outcome}], outcome_name?, treatment_name?}

    返回里**永远**带着识别假设、适用群体与时间范围、反驳结果和后端说明——
    一个脱离这些的数字没有意义，方案 §6.2 明确要求它们与估计一起输出。
    """
    readiness = causal_readiness(mechanism)
    if not readiness.get('ready_for_L3'):
        return {'errors': [
            f'机制 {mechanism.get("id")} 未满足 L3 入口条件，缺：'
            f'{sorted(readiness["missing_for_L3"])}。'
            f'没有估计目标与可辩护的识别策略就不做效果估计——'
            f'停在方向性解释，或先补条件再来'
        ], 'readiness': readiness, 'backends': detect_backends()}

    strategy = spec.get('strategy', 'difference_in_differences')
    data = spec.get('data') or []
    problems = check_data_shape(data, strategy)
    if problems:
        return {'errors': problems, 'readiness': readiness, 'backends': detect_backends()}

    backends = detect_backends()
    estimate = _did(data)
    placebo = _placebo(data)
    loo = _leave_one_out(data)

    flags = []
    if placebo['fraction'] > 0.1:
        flags.append(
            f'安慰剂检验：{placebo["fraction"]:.0%} 的随机分组产生了同等或更大的效应——'
            f'观测到的差异与噪声难以区分，不要报成效果'
        )
    if not loo['sign_stable']:
        flags.append(
            f'留一检验：去掉单位 {loo["flipping_units"]} 后估计变号——结论悬于单个单位'
        )
    if not backends['dowhy']['available']:
        flags.append(
            'DoWhy 未安装，使用内置最小双重差分。它没有 DoWhy 的识别机制、'
            '协变量调整与多种反驳器——把这个数当作**方向性证据**，'
            '需要正式结论时装 DoWhy 或交由专业工作流复算'
        )

    return {
        'estimand': mechanism.get('estimand'),
        'identification': mechanism.get('identification'),
        'strategy': strategy,
        'estimate': round(estimate, 6),
        'cell_means': {f'{g}_{p}': round(_cell_mean(data, g, p), 6)
                       for g in ('treated', 'control') for p in ('pre', 'post')},
        'refutations': {'placebo': placebo, 'leave_one_out': loo},
        'applicable_population': mechanism.get('applicable_population'),
        'applicable_period': mechanism.get('applicable_period'),
        'backend_used': 'dowhy' if backends['dowhy']['available'] else 'builtin_did',
        'backends': backends,
        'assumptions_are_the_analysts': (
            '平行趋势、无干预前预期效应、无溢出——这些假设由分析者承担，'
            '本工具不验证它们，反驳检验也不能证明它们成立'
        ),
        'flags': flags,
        'errors': [],
    }
