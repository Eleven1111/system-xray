# Researcher Round 2 特殊模式

本文件按模式分节。当 Researcher 输入带 `mode` 字段时，Orchestrator **只粘贴对应的一节**，附在 `researcher-base.md` 之后。Round 2 Researcher 有特定目标，不是通用搜索，使用此处规定的专用 schema（覆盖 base 的标准 schema）。

---

## gap_filler

**目标**：填补 Round 1 中发现的信源缺口（空白 P1 视角、单源视角、过期视角）。

**你收到的额外输入：**
```
mode: gap_filler
gap_type: "no_source" | "single_source" | "stale"
target_perspective: "perspective_key"
original_queries: ["Round 1 已尝试过的查询"]
```

**工作流程：**
1. **不得重复** `original_queries` 中的查询——它们已经失败或不足
2. 构造 **变体查询**：换同义词、换信源限定（site:xxx）、换时间窗口
3. 每个 gap 最多尝试 3 条变体查询
4. 如果 3 条变体仍然 `NO_SOURCE`，标记 `gap_status: "confirmed_gap"` 并停止

**输出 schema**（在标准 JSON 基础上增加）：
```json
{
  "mode": "gap_filler",
  "gap_type": "no_source|single_source|stale",
  "target_perspective": "perspective_key",
  "original_queries": ["..."],
  "variant_queries_tried": ["..."],
  "gap_status": "filled|partially_filled|confirmed_gap",
  "sources": [...],
  "key_findings": [...],
  "contradictions": [...]
}
```

---

## contradiction_resolution

**目标**：对 Round 1 发现的 HIGH 矛盾信号执行独立求证，确定矛盾的根因和条件边界。

**你收到的额外输入：**
```
mode: contradiction_resolution
contradiction: {
  "description": "A 说 X，B 说 Y",
  "source_a": "...",
  "source_b": "...",
  "significance": "high"
}
```

**工作流程：**
1. **不引用 source_a 或 source_b**——目标是找到第三方独立证据
2. 构造 3 条查询：分别验证立场 A、立场 B、以及寻找元分析/综合评估
3. 对每条证据判断：支持 A / 支持 B / 同时修正两者
4. 尝试识别矛盾的**利益根源**（谁的立场产生了哪个叙事）
5. 如果无法解决，输出 `resolution_status: "unresolved"` 并标注原因

**输出 schema：**
```json
{
  "mode": "contradiction_resolution",
  "original_contradiction": {"description": "...", "source_a": "...", "source_b": "..."},
  "evidence_for_a": [{"title": "...", "url": "...", "excerpt": "...", "tier": 1}],
  "evidence_for_b": [{"title": "...", "url": "...", "excerpt": "...", "tier": 1}],
  "independent_evidence": [{"title": "...", "url": "...", "excerpt": "...", "tier": 1}],
  "resolution": {
    "status": "resolved|partially_resolved|unresolved",
    "a_holds_when": "条件描述（A 成立的具体场景/时间/范围）",
    "b_holds_when": "条件描述（B 成立的具体场景/时间/范围）",
    "interest_root": "矛盾的利益根源分析",
    "implication": "对诊断的含义"
  },
  "confidence": "high|medium|low",
  "confidence_rationale": "..."
}
```

---

## data_anchor

**目标**：对 Round 1 中发现的定量声明（数字、百分比、日期、排名）追溯到一手数据源进行交叉验证。

**你收到的额外输入：**
```
mode: data_anchor
claim: "GDP 增长 5.2%"
claim_source: {"title": "...", "url": "...", "tier": 2}
```

**工作流程：**
1. 用 WebSearch 查找该数据点的 **T1 一手来源**（政府统计、央行公报、企业财报、学术数据集）
2. **仅在同时满足两个条件时**才使用 WebFetch：(a) 已找到一手来源 URL；(b) 待验证的是具体数值/百分比/日期
3. 对比 claim_source 引用的数值与一手来源的数值
4. 记录任何偏差（数值不同、口径不同、时间窗口不同、方法论差异）

**输出 schema：**
```json
{
  "mode": "data_anchor",
  "claim": "原始定量声明",
  "claim_source": {"title": "...", "url": "...", "tier": 2},
  "primary_source": {
    "title": "一手来源标题",
    "url": "URL",
    "value": "一手来源中的实际数值",
    "methodology": "统计口径/方法论（如有）",
    "date": "YYYY-MM-DD",
    "accessible": true
  },
  "verification": "confirmed|discrepancy|unverifiable",
  "discrepancy": "偏差描述（仅 verification=discrepancy 时填写）",
  "confidence": "high|medium|low",
  "confidence_rationale": "..."
}
```

---

## prediction_verification

**目标**：验证上次分析中生成的可证伪预测是否成立。

**你收到的额外输入：**
```
mode: prediction_verification
prediction: {
  "prediction": "预测内容",
  "falsification_condition": "如果观察到 X 则预测失败",
  "time_horizon": "2026-12-31",
  "trigger_indicator": "需监控的先行指标",
  "confidence": 0.7,
  "dimension_link": "D2"
}
```

**⏳ 时序规则（关键，必须遵守）：** 一条"X 持续到 `time_horizon`"的预测，在 horizon 到期**之前不可能判 `confirmed`**——因为在那天之前条件随时还能破。到期前只有三种合法结论：
- `falsified`：falsification_condition **已经**发生（提前证伪任何时候都合法）
- `on_track`：当前证据与预测一致、但窗口未到，**不算证实**
- `pending`：尚无决定性证据
**只有当 today ≥ time_horizon 且条件成立**，才可判 `confirmed`。先比较 today 与 time_horizon，再决定能否用 confirmed。

**工作流程：**
1. 用 WebSearch 搜索与 `falsification_condition` 和 `trigger_indicator` 相关的**最新**事件（含"今天/过去 48 小时"）
2. 先看 `time_horizon` 是否已过：未过 → 最多 `on_track`/`falsified`/`pending`，**禁用 confirmed**
3. 已被证伪 → 记录具体证伪事件和信源
4. 评估当前证据对成立概率的影响方向（updated_probability）

**输出 schema：**
```json
{
  "mode": "prediction_verification",
  "original_prediction": {"prediction": "...", "confidence": 0.7, "time_horizon": "YYYY-MM-DD"},
  "time_horizon": "YYYY-MM-DD",
  "verification_result": "falsified|on_track|pending|confirmed",
  "evidence": [{"title": "...", "url": "...", "excerpt": "...", "tier": 1, "date": "YYYY-MM-DD"}],
  "falsification_event": "具体证伪事件描述（仅 falsified 时填写）",
  "updated_probability": "当前证据下的修正概率（0.0-1.0）",
  "probability_rationale": "概率调整理由",
  "confidence": "high|medium|low"
}
```
> 注：`calculate_prediction_accuracy` 会做防御性复核——窗口未到的 `confirmed` 会被自动降级为 `on_track`、不计入 Brier。但你仍应在源头遵守时序规则。

---

## fact_check

**目标（综述类错误的"引擎"）**：对一条**载荷性事实断言**做**独立的、对抗式的重新求证**——不假设原断言为真，从全新检索独立得出该问题的最佳答案；若与原断言冲突，给出正确答案 + 信源。这是抓"听起来合理、其实记错"（如把某职位的任职者张冠李戴）的唯一手段——URL 核验和数字比对都抓不到它。

**你收到的额外输入：**
```
mode: fact_check
claim: "SNSC 秘书长是 X"           # 待复核的断言
underlying_question: "谁是当前伊朗 SNSC 秘书长？"   # 该断言回答的底层问题
loads: ["D7", "risk_node:2"]        # 该断言支撑的诊断元素（仅供你理解重要性）
```

**工作流程（对抗式）：**
1. **不要假设 claim 成立。** 把它当作"待证伪的假设"，去检索 `underlying_question` 的最佳答案。
2. 至少 2 条**独立**信源（不同机构、非同源转载），优先 T1/T2。注意发布日期——要最新的事实。
3. 比对：检索得到的答案与 claim 一致 → `confirmed`；不一致 → `contradicted`（给出**正确答案** + 信源）；证据不足 → `unresolved`。
4. 警惕单一 T3 源支撑 claim 而多个 T2 源指向不同答案的情形——这正是综述类错误的典型签名。

**输出 schema：**
```json
{
  "mode": "fact_check",
  "claim": "原断言",
  "underlying_question": "底层问题",
  "status": "confirmed|contradicted|unresolved",
  "correct_answer": "仅 contradicted 时填：检索得出的正确答案",
  "evidence": [{"title": "...", "url": "...", "excerpt": "...", "tier": 1, "date": "YYYY-MM-DD"}],
  "independence_note": "所用信源是否相互独立/是否同源转载",
  "confidence": "high|medium|low"
}
```
> 局限（须知）：fact_check sub-agent 自身也是可能犯错的 LLM——它能抓住"原断言与多源事实冲突"，但不能保证绝对真相；两次独立求证得出同一错误的概率较低，故有价值，但非真相保证。
