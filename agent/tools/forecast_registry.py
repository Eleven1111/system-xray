"""
Tool: 预测登记册（纯计算）

S2 的预测冻结与裁定。解决两个具体的自我欺骗：

1. **覆盖初始概率**。分析者在事件临近时把 0.4 改成 0.8，复盘时看到的是那个 0.8——
   校准分数因此变好，但那不是预测能力，是后见之明。本模块让更新**产生新版本**，
   初始值永不被覆盖。
2. **事后挑最准的版本**。复盘时对每条预测挑选对自己最有利的那一版。
   本模块要求**预先声明**复盘策略（首次预测，或固定提前量快照），并按该策略统一取版本。

登记时冻结的东西：事件定义、`event_type`、概率、生成时间、目标窗口、时区、
裁定来源优先级、缺数据处理、关联机制。这些一旦写入某个版本就不再改动——
要改就是新版本，且新版本必须说明它 `supersedes_version` 哪一版。
"""

from datetime import datetime, timedelta

from agent.tools.history_compare import VALID_EVENT_TYPES, _EARLY_ADJUDICATION

# 登记时必须冻结的字段。缺任何一个都无法在到期时做无争议的裁定。
FROZEN_FIELDS = (
    'prediction', 'falsification_condition', 'time_horizon', 'event_type',
    'confidence', 'dimension_link', 'source_step',
)

# 版本更新只能改变判断强度及其依据。允许任意字段会让调用者通过新增/替换
# 裁定语义绕过冻结规则，即使四个旧字段保持不变也会破坏可比性。
MUTABLE_UPDATE_FIELDS = {'confidence', 'update_reason', 'evidence_update'}

# 复盘取版本的策略。必须**预先**选定，不得在看到结果后再挑。
REVIEW_POLICIES = ('first', 'lead_time')


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


def freeze_predictions(predictions: list[dict], frozen_at: str,
                       registry: list[dict] | None = None) -> dict:
    """
    把一批预测登记进登记册，返回 {registry, errors, frozen}。

    每条预测需要一个稳定 `id`（如 `P1`）。若该 id 已在登记册中，**不覆盖**——
    这是 `update_prediction` 的活儿，走版本追加。
    """
    registry = list(registry or [])
    existing_ids = {p.get('id') for p in registry}
    errors, frozen = [], []

    for i, p in enumerate(predictions or []):
        if not isinstance(p, dict):
            errors.append(f'predictions[{i}] 必须是对象')
            continue
        pid = p.get('id')
        if not pid:
            errors.append(f'predictions[{i}] 缺少 id——没有稳定 id 就无法跨期追踪同一条预测')
            continue
        if pid in existing_ids:
            errors.append(
                f'预测 "{pid}" 已在登记册中，不得覆盖——修改概率请走 update_prediction()，'
                f'它会追加新版本并保留初始值'
            )
            continue
        missing = [f for f in FROZEN_FIELDS if p.get(f) in (None, '')]
        if missing:
            errors.append(f'预测 "{pid}" 缺少必须冻结的字段：{missing}')
            continue
        if not isinstance(p['confidence'], (int, float)) or isinstance(p['confidence'], bool) \
                or not 0 <= p['confidence'] <= 1:
            errors.append(f'预测 "{pid}".confidence 必须是 [0, 1] 内的数字')
            continue
        if p['event_type'] not in VALID_EVENT_TYPES or p['event_type'] == 'unspecified':
            errors.append(
                f'预测 "{pid}".event_type 必须是 '
                f'{sorted(VALID_EVENT_TYPES - {"unspecified"})} 之一——裁定规则由它决定'
            )
            continue

        entry = dict(p)
        entry.update({'version': 1, 'frozen_at': frozen_at, 'supersedes_version': None})
        registry.append(entry)
        existing_ids.add(pid)
        frozen.append(pid)

    return {'registry': registry, 'errors': errors, 'frozen': frozen}


def update_prediction(registry: list[dict], prediction_id: str, updates: dict,
                      updated_at: str, reason: str = '') -> dict:
    """
    更新一条已登记预测 → **追加新版本**，初始版本原样保留。

    只允许改概率与随之而来的说明；事件定义与裁定窗口一旦冻结就不能改——
    改了它就是另一条预测，应当新登记一个 id。
    """
    versions = [p for p in registry if p.get('id') == prediction_id]
    if not versions:
        return {'registry': registry, 'errors': [f'登记册中没有预测 "{prediction_id}"']}

    latest = max(versions, key=lambda p: p.get('version', 1))
    illegal = sorted(k for k in updates if k not in MUTABLE_UPDATE_FIELDS)
    if illegal:
        return {'registry': registry, 'errors': [
            f'字段 {illegal} 不在允许更新列表 {sorted(MUTABLE_UPDATE_FIELDS)} 中——'
            f'事件定义、裁定窗口及关联语义在登记时已冻结；改变它们请用新 id 重新登记'
        ]}
    if 'confidence' in updates and (not isinstance(updates['confidence'], (int, float))
                                    or isinstance(updates['confidence'], bool)
                                    or not 0 <= updates['confidence'] <= 1):
        return {'registry': registry, 'errors': ['confidence 必须是 [0, 1] 内的数字']}

    new_version = dict(latest)
    new_version.update(updates)
    new_version.update({
        'version': latest.get('version', 1) + 1,
        'supersedes_version': latest.get('version', 1),
        'frozen_at': updated_at,
        'update_reason': reason,
    })
    return {'registry': list(registry) + [new_version], 'errors': []}


def select_versions(registry: list[dict], policy: str = 'first',
                    lead_time_days: int = 30) -> dict:
    """
    按**预先声明**的策略为每条预测选出用于复盘的那一版。

    - `first`：始终用初始版本（version 1）。最保守，杜绝一切事后调整。
    - `lead_time`：用距 `time_horizon` 至少 `lead_time_days` 天之前冻结的**最后**一版。
      允许"随证据更新判断"，但把临到期的调整挡在外面。

    返回 {selected: [...], policy, errors}。策略必须在看到结果之前定下来。
    """
    if policy not in REVIEW_POLICIES:
        return {'selected': [], 'policy': policy,
                'errors': [f'复盘策略必须是 {list(REVIEW_POLICIES)} 之一']}

    grouped: dict[str, list[dict]] = {}
    for p in registry or []:
        if isinstance(p, dict) and p.get('id'):
            grouped.setdefault(p['id'], []).append(p)

    selected, errors = [], []
    for pid, versions in sorted(grouped.items()):
        versions = sorted(versions, key=lambda p: p.get('version', 1))
        if policy == 'first':
            selected.append(versions[0])
            continue
        horizon = _parse(versions[0].get('time_horizon'))
        if horizon is None:
            errors.append(f'预测 "{pid}" 无可解析的 time_horizon，lead_time 策略不适用')
            continue
        cutoff = horizon - timedelta(days=lead_time_days)
        eligible = [v for v in versions if (_parse(v.get('frozen_at')) or horizon) <= cutoff]
        if not eligible:
            errors.append(
                f'预测 "{pid}" 没有任何版本冻结于截止日前 {lead_time_days} 天以上——'
                f'按该策略它不计入复盘（不是失败，是不合格样本）'
            )
            continue
        selected.append(eligible[-1])

    return {'selected': selected, 'policy': policy,
            'lead_time_days': lead_time_days if policy == 'lead_time' else None,
            'errors': errors}


def due_predictions(registry: list[dict], as_of: str) -> dict:
    """
    在 `as_of` 这天，哪些预测可以裁定、哪些只能等。

    依据每条预测的 `event_type`（规则表见 `history_compare._EARLY_ADJUDICATION`）：
    到期的两个方向都可裁；未到期的只能做该类型允许的提前裁定。
    """
    ref = _parse(as_of) or datetime.now()
    due, early_only, waiting = [], [], []

    for p in registry or []:
        if not isinstance(p, dict):
            continue
        et = p.get('event_type', 'unspecified')
        if et not in VALID_EVENT_TYPES:
            et = 'unspecified'
        horizon = _parse(p.get('time_horizon'))
        row = {'id': p.get('id'), 'event_type': et, 'time_horizon': p.get('time_horizon'),
               'version': p.get('version', 1)}
        if horizon is not None and ref >= horizon:
            due.append({**row, 'adjudicable': 'both_directions'})
            continue
        can_confirm, can_falsify = _EARLY_ADJUDICATION[et]
        allowed = [d for d, ok in (('confirmed', can_confirm), ('falsified', can_falsify)) if ok]
        if et == 'occurrence':
            allowed.append('falsified（仅当预先定义的不可能条件已被证实）')
        if allowed:
            early_only.append({**row, 'adjudicable': allowed})
        else:
            waiting.append({**row, 'adjudicable': 'none_until_horizon'})

    return {'as_of': as_of, 'due': due, 'early_only': early_only, 'waiting': waiting}
