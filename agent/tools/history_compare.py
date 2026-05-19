"""
Tool: 历史对比 + 预测校准（纯计算）

比较同一系统的两次分析，输出各维度评分变化和趋势警告。
计算历史预测的校准分数（Brier score）。
"""

from agent.store.db import load_latest

DIMENSION_LABELS = {
    'D1': '边界拓扑',
    'D2': '激励架构',
    'D3': '信息神经',
    'D4': '时间代谢',
    'D5': '合法性叙事',
    'D6': '耦合架构',
    'D7': '权力拓扑',
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


def calculate_prediction_accuracy(verification_results: list[dict]) -> dict:
    """
    从预测验证结果计算校准分数。

    参数：
      verification_results: Researcher 返回的 prediction_verification JSON 列表，每条含：
        - verification_result: "confirmed" | "falsified" | "pending"
        - original_prediction: {confidence: float}
        - updated_probability: float (仅 pending)

    返回：
      {
        total: int,
        confirmed_count: int,
        falsified_count: int,
        pending_count: int,
        brier_score: float | None,   (仅 confirmed+falsified ≥ 3 时计算)
        high_confidence_misses: [{prediction, confidence}],  (confidence ≥ 0.7 且 falsified)
        summary: str,
      }
    """
    confirmed = []
    falsified = []
    pending = []

    for r in verification_results:
        result = r.get('verification_result', 'pending')
        if result == 'confirmed':
            confirmed.append(r)
        elif result == 'falsified':
            falsified.append(r)
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

    n_confirmed = len(confirmed)
    n_falsified = len(falsified)
    n_pending = len(pending)
    total = n_confirmed + n_falsified + n_pending

    if total == 0:
        summary = '无历史预测可验证'
    elif len(resolved) == 0:
        summary = f'{n_pending} 条预测尚未到期'
    else:
        accuracy = n_confirmed / len(resolved) * 100
        parts = [f'命中率 {accuracy:.0f}%（{n_confirmed}/{len(resolved)}）']
        if brier_score is not None:
            parts.append(f'Brier 分数 {brier_score:.3f}')
        if high_conf_misses:
            parts.append(f'⚠️ {len(high_conf_misses)} 条高置信预测落空')
        if n_pending > 0:
            parts.append(f'{n_pending} 条待验证')
        summary = '，'.join(parts)

    return {
        'total': total,
        'confirmed_count': n_confirmed,
        'falsified_count': n_falsified,
        'pending_count': n_pending,
        'brier_score': brier_score,
        'high_confidence_misses': high_conf_misses,
        'summary': summary,
    }
