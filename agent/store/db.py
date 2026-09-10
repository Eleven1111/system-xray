"""
分析结果持久化存储

存储路径：~/.system_pathology/data/{safe_system_name}/{YYYYMMDD}.json
Obsidian 导出（MD 素材 + HTML 报告）：
  /Users/na/Library/Mobile Documents/iCloud~md~obsidian/Documents/System Pathology/
"""

import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from textwrap import dedent

DATA_DIR = Path.home() / '.system_pathology' / 'data'

_VALID_DIMS = {'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7'}
_VALID_SOURCE_STEPS = {'dimension_analysis', 'cross_dimensional'}
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_URL_RE = re.compile(r'^https?://\S+$', re.IGNORECASE)

# 非数值评分（S0）：缺资料写 unknown，不适用写 not_applicable。
# 二者都不得用中间分 3 填补——那是把"不知道"伪装成"中等健康"。
_NON_NUMERIC_SCORES = {'unknown', 'not_applicable'}

# 事件语义（S0）：预测的裁定规则由类型决定，见 history_compare._EARLY_ADJUDICATION
_VALID_EVENT_TYPES = {'occurrence', 'persistence', 'point_in_time', 'conditional'}

# 报告完整性状态（S0/§9.4）：与"知识不确定性"分开记录。
# 不存在"流程完成＝事实真实"的状态——complete_with_uncertainty 只表示约定分析工作完成。
COMPLETENESS_STATES = ('draft', 'partial', 'complete_with_uncertainty')

_VALID_VERIFICATION_STATUS = {'confirmed', 'dead', 'mismatch', 'unverifiable', 'unchecked'}


def _is_valid_url(u) -> bool:
    return bool(isinstance(u, str) and _URL_RE.match(u.strip()))


def claims_ledger(analysis: dict) -> list:
    """
    取断言账本：S1 的 `claims[]` 优先，回落到旧字段 `key_claims`。

    两者是同一账本的新旧形态——旧记录用 `key_claims`，新契约用带 id 与来源血缘的 `claims`。
    读取时统一，避免升级后老记录被误判为"没建账本"。
    """
    for field in ('claims', 'key_claims'):
        items = analysis.get(field)
        if isinstance(items, list) and items:
            return items
    return []


def numeric_scores(scores: dict | None) -> dict:
    """只取可参与计算的数值评分；unknown / not_applicable 一律排除。"""
    return {k: v for k, v in (scores or {}).items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def _validate_predictions(preds, field_name: str) -> list[str]:
    """校验预测数组的字段完整性与取值合法性，返回错误列表。"""
    errors: list[str] = []
    if not isinstance(preds, list):
        return [f'{field_name} 必须是数组，实际为 {type(preds).__name__}']

    required = ['prediction', 'falsification_condition', 'time_horizon',
                'confidence', 'dimension_link', 'source_step']
    for i, p in enumerate(preds):
        tag = f'{field_name}[{i}]'
        if not isinstance(p, dict):
            errors.append(f'{tag} 必须是对象')
            continue
        for key in required:
            if key not in p or p[key] in (None, ''):
                errors.append(f'{tag} 缺少必填字段 `{key}`')

        th = p.get('time_horizon')
        if th is not None and not _DATE_RE.match(str(th)):
            errors.append(f'{tag}.time_horizon 必须为绝对日期 YYYY-MM-DD，实际为 "{th}"')
        elif th is not None:
            try:
                datetime.strptime(str(th), '%Y-%m-%d')
            except ValueError:
                errors.append(f'{tag}.time_horizon 不是合法日期："{th}"')

        conf = p.get('confidence')
        if conf is not None:
            if not isinstance(conf, (int, float)) or isinstance(conf, bool):
                errors.append(f'{tag}.confidence 必须是数字，实际为 {conf!r}')
            elif not (0.0 <= conf <= 1.0):
                errors.append(f'{tag}.confidence 必须在 [0,1] 区间，实际为 {conf}')

        dl = p.get('dimension_link')
        if dl is not None and dl not in _VALID_DIMS:
            errors.append(f'{tag}.dimension_link 必须是 D1-D7，实际为 "{dl}"')

        # S0：事件语义决定裁定规则——缺了它，"提前判对/提前判错"的合法条件无从区分
        et = p.get('event_type')
        if et is None:
            errors.append(
                f'{tag} 缺少 `event_type`（{sorted(_VALID_EVENT_TYPES)}）——'
                f'不声明事件类型就无法定义合法的裁定窗口'
            )
        elif et not in _VALID_EVENT_TYPES:
            errors.append(
                f'{tag}.event_type 必须是 {sorted(_VALID_EVENT_TYPES)} 之一，实际为 {et!r}'
            )

        ss = p.get('source_step')
        if ss is not None and ss not in _VALID_SOURCE_STEPS:
            errors.append(
                f'{tag}.source_step 必须是 {sorted(_VALID_SOURCE_STEPS)} 之一，实际为 "{ss}"'
            )
    return errors


def validate_analysis(analysis: dict) -> list[str]:
    """
    在持久化前校验分析结果的结构合法性（针对存储 shape，非 diagnostic-schema.json）。

    返回错误字符串列表；空列表 = 通过。错误信息可直接回报给 Orchestrator 修正。

    校验项：
      - dimension_scores: 必须存在；键 ⊆ D1-D7；七维齐全；每个分值为 1-5 数字
      - overall_score（如有）: 1-5 数字
      - predictions / candidate_predictions（如有）: 字段完整、time_horizon 绝对日期、
        confidence ∈ [0,1]、dimension_link 属 D1-D7、source_step 合法枚举
      - dimension_evidence（如有，P3）: 每个有评分的维度须挂 ≥1 条带 url 的信源
        （present→严格校验；absent→不拦截，由 process_warnings 提醒）
    """
    errors: list[str] = []
    if not isinstance(analysis, dict):
        return [f'analysis 必须是对象，实际为 {type(analysis).__name__}']

    scores = analysis.get('dimension_scores')
    if scores is None:
        errors.append('缺少必填字段 `dimension_scores`')
    elif not isinstance(scores, dict):
        errors.append(f'dimension_scores 必须是对象，实际为 {type(scores).__name__}')
    elif not scores:
        # 空 dict = 无法生成雷达图/类比/历史对比，是 C1 要拦截的"静默坏数据"典型
        errors.append('dimension_scores 不能为空（至少需要诊断出的各维度评分）')
    else:
        # 注：不强制七维齐全——D7 为后增维度，历史上 6 维（D1-D6）分析合法（见雷达图 helper 对任意维度数的支持）。
        # 只拦截"非法维度键"和"分值越界"这类无歧义的错误。
        unknown = set(scores) - _VALID_DIMS
        if unknown:
            errors.append(
                f'dimension_scores 含非法维度键：{sorted(unknown)}'
                f'（仅允许 D1-D7 短键；描述性键如 D1_boundary_topology 会让 radar/analogy 工具失效）'
            )
        for dim, val in scores.items():
            if dim not in _VALID_DIMS:
                continue
            if isinstance(val, str):
                # S0：无法识别时不评分——只接受这两个显式标记，不接受自由文本
                if val not in _NON_NUMERIC_SCORES:
                    errors.append(
                        f'dimension_scores.{dim} 只能是 1-5 数字，或 '
                        f'{sorted(_NON_NUMERIC_SCORES)} 之一，实际为 {val!r}'
                    )
            elif not isinstance(val, (int, float)) or isinstance(val, bool):
                errors.append(f'dimension_scores.{dim} 必须是数字，实际为 {val!r}')
            elif not (1 <= val <= 5):
                errors.append(f'dimension_scores.{dim} 必须在 1-5 区间，实际为 {val}')

    overall = analysis.get('overall_score')
    if overall is not None:
        if not isinstance(overall, (int, float)) or isinstance(overall, bool):
            errors.append(f'overall_score 必须是数字，实际为 {overall!r}')
        elif not (1 <= overall <= 5):
            errors.append(f'overall_score 必须在 1-5 区间，实际为 {overall}')

    if 'predictions' in analysis:
        errors.extend(_validate_predictions(analysis['predictions'], 'predictions'))
    if 'candidate_predictions' in analysis:
        errors.extend(_validate_predictions(analysis['candidate_predictions'], 'candidate_predictions'))

    # P3：dimension_evidence 当存在时严格校验——每个**有数值评分**的维度须挂 ≥1 条带合法 url 的信源。
    # unknown / not_applicable 的维度不要求证据（本来就没有可支撑的判断）。
    dim_ev = analysis.get('dimension_evidence')
    if dim_ev is not None:
        if not isinstance(dim_ev, dict):
            errors.append(f'dimension_evidence 必须是对象，实际为 {type(dim_ev).__name__}')
        elif isinstance(scores, dict) and scores:
            for dim, val in scores.items():
                if dim not in _VALID_DIMS or val in _NON_NUMERIC_SCORES:
                    continue
                items = dim_ev.get(dim)
                if not items or not isinstance(items, list):
                    errors.append(f'dimension_evidence.{dim} 缺失或非数组（该维度有评分却无证据）')
                    continue
                if not any(isinstance(it, dict) and it.get('url') for it in items):
                    errors.append(f'dimension_evidence.{dim} 无任何带 url 的信源（评分须可追溯）')
                    continue
                # S0：URL 只做真值检查不足以约束有效证据——`"url": "x"` 曾能通过全部校验
                if not any(isinstance(it, dict) and _is_valid_url(it.get('url')) for it in items):
                    bad = [it.get('url') for it in items if isinstance(it, dict)]
                    errors.append(
                        f'dimension_evidence.{dim} 的 url 不是可核验的 http(s) 地址：{bad}'
                        f'（评分须可追溯到能打开的具体条目）'
                    )

    # S0：信源核验记录须是可核验的记录，不能是占位对象（`[{}]` 曾能冒充"已核验"）
    sv = analysis.get('source_verification')
    if sv is not None:
        if not isinstance(sv, list):
            errors.append(f'source_verification 必须是数组，实际为 {type(sv).__name__}')
        else:
            for i, v in enumerate(sv):
                if not isinstance(v, dict):
                    errors.append(f'source_verification[{i}] 必须是对象')
                    continue
                if not _is_valid_url(v.get('url')):
                    errors.append(
                        f'source_verification[{i}].url 缺失或非 http(s) 地址：{v.get("url")!r}'
                    )
                st = str(v.get('status', '')).lower()
                if st not in _VALID_VERIFICATION_STATUS:
                    errors.append(
                        f'source_verification[{i}].status 必须是 '
                        f'{sorted(_VALID_VERIFICATION_STATUS)} 之一，实际为 {v.get("status")!r}'
                    )

    # S0：报告完整性状态由统一契约约束——不得自称完整却缺流程实据
    completeness = analysis.get('completeness')
    if completeness is not None:
        if completeness not in COMPLETENESS_STATES:
            errors.append(
                f'completeness 必须是 {list(COMPLETENESS_STATES)} 之一，实际为 {completeness!r}'
            )
        elif completeness == 'complete_with_uncertainty':
            derived = derive_completeness(analysis)
            if derived != 'complete_with_uncertainty':
                errors.append(
                    f'completeness 声明为 complete_with_uncertainty，但按流程实据只能达到 '
                    f'`{derived}`：{"；".join(completeness_blockers(analysis))}。'
                    f'草稿可以保存——把 completeness 改成 `{derived}` 即可落盘'
                )

    return errors


def completeness_blockers(analysis: dict) -> list[str]:
    """列出阻止本次分析达到 `complete_with_uncertainty` 的具体缺口（空列表 = 无阻塞）。"""
    blockers: list[str] = []
    scores = analysis.get('dimension_scores') or {}
    pm = analysis.get('process_metadata')
    mode = analysis.get('output_mode', 'full')

    if not numeric_scores(scores) and not any(v in _NON_NUMERIC_SCORES for v in scores.values()):
        blockers.append('无任何维度结论')
    if not isinstance(pm, dict):
        blockers.append('缺 process_metadata（无法核查流程门控是否执行）')
        return blockers
    if mode == 'full' and pm.get('ach_run') is not True:
        blockers.append('full 模式未运行 ACH（竞争假说检验）')
    if pm.get('round2_triggered') and not pm.get('round2_run'):
        blockers.append('Round 2 已触发但未运行')
    if not pm.get('source_verification_done'):
        blockers.append('信源核验门控未执行')
    else:
        sv = analysis.get('source_verification')
        if not isinstance(sv, list) or not any(
                isinstance(v, dict) and _is_valid_url(v.get('url')) for v in sv):
            blockers.append('声称已做信源核验但无可核验的 source_verification 记录')
    if analysis.get('dimension_evidence') is None:
        blockers.append('缺 dimension_evidence（各维度评分未挂可追溯信源）')
    if not claims_ledger(analysis) and mode == 'full':
        blockers.append('缺 key_claims 账本（载荷性断言未登记，无法做独立复核）')
    return blockers


def derive_completeness(analysis: dict) -> str:
    """
    按流程实据推导报告完整性状态（`draft` / `partial` / `complete_with_uncertainty`）。

    与"知识不确定性"分开：本函数只回答"约定的分析工作做完了没有"，
    不回答"结论是否为真"。缺口多寡决定 draft 还是 partial。
    """
    blockers = completeness_blockers(analysis)
    if not blockers:
        return 'complete_with_uncertainty'
    if not numeric_scores(analysis.get('dimension_scores') or {}) or len(blockers) >= 4:
        return 'draft'
    return 'partial'


def process_warnings(analysis: dict) -> list[str]:
    """
    P2：流程门控核查（非阻塞）。返回告警字符串列表，空列表 = 无告警。

    与 validate_analysis（硬拒绝结构错误）分离：这些是"流程被静默跳过"的提醒，
    不阻止落盘，但在落盘时打印出来，把跳过变成被点名的显式决定。

    依据 analysis 顶层的 `process_metadata` 块：
      {round2_triggered, round2_run, ach_run, source_verification_done,
       unresolved_high_contradictions, confidence_label,
       latest_source_date, as_of_date, breaking_event_sweep_done}  # P6b 新鲜度字段
    """
    warnings: list[str] = []
    if not isinstance(analysis, dict):
        return warnings

    # 先查 dimension_evidence 缺失——必须在 process_metadata 早返回之前，
    # 否则两块都缺时（最该被点名的情况）警告会被早返回吞掉。
    scores = analysis.get('dimension_scores')
    if 'dimension_evidence' not in analysis and isinstance(scores, dict) and scores:
        warnings.append('⚠️ 缺 dimension_evidence：各维度评分未挂可追溯信源（P3，建议补记以保证可审计）')

    # 关键断言账本（啃综述类错误）——同样置于 pm 早返回之前
    kc = claims_ledger(analysis)
    if (not kc) and isinstance(scores, dict) and scores and analysis.get('output_mode', 'full') == 'full':
        warnings.append('⚠️ 缺 key_claims 账本：未登记载荷性事实断言，无法分诊"综述类错误"（Zolghadr 类）做独立复核')
    elif isinstance(kc, list):
        for c in kc:
            if not isinstance(c, dict) or not c.get('loads'):
                continue
            ic = c.get('independent_check')
            # 新契约的 claims[].status 与旧字段的 independent_check.status 都算数
            status = str(c.get('status') or
                         (ic.get('status', '') if isinstance(ic, dict) else '')).lower()
            thin = _distinct_source_count(c.get('sources')) < 2 or _best_tier(c.get('sources')) == 3
            short = (c.get('claim') or c.get('statement') or '')[:24]
            if status == 'contradicted':
                warnings.append(
                    f'🛑 独立复核推翻了载荷性断言「{short}…」——依赖它的 {c.get("loads")} 须修订或撤下'
                )
            elif thin and status not in ('confirmed',):
                warnings.append(
                    f'⚠️ 载荷性断言「{short}…」佐证单薄（{_distinct_source_count(c.get("sources"))}源/最高T{_best_tier(c.get("sources"))}）且未独立复核——'
                    f'支撑 {c.get("loads")}，建议派 fact_check 独立求证'
                )

    pm = analysis.get('process_metadata')
    if pm is None:
        warnings.append('⚠️ 缺 process_metadata：无法核查 Round2/ACH/信源核验是否被跳过（建议补记）')
        return warnings
    if not isinstance(pm, dict):
        warnings.append(f'⚠️ process_metadata 必须是对象，实际为 {type(pm).__name__}')
        return warnings

    mode = analysis.get('output_mode', 'full')
    if mode == 'full' and pm.get('ach_run') is False:
        warnings.append('⚠️ full 模式但 ACH（竞争假说检验）未运行——可能锚定首个叙事，存在确认偏差')
    if pm.get('round2_triggered') and not pm.get('round2_run'):
        warnings.append('⚠️ Round2 深度研究已触发但未运行——HIGH 矛盾/缺 T1 定量声明可能未求证')
    if not pm.get('source_verification_done'):   # False 或字段缺失都算未跑（堵 omission 漏洞）
        warnings.append('⚠️ 信源核验门控（WebFetch 抽查）未执行——存在虚假/不可达信源风险')
    else:
        # 声称已核验，必须有记录支撑，否则是空头承诺
        sv = analysis.get('source_verification')
        if not sv or not isinstance(sv, list):
            warnings.append('⚠️ 声称已做信源核验，但缺 source_verification 记录——无法证明真核验过')
        else:
            bad = [v for v in sv if isinstance(v, dict) and str(v.get('status', '')).lower() in ('dead', 'mismatch')]
            if bad:
                warnings.append(
                    f'⚠️ 信源核验发现 {len(bad)} 条失效/不符（dead/mismatch）——依赖这些信源的结论须复核或撤下'
                )

    unresolved = pm.get('unresolved_high_contradictions')
    n_unresolved = unresolved if isinstance(unresolved, int) else (len(unresolved) if isinstance(unresolved, list) else 0)
    if n_unresolved > 0 and str(pm.get('confidence_label', '')).lower() == 'high':
        warnings.append(
            f'⚠️ 存在 {n_unresolved} 条未解决的 HIGH 矛盾，但置信度标为 high——置信度应封顶至 partial'
        )

    # P6b 新鲜度：最新信源距分析基准日的滞后 + 突发事件扫描
    latest = _parse_date(pm.get('latest_source_date'))
    as_of = _parse_date(pm.get('as_of_date')) or _parse_date(analysis.get('analysis_date'))
    if latest and as_of:
        gap = (as_of - latest).days
        if gap >= 2:
            warnings.append(
                f'⚠️ 信息滞后：最新信源({pm.get("latest_source_date")})距分析基准({pm.get("as_of_date") or analysis.get("analysis_date")}) {gap} 天——'
                f'快变系统应追"过去 48 小时/今天"再定稿，当前可能漏掉最新事件'
            )
    if pm.get('breaking_event_sweep_done') is False:
        warnings.append('⚠️ 未做突发事件扫描（定稿前未查"今天/过去 24-48 小时"重大事件）——可能漏掉改写诊断的最新进展')

    # S0：完整性状态显式化。未声明时按流程实据推导并点名，避免不完整研究以完整形态保存。
    declared = analysis.get('completeness')
    derived = derive_completeness(analysis)
    if declared is None and derived != 'complete_with_uncertainty':
        warnings.append(
            f'⚠️ 未声明 completeness：按流程实据本次只能算 `{derived}`——'
            f'{"；".join(completeness_blockers(analysis))}'
        )

    return warnings


def _parse_date(s):
    """解析 YYYY-MM-DD / YYYYMMDD 为 datetime；失败返回 None。"""
    if not s:
        return None
    digits = str(s).replace('-', '').replace('/', '')
    if len(digits) < 8:
        return None
    try:
        return datetime(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


# 报告输出目录。S0：取消个人 Obsidian 路径作为唯一出口——
# 环境变量 SYSTEM_XRAY_OUTPUT_DIR 优先，未设置时才回落到默认 Obsidian 仓库。
_DEFAULT_OUTPUT_DIR = Path(
    '/Users/na/Library/Mobile Documents/iCloud~md~obsidian/Documents/System Pathology')
OBSIDIAN_DIR = Path(os.environ['SYSTEM_XRAY_OUTPUT_DIR']) \
    if os.environ.get('SYSTEM_XRAY_OUTPUT_DIR') else _DEFAULT_OUTPUT_DIR


def _system_dir(system_name: str) -> Path:
    safe = system_name.replace('/', '_').replace(' ', '_').replace(':', '_').replace('\\', '_')
    return DATA_DIR / safe


_INDEX_NAME = 'index.json'
# 版本文件名：{YYYYMMDD}-{NNN}.json。旧的 {YYYYMMDD}.json 仍可读，
# 且按字符串排序时恰好排在同日各版本之前，视作该日的第 000 版。
_VERSION_RE = re.compile(r'^(\d{8})-(\d{3})\.json$')
_LEGACY_RE = re.compile(r'^(\d{8})\.json$')


def _version_files(system_dir: Path) -> list[Path]:
    """按 (日期, 序号) 升序返回该系统的全部分析文件，含 legacy 单日文件。"""
    if not system_dir.exists():
        return []
    out: list[tuple[str, int, Path]] = []
    for f in system_dir.glob('*.json'):
        if f.name == _INDEX_NAME:
            continue
        m = _VERSION_RE.match(f.name)
        if m:
            out.append((m.group(1), int(m.group(2)), f))
            continue
        m = _LEGACY_RE.match(f.name)
        if m:
            out.append((m.group(1), 0, f))
    out.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in out]


def _next_analysis_id(system_dir: Path, date_str: str) -> str:
    """同日已有 N 个版本 → 返回第 N+1 个 id。绝不复用已存在的 id。"""
    used = {0} if (system_dir / f'{date_str}.json').exists() else set()
    for f in system_dir.glob(f'{date_str}-*.json'):
        m = _VERSION_RE.match(f.name)
        if m:
            used.add(int(m.group(2)))
    seq = 1
    while seq in used:
        seq += 1
    return f'{date_str}-{seq:03d}'


def _reserve_analysis_file(system_dir: Path, date_str: str) -> tuple[str, Path, int]:
    """用 O_EXCL 预留版本文件，避免并发调用取得同一个 sequence 后互相覆盖。"""
    for _ in range(10000):
        analysis_id = _next_analysis_id(system_dir, date_str)
        filepath = system_dir / f'{analysis_id}.json'
        try:
            fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            return analysis_id, filepath, fd
        except FileExistsError:
            continue
    raise RuntimeError(f'无法为 {date_str} 分配唯一分析版本号')


def _rebuild_index(system_dir: Path) -> dict:
    """
    重建 index.json。

    索引是**派生物**：删掉它可以从版本文件完整重建，因此它不是真相来源，
    也不覆盖任何历史——`latest` 只是一个指针。
    """
    entries = []
    for f in _version_files(system_dir):
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        entries.append({
            'analysis_id':   data.get('analysis_id') or f.stem,
            'analysis_date': data.get('analysis_date'),
            'saved_at':      data.get('saved_at'),
            'completeness':  data.get('completeness'),
            'overall_score': data.get('overall_score'),
            'output_mode':   data.get('output_mode', 'full'),
            'supersedes':    data.get('supersedes'),
            'file':          f.name,
        })
    index = {
        'versions': entries,
        'latest': entries[-1]['analysis_id'] if entries else None,
        'note': 'latest 只是指针；版本文件不可变，历史不被覆盖。本索引可从版本文件重建。',
    }
    (system_dir / _INDEX_NAME).write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    return index


def save_analysis(
    system_name: str, system_type: str, analysis: dict,
    date_str: str | None = None, validate: bool = True,
) -> str:
    """
    保存分析结果为**不可变版本**，返回文件路径。

    S2 变更：此前按 `{YYYYMMDD}.json` 命名，同一天做两次分析后一次会**静默覆盖**前一次——
    跨期对比因此可能拿旧版跟自己比，纠错记录也无处可查。现在每次保存产生一个新版本
    `{YYYYMMDD}-{NNN}.json`，带唯一 `analysis_id`，并记录它 `supersedes` 哪一版。
    `index.json` 只是可重建的指针索引，不承载历史。

    analysis 应包含字段：
      dimension_scores: {D1: float, D2: float, ...}
      overall_score: float
      risk_nodes: [str]
      source_coverage: {perspective: bool}
      output_mode: 'full' | 'brief'
      predictions: [{prediction, falsification_condition, time_horizon, ...}]  （可选）

    validate=True（默认）时，落盘前调用 validate_analysis() 校验结构；不合法则
    抛 ValueError 并附完整错误清单，避免污染数据持久化。测试可传 validate=False 绕过。
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    if validate:
        errors = validate_analysis(analysis)
        # 新契约对象存在时，不能绕过对象层、血缘与行动约束直接落盘。
        # 延迟导入避免 validation -> db 的模块循环；旧记录保持原有兼容路径。
        if any(k in analysis for k in ('claims', 'mechanisms', 'actions',
                                       'analysis_contract', 'coverage_audit')):
            from agent.validation import validate_contract
            contract_errors, _ = validate_contract(analysis)
            errors = contract_errors
        if errors:
            raise ValueError(
                'analysis 结构校验失败，已拒绝持久化：\n  - ' + '\n  - '.join(errors)
            )

    system_dir = _system_dir(system_name)
    system_dir.mkdir(parents=True, exist_ok=True)

    previous = _version_files(system_dir)
    supersedes, previous_record = None, {}
    if previous:
        try:
            prev = json.loads(previous[-1].read_text())
            previous_record = prev
            supersedes = prev.get('analysis_id') or previous[-1].stem
        except json.JSONDecodeError:
            supersedes = previous[-1].stem

    # S2 主路径：新预测在第一次保存时冻结，后续概率调整只能通过追加版本。
    # 没有稳定 id 的旧 predictions 保持兼容读取，但不能被当作登记册的新增条目。
    prediction_registry = list(previous_record.get('prediction_registry') or [])
    incoming_predictions = analysis.get('predictions') or []
    registry_errors = []
    if incoming_predictions and all(isinstance(p, dict) and p.get('id') for p in incoming_predictions):
        from agent.tools.forecast_registry import freeze_predictions
        frozen = freeze_predictions(incoming_predictions, frozen_at=date_str,
                                    registry=prediction_registry)
        prediction_registry, registry_errors = frozen['registry'], frozen['errors']
    if analysis.get('prediction_updates'):
        from agent.tools.forecast_registry import update_prediction
        for update in analysis.get('prediction_updates') or []:
            if not isinstance(update, dict):
                registry_errors.append('prediction_updates 条目必须是对象')
                continue
            changed = update_prediction(prediction_registry, update.get('id'),
                                        update.get('updates') or {}, date_str,
                                        update.get('reason', ''))
            prediction_registry, errors = changed['registry'], changed['errors']
            registry_errors += errors
    if registry_errors:
        raise ValueError('预测登记失败，已拒绝持久化：\n  - ' + '\n  - '.join(registry_errors))

    analysis_id, filepath, fd = _reserve_analysis_file(system_dir, date_str)

    # S0：系统元数据由调用方参数决定，**不允许被 analysis 输入覆盖**。
    # 此前 `**analysis` 展开在后，一份 analysis 里写个 analysis_date 就能改写生成元数据。
    record = {
        **analysis,
        'system_name':   system_name,
        'system_type':   system_type,
        'analysis_date': date_str,
        'analysis_id':   analysis_id,
        'supersedes':    supersedes,
        'saved_at':      datetime.now().isoformat(),
        'completeness':  analysis.get('completeness') or derive_completeness(analysis),
    }
    if prediction_registry:
        record['prediction_registry'] = prediction_registry
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        filepath.unlink(missing_ok=True)
        raise
    _rebuild_index(system_dir)
    return str(filepath)


def load_version(system_name: str, analysis_id: str) -> dict | None:
    """按 analysis_id 重建当时的输入、判断与预测（版本不可变，故可精确重建）。"""
    system_dir = _system_dir(system_name)
    for f in _version_files(system_dir):
        if f.stem == analysis_id:
            return json.loads(f.read_text())
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if data.get('analysis_id') == analysis_id:
            return data
    return None


def list_versions(system_name: str) -> list[dict]:
    """列出全部不可变版本（升序）。索引缺失时从版本文件重建。"""
    system_dir = _system_dir(system_name)
    if not system_dir.exists():
        return []
    index_path = system_dir / _INDEX_NAME
    if not index_path.exists():
        return _rebuild_index(system_dir)['versions']
    try:
        return json.loads(index_path.read_text()).get('versions', [])
    except json.JSONDecodeError:
        return _rebuild_index(system_dir)['versions']


def load_latest(system_name: str) -> dict | None:
    """
    加载最近一次分析结果（最新版本）。

    注意排序用的是 (日期, 版本序号) 而不是文件名字符串——`index.json` 与
    未来可能出现的其他文件不得混进来当成分析记录。
    """
    files = _version_files(_system_dir(system_name))
    if not files:
        return None
    return json.loads(files[-1].read_text())


def load_analysis(system_name: str, date_str: str) -> dict | None:
    """
    加载指定日期的分析结果；同日有多个版本时返回**该日最后一个**版本。

    要精确定位某一版，用 `load_version(system_name, analysis_id)`。
    """
    system_dir = _system_dir(system_name)
    same_day = [f for f in _version_files(system_dir) if f.name.startswith(date_str)]
    if not same_day:
        return None
    return json.loads(same_day[-1].read_text())


def load_predictions(system_name: str) -> list[dict]:
    """
    加载最近一次分析中的预测列表。

    返回预测数组（可能为空）。向后兼容：旧 JSON 文件没有 predictions 字段时返回 []。
    """
    latest = load_latest(system_name)
    if latest is None:
        return []
    registry = latest.get('prediction_registry')
    if registry:
        from agent.tools.forecast_registry import select_versions
        return select_versions(registry, policy='first')['selected']
    return latest.get('predictions', [])


def save_to_obsidian(
    system_name: str, system_type: str, report_markdown: str,
    date_str: str | None = None, output_dir: Path | None = None,
) -> str:
    """
    将诊断报告 Markdown 保存到 Obsidian 仓库。

    返回保存路径。report_markdown 应为完整的 Markdown 文本（含正文，不含 frontmatter）。
    output_dir: 可选，覆盖默认 OBSIDIAN_DIR（用于测试隔离）。
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    target_dir = output_dir or OBSIDIAN_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    safe = system_name.replace('/', '-').replace('\\', '-').replace(':', '-')
    filename = f'{date_str} {safe} 系统诊断.md'
    filepath = target_dir / filename

    frontmatter = f"""---
title: "{system_name} 系统诊断报告"
date: {date_str}
type: system-xray
system: "{system_name}"
system_type: "{system_type}"
tags:
  - system-xray
  - {system_type}
---

"""
    filepath.write_text(frontmatter + report_markdown, encoding='utf-8')
    return str(filepath)


def save_research_materials(
    system_name: str,
    system_type: str,
    research_brief: dict,
    date_str: str | None = None,
    output_dir: Path | None = None,
) -> str:
    """
    保存 Research Brief 原始素材为 MD 格式到 Obsidian。

    research_brief 应包含：
      sources: [{query, title, url, excerpt, tier, date}]
      contradictions: [{description, source_a, source_b, significance}]
      no_source_perspectives: [str]
      stale_perspectives: [str]
      confidence: str
      confidence_rationale: str
    output_dir: 可选，覆盖默认 OBSIDIAN_DIR（用于测试隔离）。
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    target_dir = output_dir or OBSIDIAN_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    safe = system_name.replace('/', '-').replace('\\', '-').replace(':', '-')
    filename = f'{date_str} {safe} 研究素材.md'
    filepath = target_dir / filename

    lines = [
        '---',
        f'title: "{system_name} 研究素材"',
        f'date: {date_str}',
        'type: research-materials',
        f'system: "{system_name}"',
        f'system_type: "{system_type}"',
        'tags:',
        '  - system-xray',
        '  - research-materials',
        f'  - {system_type}',
        '---',
        '',
        f'# {system_name} — 研究素材',
        f'**采集日期：** {date_str}',
        '',
    ]

    sources = research_brief.get('sources', [])
    if sources:
        lines += ['## 信源清单', '']
        for s in sources:
            tier_tag = f'T{s.get("tier", "?")}'
            date_tag = s.get('date', '日期未知')
            lines.append(f'### [{tier_tag}] {s.get("title", "无标题")}')
            lines.append(f'- **查询：** `{s.get("query", "")}`')
            if s.get('url'):
                lines.append(f'- **URL：** {s["url"]}')
            lines.append(f'- **日期：** {date_tag}')
            if s.get('excerpt'):
                lines.append(f'- **摘录：** {s["excerpt"]}')
            lines.append('')

    contradictions = research_brief.get('contradictions', [])
    if contradictions:
        lines += ['## 矛盾信号', '']
        for c in contradictions:
            sig = c.get('significance', 'medium').upper()
            lines.append(f'### [{sig}] {c.get("description", "")}')
            lines.append(f'- 来源 A: {c.get("source_a", "")}')
            lines.append(f'- 来源 B: {c.get("source_b", "")}')
            lines.append('')

    no_src = research_brief.get('no_source_perspectives', [])
    if no_src:
        lines += ['## 未覆盖视角', '']
        for p in no_src:
            lines.append(f'- {p}')
        lines.append('')

    stale = research_brief.get('stale_perspectives', [])
    if stale:
        lines += ['## 过期视角', '']
        for p in stale:
            lines.append(f'- {p}')
        lines.append('')

    conf = research_brief.get('confidence', 'unknown')
    rationale = research_brief.get('confidence_rationale', '')
    lines += [
        '## 置信度评估',
        f'**等级：** {conf}',
        f'**理由：** {rationale}',
    ]

    filepath.write_text('\n'.join(lines), encoding='utf-8')
    return str(filepath)


# ── Brookings/CSIS 智库风格 HTML 模板 ──

_HTML_TEMPLATE = dedent("""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Source+Serif+4:ital,wght@0,400;0,600;0,700;1,400&display=swap');

  :root {{
    --blue-900: #0a2540;
    --blue-700: #1a3a5c;
    --blue-500: #2563eb;
    --blue-100: #dbeafe;
    --blue-50:  #eff6ff;
    --red-600:  #dc2626;
    --amber-500:#f59e0b;
    --green-600:#16a34a;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-300: #d1d5db;
    --gray-600: #4b5563;
    --gray-800: #1f2937;
    --font-serif: 'Source Serif 4', 'Noto Serif SC', 'Georgia', serif;
    --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: var(--font-serif);
    color: var(--gray-800);
    background: #fff;
    line-height: 1.7;
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 32px 80px;
  }}

  /* ── 顶部标识条 ── */
  .header-bar {{
    border-top: 4px solid var(--blue-900);
    padding-top: 24px;
    margin-bottom: 40px;
  }}
  .header-bar .institute {{
    font-family: var(--font-sans);
    font-size: 12px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--gray-600);
    margin-bottom: 8px;
  }}
  .header-bar h1 {{
    font-size: 28px;
    font-weight: 700;
    color: var(--blue-900);
    line-height: 1.3;
    margin-bottom: 8px;
  }}
  .header-bar .meta {{
    font-family: var(--font-sans);
    font-size: 13px;
    color: var(--gray-600);
  }}

  /* ── 执行摘要卡片 ── */
  .exec-summary {{
    background: var(--blue-50);
    border-left: 4px solid var(--blue-500);
    padding: 24px 28px;
    margin: 32px 0;
    border-radius: 0 8px 8px 0;
  }}
  .exec-summary h2 {{
    font-size: 16px;
    font-weight: 700;
    color: var(--blue-700);
    margin-bottom: 12px;
    font-family: var(--font-sans);
    text-transform: uppercase;
    letter-spacing: 1px;
  }}

  /* ── 章节 ── */
  h2 {{
    font-size: 20px;
    color: var(--blue-900);
    border-bottom: 2px solid var(--blue-900);
    padding-bottom: 6px;
    margin: 40px 0 16px;
  }}
  h3 {{
    font-size: 17px;
    color: var(--blue-700);
    margin: 24px 0 10px;
  }}
  h4 {{
    font-size: 15px;
    color: var(--gray-600);
    margin: 16px 0 8px;
    font-family: var(--font-sans);
  }}

  p {{ margin: 10px 0; }}
  ul, ol {{ margin: 8px 0 8px 24px; }}
  li {{ margin: 4px 0; }}

  /* ── 表格（zebra stripes） ── */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 14px;
  }}
  thead {{
    background: var(--blue-900);
    color: #fff;
  }}
  th {{
    padding: 10px 14px;
    text-align: left;
    font-family: var(--font-sans);
    font-weight: 600;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  td {{
    padding: 10px 14px;
    border-bottom: 1px solid var(--gray-200);
  }}
  tbody tr:nth-child(even) {{
    background: var(--gray-100);
  }}

  /* ── 风险 callout ── */
  .callout {{
    border-radius: 6px;
    padding: 16px 20px;
    margin: 16px 0;
    font-size: 14px;
  }}
  .callout-red {{
    background: #fef2f2;
    border-left: 4px solid var(--red-600);
  }}
  .callout-amber {{
    background: #fffbeb;
    border-left: 4px solid var(--amber-500);
  }}
  .callout-green {{
    background: #f0fdf4;
    border-left: 4px solid var(--green-600);
  }}
  .callout-title {{
    font-weight: 700;
    font-family: var(--font-sans);
    margin-bottom: 6px;
  }}

  /* ── 雷达图容器 ── */
  .radar-container {{
    text-align: center;
    margin: 24px 0;
  }}
  .radar-container svg {{
    width: 100%;
    max-width: 520px;
    height: auto;
  }}

  /* ── 折叠信源审计 ── */
  details {{
    margin: 16px 0;
    border: 1px solid var(--gray-200);
    border-radius: 6px;
  }}
  summary {{
    padding: 12px 16px;
    background: var(--gray-100);
    cursor: pointer;
    font-family: var(--font-sans);
    font-weight: 600;
    font-size: 14px;
    border-radius: 6px;
  }}
  details[open] summary {{
    border-bottom: 1px solid var(--gray-200);
    border-radius: 6px 6px 0 0;
  }}
  details .content {{
    padding: 16px;
    font-size: 14px;
  }}

  /* ── 评分徽章 ── */
  .score-badge {{
    display: inline-block;
    font-family: var(--font-sans);
    font-weight: 700;
    font-size: 13px;
    padding: 2px 10px;
    border-radius: 12px;
    color: #fff;
  }}
  .score-1 {{ background: var(--red-600); }}
  .score-2 {{ background: #ea580c; }}
  .score-3 {{ background: var(--amber-500); color: var(--gray-800); }}
  .score-4 {{ background: var(--blue-500); }}
  .score-5 {{ background: var(--green-600); }}

  /* ── 预测卡片 ── */
  .prediction-review,
  .predictions {{
    margin: 32px 0;
  }}
  .prediction-card {{
    border: 1px solid var(--gray-200);
    border-left: 4px solid var(--blue-500);
    border-radius: 6px;
    padding: 16px 20px;
    margin: 12px 0;
    background: var(--gray-50);
  }}
  .prediction-title {{
    font-family: var(--font-sans);
    font-weight: 600;
    font-size: 15px;
    margin-bottom: 8px;
    color: var(--gray-800);
  }}
  .prediction-meta {{
    font-family: var(--font-sans);
    font-size: 13px;
    color: var(--gray-600);
    line-height: 1.6;
  }}
  .prediction-link {{
    font-family: var(--font-sans);
    font-size: 12px;
    color: var(--blue-500);
    margin-top: 6px;
  }}

  /* ── 页脚 ── */
  .footer {{
    margin-top: 60px;
    padding-top: 20px;
    border-top: 1px solid var(--gray-300);
    font-family: var(--font-sans);
    font-size: 12px;
    color: var(--gray-600);
    text-align: center;
  }}

  @media print {{
    body {{ padding: 20px; font-size: 11pt; }}
    .header-bar {{ border-top-width: 2px; }}
    details {{ page-break-inside: avoid; }}
    table {{ font-size: 10pt; }}
  }}
</style>
</head>
<body>

<div class="header-bar">
  <div class="institute">SYSTEM PATHOLOGY DIAGNOSTIC REPORT</div>
  <h1>{title}</h1>
  <div class="meta">{date} &nbsp;|&nbsp; System Type: {system_type} &nbsp;|&nbsp; Generated by System Pathology Framework</div>
</div>

{body}

<div class="footer">
  <p>System Pathology Framework &mdash; Cross-disciplinary diagnostic analysis</p>
  <p>This report is auto-generated. Source verification audit attached. Confidence levels noted per section.</p>
</div>

</body>
</html>
""")


def _esc(s) -> str:
    """最小 HTML 转义。"""
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _tier_num(t) -> int:
    if isinstance(t, int):
        return t if t in (1, 2, 3) else 9
    m = re.search(r'[123]', str(t))
    return int(m.group()) if m else 9


_HAS_NUMBER = re.compile(r'\d')


def _distinct_source_count(sources) -> int:
    if not isinstance(sources, list):
        return 0
    return len({(s.get('url') or '').strip() for s in sources
                if isinstance(s, dict) and (s.get('url') or '').strip()})


def _best_tier(sources) -> int:
    """返回支撑信源里最高的层级（数字最小=最高）；无则 9。"""
    tiers = [_tier_num(s.get('tier')) for s in sources if isinstance(s, dict)] if isinstance(sources, list) else []
    return min(tiers) if tiers else 9


def triage_claims_for_factcheck(key_claims: list[dict], max_n: int = 5) -> list[dict]:
    """
    啃硬骨头（综述类错误）：从关键断言账本里挑出**最该独立复核**的断言。

    这是**触发器/分诊**，不是"catch"本身——真正抓错的是独立 fact_check sub-agent 的
    重新求证（见 researcher-modes.md `fact_check`）。本函数只决定哪些断言值得那次昂贵的复核。

    "载荷性"按**后果**定义：断言的 `loads` 非空（支撑了某维度评分/风险节点/预测）。
    "薄佐证"：去重信源 < 2，或最高层级仅 T3。
    分诊集 = 载荷性 ∩ 薄佐证 ∩ 尚未独立复核，按 loads 多少（影响面）降序，截断 max_n。

    ⚠️ 局限：账本由同一个可能犯错的流程自报——信源计数是**下限不是真相**
    （2 个源可能都不支撑该断言、或同源转载）。分诊浮出的是"佐证单薄"的断言，
    与"错误"断言**重叠但不等同**。
    """
    triaged = []
    for c in key_claims or []:
        if not isinstance(c, dict):
            continue
        loads = c.get('loads')
        if not loads:                       # 不载荷任何诊断元素 → 噪音，跳过
            continue
        ic = c.get('independent_check')
        if isinstance(ic, dict) and str(ic.get('status', '')).lower() in ('confirmed', 'contradicted'):
            continue                        # 已独立复核过
        srcs = c.get('sources')
        thin = _distinct_source_count(srcs) < 2 or _best_tier(srcs) == 3
        if not thin:
            continue
        reason = []
        if _distinct_source_count(srcs) < 2:
            reason.append('单一信源')
        if _best_tier(srcs) == 3:
            reason.append('仅 T3 支撑')
        triaged.append({
            'claim': c.get('claim', ''),
            'loads': loads,
            'n_sources': _distinct_source_count(srcs),
            'best_tier': _best_tier(srcs),
            'reason': '；'.join(reason),
            'stakes': len(loads) if isinstance(loads, list) else 1,
        })
    triaged.sort(key=lambda x: x['stakes'], reverse=True)
    return triaged[:max(0, max_n)]


def select_verification_sample(sources: list[dict], n: int = 3) -> list[dict]:
    """
    内容可信度（本轮）：从信源池中挑出**最该 WebFetch 抽查**的 n 条，供 Orchestrator 核验。

    优先级：信源层级越高越优先（T1>T2>T3）；**承载定量声明（标题/摘录含数字）的信源额外加权**——
    这些"权威感十足的具体数字"正是 sub-agent 最容易编错、最该追一手核验的（如"39 处决""85% 票"）。
    去重(按 url)，仅取带 url 的。返回 [{title, url, tier, reason}]。
    """
    seen: set = set()
    scored: list[tuple] = []
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        url = (s.get('url') or '').strip()
        if not url or url in seen:
            continue
        seen.add(url)
        tier = _tier_num(s.get('tier'))
        tier_score = {1: 3, 2: 2, 3: 1}.get(tier, 0)
        has_num = bool(_HAS_NUMBER.search((s.get('title') or '') + ' ' + (s.get('excerpt') or '')))
        score = tier_score + (2 if has_num else 0)
        reason = []
        if tier <= 2:
            reason.append(f'T{tier} 高权重信源' if tier in (1, 2) else '')
        if has_num:
            reason.append('含定量声明，需追一手核验')
        scored.append((score, {'title': s.get('title', ''), 'url': url,
                               'tier': tier, 'reason': '；'.join(r for r in reason if r) or '一般抽查'}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:max(0, n)]]


def build_source_audit_html(sources: list[dict], verifications: list[dict] | None = None) -> str:
    """
    P1：从 Researcher 返回的合并 sources[] 机械生成逐条 URL 的信源审计 HTML 片段。

    取代手写"信源类别"——审计直接由真实返回信源派生，每条含 标题/URL/日期，按 T 级分组。
    sources 每项形如 {query,title,url,excerpt,tier,date}。tier 可为 1/2/3 或 "T1"/"T2"/"T3"。

    verifications（可选）：[{url, status}]，status ∈ confirmed|dead|mismatch|unverifiable。
    提供时为对应信源加核验徽章（✓核实/✗失效/⚠不符/？未达），把"是否真核验过"写进可读报告。
    返回可直接嵌入报告正文的 <details>…</details> 字符串。
    """
    vmap = {}
    for v in verifications or []:
        if isinstance(v, dict) and v.get('url'):
            vmap[v['url'].strip()] = str(v.get('status', '')).lower()
    badge = {'confirmed': '✓核实', 'dead': '✗失效', 'mismatch': '⚠不符', 'unverifiable': '？未达'}

    buckets: dict[int, list[dict]] = {1: [], 2: [], 3: [], 9: []}
    seen: set = set()
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        url = (s.get('url') or '').strip()
        key = url or (s.get('title') or '').strip()
        if not key or key in seen:
            continue
        seen.add(key)
        buckets[_tier_num(s.get('tier'))].append(s)

    total = sum(len(v) for v in buckets.values())
    n_verified = sum(1 for s in sum(buckets.values(), []) if (s.get('url') or '').strip() in vmap)
    summary_extra = f'，已抽查核验 {n_verified} 条' if vmap else ''
    lines = [f'<details>', f'<summary>信源审计（{total} 条{summary_extra}，点击展开）</summary>', '<div class="content">']
    tier_titles = {1: 'T1 · 官方/一手', 2: 'T2 · 机构媒体/分析', 3: 'T3 · 社区/间接', 9: '未分级'}
    for tier in (1, 2, 3, 9):
        items = buckets[tier]
        if not items:
            continue
        lines.append(f'<h4>{tier_titles[tier]}（{len(items)}）</h4>')
        lines.append('<ul>')
        for s in items:
            title = _esc(s.get('title') or '无标题')
            date = _esc(s.get('date') or '日期未知')
            url = (s.get('url') or '').strip()
            mark = ''
            if url in vmap:
                mark = f' <strong>[{badge.get(vmap[url], vmap[url])}]</strong>'
            if url:
                lines.append(f'<li><a href="{_esc(url)}">{title}</a> — {date}{mark}</li>')
            else:
                lines.append(f'<li>{title} — {date}（无 URL）</li>')
        lines.append('</ul>')
    lines.append('</div></details>')
    return '\n'.join(lines)


_DIMENSION_LABELS = {
    'D1': '边界结构',
    'D2': '激励机制',
    'D3': '信息与反馈',
    'D4': '演化能力',
    'D5': '合法性与叙事',
    'D6': '耦合与依赖',
    'D7': '权力结构',
}


def build_radar_svg(scores: dict[str, int | float], size: int = 380) -> str:
    """
    从 n 维评分生成内联 SVG 雷达图（支持任意维度数量）。

    scores: {'D1': 3, 'D2': 4, ..., 'Dn': v}
    返回可直接嵌入 <div class="radar-container"> 的 SVG 字符串。
    """
    # unknown / not_applicable 不进雷达图：没有分数就没有顶点，不用中性 3 顶上去
    scores = numeric_scores(scores)
    if not scores:
        return '<!-- 无数值维度评分，未生成雷达图 -->'
    cx, cy = size / 2, size / 2
    r_max = size / 2 - 50
    n = len(scores)
    angle_offset = -math.pi / 2

    def polar(level: float, i: int) -> tuple[float, float]:
        theta = angle_offset + 2 * math.pi * i / n
        r = r_max * level / 5
        return cx + r * math.cos(theta), cy + r * math.sin(theta)

    # viewBox 留白：维度标签放在 polar(5.8) 处、向外延伸，长中文名（如"合法性与叙事 3/5"）
    # 会超出 size×size 边界被裁。给左右各 110、上下各 28 的留白把文字包进画布，
    # 再由 .radar-container svg 的 max-width 整体缩放，确保任何长度的标签都完整显示。
    pad_x, pad_y = 110, 28
    vb_w, vb_h = size + 2 * pad_x, size + 2 * pad_y
    lines: list[str] = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{-pad_x} {-pad_y} {vb_w} {vb_h}" '
        f'width="{vb_w}" height="{vb_h}">'
    )

    for level in range(1, 6):
        pts = ' '.join(f'{polar(level, i)[0]:.1f},{polar(level, i)[1]:.1f}' for i in range(n))
        opacity = '0.15' if level < 5 else '0.3'
        lines.append(
            f'  <polygon points="{pts}" fill="none" stroke="#94a3b8" '
            f'stroke-width="0.8" opacity="{opacity}" />'
        )

    for i in range(n):
        x, y = polar(5, i)
        lines.append(
            f'  <line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
            f'stroke="#94a3b8" stroke-width="0.5" opacity="0.3" />'
        )

    dim_keys = sorted(scores.keys())
    data_pts = []
    for i, key in enumerate(dim_keys):
        val = max(0, min(5, scores.get(key, 0)))
        data_pts.append(polar(val, i))

    pts_str = ' '.join(f'{x:.1f},{y:.1f}' for x, y in data_pts)
    lines.append(
        f'  <polygon points="{pts_str}" fill="rgba(37,99,235,0.2)" '
        f'stroke="#2563eb" stroke-width="2" />'
    )

    for x, y in data_pts:
        lines.append(f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#2563eb" />')

    for i, key in enumerate(dim_keys):
        lx, ly = polar(5.8, i)
        val = scores.get(key, 0)
        label = _DIMENSION_LABELS.get(key, key)
        anchor = 'middle'
        if lx < cx - 10:
            anchor = 'end'
        elif lx > cx + 10:
            anchor = 'start'
        lines.append(
            f'  <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'dominant-baseline="central" '
            f'font-family="-apple-system,BlinkMacSystemFont,sans-serif" '
            f'font-size="12" fill="#1f2937">'
            f'{label} {val}/5</text>'
        )

    lines.append('</svg>')
    return '\n'.join(lines)


def save_html_report(
    system_name: str,
    system_type: str,
    report_body_html: str,
    date_str: str | None = None,
    output_dir: Path | None = None,
    title: str | None = None,
) -> str:
    """
    保存 Brookings/CSIS 智库风格 HTML 报告到 Obsidian 仓库。

    report_body_html: 报告正文的 HTML（不含 <html>/<head>/<body> 标签）。
    Orchestrator 负责将 Markdown 报告转换为 HTML 片段后调用此函数。

    HTML 使用内嵌 CSS，自包含无外部依赖（字体通过 Google Fonts CDN 加载，离线时降级到系统衬线字体）。
    output_dir: 可选，覆盖默认 OBSIDIAN_DIR（用于测试隔离）。

    CSS class 速查（供 Orchestrator 在转换报告时使用）：
      .exec-summary        — 执行摘要蓝色卡片
      .callout-red/amber/green — 风险等级 callout 块
      .score-badge .score-N — 评分徽章（N=1-5）
      .radar-container     — 雷达图 SVG 容器
      <details><summary>    — 折叠区域（用于信源审计）
      table (thead/tbody)   — zebra stripe 表格
      .prediction-review    — 上期预测复盘区块
      .predictions          — 可证伪预测区块
      .prediction-card      — 单条预测卡片（蓝色左边框）
      .prediction-title     — 预测内容标题
      .prediction-meta      — 证伪条件/时间窗口/置信度元信息
      .prediction-link      — 关联维度标签
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    target_dir = output_dir or OBSIDIAN_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    safe = system_name.replace('/', '-').replace('\\', '-').replace(':', '-')
    filename = f'{date_str} {safe} 诊断报告.html'
    filepath = target_dir / filename

    display_title = title or f'{system_name} — 系统诊断报告'
    html = _HTML_TEMPLATE.format(
        title=display_title,
        date=date_str,
        system_type=system_type,
        body=report_body_html,
    )
    filepath.write_text(html, encoding='utf-8')
    return str(filepath)


def list_analyses(system_name: str) -> list[dict]:
    """列出该系统的所有历史分析记录摘要（按日期与版本倒序）。"""
    records = []
    for f in reversed(_version_files(_system_dir(system_name))):
        try:
            data = json.loads(f.read_text())
            records.append({
                'date':          data.get('analysis_date'),
                'analysis_id':   data.get('analysis_id') or f.stem,
                'system_type':   data.get('system_type'),
                'overall_score': data.get('overall_score'),
                'completeness':  data.get('completeness'),
                'output_mode':   data.get('output_mode', 'full'),
                'file':          str(f),
            })
        except json.JSONDecodeError:
            continue
    return records
