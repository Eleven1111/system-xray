"""
Tool: 跨维度因果图引擎（纯计算）

把 Step 5.2 的"21 对扫描"产出的交互边变成确定性结构：
  - 反馈回路检测（DFS 简单环搜索，按边符号乘积分类 reinforcing/balancing）
  - 恶性/良性循环判定（reinforcing 回路 + 回路内维度的当前评分/趋势）
  - 杠杆点排序（回路参与数为主，加权度数为辅 — Meadows）
  - 干预传播模拟（处方打在 Di 上，沿因果边逐跳衰减算出全维度涟漪）
  - 处方交叉检查（多处方对同一维度的叠加恶化 + 处方对之间的方向冲突）

边的语义：维度**健康度**的影响关系。
  sign='+'  : Di 健康 ↑ → Dj 健康 ↑（同向传导）
  sign='-'  : Di 健康 ↑ → Dj 健康 ↓（反向传导/拮抗）
strength='strong'（Di 变 1 分 → Dj 变 ≥0.5 分）或 'weak'。

回路分类（与 SKILL.md Step 3b 对齐）：
  - 边符号乘积为正 = reinforcing（自增强）——系统在恶化时表现为恶性循环，
    在改善时表现为良性循环，由回路内维度的评分/趋势判定方向
  - 边符号乘积为负 = balancing（自稳定/拮抗）

LLM 仍负责判断"有没有这条边、机制是什么"；本工具负责把这些判断的
**逻辑后果**（闭环、杠杆、涟漪、冲突）算到底，不靠手工记账。
"""

VALID_DIMS = {'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7'}
_STRENGTH_WEIGHT = {'strong': 0.6, 'weak': 0.3}

DIMENSION_LABELS = {
    'D1': '边界结构',
    'D2': '激励机制',
    'D3': '信息与反馈',
    'D4': '演化能力',
    'D5': '合法性与叙事',
    'D6': '耦合与依赖',
    'D7': '权力结构',
}


def validate_edges(edges: list[dict]) -> list[str]:
    """校验交互边数组，返回错误列表；空列表 = 通过。"""
    errors: list[str] = []
    if not isinstance(edges, list):
        return [f'edges 必须是数组，实际为 {type(edges).__name__}']
    for i, e in enumerate(edges):
        tag = f'edges[{i}]'
        if not isinstance(e, dict):
            errors.append(f'{tag} 必须是对象')
            continue
        src, dst = e.get('from'), e.get('to')
        if src not in VALID_DIMS:
            errors.append(f'{tag}.from 必须是 D1-D7，实际为 {src!r}')
        if dst not in VALID_DIMS:
            errors.append(f'{tag}.to 必须是 D1-D7，实际为 {dst!r}')
        if src == dst:
            errors.append(f'{tag} 不允许自环（{src}→{dst}）')
        if e.get('sign') not in ('+', '-'):
            errors.append(f'{tag}.sign 必须是 "+" 或 "-"，实际为 {e.get("sign")!r}')
        if e.get('strength') not in _STRENGTH_WEIGHT:
            errors.append(f'{tag}.strength 必须是 strong/weak，实际为 {e.get("strength")!r}')
    return errors


def find_feedback_loops(edges: list[dict], max_len: int = 4) -> list[dict]:
    """
    检测所有长度 ≤ max_len 的简单环（节点不重复），按边符号乘积分类。

    返回 [{dims: [Di,...], edges: [edge,...], polarity: 'reinforcing'|'balancing',
           min_strength: 'strong'|'weak'}]。
    去重：同一个环只按最小起点的规范形式报告一次。
    """
    adj: dict[str, list[dict]] = {}
    for e in edges:
        adj.setdefault(e['from'], []).append(e)

    seen: set[tuple] = set()
    loops: list[dict] = []

    def dfs(start: str, node: str, path_nodes: list[str], path_edges: list[dict]):
        for e in adj.get(node, []):
            nxt = e['to']
            if nxt == start and len(path_nodes) >= 2:
                cycle_nodes = path_nodes[:]
                # 规范形式：从字典序最小节点旋转，消除同环不同起点的重复
                k = cycle_nodes.index(min(cycle_nodes))
                canon = tuple(cycle_nodes[k:] + cycle_nodes[:k])
                if canon in seen:
                    continue
                seen.add(canon)
                cycle_edges = path_edges + [e]
                neg = sum(1 for ce in cycle_edges if ce['sign'] == '-')
                polarity = 'balancing' if neg % 2 else 'reinforcing'
                min_strength = 'weak' if any(
                    ce['strength'] == 'weak' for ce in cycle_edges) else 'strong'
                loops.append({
                    'dims': cycle_nodes,
                    'edges': cycle_edges,
                    'polarity': polarity,
                    'min_strength': min_strength,
                })
            elif nxt not in path_nodes and len(path_nodes) < max_len:
                # 只从最小起点展开，避免同环多起点重复搜索
                if nxt > start:
                    dfs(start, nxt, path_nodes + [nxt], path_edges + [e])

    for start in sorted({e['from'] for e in edges}):
        dfs(start, start, [start], [])
    return loops


def classify_loops(loops: list[dict], scores: dict | None = None,
                   trajectories: dict | None = None) -> list[dict]:
    """
    给回路标注诊断方向：reinforcing 回路结合回路内维度的评分/趋势判定
    恶性（vicious）/ 良性（virtuous）/ 方向待定；balancing 回路标 antagonistic。

    scores: {D1: 1-5, ...}（可选）；trajectories: {D1: 'up'|'stable'|'down', ...}（可选）。
    判定规则：reinforcing 回路内有任一维度 trajectory='down' 或平均分 ≤2.5 → vicious；
    全部 trajectory≠'down' 且平均分 ≥3.5 → virtuous；其余 → indeterminate。
    """
    scores = scores or {}
    trajectories = trajectories or {}
    out = []
    for lp in loops:
        item = dict(lp)
        if lp['polarity'] == 'balancing':
            item['diagnosis'] = 'antagonistic'
        else:
            dims = lp['dims']
            dim_scores = [scores[d] for d in dims if d in scores]
            avg = sum(dim_scores) / len(dim_scores) if dim_scores else None
            any_down = any(trajectories.get(d) == 'down' for d in dims)
            if any_down or (avg is not None and avg <= 2.5):
                item['diagnosis'] = 'vicious'
            elif not any_down and avg is not None and avg >= 3.5:
                item['diagnosis'] = 'virtuous'
            else:
                item['diagnosis'] = 'indeterminate'
        out.append(item)
    return out


def rank_leverage(edges: list[dict], loops: list[dict] | None = None) -> list[dict]:
    """
    杠杆点排序（Meadows）：主键 = 回路参与数，次键 = 加权度数（出+入，strong=0.6/weak=0.3）。

    返回降序 [{dim, label, loop_count, weighted_degree}]。
    """
    if loops is None:
        loops = find_feedback_loops(edges)
    loop_count: dict[str, int] = {}
    for lp in loops:
        for d in lp['dims']:
            loop_count[d] = loop_count.get(d, 0) + 1

    degree: dict[str, float] = {}
    for e in edges:
        w = _STRENGTH_WEIGHT[e['strength']]
        degree[e['from']] = degree.get(e['from'], 0.0) + w
        degree[e['to']] = degree.get(e['to'], 0.0) + w

    dims = sorted(set(loop_count) | set(degree))
    ranked = [{
        'dim': d,
        'label': DIMENSION_LABELS.get(d, d),
        'loop_count': loop_count.get(d, 0),
        'weighted_degree': round(degree.get(d, 0.0), 2),
    } for d in dims]
    ranked.sort(key=lambda x: (x['loop_count'], x['weighted_degree']), reverse=True)
    return ranked


def propagate_intervention(edges: list[dict], target_dim: str,
                           direction: float = 1.0, max_hops: int = 3) -> dict[str, float]:
    """
    干预传播模拟：对 target_dim 施加 direction（+1=改善该维度）的冲击，
    沿因果边逐跳传播（每跳乘 strength 权重和 sign），累加各维度净效应。

    简单环会被路径内去重截断（一条传播路径不重访节点），max_hops 限深。
    返回 {dim: net_effect}（含 target 自身 = direction），正=该维度被改善，负=被恶化。
    """
    adj: dict[str, list[dict]] = {}
    for e in edges:
        adj.setdefault(e['from'], []).append(e)

    effects: dict[str, float] = {target_dim: float(direction)}

    def walk(node: str, magnitude: float, visited: frozenset, hops: int):
        if hops >= max_hops or abs(magnitude) < 0.05:
            return
        for e in adj.get(node, []):
            nxt = e['to']
            if nxt in visited:
                continue
            eff = magnitude * _STRENGTH_WEIGHT[e['strength']] * (1 if e['sign'] == '+' else -1)
            effects[nxt] = round(effects.get(nxt, 0.0) + eff, 4)
            walk(nxt, eff, visited | {nxt}, hops + 1)

    walk(target_dim, float(direction), frozenset({target_dim}), 0)
    return {d: round(v, 3) for d, v in effects.items()}


def cross_check_prescriptions(prescriptions: list[dict], edges: list[dict]) -> dict:
    """
    Step 5.6 交叉检查的确定性实现。

    prescriptions: [{title, target_dimension, direction}]，direction 默认 +1（改善目标维度）。
    返回：
      per_prescription: [{title, target_dimension, spillover: {dim: effect}}]
      aggregate_effects: {dim: 各处方净效应之和}
      multi_worsened: [被 ≥2 条处方同时恶化的维度]
      conflicts: [{dim, prescription_a, prescription_b}]  # 两处方对同一维度方向相反且效应都不可忽略
    """
    per = []
    agg: dict[str, float] = {}
    dim_effects: dict[str, list[tuple[str, float]]] = {}

    for p in prescriptions:
        target = p['target_dimension']
        direction = float(p.get('direction', 1.0))
        spill = propagate_intervention(edges, target, direction)
        per.append({
            'title': p.get('title', target),
            'target_dimension': target,
            'spillover': spill,
        })
        for d, v in spill.items():
            agg[d] = round(agg.get(d, 0.0) + v, 3)
            dim_effects.setdefault(d, []).append((p.get('title', target), v))

    multi_worsened = sorted(
        d for d, pairs in dim_effects.items()
        if sum(1 for _, v in pairs if v <= -0.1) >= 2
    )

    conflicts = []
    for d, pairs in dim_effects.items():
        pos = [(t, v) for t, v in pairs if v >= 0.1]
        neg = [(t, v) for t, v in pairs if v <= -0.1]
        for tp, _ in pos:
            for tn, _ in neg:
                if tp != tn:
                    conflicts.append({'dim': d, 'prescription_a': tp, 'prescription_b': tn})

    return {
        'per_prescription': per,
        'aggregate_effects': agg,
        'multi_worsened': multi_worsened,
        'conflicts': conflicts,
    }


def analyze_graph(payload: dict) -> dict:
    """
    一次性入口（供 CLI）：payload = {edges, scores?, trajectories?, prescriptions?}。

    返回 {loops, leverage_ranking, prescription_check?, errors?}。
    edges 校验失败时只返回 errors。
    """
    edges = payload.get('edges', [])
    errors = validate_edges(edges)
    if errors:
        return {'errors': errors}

    loops = classify_loops(
        find_feedback_loops(edges),
        scores=payload.get('scores'),
        trajectories=payload.get('trajectories'),
    )
    result = {
        'loops': [{
            'path': ' → '.join(lp['dims'] + [lp['dims'][0]]),
            'dims': lp['dims'],
            'polarity': lp['polarity'],
            'diagnosis': lp['diagnosis'],
            'min_strength': lp['min_strength'],
        } for lp in loops],
        'leverage_ranking': rank_leverage(edges, loops),
    }
    if payload.get('prescriptions'):
        result['prescription_check'] = cross_check_prescriptions(
            payload['prescriptions'], edges)
    return result
