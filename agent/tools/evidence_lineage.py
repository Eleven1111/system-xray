"""
Tool: 证据血缘与依赖传播（纯计算）

S1 的核心闭环：`source → claim → mechanism → judgment → forecast/action`。
本模块回答三个此前只能靠人工记账的问题：

1. **哪些"多条信源"其实是同一条？** 按 `source_family` 与规范化 URL 折叠转载/翻译/引用，
   给出**独立来源家族数**——这是断言支撑强度的真实分母。
2. **某条断言被推翻后，什么跟着塌？** 沿 `loads` 关系传播，把依赖它的机制、预测、行动
   标 `needs_review`。**只传播实质反证**（`contradicted`），不因链接暂时打不开就判断言为假。
3. **哪些结论悬空？** 载荷性断言未被任何 claim 支撑、或引用了不存在的 id。

设计约束（诚实边界）：
- 折叠是**保守下限**。未标 `source_family` 的不同措辞转述仍会被当成两族——
  本工具不声称能识别所有转载。
- `supported` 只表示"在所列材料与口径下获得支持"，不等同于永久为真。
- 传播只标记 `needs_review`，**不自动撤销**其他独立支撑的结论。
"""

from urllib.parse import urlsplit, urlunsplit

# 被推翻的断言会传播到这些对象类型；报告完整性状态不在其中（§9.4：二者并列，不互相抹去）
DEPENDENT_KINDS = ('mechanisms', 'predictions', 'actions', 'risk_nodes', 'dimensions')

_TRACKING_PREFIXES = ('utm_', 'fbclid', 'gclid', 'ref', 'ref_src', 'spm')


def normalize_url(url) -> str:
    """
    规范化 URL 用于去重：去 scheme 大小写、去 www、去追踪参数、去末尾斜杠与锚点。

    这是**保守**去重：只合并明显同一资源的地址，不做跨域猜测。
    """
    if not isinstance(url, str) or not url.strip():
        return ''
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = (parts.netloc or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    query = '&'.join(
        q for q in (parts.query or '').split('&')
        if q and not any(q.lower().startswith(p) for p in _TRACKING_PREFIXES)
    )
    path = (parts.path or '').rstrip('/')
    return urlunsplit(((parts.scheme or 'https').lower(), host, path, query, ''))


def source_families(sources: list[dict]) -> dict:
    """
    把信源折叠为独立来源家族。

    家族键优先取显式 `source_family`；否则取规范化 URL。
    返回 {families: {fid: [source,...]}, independent_count, collapsed: [...]}。
    """
    families: dict[str, list[dict]] = {}
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        fid = s.get('source_family') or normalize_url(s.get('url')) or (s.get('title') or '').strip()
        if not fid:
            continue
        families.setdefault(fid, []).append(s)

    collapsed = [
        {'family_id': fid, 'members': len(items),
         'lineages': sorted({str(i.get('lineage', 'unknown')) for i in items}),
         'note': '同一来源家族的多条信源，只计一份独立支撑'}
        for fid, items in families.items() if len(items) > 1
    ]
    return {
        'families': families,
        'independent_count': len(families),
        'collapsed': collapsed,
    }


def claim_support(claim: dict) -> dict:
    """
    单条断言的支撑强度画像。

    区分 supports / contradicts / background：**背景链接不算支撑**。
    可达状态与核验状态分开报告——链接打不开不等于断言为假。
    """
    sources = claim.get('sources') or []
    supporting = [s for s in sources if isinstance(s, dict) and s.get('role') == 'supports']
    contradicting = [s for s in sources if isinstance(s, dict) and s.get('role') == 'contradicts']
    background = [s for s in sources if isinstance(s, dict) and s.get('role') == 'background']

    fam = source_families(supporting)
    direct = [s for s in supporting if s.get('directness') == 'direct']
    tiers = [s.get('tier') for s in supporting if isinstance(s.get('tier'), int)]
    unreachable = [s for s in sources
                   if isinstance(s, dict) and s.get('reachability') == 'unavailable']

    notes = []
    if fam['independent_count'] < 2:
        notes.append('独立来源家族 < 2——支撑单薄，建议独立复核')
    if supporting and not direct:
        notes.append('无任何 direct 支撑：所列材料只能间接触及该断言')
    if background and not supporting:
        notes.append('只有 background 材料——背景链接不构成支撑，状态不应为 supported')
    if unreachable:
        notes.append(
            f'{len(unreachable)} 条信源当前不可达——先查存档与其他独立支撑，'
            f'不因不可达就判断言为假'
        )

    return {
        'id': claim.get('id'),
        'status': claim.get('status', 'unresolved'),
        'independent_families': fam['independent_count'],
        'collapsed': fam['collapsed'],
        'supporting': len(supporting),
        'contradicting': len(contradicting),
        'background_only': len(background) if not supporting else 0,
        'direct_support': len(direct),
        'best_tier': min(tiers) if tiers else None,
        'unreachable_sources': len(unreachable),
        'notes': notes,
    }


def affected_by_contradiction(analysis: dict) -> dict:
    """
    某些断言被实质反证后，哪些结论必须复核。

    传播规则（保守）：
      - 只有 `status == 'contradicted'` 的断言才传播（`unresolved` 不传播，
        `unavailable` 的信源更不传播——可达性不是真伪）
      - 依赖对象通过 `claims[].loads` 中的 id 标识
      - 结果是 `needs_review` 标记，**不是自动撤销**：其他独立支撑的结论不必全部失效

    返回 {contradicted_claims, needs_review: {object_id: [claim_id,...]},
          dangling_loads, orphan_dependents}
    """
    claims = analysis.get('claims') or analysis.get('key_claims') or []
    known_ids = _known_object_ids(analysis)

    contradicted, needs_review, dangling = [], {}, []
    for c in claims:
        if not isinstance(c, dict):
            continue
        status = str(c.get('status') or
                     (c.get('independent_check') or {}).get('status') or '').lower()
        loads = c.get('loads') or []
        for target in loads:
            if known_ids and target not in known_ids:
                dangling.append({'claim': c.get('id'), 'missing_target': target})
        if status != 'contradicted':
            continue
        contradicted.append({'id': c.get('id'), 'statement': c.get('statement') or c.get('claim', '')})
        for target in loads:
            needs_review.setdefault(target, []).append(c.get('id'))

    return {
        'contradicted_claims': contradicted,
        'needs_review': needs_review,
        'dangling_loads': dangling,
        'rule': ('只有实质反证（contradicted）向下传播，且只标 needs_review 不自动撤销；'
                 '信源不可达（unavailable）不构成反证'),
    }


def _known_object_ids(analysis: dict) -> set:
    """收集 analysis 中可被 `loads` 指向的对象 id（为空时不做悬空检查）。"""
    ids: set = set()
    for kind in DEPENDENT_KINDS:
        items = analysis.get(kind)
        if isinstance(items, dict):          # dimensions: {D1: {...}}
            ids |= set(items)
        elif isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get('id'):
                    ids.add(it['id'])
    return ids


def lineage_report(analysis: dict) -> dict:
    """一次性入口（供 CLI）：断言支撑画像 + 反证传播 + 悬空引用。"""
    claims = analysis.get('claims') or analysis.get('key_claims') or []
    profiles = [claim_support(c) for c in claims if isinstance(c, dict)]
    propagation = affected_by_contradiction(analysis)

    thin = [p for p in profiles if p['independent_families'] < 2 and p['status'] == 'supported']
    flags = []
    if thin:
        flags.append(
            f'{len(thin)} 条已标 supported 的断言只有 1 个独立来源家族——'
            f'"supported" 只表示在所列材料与口径下获得支持，不等同于永久为真'
        )
    if propagation['needs_review']:
        flags.append(
            f'{len(propagation["needs_review"])} 个结论依赖已被反证的断言，须标 needs_review 并修订或撤下'
        )
    if propagation['dangling_loads']:
        flags.append(
            f'{len(propagation["dangling_loads"])} 条 loads 指向不存在的对象 id——依赖链断裂'
        )

    return {'claims': profiles, 'propagation': propagation, 'flags': flags}
