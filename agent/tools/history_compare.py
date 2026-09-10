"""
Tool: 历史对比 + 预测校准 + 历史类比匹配（纯计算）

比较同一系统的两次分析，输出各维度评分变化和趋势警告。
计算历史预测的校准分数（Brier score）。
基于七维评分向量进行历史类比匹配（量级敏感的欧氏度量）。
"""

import json
import math
from datetime import datetime
from pathlib import Path

from agent.store.db import load_latest
from agent.tools.temporal import comparability


def _parse_ymd(s) -> datetime | None:
    """解析 YYYY-MM-DD 或 YYYYMMDD；失败返回 None。"""
    if not s:
        return None
    digits = str(s).replace('-', '').replace('/', '')
    if len(digits) < 8:
        return None
    try:
        return datetime(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None

_CASES_PATH = Path(__file__).resolve().parent.parent.parent / 'references' / 'analogy-cases.json'
_CASES_CACHE: list[dict] | None = None
_CASES_PROVENANCE: dict | None = None

DIMENSION_LABELS = {
    'D1': '边界结构',
    'D2': '激励机制',
    'D3': '信息与反馈',
    'D4': '演化能力',
    'D5': '合法性与叙事',
    'D6': '耦合与依赖',
    'D7': '权力结构',
}


def _is_num(v) -> bool:
    """数值分值判定：显式排除 bool，并把 `unknown` / `not_applicable` 挡在外面。"""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def compare_history(system_name: str, current: dict, previous: dict | None = None) -> dict:
    """
    与上期分析对比，输出维度评分变化。

    参数：
      system_name: 系统名称
      current:     当期分析数据（含 dimension_scores 字段）
      previous:    上期数据（可选，未提供则自动从 db 加载）

    返回：
      {
        has_previous: bool,
        previous_date: str | None,
        score_delta: {dimension: float},
        deteriorating: [str],
        improving: [str],
        trajectory_warnings: [str],
        overall_trend: 'improving' | 'deteriorating' | 'stable',
        overall_score_delta: float | None,
      }
    """
    if previous is None:
        previous = load_latest(system_name)

    if previous is None:
        return {
            'has_previous':        False,
            'previous_date':       None,
            'score_delta':         {},
            'deteriorating':       [],
            'improving':           [],
            'trajectory_warnings': ['⚠️ 首次分析，趋势数据不可用'],
            'overall_trend':       'stable',
            'overall_score_delta': None,
        }

    current_scores  = current.get('dimension_scores', {})
    previous_scores = previous.get('dimension_scores', {})
    basis = comparability(current, previous)

    delta        = {}
    deteriorating = []
    improving     = []
    warnings      = []

    incomparable = []
    for dim, cur_score in current_scores.items():
        prev_score = previous_scores.get(dim)
        if prev_score is None:
            continue
        if dim in basis['incomparable_dims']:
            incomparable.append(dim)
            continue
        # `unknown` / `not_applicable` 不是分数，不做差（S0：缺资料不用中间分填补）
        if not _is_num(cur_score) or not _is_num(prev_score):
            incomparable.append(dim)
            continue
        d = round(cur_score - prev_score, 2)
        delta[dim] = d
        label = DIMENSION_LABELS.get(dim, dim)
        if d <= -0.5:
            deteriorating.append(dim)
        elif d >= 0.5:
            improving.append(dim)
        if d <= -1.0:
            warnings.append(f'⚠️ {label}（{dim}）急剧恶化 {d:+.1f}，需立即关注')

    # 整体评分对比
    if incomparable:
        warnings.append(
            f'以下维度本期或上期不可比（unknown/not_applicable 或口径变更）：{sorted(incomparable)}'
        )
    warnings += basis['warnings']

    cur_overall  = current.get('overall_score')
    prev_overall = previous.get('overall_score')
    overall_delta = None
    if _is_num(cur_overall) and _is_num(prev_overall):
        overall_delta = round(cur_overall - prev_overall, 2)
        if overall_delta <= -0.5:
            warnings.append(f'整体健康评分下滑 {overall_delta:+.1f}（{prev_overall} → {cur_overall}）')

    # 判断整体趋势
    if len(deteriorating) > len(improving):
        overall_trend = 'deteriorating'
    elif len(improving) > len(deteriorating):
        overall_trend = 'improving'
    else:
        overall_trend = 'stable'

    return {
        'has_previous':        True,
        'previous_date':       previous.get('analysis_date'),
        'score_delta':         delta,
        'deteriorating':       deteriorating,
        'improving':           improving,
        'trajectory_warnings': warnings,
        'overall_trend':       overall_trend,
        'overall_score_delta': overall_delta,
    }


VALID_EVENT_TYPES = {'occurrence', 'persistence', 'point_in_time', 'conditional', 'unspecified'}

# 每种事件类型：提前裁定是否合法（早于 time_horizon 时）。
# 依据升级方案 §8.2「预测事件与裁定规则」表。
_EARLY_ADJUDICATION = {
    # event_type:      (可提前判成立, 可提前判不成立)
    'occurrence':      (True,  False),  # 截止日前至少发生一次：发生即成立；不成立通常须等到期
    'persistence':     (False, True),   # 持续到截止日：到期才能确认；窗口内被破即否定
    'point_in_time':   (False, False),  # 截止日的状态/数值：两个方向都须等目标时点
    'conditional':     (False, False),  # 触发条件确认后再按约定窗口裁定
    'unspecified':     (False, False),  # 未声明事件语义 → 最保守：两个方向都不提前裁定
}


def _event_type(r: dict) -> str:
    et = (r.get('event_type')
          or r.get('original_prediction', {}).get('event_type')
          or 'unspecified')
    return et if et in VALID_EVENT_TYPES else 'unspecified'


def calculate_prediction_accuracy(verification_results: list[dict], as_of_date: str | None = None) -> dict:
    """
    从预测验证结果计算校准分数——**按事件类型裁定**（S0：修正"提前确认/提前判假"两类谬误）。

    此前本函数只实现了持续型（persistence）的时序规则：到期前的 confirmed 降级为 on_track，
    而 falsified 在任何时候都被计分。后者对**发生型**（"X 在 2099 年前发生"）是错的——
    截止日之前它不可能被判为不成立，除非预先定义的不可能条件已被证实。
    S0 起，裁定规则由每条预测的 `event_type` 决定（见 `_EARLY_ADJUDICATION`）：

      | event_type      | 提前成立 | 提前不成立 |
      |-----------------|---------|-----------|
      | occurrence      | 可（已被充分证据确认） | 否（除非 `impossibility_established=true`） |
      | persistence     | 否（到期才确认） | 可（窗口内明确破坏） |
      | point_in_time   | 否 | 否 |
      | conditional     | 触发前标 not_activated，不计分 | 同左 |
      | unspecified     | 否 | 否（缺事件语义 → 最保守，且给出 flag） |

    不合法的提前裁定不计入 Brier，降级为未决（on_track）并计入 `reclassified_*`。

    参数：
      verification_results: 每条含 verification_result、original_prediction:{confidence,prediction}、
                            time_horizon（或 original_prediction.time_horizon）、
                            event_type（可选，强烈建议显式声明）、
                            impossibility_established / trigger_occurred（可选）
      as_of_date: 评估基准日（YYYY-MM-DD/YYYYMMDD），默认今天

    返回：{total, confirmed_count, falsified_count, on_track_count, pending_count,
           not_activated_count, resolved_count, unresolved_ratio,
           brier_score|None, baseline_brier|None, brier_vs_baseline|None,
           high_confidence_misses, reclassified_early_confirmed,
           reclassified_early_falsified, by_event_type, flags, summary}
    """
    as_of = _parse_ymd(as_of_date) or datetime.now()

    confirmed, falsified, on_track, pending, not_activated = [], [], [], [], []
    reclassified = 0
    reclassified_falsified = 0
    by_event_type: dict[str, int] = {}
    unspecified_n = 0

    for r in verification_results:
        result = r.get('verification_result', 'pending')
        horizon = r.get('time_horizon') or r.get('original_prediction', {}).get('time_horizon')
        hz = _parse_ymd(horizon)
        et = _event_type(r)
        by_event_type[et] = by_event_type.get(et, 0) + 1
        if et == 'unspecified':
            unspecified_n += 1
        due = hz is not None and as_of >= hz
        can_early_confirm, can_early_falsify = _EARLY_ADJUDICATION[et]

        # 条件预测：触发条件未发生 → 未激活，既不算命中也不算落空
        if et == 'conditional' and not r.get('trigger_occurred'):
            not_activated.append(r)
            continue

        if result == 'confirmed':
            if due or can_early_confirm:
                confirmed.append(r)
            else:
                reclassified += 1
                on_track.append(r)
        elif result == 'falsified':
            # occurrence 型的提前判假只在"预先定义且已证实的不可能条件"下合法
            legit_early = can_early_falsify or (
                et == 'occurrence' and bool(r.get('impossibility_established')))
            if due or legit_early:
                falsified.append(r)
            else:
                reclassified_falsified += 1
                on_track.append(r)
        elif result == 'on_track':
            on_track.append(r)
        else:
            pending.append(r)

    resolved = confirmed + falsified
    brier_score = baseline_brier = brier_vs_baseline = None
    if len(resolved) >= 3:
        outcomes = [1.0 if r.get('verification_result') == 'confirmed' else 0.0 for r in resolved]
        confs = [r.get('original_prediction', {}).get('confidence', 0.5) for r in resolved]
        # 标准二元 Brier：mean((p - y)^2)
        brier_score = round(sum((p - y) ** 2 for p, y in zip(confs, outcomes)) / len(resolved), 4)
        # 基准（climatology）：一律报出该样本的实际基础率，比"低 Brier"本身有信息量得多
        base_rate = sum(outcomes) / len(outcomes)
        baseline_brier = round(sum((base_rate - y) ** 2 for y in outcomes) / len(outcomes), 4)
        brier_vs_baseline = round(brier_score - baseline_brier, 4)

    high_conf_misses = [
        {
            'prediction': r.get('original_prediction', {}).get('prediction', ''),
            'confidence': r.get('original_prediction', {}).get('confidence', 0),
        }
        for r in falsified
        if r.get('original_prediction', {}).get('confidence', 0) >= 0.7
    ]

    n_conf, n_fals, n_track, n_pend = len(confirmed), len(falsified), len(on_track), len(pending)
    n_na = len(not_activated)
    total = n_conf + n_fals + n_track + n_pend + n_na
    unresolved_ratio = round((total - len(resolved)) / total, 3) if total else None

    flags: list[str] = []
    if unspecified_n:
        flags.append(
            f'{unspecified_n} 条预测未声明 event_type——已按最保守规则处理（两个方向都不提前裁定）。'
            f'登记预测时须写明 occurrence / persistence / point_in_time / conditional'
        )
    if reclassified_falsified:
        flags.append(
            f'{reclassified_falsified} 条"提前判不成立"缺乏合法依据（事件类型不允许提前否定，'
            f'且未提供 impossibility_established）——已降级为未决，不计入 Brier'
        )
    if brier_score is not None and len(resolved) < 30:
        flags.append(
            f'已裁定样本仅 {len(resolved)} 条——不足以判断校准好坏；'
            f'方案要求累计 ≥30 条跨系统已裁定事件后才做首次探索性汇总'
        )

    if total == 0:
        summary = '无历史预测可验证'
    elif len(resolved) == 0:
        parts = ['尚无到期可裁定的预测（Brier 不计算）']
        if n_track:
            parts.append(f'{n_track} 条进行中(on_track)')
        if n_pend:
            parts.append(f'{n_pend} 条待验证')
        if n_na:
            parts.append(f'{n_na} 条条件未触发(未激活)')
        if reclassified:
            parts.append(f'⚠️ {reclassified} 条"提前确认"已按未到期降级')
        if reclassified_falsified:
            parts.append(f'⚠️ {reclassified_falsified} 条"提前判假"无合法依据，已降级为未决')
        summary = '，'.join(parts)
    else:
        accuracy = n_conf / len(resolved) * 100
        parts = [f'命中率 {accuracy:.0f}%（{n_conf}/{len(resolved)} 已裁定，共 {total} 条）']
        if brier_score is not None:
            parts.append(f'Brier {brier_score:.3f}（同样本基准 {baseline_brier:.3f}，'
                         f'差值 {brier_vs_baseline:+.3f}）')
        if high_conf_misses:
            parts.append(f'⚠️ {len(high_conf_misses)} 条高置信预测落空')
        if n_track:
            parts.append(f'{n_track} 条进行中')
        if n_pend:
            parts.append(f'{n_pend} 条待验证')
        if n_na:
            parts.append(f'{n_na} 条条件未触发')
        if reclassified:
            parts.append(f'⚠️ {reclassified} 条"提前确认"已降级')
        if reclassified_falsified:
            parts.append(f'⚠️ {reclassified_falsified} 条"提前判假"已降级')
        summary = '，'.join(parts)

    return {
        'total': total,
        'confirmed_count': n_conf,
        'falsified_count': n_fals,
        'on_track_count': n_track,
        'pending_count': n_pend,
        'not_activated_count': n_na,
        'resolved_count': len(resolved),
        'unresolved_ratio': unresolved_ratio,
        'brier_score': brier_score,
        'baseline_brier': baseline_brier,
        'brier_vs_baseline': brier_vs_baseline,
        'high_confidence_misses': high_conf_misses,
        'reclassified_early_confirmed': reclassified,
        'reclassified_early_falsified': reclassified_falsified,
        'by_event_type': by_event_type,
        'flags': flags,
        'summary': summary,
    }


# ── 危险区 / 生存区签名（机械化 references/scoring-calibration.md 的 Cross-Reference 表）──
# 评分一出即自动比对，命中即在报告中点名。
#
# ⚠️ 证据地位（S0 降格）：这些签名是**假说**，不是已验证的高置信规律。
# 它们由一组著名案例事后归纳而来，没有对应的验证样本、基础率或错误率——
# 未做过"多少个 D5≤2+D2≤2 的系统其实没有崩塌"的负例统计。
# 命中只意味着"值得按该机制去查证"，不意味着"灾难前兆已确认"。
SIGNATURE_EVIDENCE_STATUS = (
    'hypothesis: 由著名案例事后归纳，无验证样本与错误率；命中=调查线索，不是已验证的灾难前兆'
)

_DANGER_ZONES = [
    ('legitimacy_incentive_collapse', '合法性-激励双崩塌', {'D5': 2, 'D2': 2},
     'Enron / Theranos / FTX 型签名：叙事失真掩护激励作弊，互为燃料'),
    ('information_boundary_dysfunction', '信息-边界双失灵', {'D3': 2, 'D1': 2},
     '苏联企业 / Wirecard 型签名：边界欺诈在信息失真下长期不被发现'),
    ('temporal_coupling_catastrophe', '透支-紧耦合灾难', {'D4': 2, 'D6': 2},
     'Toys "R" Us / 重 LBO 型签名：未来被抵押 + 无缓冲，一震即溃'),
    ('narrative_feedback_death_spiral', '叙事-反馈死亡螺旋', {'D5': 2, 'D3': 2},
     'WeWork / 独角兽爆雷型签名：故事替代了信号，反馈环失效'),
    ('power_information_doom_loop', '权力-信息恶性循环', {'D7': 2, 'D3': 2},
     'Theranos / 朝鲜 / 晚期 GE 型签名：权力集中过滤信息，决策脱实'),
    ('succession_crisis_cascade', '继承危机级联', {'D7': 2, 'D4': 2},
     '无继承计划家族企业 / 后创始人时代型签名：权力不确定缩短时间视野'),
]

_SURVIVAL_ZONES = [
    ('antifragile_core', '反脆弱内核', {'D4': 4, 'D6': 4},
     '演化能力强 + 耦合得当：能从冲击中受益而非仅存活'),
    ('trust_information_flywheel', '信任-信息飞轮', {'D5': 4, 'D3': 4},
     '叙事可信 + 信号保真：坏消息能上行，承诺能兑现'),
    ('incentive_boundary_alignment', '激励-边界对齐', {'D2': 4, 'D1': 4},
     '奖励与生存需要一致 + 边界清晰：作弊无利可图'),
    ('power_accountability_balance', '权责对称', {'D7': 4, 'D2': 4},
     '权力有制衡 + 激励相容：决策者承担其决策的后果'),
]


def detect_danger_zones(scores: dict) -> dict:
    """
    将七维评分自动比对危险区/生存区签名（高置信灾难前兆 / 抗冲击结构）。

    危险区命中条件：签名内全部维度评分 ≤ 阈值（如 D5≤2 且 D2≤2）。
    生存区命中条件：签名内全部维度评分 ≥ 阈值。
    返回 {danger_zones: [...], survival_zones: [...], evidence_status, summary}。
    缺失维度不视为命中（保守：不对没有评分的维度下判断）；
    非数值评分（`unknown` / `not_applicable`）同样不参与比对。

    ⚠️ 命中是**假说线索**，不是高置信前兆——见 SIGNATURE_EVIDENCE_STATUS。
    """
    scores = {k: v for k, v in (scores or {}).items()
              if isinstance(v, (int, float)) and not isinstance(v, bool)}
    dangers, survivals = [], []
    for key, label, sig, note in _DANGER_ZONES:
        if all(d in scores and scores[d] <= v for d, v in sig.items()):
            dangers.append({
                'key': key, 'label': label, 'note': note, 'status': 'hypothesis',
                'signature': {d: f'≤{v}' for d, v in sig.items()},
                'actual': {d: scores[d] for d in sig},
            })
    for key, label, sig, note in _SURVIVAL_ZONES:
        if all(d in scores and scores[d] >= v for d, v in sig.items()):
            survivals.append({
                'key': key, 'label': label, 'note': note, 'status': 'hypothesis',
                'signature': {d: f'≥{v}' for d, v in sig.items()},
                'actual': {d: scores[d] for d in sig},
            })

    if dangers:
        summary = (f'🛑 命中 {len(dangers)} 个危险区签名（假说级线索，非已验证前兆）：'
                   + '；'.join(d['label'] for d in dangers))
    elif survivals:
        summary = (f'✅ 命中 {len(survivals)} 个生存区签名（假说级线索）：'
                   + '；'.join(s['label'] for s in survivals))
    else:
        summary = '未命中已知危险区/生存区签名'
    return {
        'danger_zones': dangers,
        'survival_zones': survivals,
        'evidence_status': SIGNATURE_EVIDENCE_STATUS,
        'summary': summary,
    }


def _load_cases() -> list[dict]:
    """
    读取类比案例库，统一成内部扁平结构。

    兼容两种格式：
      v1（旧）：`[{name, scores, outcome, key_lesson, ...}]`
      v2（现）：`{schema_version: 2, provenance: {...},
                cases: [{name, as_of_known: {scores, ...}, hindsight: {outcome, key_lesson}}]}`

    v2 把**当时可知信息**与**事后结果**分成两块存放，这样回放评估可以整块隔离 `hindsight`。
    但要诚实：现有 51 条的评分**本来就是结局已知后编定的**，拆分只是让这个事实变得可见、
    让隔离在结构上可执行，**不等于**这些评分已经去污染。库的 provenance 里写明了这一点。
    """
    global _CASES_CACHE, _CASES_PROVENANCE
    if _CASES_CACHE is not None:
        return _CASES_CACHE

    raw = json.loads(_CASES_PATH.read_text(encoding='utf-8'))
    if isinstance(raw, list):                       # v1
        _CASES_PROVENANCE = {'schema_version': 1, 'coding': 'post_hoc'}
        _CASES_CACHE = raw
        return _CASES_CACHE

    _CASES_PROVENANCE = {'schema_version': raw.get('schema_version'),
                         'library_role': raw.get('library_role'),
                         **(raw.get('provenance') or {})}
    _CASES_CACHE = [
        {
            'name': c['name'],
            'system_type': c['system_type'],
            'time_snapshot': c.get('time_snapshot', ''),
            'scores': (c.get('as_of_known') or {}).get('scores', {}),
            'information_cutoff': (c.get('as_of_known') or {}).get('information_cutoff'),
            'coder_blind_to_outcome': (c.get('as_of_known') or {}).get(
                'coder_blind_to_outcome', False),
            'outcome': (c.get('hindsight') or {}).get('outcome', ''),
            'key_lesson': (c.get('hindsight') or {}).get('key_lesson', ''),
        }
        for c in raw.get('cases', [])
    ]
    return _CASES_CACHE


def case_library_provenance() -> dict:
    """案例库的来源与编码方式——引用类比结论时必须一并呈现。"""
    _load_cases()
    return dict(_CASES_PROVENANCE or {})


def _distance_similarity(a: list[float], b: list[float]) -> float:
    """
    基于欧氏距离的相似度（量级敏感），返回 [0,1]，1.0=完全相同。

    用欧氏距离而非余弦：健康评分向量比的是"高低水平+形状"，不是"方向"。
    余弦只看方向——七维全低(危机)与全高(健康)因各维度比例接近会被判高度相似，
    这是真实的度量缺陷（曾使危机系统与瑞士/新加坡相似度同为 1.0）。

    归一化：每维取值 1-5，最大单维差=4，n 维最大距离=sqrt(n*16)，
    使 6 维与 7 维查询都落在可比的 [0,1] 标度。
    """
    n = len(a)
    if n == 0:
        return 0.0
    dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    max_dist = math.sqrt(n * 16)
    return 1.0 - dist / max_dist


# 同类型系统加性 tiebreaker（非乘性）：在线性标度上，乘性 1.2x 会让松散匹配的同类型
# 反超紧密匹配的跨类型。加性微调只在相似度接近时起决胜作用，clamp 到 1.0。
_SAME_TYPE_BONUS = 0.08


# 类比的最低维度覆盖：低于此数不给"结构相似"结论。
# 依据：仅凭 1 个维度就能让 Enron / Theranos / FTX 同时 similarity=1.0——
# 低覆盖会伪装成结构匹配，这是升级方案 B.1 点名的边界缺陷。
MIN_DIMS_FOR_FULL_MATCH = 6
MIN_DIMS_FOR_ANY_MATCH = 3


def find_analogies(current_scores: dict, system_type: str | None = None, top_k: int = 3,
                   blind: bool = False) -> list[dict]:
    """
    按七维评分向量匹配历史案例。

    `blind=True`：**隔离结果字段**——不返回 `outcome` / `key_lesson`。
    用于回放评估：让类比只能生成"该去查什么"，而不能让已知结局倒灌进当期判断。
    这是 S3 对照评估的必需开关，也可在正式分析中用来先做一轮无污染的结构比对。

    覆盖约束（S0）：
      - 无可用维度 → 返回 `[]`（不推荐类比，输入不足）
      - 覆盖 < MIN_DIMS_FOR_ANY_MATCH → 返回 `[]`，不给相似度
      - 覆盖 < MIN_DIMS_FOR_FULL_MATCH → 结果标 `match_type='partial'`，
        调用方必须按"部分匹配、覆盖不足"呈现，不得写成结构相似结论

    每条结果附 `coverage` / `covered_dims` / `match_type` / `outcome_is_hindsight`。
    `outcome_is_hindsight=True` 提醒：案例的评分是在结局已知的情况下事后编定的，
    类比只能生成待验证线索，不能直接产生发生概率（方案 §4.1「启发式与历史类比」）。
    """
    cases = _load_cases()
    # 只用数值维度：'unknown' / 'not_applicable' 不参与距离计算，也不按中性 3 填补
    current_scores = {k: v for k, v in (current_scores or {}).items()
                      if isinstance(v, (int, float)) and not isinstance(v, bool)}
    dim_keys = sorted(current_scores.keys())
    coverage = len(dim_keys)
    if coverage < MIN_DIMS_FOR_ANY_MATCH:
        return []
    match_type = 'full' if coverage >= MIN_DIMS_FOR_FULL_MATCH else 'partial'
    # dim_keys 来自已过滤的 current_scores，故此处 get 必然命中；
    # case 侧的缺省 3 是防御非规范案例（当前案例库均为 7 维）。
    current_vec = [current_scores[k] for k in dim_keys]

    scored = []
    for case in cases:
        case_vec = [case['scores'].get(k, 3) for k in dim_keys]
        sim = _distance_similarity(current_vec, case_vec)
        if system_type and case.get('system_type') == system_type:
            sim = min(sim + _SAME_TYPE_BONUS, 1.0)
        sim = max(0.0, min(sim, 1.0))
        scored.append({
            'similarity': round(sim, 4),
            'name': case['name'],
            'system_type': case['system_type'],
            'time_snapshot': case.get('time_snapshot', ''),
            'scores': case['scores'],
            'outcome': case['outcome'],
            'key_lesson': case['key_lesson'],
            'coverage': f'{coverage}/7',
            'covered_dims': dim_keys,
            'match_type': match_type,
            'outcome_is_hindsight': True,
            'coder_blind_to_outcome': case.get('coder_blind_to_outcome', False),
            'information_cutoff': case.get('information_cutoff'),
        })

    scored.sort(key=lambda x: x['similarity'], reverse=True)
    top = scored[:top_k]
    if blind:
        # 结局字段被剔除而不是置空——留个空的 outcome 键仍会诱使下游去读它
        top = [{k: v for k, v in item.items() if k not in ('outcome', 'key_lesson')}
               | {'blinded': True,
                  'note': '回放模式：已隔离结局字段，类比只用于生成待查线索'}
               for item in top]
    return top
