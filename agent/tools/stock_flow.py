"""
Tool: L2 参数化局部模型（存量—流量，纯计算）

升级方案 §6.2 的 L2 层：**有单位、数据或可说明的专家范围时**，才把一条机制从
"箭头图"升级成带时间步长、初值、延迟与参数区间的局部动态模型。

它刻意做得很小：线性流量 + 一阶物质延迟 + 显式欧拉积分。这不是通用 SD 工具
（PySD/Vensim 才是），而是**够用来回答一个具体问题**的最小模型：
"在可辩护的参数区间内，这个定性结论还成立吗？"

**最重要的输出不是曲线，是稳健性判定。** 方案原话：若结论依赖某个任意参数，
直接显示不稳健。因此 `run_with_sensitivity()` 会在参数区间的**角点**上重跑，
只要定性结论翻转，就返回 `robust=False` 并点名是哪个参数翻的。

不做的事：
- 不做非线性、不做优化、不做参数拟合。需要那些就该上真正的 SD 工具。
- 不接受表达式字符串（不 eval 用户输入）。流量只能是常量或"与某存量成比例"。
- 不在缺参数区间时给单点结论——那是把任意假设包装成结果。
"""

from agent.validation import causal_readiness

# 流量的两种形式，足够表达"积压—处理""缓冲—消耗"这类局部机制
RATE_KINDS = ('const', 'proportional_to')


def validate_model(model: dict) -> list[str]:
    """校验模型规格，返回错误列表；空列表 = 通过。"""
    errors: list[str] = []
    if not isinstance(model, dict):
        return [f'model 必须是对象，实际为 {type(model).__name__}']

    stocks = model.get('stocks')
    if not isinstance(stocks, dict) or not stocks:
        errors.append('缺少 stocks（存量及其初值）')
        stocks = {}
    for name, v in (stocks or {}).items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errors.append(f'stocks.{name} 初值必须是数字，实际 {v!r}')

    dt = model.get('time_step')
    if not isinstance(dt, (int, float)) or isinstance(dt, bool) or dt <= 0:
        errors.append('time_step 必须是正数（L2 要求显式时间步长）')
    horizon = model.get('horizon')
    if not isinstance(horizon, (int, float)) or isinstance(horizon, bool) or horizon <= 0:
        errors.append('horizon 必须是正数')

    flows = model.get('flows')
    if not isinstance(flows, list) or not flows:
        errors.append('缺少 flows')
        flows = []
    for i, f in enumerate(flows or []):
        tag = f'flows[{i}]'
        if not isinstance(f, dict):
            errors.append(f'{tag} 必须是对象')
            continue
        if not f.get('name'):
            errors.append(f'{tag} 缺少 name')
        src, dst = f.get('from'), f.get('to')
        if src is None and dst is None:
            errors.append(f'{tag} 必须至少有 from 或 to（否则它不改变任何存量）')
        for end, label in ((src, 'from'), (dst, 'to')):
            if end is not None and end not in stocks:
                errors.append(f'{tag}.{label} 引用了未声明的存量 "{end}"')
        rate = f.get('rate')
        if not isinstance(rate, dict):
            errors.append(f'{tag}.rate 必须是对象')
            continue
        kind = rate.get('kind')
        if kind not in RATE_KINDS:
            errors.append(f'{tag}.rate.kind 必须是 {list(RATE_KINDS)} 之一，实际 {kind!r}')
        elif kind == 'const':
            if not isinstance(rate.get('value'), (int, float)):
                errors.append(f'{tag}.rate.value 必须是数字')
        else:
            if rate.get('stock') not in stocks:
                errors.append(f'{tag}.rate.stock 引用了未声明的存量 {rate.get("stock")!r}')
            if not isinstance(rate.get('coefficient'), (int, float)):
                errors.append(f'{tag}.rate.coefficient 必须是数字')
        delay = f.get('delay', 0)
        if not isinstance(delay, (int, float)) or isinstance(delay, bool) or delay < 0:
            errors.append(f'{tag}.delay 必须是非负数（0 = 无延迟）')
    return errors


def simulate(model: dict, overrides: dict | None = None) -> dict:
    """
    显式欧拉积分。返回 {times, series: {stock: [...]}, final: {stock: value}}。

    延迟用一阶物质延迟实现：感知值向真实存量指数逼近，时间常数 = `delay`。
    这是 SD 的标准做法，也是"看得见但反应慢"这类机制的最小表达。

    `overrides`：`{"流量名.coefficient": 0.3}` 形式的参数覆盖，供敏感性扫描使用。
    """
    errors = validate_model(model)
    if errors:
        return {'errors': errors}

    overrides = overrides or {}
    dt = float(model['time_step'])
    steps = int(round(float(model['horizon']) / dt))
    stocks = {k: float(v) for k, v in model['stocks'].items()}
    flows = [dict(f) for f in model['flows']]

    # 参数覆盖：只允许覆盖已声明的数值参数，避免"扫描"悄悄改变模型结构
    bad = []
    for key, value in overrides.items():
        fname, _, param = key.partition('.')
        target = next((f for f in flows if f.get('name') == fname), None)
        if target is None or param not in ('coefficient', 'value', 'delay'):
            bad.append(key)
            continue
        if param == 'delay':
            target['delay'] = value
        else:
            target['rate'] = {**target['rate'], param: value}
    if bad:
        return {'errors': [f'无法覆盖的参数：{bad}（只能覆盖已声明流量的 '
                           f'coefficient / value / delay）']}

    perceived = {f['name']: stocks.get(f.get('rate', {}).get('stock'), 0.0) for f in flows}
    times = [0.0]
    series = {k: [v] for k, v in stocks.items()}

    for step in range(steps):
        rates = {}
        for f in flows:
            rate, delay = f['rate'], float(f.get('delay', 0) or 0)
            if rate['kind'] == 'const':
                rates[f['name']] = float(rate['value'])
                continue
            actual = stocks[rate['stock']]
            if delay > 0:
                # 一阶物质延迟：感知值以 dt/delay 的速度向真实值逼近
                perceived[f['name']] += (dt / delay) * (actual - perceived[f['name']])
                basis = perceived[f['name']]
            else:
                basis = actual
            rates[f['name']] = float(rate['coefficient']) * basis

        deltas = {k: 0.0 for k in stocks}
        for f in flows:
            r = rates[f['name']]
            if f.get('from') is not None:
                # 存量不能被抽成负数：一步之内最多抽干
                r = min(r, stocks[f['from']] / dt) if r > 0 else r
                deltas[f['from']] -= r
            if f.get('to') is not None:
                deltas[f['to']] += r

        for k in stocks:
            stocks[k] = max(0.0, stocks[k] + deltas[k] * dt)
            series[k].append(stocks[k])
        times.append((step + 1) * dt)

    return {'times': times, 'series': series,
            'final': {k: round(v, 6) for k, v in stocks.items()}, 'errors': []}


def _corners(parameter_ranges: dict) -> list[dict]:
    """参数区间的角点组合（每个参数取上下界）。参数多时只取单参数扰动，避免组合爆炸。"""
    keys = sorted(parameter_ranges)
    if not keys:
        return []
    if len(keys) <= 3:
        combos = [{}]
        for k in keys:
            lo, hi = parameter_ranges[k]
            combos = [{**c, k: v} for c in combos for v in (lo, hi)]
        return combos
    # 超过 3 个参数：逐个单独扰动（一次一个），其余取区间中点
    mid = {k: (parameter_ranges[k][0] + parameter_ranges[k][1]) / 2 for k in keys}
    out = []
    for k in keys:
        for v in parameter_ranges[k]:
            out.append({**mid, k: v})
    return out


def run_with_sensitivity(model: dict, verdict: dict) -> dict:
    """
    在参数区间上跑敏感性，返回定性结论是否稳健。

    `verdict`：`{'stock': 'backlog', 'test': 'above'|'below', 'threshold': 50}`
    —— 要检验的**定性**结论，例如"期末积压仍高于 50"。
    这是刻意的限制：L2 给的是方向与量级感，不是精确预测。

    缺 `parameter_ranges` 时**拒绝给结论**——没有区间就只有一次任意参数下的单点运行，
    那不是模型结果，是一个假设。
    """
    ranges = model.get('parameter_ranges') or {}
    if not ranges:
        return {'errors': ['缺少 parameter_ranges：没有可辩护的参数区间就不能给 L2 结论'
                           '（单点运行只是把任意假设包装成结果）']}
    for k, v in ranges.items():
        if not (isinstance(v, (list, tuple)) and len(v) == 2
                and all(isinstance(x, (int, float)) for x in v) and v[0] <= v[1]):
            return {'errors': [f'parameter_ranges.{k} 必须是 [下界, 上界] 且下界 ≤ 上界']}

    stock = verdict.get('stock')
    test = verdict.get('test')
    threshold = verdict.get('threshold')
    if stock not in (model.get('stocks') or {}) or test not in ('above', 'below') \
            or not isinstance(threshold, (int, float)):
        return {'errors': ['verdict 需形如 {stock, test: above|below, threshold: 数字}']}

    def holds(run):
        val = run['final'][stock]
        return val > threshold if test == 'above' else val < threshold

    # 基线跑在**区间中点**上，不是模型里写死的那个点值——否则点值落在区间外时，
    # 基线本身就不在被检验的假设空间里，"翻转"会变成与区间无关的伪信号。
    midpoints = {k: (v[0] + v[1]) / 2 for k, v in ranges.items()}
    base = simulate(model, overrides=midpoints)
    if base.get('errors'):
        return {'errors': base['errors']}
    base_holds = holds(base)

    # 点值落在自己声明的区间外，是模型规格自相矛盾，必须点名
    declared_outside = []
    for key, (lo, hi) in ranges.items():
        fname, _, param = key.partition('.')
        f = next((x for x in model['flows'] if x.get('name') == fname), None)
        if f is None:
            continue
        current = f.get('delay') if param == 'delay' else f.get('rate', {}).get(param)
        if isinstance(current, (int, float)) and not (lo <= current <= hi):
            declared_outside.append(f'{key}={current} 不在声明区间 [{lo}, {hi}] 内')

    runs, flips = [], []
    for combo in _corners(ranges):
        r = simulate(model, overrides=combo)
        if r.get('errors'):
            return {'errors': r['errors']}
        ok = holds(r)
        runs.append({'overrides': combo, 'final': r['final'], 'verdict_holds': ok})
        if ok != base_holds:
            flips.append(combo)

    # 哪个参数单独就能翻转结论——这是"结论依赖某个任意参数"的直接证据
    culprits = sorted({k for combo in flips for k, v in combo.items()
                       if any(r['verdict_holds'] != base_holds and r['overrides'].get(k) == v
                              for r in runs)})

    robust = not flips
    return {
        'verdict': f'{stock} 期末{"高于" if test == "above" else "低于"} {threshold}',
        'baseline_overrides': midpoints,
        'holds_at_base': base_holds,
        'robust': robust,
        'runs': runs,
        'flipping_parameters': culprits,
        'spec_warnings': declared_outside,
        'conclusion': ('结论在整个参数区间内稳健' if robust else
                       f'**结论不稳健**：在参数区间内会翻转，翻转由 {culprits} 驱动——'
                       f'按 L2 规则应停在方向性描述，或先把这些参数钉死'),
        'errors': [],
    }


def run_gated(mechanism: dict, model: dict, verdict: dict) -> dict:
    """
    带入口门的运行：机制卡不满足 L2 条件时**拒绝出数**。

    这是 S4 的真正约束——工具能跑不代表当前输入满足算法要求。
    """
    readiness = causal_readiness(mechanism)
    if not readiness.get('ready_for_L2'):
        return {
            'errors': [f'机制 {mechanism.get("id")} 未满足 L2 入口条件，缺：'
                       f'{sorted(readiness["missing_for_L2"])}。'
                       f'停在 L1 的方向性解释，不要先跑模型再补条件'],
            'readiness': readiness,
        }
    result = run_with_sensitivity(model, verdict)
    result['readiness'] = readiness
    return result
