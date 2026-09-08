"""
Tool: ACH 竞争假说定量评分（纯计算）

把 Step 4.5 的 C/I/N 证据矩阵从"目测排序"变成可复算的加权判定：
  - **独立证据家族去重**（S0）：同一条原始证据被转载/翻译/复制 N 次只算 1 份权重。
    计数制造确定性是 ACH 最危险的失效模式——四篇转载同一公告不是四条独立支持。
  - 信源层级加权：同样一条 I，T1 证据的排除力远大于 T3
    （对应 system.md "如果 I 全部来自 T3 信源，降低排除信心"）
  - 鉴别力（diagnosticity）：对所有假说打同一标记的证据没有区分价值，降权
    （对应 ACH 原则"大多数证据与多个假说一致——能区分假说的是不一致证据"）
  - "一条强 I 比十条 C 更有诊断力"：排序主键是加权不一致分（升序），
    一致分只作次键，永不抵消 I
  - 状态机械判定：refuted(=eliminated) / stressed / active / untestable
  - **留一敏感性**（S0）：逐一移除载荷最大的证据家族，报告哪些状态因此翻转。
    翻转即"结论依赖单条证据"，必须在报告中显示，不能被一个综合置信分掩盖。
  - 全体存活 → 自动标记"高不确定状态"（本身就是关键发现）；
    全体被排除 → 提示复查证据矩阵或补充假说

**状态语义（S0 收紧）**：`eliminated` 表示"在当前所列证据与当前 C/I/N 编码下被条件性反驳"，
不表示该假说已被证明为假。编码变化或新证据到达都可能使它复活——这正是 `sensitivity` 要暴露的。

LLM 仍负责生成假说和逐条评 C/I/N；本工具负责把这些判断的逻辑后果算到底。
"""

import hashlib

_TIER_WEIGHT = {1: 3.0, 2: 2.0, 3: 1.0}
_NON_DIAGNOSTIC_FACTOR = 0.25   # 全 C / 全 I（无区分力）的证据按此降权
_ELIMINATION_THRESHOLD = 3.0    # 加权不一致分 ≥ 此值 → eliminated（= 一条满鉴别力的 T1 I）

VALID_RATINGS = {'C', 'I', 'N'}

STATUS_LEGEND = {
    'eliminated': '在当前证据集与当前 C/I/N 编码下被条件性反驳；不等于已证伪',
    'stressed':   '存在不一致证据但未达反驳阈值',
    'active':     '当前证据无法反驳；不等于已获证实',
    'untestable': '全部证据对它为中性——不可检验，不得标"成立"',
}


def validate_matrix(hypotheses: list[dict], evidence: list[dict]) -> list[str]:
    """校验假说清单与证据矩阵，返回错误列表；空列表 = 通过。"""
    errors: list[str] = []
    if not isinstance(hypotheses, list) or not hypotheses:
        return ['hypotheses 必须是非空数组']
    ids = []
    for i, h in enumerate(hypotheses):
        if not isinstance(h, dict) or not h.get('id'):
            errors.append(f'hypotheses[{i}] 缺少 id')
        else:
            ids.append(h['id'])
    if len(set(ids)) != len(ids):
        errors.append('hypotheses id 重复')

    if not isinstance(evidence, list) or not evidence:
        errors.append('evidence 必须是非空数组')
        return errors
    id_set = set(ids)
    for i, e in enumerate(evidence):
        tag = f'evidence[{i}]'
        if not isinstance(e, dict):
            errors.append(f'{tag} 必须是对象')
            continue
        tier = e.get('tier')
        if tier not in _TIER_WEIGHT:
            errors.append(f'{tag}.tier 必须是 1/2/3，实际为 {tier!r}')
        ratings = e.get('ratings')
        if not isinstance(ratings, dict) or not ratings:
            errors.append(f'{tag}.ratings 缺失或为空')
            continue
        for hid, r in ratings.items():
            if hid not in id_set:
                errors.append(f'{tag}.ratings 引用了未声明的假说 {hid!r}')
            if r not in VALID_RATINGS:
                errors.append(f'{tag}.ratings[{hid}] 必须是 C/I/N，实际为 {r!r}')
    return errors


def _family_key(e: dict):
    """
    证据的**独立来源家族**标识。

    显式 `source_family`（LLM 判定同一原始出处的转载/翻译/引用）优先；
    否则回退到内容指纹（描述 + 层级 + 评级组合）——机械复制的同一条证据会自动折叠。
    这是保守下限：本工具**不声称**能识别所有转载，未标 family 的不同措辞转述仍会被当成两族。
    """
    fam = e.get('source_family')
    if fam:
        return ('explicit', str(fam))
    desc = ' '.join(str(e.get('description', '')).split()).lower()
    ratings = tuple(sorted((k, v) for k, v in (e.get('ratings') or {}).items()))
    return ('fingerprint', desc, e.get('tier'), ratings)


def collapse_evidence_families(evidence: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    把证据列表折叠为独立证据家族，返回 (families, collapse_report)。

    每个家族取**层级最高**（tier 数字最小）的一条作代表，其余仅记入 `copies`。
    collapse_report 只列真正发生折叠（copies ≥ 2）的家族。
    """
    order: list = []
    grouped: dict = {}
    for e in evidence:
        k = _family_key(e)
        if k not in grouped:
            grouped[k] = []
            order.append(k)
        grouped[k].append(e)

    families, report = [], []
    for k in order:
        members = grouped[k]
        rep = min(members, key=lambda m: m.get('tier', 9))
        fam = dict(rep)
        fam['copies'] = len(members)
        # 指纹用稳定摘要，不用内置 hash()——后者按进程加盐，family_id 会跨运行漂移
        fam['family_id'] = (
            k[1] if k[0] == 'explicit'
            else 'fp:' + hashlib.sha1(repr(k).encode('utf-8')).hexdigest()[:8]
        )
        families.append(fam)
        if len(members) > 1:
            report.append({
                'family_id': fam['family_id'],
                'description': fam.get('description', ''),
                'copies': len(members),
                'note': '同一证据的重复条目已折叠为 1 份独立权重',
            })
    return families, report


def _diagnosticity(ratings: dict) -> float:
    """证据的鉴别力：对不同假说打出不同标记 = 有区分价值（1.0），否则降权。"""
    non_neutral = [r for r in ratings.values() if r in ('C', 'I')]
    if not non_neutral:
        return 0.0                       # 全 N：无信息量
    if len(set(ratings.values())) == 1:
        return _NON_DIAGNOSTIC_FACTOR    # 全 C 或全 I：与所有假说同关系，无区分力
    return 1.0


def _rank(hypotheses: list[dict], evidence: list[dict]) -> list[dict]:
    """在给定证据家族集合上计算排序（不做校验、不做敏感性）。"""
    ranking = []
    for h in hypotheses:
        hid = h['id']
        w_i = w_c = 0.0
        i_count = c_count = n_count = 0
        strongest_i = None
        strongest_i_w = 0.0
        for e in evidence:
            r = e.get('ratings', {}).get(hid, 'N')
            if r == 'N':
                n_count += 1
                continue
            w = _TIER_WEIGHT[e['tier']] * _diagnosticity(e['ratings'])
            if r == 'I':
                i_count += 1
                w_i += w
                if w > strongest_i_w:
                    strongest_i_w = w
                    strongest_i = {'description': e.get('description', ''), 'tier': e['tier']}
            else:
                c_count += 1
                w_c += w

        if w_i >= _ELIMINATION_THRESHOLD:
            status = 'eliminated'
        elif w_i > 0:
            status = 'stressed'
        elif i_count + c_count == 0:
            status = 'untestable'
        else:
            status = 'active'

        ranking.append({
            'id': hid,
            'statement': h.get('statement', ''),
            'status': status,
            'weighted_inconsistency': round(w_i, 2),
            'weighted_consistency': round(w_c, 2),
            'i_count': i_count,
            'c_count': c_count,
            'n_count': n_count,
            'strongest_i': strongest_i,
        })

    # 主键：加权不一致分升序（I 最少 = 最难排除 = 最可能成立）；次键：一致分降序
    ranking.sort(key=lambda x: (x['weighted_inconsistency'], -x['weighted_consistency']))
    return ranking


def _leave_one_out(hypotheses: list[dict], families: list[dict],
                   baseline: list[dict]) -> list[dict]:
    """
    逐一移除证据家族，报告哪些假说状态因此翻转。

    结论对单条证据敏感 = "依赖关键假设"，必须显示，不能藏进综合置信分。
    """
    base_status = {r['id']: r['status'] for r in baseline}
    out = []
    for i, fam in enumerate(families):
        reduced = families[:i] + families[i + 1:]
        if not reduced:
            continue
        changes = [
            {'id': r['id'], 'from': base_status[r['id']], 'to': r['status']}
            for r in _rank(hypotheses, reduced) if r['status'] != base_status[r['id']]
        ]
        if changes:
            out.append({
                'removed_family': fam.get('family_id'),
                'description': fam.get('description', ''),
                'tier': fam.get('tier'),
                'status_changes': changes,
            })
    return out


def score_hypotheses(hypotheses: list[dict], evidence: list[dict]) -> dict:
    """
    计算每个假说的加权一致/不一致分并判定状态。

    hypotheses: [{id, statement?}]
    evidence:   [{description?, tier: 1|2|3, ratings: {hid: 'C'|'I'|'N'},
                  source_family?: str}]   ← 同一原始出处的转载/翻译请标同一 source_family

    返回：
      {
        ranking: [{id, statement, status, weighted_inconsistency, weighted_consistency,
                   i_count, c_count, n_count, strongest_i: {description, tier} | None}],
        evidence_families: int,          # 折叠后的独立证据家族数
        collapsed_duplicates: [...],     # 被折叠的重复证据（copies ≥ 2）
        sensitivity: {leave_one_out: [...], robust: bool},
        status_legend: {...},            # 状态的条件性语义
        flags: [str],                    # 全体存活 / 全体排除 / 重复证据 等结构性信号
        errors: [str]                    # 非空时其余字段缺省
      }
    状态规则（作用于**独立证据家族**，不是原始条目数）：
      eliminated  — 加权不一致分 ≥ 3.0（如一条满鉴别力的 T1 I）；语义见 STATUS_LEGEND
      stressed    — 0 < 加权不一致分 < 3.0
      active      — 不一致分 = 0 且至少有 1 条非中性证据
      untestable  — 全部证据对它都是 N（零 I + 零 C，不可标"成立"）
    """
    errors = validate_matrix(hypotheses, evidence)
    if errors:
        return {'errors': errors}

    families, collapsed = collapse_evidence_families(evidence)
    ranking = _rank(hypotheses, families)
    loo = _leave_one_out(hypotheses, families, ranking)

    flags: list[str] = []
    if collapsed:
        n_dropped = sum(c['copies'] - 1 for c in collapsed)
        flags.append(
            f'{n_dropped} 条重复证据已折叠为独立家族——转载/复制不增加独立证据权重'
        )
    if loo:
        flags.append(
            f'{len(loo)} 条证据家族具有决定性：移除任一条会翻转假说状态——结论依赖关键证据，'
            f'须在报告中显式说明，不得输出无条件强结论'
        )
    statuses = [r['status'] for r in ranking]
    survivors = [r for r in ranking if r['status'] in ('active', 'stressed')]
    if 'eliminated' not in statuses and len(survivors) >= 2:
        flags.append('全部假说存活——系统处于高不确定状态，多个解释模型同时可行（这本身是关键发现）')
    if all(s == 'eliminated' for s in statuses):
        flags.append('全部假说被条件性反驳——须复查证据矩阵是否有误，或补充新假说')
    for r in ranking:
        if r['status'] == 'untestable':
            flags.append(f'{r["id"]} 不可检验（全部证据为 N）——标注"不可检验"而非"成立"')
        if r['status'] == 'stressed' and r['strongest_i'] and r['strongest_i']['tier'] == 3:
            flags.append(f'{r["id"]} 的不一致证据最高仅 T3——排除信心有限，建议 Round 2 求证')

    return {
        'ranking': ranking,
        'evidence_families': len(families),
        'evidence_items_submitted': len(evidence),
        'collapsed_duplicates': collapsed,
        'sensitivity': {'leave_one_out': loo, 'robust': not loo},
        'status_legend': STATUS_LEGEND,
        'flags': flags,
        'errors': [],
    }
