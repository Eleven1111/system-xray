"""
统一契约校验（S1）

此前校验散在三处：`db.validate_analysis`（存储 shape）、`db.process_warnings`（流程告警）、
`references/diagnostic-schema.json`（结构规范），三者语义并不一致，
而 S1 新增的 claims / mechanisms / actions / coverage_audit 没有任何出口在校验。

本模块是**各 CLI 出口复用的单一入口**：

    errors, warnings = validate_contract(analysis)

- `errors`：硬错误，拒绝落盘（结构非法、依赖断裂、预测语义缺失、自称完整却缺流程实据）
- `warnings`：非阻塞提醒（覆盖缺口、支撑单薄、需复核对象）

分工不变：`db.validate_analysis` 继续负责存储 shape 的向后兼容校验，本模块调用它并叠加
S1 的对象层校验。旧记录（没有 claims/mechanisms/actions）仍可读、仍可存——
新契约只在**字段存在时**严格，缺失时给告警，避免一次升级把历史数据全判死。
"""

from agent.store.db import (
    COMPLETENESS_STATES, completeness_blockers, derive_completeness,
    process_warnings, validate_analysis,
)
from agent.tools.evidence_lineage import lineage_report
from agent.tools.temporal import check_time_fields, staleness_report
from agent.schema_adapter import to_runtime

_ID_PREFIX = {'claims': 'C', 'mechanisms': 'M', 'actions': 'A'}

_VALID_EXECUTOR_ROLES = {'user_direct', 'user_influence', 'user_monitor_only', 'third_party'}
_VALID_CLAIM_STATUS = {'supported', 'contradicted', 'unresolved'}
_VALID_COVERAGE_STATUS = {'covered', 'unknown', 'not_applicable'}
_VALID_CAUSAL_LEVELS = {'L1_explanatory', 'L2_parameterised', 'L3_effect_estimate'}

# 权限边界：契约声明的用户权限 → 允许出现的行动执行角色。
# "建议正确"不等于执行者有权限——行动卡不得超出契约里写明的权限。
_AUTHORITY_ALLOWS = {
    'can_act':           {'user_direct', 'user_influence', 'user_monitor_only', 'third_party'},
    'can_influence':     {'user_influence', 'user_monitor_only', 'third_party'},
    'can_only_monitor':  {'user_monitor_only', 'third_party'},
    'unknown':           {'user_direct', 'user_influence', 'user_monitor_only', 'third_party'},
}

REQUIRED_ELEMENT_GROUPS = (
    'goals_and_evaluators', 'boundary_and_environment', 'actors_and_capabilities',
    'rules_and_metarules', 'resources_and_stocks', 'information_and_measurement',
    'production_process', 'dependencies_and_substitutes', 'power_and_legitimacy',
    'time_and_adaptation', 'distribution_and_externalities', 'analyst_and_reflexivity',
)


def _check_ids(analysis: dict) -> list[str]:
    """对象 id 必须存在、唯一、带正确前缀——依赖链靠它串起来。"""
    errors: list[str] = []
    for kind, prefix in _ID_PREFIX.items():
        items = analysis.get(kind)
        if items is None:
            continue
        if not isinstance(items, list):
            errors.append(f'{kind} 必须是数组，实际为 {type(items).__name__}')
            continue
        seen: set = set()
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                errors.append(f'{kind}[{i}] 必须是对象')
                continue
            oid = it.get('id')
            if not oid:
                errors.append(f'{kind}[{i}] 缺少 id（依赖链无法引用它）')
                continue
            if not str(oid).startswith(prefix):
                errors.append(f'{kind}[{i}].id "{oid}" 应以 `{prefix}` 开头')
            if oid in seen:
                errors.append(f'{kind} 中 id "{oid}" 重复')
            seen.add(oid)
    return errors


def _check_claims(analysis: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    claims = analysis.get('claims')
    if claims is None or not isinstance(claims, list):
        return errors, warnings
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            continue
        tag = f'claims[{i}]({c.get("id")})'
        if not c.get('statement'):
            errors.append(f'{tag} 缺少 statement')
        st = c.get('status')
        if st not in _VALID_CLAIM_STATUS:
            errors.append(f'{tag}.status 必须是 {sorted(_VALID_CLAIM_STATUS)} 之一，实际为 {st!r}')
        srcs = c.get('sources')
        if not isinstance(srcs, list) or not srcs:
            errors.append(f'{tag} 缺少 sources（断言必须可追溯到具体材料）')
            continue
        for j, s in enumerate(srcs):
            if not isinstance(s, dict):
                errors.append(f'{tag}.sources[{j}] 必须是对象')
                continue
            if not isinstance(s.get('url'), str) or not s['url'].strip():
                errors.append(f'{tag}.sources[{j}] 缺少 url（断言必须可回到原始材料）')
            if s.get('role') not in ('supports', 'contradicts', 'background'):
                errors.append(
                    f'{tag}.sources[{j}].role 必须是 supports/contradicts/background——'
                    f'背景链接不得冒充支撑'
                )
            # 可达状态与核验状态分开：这里只校验取值，不据可达性推断真伪
            reach = s.get('reachability')
            if reach is not None and reach not in ('reachable', 'unavailable', 'unchecked'):
                errors.append(f'{tag}.sources[{j}].reachability 取值非法：{reach!r}')
        if c.get('status') == 'supported' and not any(
                isinstance(s, dict) and s.get('role') == 'supports' for s in srcs):
            errors.append(f'{tag} 标为 supported 却无任何 role=supports 的信源')
    return errors, warnings


def _check_mechanisms(analysis: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    mechs = analysis.get('mechanisms')
    if mechs is None or not isinstance(mechs, list):
        return errors, warnings
    claim_ids = {c.get('id') for c in (analysis.get('claims') or []) if isinstance(c, dict)}
    for i, m in enumerate(mechs):
        if not isinstance(m, dict):
            continue
        tag = f'mechanisms[{i}]({m.get("id")})'
        for field in ('explains', 'chain'):
            if not m.get(field):
                errors.append(f'{tag} 缺少 {field}')
        if not m.get('alternatives'):
            errors.append(
                f'{tag} 缺少 alternatives——机制卡必须给至少一个会导向不同观察或行动的替代解释；'
                f'确无合理替代时把搜索过程写进这个字段'
            )
        if not m.get('failure_conditions'):
            errors.append(f'{tag} 缺少 failure_conditions（哪条观察会使该机制降级或被替代）')
        if not m.get('discriminating_predictions'):
            warnings.append(f'⚠️ {tag} 无鉴别预测：无法把它与替代解释区分开，解释价值受限')
        lvl = m.get('causal_level')
        if lvl is not None and lvl not in _VALID_CAUSAL_LEVELS:
            errors.append(f'{tag}.causal_level 必须是 {sorted(_VALID_CAUSAL_LEVELS)} 之一')
        elif lvl in ('L2_parameterised', 'L3_effect_estimate'):
            readiness = causal_readiness(m)
            if readiness['overclaimed']:
                need = (readiness['missing_for_L3'] if lvl == 'L3_effect_estimate'
                        else readiness['missing_for_L2'])
                errors.append(
                    f'{tag} 声明 {lvl}，但只满足 {readiness["ready_for"]} 的入口条件——'
                    f'缺：{sorted(need)}。不能由 L1 箭头直接升级；'
                    f'条件不满足时说明不能识别或不能估计，停在方向性解释'
                )
        for ref in (m.get('supporting_claims') or []) + (m.get('contradicting_claims') or []):
            if ref not in claim_ids:
                errors.append(f'{tag} 引用了不存在的断言 id "{ref}"')
    return errors, warnings


def _check_actions(analysis: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    actions = analysis.get('actions')
    if actions is None or not isinstance(actions, list):
        return errors, warnings
    mech_ids = {m.get('id') for m in (analysis.get('mechanisms') or []) if isinstance(m, dict)}
    authority = ((analysis.get('analysis_contract') or {}).get('user_authority')) or 'unknown'
    allowed = _AUTHORITY_ALLOWS.get(authority, _AUTHORITY_ALLOWS['unknown'])

    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            continue
        tag = f'actions[{i}]({a.get("id")})'
        if not a.get('action'):
            errors.append(f'{tag} 缺少 action')
        mid = a.get('mechanism_id')
        if not mid:
            errors.append(f'{tag} 缺少 mechanism_id——建议必须说明通过哪个机制起作用')
        elif mid not in mech_ids:
            errors.append(f'{tag} 引用了不存在的机制 id "{mid}"')
        role = a.get('executor_role')
        if role not in _VALID_EXECUTOR_ROLES:
            errors.append(f'{tag}.executor_role 必须是 {sorted(_VALID_EXECUTOR_ROLES)} 之一')
        elif role not in allowed:
            errors.append(
                f'{tag}.executor_role="{role}" 超出契约声明的用户权限 '
                f'"{authority}"——对只能监测的读者不得给出虚假可执行承诺'
            )
        if not a.get('first_step'):
            errors.append(f'{tag} 缺少 first_step（第一个可交付动作与完成定义）')
        ver = a.get('verification')
        if not isinstance(ver, dict) or not ver.get('outcome_metric'):
            errors.append(f'{tag} 缺少 verification.outcome_metric（无法验证 = 不是建议，是观察）')
        guard = a.get('guardrails')
        if not isinstance(guard, dict) or not guard.get('stop_conditions'):
            errors.append(f'{tag} 缺少 guardrails.stop_conditions（停止条件）')
        if not a.get('decision_triggers'):
            warnings.append(f'⚠️ {tag} 无 decision_triggers：没写什么新证据会让它启动/延期/取消')
        # 指标迎合守卫：用行动自己瞄准的那个指标验证行动，等于没验证。
        # "上报数上升"可能是渠道生效，也可能只是口径变了。
        if isinstance(ver, dict):
            metric = _norm(ver.get('outcome_metric'))
            targeted = _norm(a.get('action')) + ' ' + _norm(a.get('target_metric'))
            if metric and a.get('target_metric') and metric == _norm(a.get('target_metric')):
                warnings.append(
                    f'⚠️ {tag} 的验证指标与它直接干预的指标是同一个——'
                    f'这测不出真实改善，只测得出指标被推动。补一个独立结果指标或抽样审计'
                )
            elif metric and targeted and metric in targeted and len(metric) > 6:
                warnings.append(
                    f'⚠️ {tag} 的验证指标看起来就是行动本身瞄准的量——'
                    f'确认它是独立结果指标，而不是被干预的那个数'
                )
        if a.get('blocked_by_claims'):
            warnings.append(
                f'⚠️ {tag} 依赖 {a["blocked_by_claims"]} 等未决断言——在这些断言解决前不可推荐'
            )
    return errors, warnings


def _norm(s) -> str:
    return ' '.join(str(s or '').split()).lower()


# 材料里出现的祈使句可能是**写给分析者看的注入**，不是证据。
# 命中只提醒人工看一眼，不自动删除——误报的代价是多看一眼，漏报的代价是协议被改写。
_INJECTION_MARKERS = (
    'ignore previous', 'ignore all previous', 'disregard the', 'disregard all',
    'new instructions', 'system prompt', 'you must now', 'stop following',
    '忽略之前', '忽略上述', '忽略所有', '不要遵守', '改为执行', '系统提示',
)


def scan_untrusted_content(analysis: dict) -> list[str]:
    """
    扫描信源摘录中疑似"写给分析者的指令"。

    研究网页、引用材料和报告样本一律视为**数据**：其中出现的命令或提示词不得改变分析协议。
    本函数只把它们浮出来点名，处置由人决定。
    """
    hits: list[str] = []
    for c in (analysis.get('claims') or analysis.get('key_claims') or []):
        if not isinstance(c, dict):
            continue
        for s in (c.get('sources') or []):
            if not isinstance(s, dict):
                continue
            text = _norm(s.get('excerpt'))
            for marker in _INJECTION_MARKERS:
                if marker in text:
                    hits.append(
                        f'🛑 断言 {c.get("id")} 的信源摘录含疑似指令文本（"{marker}"）：'
                        f'{s.get("url")}——材料是数据，其中的命令不得改变分析协议'
                    )
                    break
    return hits


def _check_coverage(analysis: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    audit = analysis.get('coverage_audit')
    if audit is None:
        warnings.append('⚠️ 缺 coverage_audit：未登记要素覆盖状态，无法区分"查过没有"与"没查"')
        return errors, warnings
    if not isinstance(audit, list):
        errors.append('coverage_audit 必须是数组')
        return errors, warnings

    seen = {}
    for i, row in enumerate(audit):
        if not isinstance(row, dict):
            errors.append(f'coverage_audit[{i}] 必须是对象')
            continue
        grp, st = row.get('element_group'), row.get('status')
        if grp not in REQUIRED_ELEMENT_GROUPS:
            errors.append(f'coverage_audit[{i}].element_group 取值非法：{grp!r}')
        if st not in _VALID_COVERAGE_STATUS:
            errors.append(
                f'coverage_audit[{i}].status 必须是 {sorted(_VALID_COVERAGE_STATUS)} 之一'
            )
        if not row.get('evidence_or_reason'):
            errors.append(f'coverage_audit[{i}] 缺少 evidence_or_reason（证据或理由）')
        seen[grp] = row

    missing = [g for g in REQUIRED_ELEMENT_GROUPS if g not in seen]
    if missing:
        warnings.append(f'⚠️ 要素组未登记覆盖状态：{missing}')
    blind = [g for g, row in seen.items()
             if row.get('status') == 'unknown' and row.get('affects_current_decision')]
    if blind:
        warnings.append(
            f'⚠️ 以下未知项对当前决策有实质影响，必须在摘要或行动条件中可见：{blind}'
        )
    return errors, warnings


# 可消融的模块（升级方案 §14.4）：分别移除后比较准确性、决策增量与成本，
# 没有稳定增益的模块转为按需选项或删除。**这里只提供开关，不产生任何评估结论。**
ABLATABLE = ('lineage', 'mechanisms', 'actions', 'coverage', 'temporal', 'injection_scan')


def validate_contract(analysis: dict, ablate: frozenset = frozenset()) -> tuple[list[str], list[str]]:
    """
    统一契约校验入口，返回 (errors, warnings)。

    errors 非空 → 拒绝落盘。warnings 非空 → 照常落盘但必须打印。

    `ablate`：消融实验用，关掉指定模块（取值见 `ABLATABLE`）。
    **只在评估时使用**——正式分析路径不传这个参数。
    """
    if not isinstance(analysis, dict):
        return ([f'analysis 必须是对象，实际为 {type(analysis).__name__}'], [])
    analysis = to_runtime(analysis)

    unknown = sorted(set(ablate) - set(ABLATABLE))
    if unknown:
        return ([f'未知的消融模块：{unknown}（可选：{list(ABLATABLE)}）'], [])

    errors = list(validate_analysis(analysis))
    warnings = list(process_warnings(analysis))

    errors += _check_ids(analysis)
    checks = [(None, _check_claims), ('mechanisms', _check_mechanisms),
              ('actions', _check_actions), ('coverage', _check_coverage)]
    for name, check in checks:
        if name in ablate:
            continue
        e, w = check(analysis)
        errors += e
        warnings += w

    if 'injection_scan' not in ablate:
        warnings += scan_untrusted_content(analysis)
    if 'temporal' in ablate:
        return errors, warnings

    # 时效：按断言类型判定，不用统一阈值
    as_of = (analysis.get('analysis_contract') or {}).get('as_of') or \
        (analysis.get('process_metadata') or {}).get('as_of_date')
    stale = staleness_report(analysis.get('claims') or [], as_of=as_of)
    for row in stale['needs_recheck']:
        warnings.append(
            f'⚠️ 断言 {row["id"]}（{row["claim_type"]}）'
            + (f'已 {row["age_days"]} 天，超过该类型 {row["threshold_days"]} 天阈值'
               if row['status'] == 'stale' else '无时间锚点')
            + f'，且支撑 {row["loads"]}——须复查'
        )

    # 双时间：未知时间必须留空，不得用检索日期冒充事件日期
    for c in (analysis.get('claims') or []):
        if not isinstance(c, dict):
            continue
        for s in (c.get('sources') or []):
            if isinstance(s, dict):
                for p in check_time_fields(s):
                    errors.append(f'claims[{c.get("id")}] 的信源 {s.get("url")}：{p}')

    # 依赖一致性：被反证的断言必须把依赖对象标出来
    if analysis.get('claims') and 'lineage' not in ablate:
        lineage = lineage_report(analysis)
        warnings += [f'⚠️ {f}' for f in lineage['flags']]
        for target, claim_ids in lineage['propagation']['needs_review'].items():
            obj = _find_object(analysis, target)
            if isinstance(obj, dict) and not obj.get('needs_review'):
                errors.append(
                    f'"{target}" 依赖已被反证的断言 {claim_ids}，却未标 needs_review——'
                    f'不得继续显示"断言已获支持"'
                )

    return errors, warnings


def _find_object(analysis: dict, oid: str):
    for kind in ('mechanisms', 'actions', 'risk_nodes', 'predictions'):
        items = analysis.get(kind)
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get('id') == oid:
                    return it
    dims = analysis.get('dimensions')
    if isinstance(dims, dict):
        return dims.get(oid)
    return None


# L2/L3 的入口条件。S4（接仿真/因果工具）本身没有实施——
# 但**判断该不该升级**的门在这里，且这道门比工具接入更重要：
# 不满足条件就升级，得到的是不可验证的模拟和伪精度。
_L2_REQUIREMENTS = {
    'variables':        '可观察变量及其单位或代理指标',
    'time_step':        '时间步长',
    'initial_values':   '初值',
    'delays':           '作用延迟',
    'parameter_ranges': '参数区间（含来源：数据或可说明的专家范围）',
    'boundary_conditions': '边界条件',
    'sensitivity_plan': '敏感性检验方案（结论若依赖某个任意参数，直接显示不稳健）',
}

_L3_REQUIREMENTS = {
    'estimand':             '估计目标（对谁、在什么时间范围内、什么干预与什么结果的对比）',
    'identification':       '可辩护的识别策略（比较条件、时间顺序、混杂与选择机制）',
    'data_source':          '数据来源与可得性',
    'refutation_plan':      '反驳/稳健性检验方案',
    'applicable_population': '定量效果的适用群体',
    'applicable_period':    '定量效果的适用时间范围',
}


def causal_readiness(mechanism: dict) -> dict:
    """
    判断一条机制卡够不够格升到 L2 / L3，返回缺什么。

    用法：想给某个机制做参数化模型或效果估计之前先跑这个。
    缺项非空 = 停在 L1 的方向性解释，**不是**"先做了再补"。

    这也是 S4（对接仿真/因果工具）的前置门：工具能跑不代表当前输入满足算法要求。
    """
    if not isinstance(mechanism, dict):
        return {'ready_for': 'L1_explanatory', 'missing': {'mechanism': '不是对象'}}

    def _declared(k) -> bool:
        # 显式声明为空（如 delays={} = "本机制无延迟"）算已声明；
        # 只有**缺字段**或 None / 空字符串才算没交代。
        return k in mechanism and mechanism[k] is not None and mechanism[k] != ''

    missing_l2 = {k: why for k, why in _L2_REQUIREMENTS.items() if not _declared(k)}
    missing_l3 = {k: why for k, why in _L3_REQUIREMENTS.items() if not _declared(k)}

    # L2 与 L3 是**并列的两种能力**，不是阶梯：
    # 效果估计不需要先有一个参数化仿真模型，反之亦然。
    # 此前按阶梯判定，会让一份识别条件完备的 L3 因为没写 time_step 被打回 L1。
    ready_l2, ready_l3 = not missing_l2, not missing_l3
    ready = ('L3_effect_estimate' if ready_l3
             else 'L2_parameterised' if ready_l2
             else 'L1_explanatory')

    declared = mechanism.get('causal_level', 'L1_explanatory')
    overclaimed = ((declared == 'L2_parameterised' and not ready_l2)
                   or (declared == 'L3_effect_estimate' and not ready_l3))

    return {
        'id': mechanism.get('id'),
        'declared_level': declared,
        'ready_for': ready,
        'ready_for_L2': ready_l2,
        'ready_for_L3': ready_l3,
        'overclaimed': overclaimed,
        'missing_for_L2': missing_l2,
        'missing_for_L3': missing_l3,
        'note': ('L2 与 L3 并列，各查各的入口条件；任一缺项即不得升到该级。'
                 '禁止由箭头、序数分数或自定传播系数生成 L3 风格的效果承诺；'
                 '含反馈的机制图不能直接当无环因果图使用'),
    }


def causal_readiness_report(analysis: dict) -> dict:
    """对全部机制卡做能力分层体检。"""
    rows = [causal_readiness(m) for m in (analysis.get('mechanisms') or [])
            if isinstance(m, dict)]
    over = [r['id'] for r in rows if r['overclaimed']]
    return {
        'mechanisms': rows,
        'overclaimed': over,
        'flags': ([f'{len(over)} 条机制声明的因果级别高于它满足的入口条件：{over}'] if over else []),
    }


def completeness_report(analysis: dict) -> dict:
    """报告完整性状态的推导结果与缺口（供 CLI 打印）。"""
    declared = analysis.get('completeness')
    derived = derive_completeness(analysis)
    return {
        'declared': declared,
        'derived': derived,
        'blockers': completeness_blockers(analysis),
        'states': list(COMPLETENESS_STATES),
        'note': '完整性 ≠ 事实真实：complete_with_uncertainty 只表示约定的分析工作完成',
    }
