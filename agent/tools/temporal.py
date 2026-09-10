"""
Tool: 跨期更新（纯计算）

S2 的四件事，全部围绕一个判断：**看到的变化，究竟是系统变了，还是我们的观测变了？**

1. **双时间校验**：事件时间 / 发布时间 / 检索时间分开记。用检索日期冒充事件日期，
   会让一条旧闻看起来像刚发生的新进展。
2. **按断言类型的时效**：职位与危机状态按天计，组织章程按年计，统计序列看期次——
   废除"所有材料一个阈值"（此前是统一的两天 / 六个月）。
3. **口径可比性**：指标改口径造成的数值改善**不是系统改善**。改了口径就标为不可直接比较。
4. **判断变更分类**：两次分析之间新增/撤回/修订/保留了什么，以及每条变化属于
   系统状态变化 / 机制变化 / 观测变化 / 分析修正中的哪一类。

这些都是纯计算：LLM 负责判断"这条断言是什么类型""口径变了没有"，本模块负责把这些判断
的逻辑后果算到底。
"""

from datetime import datetime

# ── 1. 双时间 ──────────────────────────────────────────────────────────────

TIME_FIELDS = ('event_time', 'published_at', 'retrieved_at', 'valid_from', 'valid_to', 'as_of')


def _parse(s) -> datetime | None:
    if not s:
        return None
    digits = str(s).replace('-', '').replace('/', '')[:8]
    if len(digits) < 8:
        return None
    try:
        return datetime(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def check_time_fields(source: dict) -> list[str]:
    """
    校验单条信源的时间字段，返回问题列表。

    关键约束：**未知时间必须显式为空，不能用检索日期替代事件日期。**
    因此 `event_time == retrieved_at` 且没有 `published_at` 支撑时会被点名——
    这通常是"不知道事件何时发生，就填了今天"的痕迹。
    """
    problems: list[str] = []
    ev, pub, ret = (_parse(source.get(f)) for f in ('event_time', 'published_at', 'retrieved_at'))

    for f in TIME_FIELDS:
        if f in source and source[f] not in (None, '') and _parse(source[f]) is None:
            problems.append(f'{f} 不是可解析的日期：{source[f]!r}')

    if ev and pub and ev > pub:
        problems.append(f'event_time({source.get("event_time")}) 晚于 published_at'
                        f'({source.get("published_at")})——材料不可能先于事件发布')
    if pub and ret and pub > ret:
        problems.append(f'published_at 晚于 retrieved_at——检索时它还没发布，时间线不成立')
    if ev and ret and ev == ret and not pub:
        problems.append('event_time 等于 retrieved_at 且无 published_at——'
                        '疑似用检索日期替代了未知的事件日期；不知道就留空')

    vf, vt = _parse(source.get('valid_from')), _parse(source.get('valid_to'))
    if vf and vt and vf > vt:
        problems.append('valid_from 晚于 valid_to')
    return problems


def is_republication(source: dict, known_events: list[dict]) -> dict | None:
    """
    判断一条"新报道"是否只是旧事件的重发。

    命中条件：同一 `source_family`，或同一 `event_time` + 已登记过该事件。
    命中时返回原事件条目——调用方应**只更新访问记录，不当成新的系统变化**。
    """
    fam = source.get('source_family')
    ev = source.get('event_time')
    for known in known_events or []:
        if fam and known.get('source_family') == fam:
            return known
        if ev and known.get('event_time') == ev and known.get('event_key') and \
                known.get('event_key') == source.get('event_key'):
            return known
    return None


# ── 2. 按断言类型的时效 ────────────────────────────────────────────────────

# 每类断言的"多久算过期"。依据是**该类事实的实际变化速度**，不是一个统一的舒适阈值。
# `None` = 不按时间过期，改为按事件触发复查（见 recheck_trigger）。
CLAIM_TYPE_STALENESS = {
    'officeholder':      {'days': 7,    'why': '任免可以在一天内发生，且是最常被写错的载荷性事实'},
    'crisis_status':     {'days': 2,    'why': '危机按小时演进；两天前的状态描述可能已经作废'},
    'operational_status':{'days': 7,    'why': '停运/复运、封锁/解封变化快'},
    'market_price':      {'days': 1,    'why': '价格类数据当日即失效'},
    'policy_in_force':   {'days': 90,   'why': '政策生效状态变化慢，但修订需检查'},
    'financial_period':  {'days': 120,  'why': '按期次发布；关键是期次与修订版本，不是天数'},
    'statistical_series':{'days': 180,  'why': '看期次、发布日期与修订版本，而非新鲜度'},
    'charter_rule':      {'days': 730,  'why': '章程可长期有效，但须检查是否被修订'},
    'structural_fact':   {'days': 365,  'why': '所有权、依赖结构等变化缓慢'},
    'historical_fact':   {'days': None, 'why': '已发生的历史事实不因时间过期；只在新证据出现时复查'},
}

DEFAULT_CLAIM_TYPE = 'structural_fact'


def staleness(claim: dict, as_of: str | None = None) -> dict:
    """
    按断言类型判断一条断言是否过期。

    claim 需含 `claim_type`（见 CLAIM_TYPE_STALENESS）与一个时间锚点
    （`event_time` 优先，其次 `published_at`）。类型缺失时按 `structural_fact` 处理并给出提示。
    """
    ctype = claim.get('claim_type') or DEFAULT_CLAIM_TYPE
    policy = CLAIM_TYPE_STALENESS.get(ctype)
    notes = []
    if claim.get('claim_type') is None:
        notes.append(f'未声明 claim_type，按 `{DEFAULT_CLAIM_TYPE}` 处理——'
                     f'职位/危机状态类断言若被当作结构事实，会漏掉最该核验的过期')
    if policy is None:
        return {'claim_type': ctype, 'status': 'unknown_type', 'notes':
                notes + [f'未知 claim_type "{ctype}"，无法判定时效']}

    anchor_field = 'event_time' if claim.get('event_time') else 'published_at'
    anchor = _parse(claim.get(anchor_field))
    ref = _parse(as_of) or datetime.now()

    if policy['days'] is None:
        return {'claim_type': ctype, 'status': 'not_time_bound',
                'why': policy['why'], 'notes': notes}
    if anchor is None:
        return {'claim_type': ctype, 'status': 'no_anchor', 'notes':
                notes + ['无 event_time / published_at 锚点，无法判定时效——不得默认它还新鲜']}

    age = (ref - anchor).days
    return {
        'claim_type': ctype,
        'age_days': age,
        'threshold_days': policy['days'],
        'status': 'stale' if age > policy['days'] else 'fresh',
        'why': policy['why'],
        'notes': notes,
    }


def staleness_report(claims: list[dict], as_of: str | None = None) -> dict:
    """对断言账本整体做时效体检，按"过期且载荷"排序——最该复查的排在前面。"""
    rows = []
    for c in claims or []:
        if not isinstance(c, dict):
            continue
        r = staleness(c, as_of=as_of)
        r['id'] = c.get('id')
        r['statement'] = c.get('statement') or c.get('claim', '')
        r['loads'] = c.get('loads') or []
        rows.append(r)
    needs_recheck = [r for r in rows if r['status'] in ('stale', 'no_anchor') and r['loads']]
    needs_recheck.sort(key=lambda r: (-len(r['loads']), -(r.get('age_days') or 0)))
    return {
        'claims': rows,
        'needs_recheck': needs_recheck,
        'note': '时效按断言类型判定；不存在适用于所有材料的统一阈值',
    }


# ── 3. 口径可比性 ──────────────────────────────────────────────────────────

def comparability(current: dict, previous: dict) -> dict:
    """
    比较两次分析的口径版本，判断评分是否可直接比较。

    输入两份 analysis。看两处：
      - `dimension_basis_version`：{D1: "v2", ...} 或各维度自带的 `score_basis_version`
      - `measurement_changes`：LLM 登记的口径变更 [{metric, dimension, change, effective}]

    口径变了却出现"改善"，是 S2 明确要拦的假信号：数值上去了，测的东西已经不是同一个。
    """
    cur_basis = _basis_map(current)
    prev_basis = _basis_map(previous)

    changed = sorted(d for d in set(cur_basis) & set(prev_basis)
                     if cur_basis[d] != prev_basis[d])
    declared = [m for m in (current.get('measurement_changes') or []) if isinstance(m, dict)]
    declared_dims = {m.get('dimension') for m in declared if m.get('dimension')}
    affected = sorted(set(changed) | declared_dims)

    warnings = []
    for dim in affected:
        cur_s = (current.get('dimension_scores') or {}).get(dim)
        prev_s = (previous.get('dimension_scores') or {}).get(dim)
        if isinstance(cur_s, (int, float)) and isinstance(prev_s, (int, float)) \
                and not isinstance(cur_s, bool) and not isinstance(prev_s, bool):
            delta = round(cur_s - prev_s, 2)
            if delta > 0:
                warnings.append(
                    f'{dim} 评分 {prev_s} → {cur_s}（{delta:+.1f}）**但口径已变更**——'
                    f'不得读作系统改善；先校准口径，或标为不可直接比较'
                )
            elif delta != 0:
                warnings.append(
                    f'{dim} 评分 {prev_s} → {cur_s}（{delta:+.1f}）且口径已变更——'
                    f'变化量无法归因，先校准口径'
                )
            else:
                warnings.append(f'{dim} 口径已变更，分数相同不代表状态相同')

    return {
        'basis_changed_dims': changed,
        'declared_measurement_changes': declared,
        'incomparable_dims': affected,
        'comparable': not affected,
        'warnings': warnings,
    }


def _basis_map(analysis: dict) -> dict:
    """取各维度的口径版本：顶层 `dimension_basis_version` 优先，其次维度对象内的字段。"""
    top = analysis.get('dimension_basis_version')
    if isinstance(top, dict):
        return {k: str(v) for k, v in top.items()}
    dims = analysis.get('dimensions')
    out = {}
    if isinstance(dims, dict):
        for k, v in dims.items():
            if isinstance(v, dict) and v.get('score_basis_version'):
                out[k] = str(v['score_basis_version'])
    return out


# ── 4. 判断变更 ────────────────────────────────────────────────────────────

CHANGE_TYPES = ('system_state', 'mechanism', 'measurement', 'analysis_correction')


def diff_analyses(current: dict, previous: dict) -> dict:
    """
    两次分析之间的判断变更清单。

    对 mechanisms / actions / predictions 按 id 做集合差，对维度评分做数值差，
    并把每条变化归入四类之一（`measurement` 由口径比较推出，`analysis_correction`
    由被反证的断言推出）。

    返回 `judgement_changes`（可直接写入 analysis）+ 一份人读摘要。
    """
    comp = comparability(current, previous)
    incomparable = set(comp['incomparable_dims'])
    corrected = _corrected_targets(current)

    changes: list[dict] = []
    for kind in ('mechanisms', 'actions', 'predictions'):
        cur_map = _by_id(current.get(kind))
        prev_map = _by_id(previous.get(kind))
        for oid in sorted(set(cur_map) - set(prev_map)):
            changes.append({'object_id': oid, 'kind': kind, 'change': 'added',
                            'change_type': 'mechanism' if kind == 'mechanisms' else 'system_state',
                            'reason': '本期新增'})
        for oid in sorted(set(prev_map) - set(cur_map)):
            changes.append({'object_id': oid, 'kind': kind, 'change': 'withdrawn',
                            'change_type': 'analysis_correction' if oid in corrected else 'system_state',
                            'reason': '依赖的断言被反证' if oid in corrected else '本期不再成立或不再相关'})
        for oid in sorted(set(cur_map) & set(prev_map)):
            if cur_map[oid] == prev_map[oid]:
                changes.append({'object_id': oid, 'kind': kind, 'change': 'retained',
                               'change_type': 'system_state', 'reason': '未变'})
            else:
                changes.append({
                    'object_id': oid, 'kind': kind, 'change': 'revised',
                    'change_type': 'analysis_correction' if oid in corrected else 'mechanism',
                    'reason': '依赖的断言被反证' if oid in corrected else '内容有修订',
                })

    cur_scores = current.get('dimension_scores') or {}
    prev_scores = previous.get('dimension_scores') or {}
    for dim in sorted(set(cur_scores) & set(prev_scores)):
        if cur_scores[dim] == prev_scores[dim]:
            continue
        if dim in incomparable:
            changes.append({
                'object_id': dim, 'kind': 'dimension', 'change': 'revised',
                'change_type': 'measurement',
                'reason': f'口径变更，{prev_scores[dim]} → {cur_scores[dim]} 不可直接比较',
            })
        else:
            changes.append({
                'object_id': dim, 'kind': 'dimension', 'change': 'revised',
                'change_type': 'system_state',
                'reason': f'评分 {prev_scores[dim]} → {cur_scores[dim]}',
            })

    counts: dict[str, int] = {}
    for c in changes:
        counts[c['change']] = counts.get(c['change'], 0) + 1
    by_type: dict[str, int] = {}
    for c in changes:
        by_type[c['change_type']] = by_type.get(c['change_type'], 0) + 1

    return {
        'judgement_changes': changes,
        'counts': counts,
        'by_change_type': by_type,
        'comparability': comp,
        'previous_analysis_id': previous.get('analysis_id'),
        'current_analysis_id': current.get('analysis_id'),
        'note': ('观测变化（measurement）不是系统变化——先校准口径再解释；'
                 '分析修正（analysis_correction）须保留修订记录，不静默改写历史'),
    }


def _by_id(items) -> dict:
    if not isinstance(items, list):
        return {}
    out = {}
    for i, it in enumerate(items):
        if isinstance(it, dict):
            out[it.get('id') or f'#{i}'] = it
    return out


def _corrected_targets(analysis: dict) -> set:
    """被反证断言所load的对象 id——它们的变化属于分析修正，不是系统状态变化。"""
    targets: set = set()
    for c in (analysis.get('claims') or analysis.get('key_claims') or []):
        if not isinstance(c, dict):
            continue
        status = str(c.get('status') or
                     (c.get('independent_check') or {}).get('status') or '').lower()
        if status == 'contradicted':
            targets |= set(c.get('loads') or [])
    return targets
