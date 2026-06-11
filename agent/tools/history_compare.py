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

DIMENSION_LABELS = {
    'D1': '边界结构',
    'D2': '激励机制',
    'D3': '信息与反馈',
    'D4': '演化能力',
    'D5': '合法性与叙事',
    'D6': '耦合与依赖',
    'D7': '权力结构',
}


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

    delta        = {}
    deteriorating = []
    improving     = []
    warnings      = []

    for dim, cur_score in current_scores.items():
        prev_score = previous_scores.get(dim)
        if prev_score is None:
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
    cur_overall  = current.get('overall_score')
    prev_overall = previous.get('overall_score')
    overall_delta = None
    if cur_overall is not None and prev_overall is not None:
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


def calculate_prediction_accuracy(verification_results: list[dict], as_of_date: str | None = None) -> dict:
    """
    从预测验证结果计算校准分数——**时序感知**（修正"提前确认"谬误）。

    核心规则：一条"X 持续到 time_horizon"的预测，在 horizon 到期**之前不可能被证实**
    （在 D 之前随时还能破），只可能被**证伪**（条件已破）。因此：
      - verification_result='confirmed' 但 as_of_date < time_horizon → 降级为 on_track（未决，不计入 Brier）
      - verification_result='confirmed' 且 as_of_date >= time_horizon → 真正 resolved
      - verification_result='falsified' → 任何时候都算 resolved（提前证伪合法）
      - 'on_track' / 'pending' → 未决
    Brier 仅在真正 resolved（confirmed-到期 + falsified）≥ 3 时计算，避免用未到期预测刷出假校准。

    注：本规则假设预测为**持续型**（"X 持续到 D"→ 到期才能 confirm、可提前 falsify）。
    若为**发生型**（"X 在 D 前发生"→ 可提前 confirm、到期才能 falsify），逻辑需反转；
    当前会把发生型的提前成真保守降级为 on_track（少计 confirm，不会危险地多计）。

    参数：
      verification_results: 每条含 verification_result、original_prediction:{confidence,prediction}、
                            time_horizon（或 original_prediction.time_horizon）
      as_of_date: 评估基准日（YYYY-MM-DD/YYYYMMDD），默认今天

    返回：{total, confirmed_count, falsified_count, on_track_count, pending_count,
           brier_score|None, high_confidence_misses, reclassified_early_confirmed, summary}
    """
    as_of = _parse_ymd(as_of_date) or datetime.now()

    confirmed, falsified, on_track, pending = [], [], [], []
    reclassified = 0

    for r in verification_results:
        result = r.get('verification_result', 'pending')
        horizon = r.get('time_horizon') or r.get('original_prediction', {}).get('time_horizon')
        hz = _parse_ymd(horizon)
        if result == 'falsified':
            falsified.append(r)
        elif result == 'confirmed':
            if hz is not None and as_of >= hz:
                confirmed.append(r)
            else:
                # 时序谬误防护：窗口未到，"证实"无效，按 on_track 计（不进 Brier）
                reclassified += 1
                on_track.append(r)
        elif result == 'on_track':
            on_track.append(r)
        else:
            pending.append(r)

    resolved = confirmed + falsified
    brier_score = None
    if len(resolved) >= 3:
        brier_sum = 0.0
        for r in resolved:
            conf = r.get('original_prediction', {}).get('confidence', 0.5)
            outcome = 1.0 if r.get('verification_result') == 'confirmed' else 0.0
            brier_sum += (conf - outcome) ** 2
        brier_score = round(brier_sum / len(resolved), 4)

    high_conf_misses = [
        {
            'prediction': r.get('original_prediction', {}).get('prediction', ''),
            'confidence': r.get('original_prediction', {}).get('confidence', 0),
        }
        for r in falsified
        if r.get('original_prediction', {}).get('confidence', 0) >= 0.7
    ]

    n_conf, n_fals, n_track, n_pend = len(confirmed), len(falsified), len(on_track), len(pending)
    total = n_conf + n_fals + n_track + n_pend

    if total == 0:
        summary = '无历史预测可验证'
    elif len(resolved) == 0:
        parts = ['尚无到期可裁定的预测（Brier 不计算）']
        if n_track:
            parts.append(f'{n_track} 条进行中(on_track)')
        if n_pend:
            parts.append(f'{n_pend} 条待验证')
        if reclassified:
            parts.append(f'⚠️ {reclassified} 条"提前确认"已按未到期降级')
        summary = '，'.join(parts)
    else:
        accuracy = n_conf / len(resolved) * 100
        parts = [f'命中率 {accuracy:.0f}%（{n_conf}/{len(resolved)} 已到期）']
        if brier_score is not None:
            parts.append(f'Brier 分数 {brier_score:.3f}')
        if high_conf_misses:
            parts.append(f'⚠️ {len(high_conf_misses)} 条高置信预测落空')
        if n_track:
            parts.append(f'{n_track} 条进行中')
        if n_pend:
            parts.append(f'{n_pend} 条待验证')
        if reclassified:
            parts.append(f'⚠️ {reclassified} 条"提前确认"已降级')
        summary = '，'.join(parts)

    return {
        'total': total,
        'confirmed_count': n_conf,
        'falsified_count': n_fals,
        'on_track_count': n_track,
        'pending_count': n_pend,
        'brier_score': brier_score,
        'high_confidence_misses': high_conf_misses,
        'reclassified_early_confirmed': reclassified,
        'summary': summary,
    }


# ── 危险区 / 生存区签名（机械化 references/scoring-calibration.md 的 Cross-Reference 表）──
# 这张表是项目最有预测力的资产之一，此前只存在于文档里靠 Orchestrator 记得去查。
# 评分一出即自动比对，命中即在报告中点名。

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
    返回 {danger_zones: [...], survival_zones: [...], summary}。
    缺失维度不视为命中（保守：不对没有评分的维度下判断）。
    """
    dangers, survivals = [], []
    for key, label, sig, note in _DANGER_ZONES:
        if all(d in scores and scores[d] <= v for d, v in sig.items()):
            dangers.append({
                'key': key, 'label': label, 'note': note,
                'signature': {d: f'≤{v}' for d, v in sig.items()},
                'actual': {d: scores[d] for d in sig},
            })
    for key, label, sig, note in _SURVIVAL_ZONES:
        if all(d in scores and scores[d] >= v for d, v in sig.items()):
            survivals.append({
                'key': key, 'label': label, 'note': note,
                'signature': {d: f'≥{v}' for d, v in sig.items()},
                'actual': {d: scores[d] for d in sig},
            })

    if dangers:
        summary = f'🛑 命中 {len(dangers)} 个高置信危险区签名：' + '；'.join(d['label'] for d in dangers)
    elif survivals:
        summary = f'✅ 命中 {len(survivals)} 个生存区签名：' + '；'.join(s['label'] for s in survivals)
    else:
        summary = '未命中已知危险区/生存区签名'
    return {'danger_zones': dangers, 'survival_zones': survivals, 'summary': summary}


def _load_cases() -> list[dict]:
    global _CASES_CACHE
    if _CASES_CACHE is None:
        _CASES_CACHE = json.loads(_CASES_PATH.read_text(encoding='utf-8'))
    return _CASES_CACHE


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


def find_analogies(current_scores: dict, system_type: str | None = None, top_k: int = 3) -> list[dict]:
    cases = _load_cases()
    dim_keys = sorted(current_scores.keys())
    # 缺省值取中性 3（非 0）：避免缺维在欧氏距离下变成 |score-0| 的幽灵距离，
    # 把某 case 错误推向"最远"。当前案例库 43 条均为规范 7 维，此为防御未来 6 维查询。
    current_vec = [current_scores.get(k, 3) for k in dim_keys]

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
        })

    scored.sort(key=lambda x: x['similarity'], reverse=True)
    return scored[:top_k]
