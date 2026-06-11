"""
Tool: ACH 竞争假说定量评分（纯计算）

把 Step 4.5 的 C/I/N 证据矩阵从"目测排序"变成可复算的加权判定：
  - 信源层级加权：同样一条 I，T1 证据的排除力远大于 T3
    （对应 system.md "如果 I 全部来自 T3 信源，降低排除信心"）
  - 鉴别力（diagnosticity）：对所有假说打同一标记的证据没有区分价值，降权
    （对应 ACH 原则"大多数证据与多个假说一致——能区分假说的是不一致证据"）
  - "一条强 I 比十条 C 更有诊断力"：排序主键是加权不一致分（升序），
    一致分只作次键，永不抵消 I
  - 状态机械判定：eliminated / stressed / active / untestable
  - 全体存活 → 自动标记"高不确定状态"（本身就是关键发现）；
    全体被排除 → 提示复查证据矩阵或补充假说

LLM 仍负责生成假说和逐条评 C/I/N；本工具负责把这些判断的逻辑后果算到底。
"""

_TIER_WEIGHT = {1: 3.0, 2: 2.0, 3: 1.0}
_NON_DIAGNOSTIC_FACTOR = 0.25   # 全 C / 全 I（无区分力）的证据按此降权
_ELIMINATION_THRESHOLD = 3.0    # 加权不一致分 ≥ 此值 → eliminated（= 一条满鉴别力的 T1 I）

VALID_RATINGS = {'C', 'I', 'N'}


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


def _diagnosticity(ratings: dict) -> float:
    """证据的鉴别力：对不同假说打出不同标记 = 有区分价值（1.0），否则降权。"""
    non_neutral = [r for r in ratings.values() if r in ('C', 'I')]
    if not non_neutral:
        return 0.0                       # 全 N：无信息量
    if len(set(ratings.values())) == 1:
        return _NON_DIAGNOSTIC_FACTOR    # 全 C 或全 I：与所有假说同关系，无区分力
    return 1.0


def score_hypotheses(hypotheses: list[dict], evidence: list[dict]) -> dict:
    """
    计算每个假说的加权一致/不一致分并判定状态。

    hypotheses: [{id, statement?}]
    evidence:   [{description?, tier: 1|2|3, ratings: {hid: 'C'|'I'|'N'}}]

    返回：
      {
        ranking: [{id, statement, status, weighted_inconsistency, weighted_consistency,
                   i_count, c_count, n_count, strongest_i: {description, tier} | None}],
        flags: [str],            # 全体存活 / 全体排除 / 不可检验假说 等结构性信号
        errors: [str]            # 非空时其余字段缺省
      }
    状态规则：
      eliminated  — 加权不一致分 ≥ 3.0（如一条满鉴别力的 T1 I）
      stressed    — 0 < 加权不一致分 < 3.0
      active      — 不一致分 = 0 且至少有 1 条非中性证据
      untestable  — 全部证据对它都是 N（零 I + 零 C，不可标"成立"）
    """
    errors = validate_matrix(hypotheses, evidence)
    if errors:
        return {'errors': errors}

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

    flags: list[str] = []
    statuses = [r['status'] for r in ranking]
    survivors = [r for r in ranking if r['status'] in ('active', 'stressed')]
    if 'eliminated' not in statuses and len(survivors) >= 2:
        flags.append('全部假说存活——系统处于高不确定状态，多个解释模型同时可行（这本身是关键发现）')
    if all(s == 'eliminated' for s in statuses):
        flags.append('全部假说被排除——须复查证据矩阵是否有误，或补充新假说')
    for r in ranking:
        if r['status'] == 'untestable':
            flags.append(f'{r["id"]} 不可检验（全部证据为 N）——标注"不可检验"而非"成立"')
        if r['status'] == 'stressed' and r['strongest_i'] and r['strongest_i']['tier'] == 3:
            flags.append(f'{r["id"]} 的不一致证据最高仅 T3——排除信心有限，建议 Round 2 求证')

    return {'ranking': ranking, 'flags': flags, 'errors': []}
