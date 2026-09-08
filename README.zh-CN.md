# System Pathology（系统病理学）

*[English README](README.md)*

一套**七维度**复杂系统诊断框架——适用于企业、政府机构、DAO、市场、地缘政治实体、平台生态，以及**关系系统**（系统本身就是多方互动关系，而非任何单一实体，例如冲突格局、战略对抗、联盟体系）。以 [Claude Code](https://claude.ai/claude-code) skill 的形式实现，采用 Orchestrator + 并行 Researcher sub-agent 架构。

可以把它想象成组织的病理学工具箱：不是在显微镜下观察细胞，而是检视边界结构、激励机制、信息与反馈、演化能力、合法性叙事、耦合与依赖、权力结构——再交叉比对，找出表层分析看不见的系统性病理。同样这七个问题，在关系系统中会被重新诠释（见下文"关系系统"一节）——健康度衡量的是互动的**可管理性**，不是友好程度。

> **关于可靠性（请先读这段）。** 这个工具让 LLM 分析可能晚于其训练截止日期的事件，证据来自 sub-agent 的网络采集。它可能出错，它自己的核查机制也可能出错。系统的设计目标是**让不确定性可见，而不是保证真相**：它给信源分级并核验、记录哪些流程门控被执行、为自己过去的预测做校准、独立复核载荷性断言——然后把仍然佐证单薄的部分暴露出来交给人判断。请把它的输出当作一份结构化的、自我审计过的分析师草稿，而非神谕。

## 它做什么

**输入**：系统名称 + 类型（如"伊朗-美国-以色列冲突" / relational，"ByteDance" / public_company）。实体系统（公司、国家、DAO）与关系系统（冲突、对抗、联盟——关系本身就是系统）均支持；七个维度按类型重新诠释（详见 SKILL.md）。

**流程**：
1. 自动生成多视角搜索查询（官方、反对派、媒体、智库、区域、本地语言）
2. 派发并行 Researcher sub-agent（模型分层：`haiku` 处理英文/近期事件批次，`sonnet` 处理非拉丁本地语言与敏感话题批次）
3. 执行质量门控——新鲜度 + **突发事件扫描**、覆盖率、以及**真正执行的信源核验**（对高权重信源做 WebFetch 抽查）
4. 条件触发 Round 2 深度研究（矛盾求证、数据锚定、缺口填补）
5. 执行**七维度**诊断，评分（1-5 分）锚定于参考案例
6. 机械化比对评分向量与**危险区/生存区签名**（如 D5≤2 + D2≤2 = Enron/Theranos 型合法性-激励崩塌；这些签名是**事后归纳的假说**，无验证样本与误报率，命中=调查线索而非已验证前兆），并从一张声明的因果图中计算**反馈回路、结构中心性与处方溢出**——分析师判断的逻辑后果由代码推导，不是靠手工记账
7. 独立复核载荷性事实断言（fact-check sub-agent），抓住"听起来合理但记错了"的综述类错误
8. 生成可证伪预测，并跨轮次追踪**时序合规**的校准分数

**输出**：默认一份 Markdown 报告 + 一份结构化 analysis JSON；以下为按需导出的完整形态——

| 文件 | 格式 | 何时生成 | 内容 |
|------|------|---------|------|
| 结构化 `analysis.json` | JSON | 总是 | 审计链：断言 → 机制 → 判断 → 预测/行动。持久化到 `~/.system_pathology/data/` 供纵向追踪 |
| `{日期} {系统名} 系统诊断.md` | Markdown | 总是 | 可读交付（骨架见 `references/report-template.md`） |
| `{日期} {系统名} 研究素材.md` | Markdown | 按需 | 原始信源、矛盾信号、覆盖缺口 |
| `{日期} {系统名} 诊断报告.html` | HTML | 按需 | Brookings/CSIS 智库风格长文，内嵌雷达图 |

报告输出目录优先读 `SYSTEM_XRAY_OUTPUT_DIR` 环境变量，未设置时回落到配置的 Obsidian 仓库。
**文件份数不是分析质量的度量**——完整性由 `completeness` 字段与统一契约校验判定。

## 架构

```
用户请求
  │
  ▼
Orchestrator（Claude Code 主 agent）
  ├─ generate_queries() + group_into_batches()     ← Python 工具，经 Bash 调用
  │
  ├─ ROUND 1：并行 Researcher 派发（模型分层：haiku / sonnet）
  │   ├─ Researcher A：Batch 0（近期事件扫描，含过去 24-48 小时）
  │   ├─ Researcher B：Batch 1（结构性视角）
  │   ├─ Researcher C：Batch 2（本地语言视角 → sonnet）
  │   └─ ...
  │         ↓ 每个返回结构化 JSON：信源 + 发现 + 矛盾
  │
  ├─ 质量门控：新鲜度 + 突发事件扫描 / 覆盖率 / 信源核验
  │
  ├─ [条件触发] ROUND 2：深度研究（最多 5 个 Researcher）
  │   ├─ contradiction_resolution / data_anchor / gap_filler
  │
  ├─ [条件触发] 预测验证（时序合规：不允许提前判 "confirmed"）
  ├─ Research Brief → 用户确认
  ├─ 竞争假说检验（ACH，full 模式，经 ach_score 做信源层级加权评分）
  ├─ 七维诊断（依据校准锚点评分）
  ├─ detect_danger_zones() — 自动比对灾难性/生存性签名
  ├─ causal_graph：反馈回路 + 杠杆点排序 + 处方溢出模拟
  ├─ 关键断言账本 → 分诊薄佐证断言 → fact_check sub-agent 独立复核
  ├─ 生成 3-5 条可证伪预测
  ├─ history_compare() + find_analogies() + calculate_prediction_accuracy(as_of_date)
  └─ validate_analysis() 门控 → save_analysis() → JSON + MD + HTML（+ 信源审计）
```

**设计原则：**
- Orchestrator 只协调，不搜索。Researcher 只采集，不分析。
- 同一轮次内所有 Researcher 同时派发（单条消息、并行 Agent 调用），按成本（haiku）与多语言/敏感能力（sonnet）分层选模型。
- 工具是纯计算 Python，经 Bash 调用——查询生成、评分对比、持久化、校验全程无 LLM 参与。
- Round 2 有条件触发且有硬上限（最多 5 个 Researcher，不存在 Round 3）。
- **跳过被显式记录，而非被禁止**：`validate_analysis()` 门控在落盘前硬拒绝结构不合法/超范围的数据；`process_warnings()` 标记任何被跳过的门控（ACH、Round 2、信源核验、突发事件扫描）——把静默省略变成被记录在案的决定。
- 每次分析生成可证伪预测；下一次分析自动验证（时序合规）并计算 Brier 分数校准。

## 七个诊断维度

| # | 维度 | 核心问题 | 病理示例 |
|---|------|---------|---------|
| D1 | **边界结构** | 硬墙与软膜在哪里？ | 边界侵蚀、堡垒综合征、寄生负荷 |
| D2 | **激励机制** | 奖励是否产生生存所需的行为？ | 激励倒置、道德风险级联、眼镜蛇效应、纳什陷阱 |
| D3 | **信息与反馈** | 系统能否感知现实并据此行动？ | 幻境综合征、正反馈死亡螺旋、Ashby 律违反 |
| D4 | **演化能力** | 是否在透支未来供养现在？ | 时间蚕食、演化锁定、热寂轨迹 |
| D5 | **合法性与叙事** | 系统讲给自己的故事是否还成立？ | 叙事崩塌、合法性债务、货物崇拜式表演 |
| D6 | **耦合与依赖** | 连接是过紧、过松还是连错了地方？ | 紧耦合灾难、依赖陷阱、级联架构 |
| D7 | **权力结构** | 谁能决定什么？权力如何分配与转移？ | 影子权力结构、否决陷阱、权力真空、赢家通吃级联 |

> D7（权力结构）是在最初六维设计之后新增的。框架保持向后兼容：接受 6 维或 7 维评分向量的历史分析与工具均可正常运行。

跨维度交互是最危险的病理藏身之处：

| 模式 | 涉及维度 | 机制 |
|------|---------|------|
| 信任死亡螺旋 | D1×D2×D5 | 边界侵蚀 → 激励作弊 → 叙事崩塌 → 进一步侵蚀 |
| 创新剧场陷阱 | D4×D5×D2 | 更新表演 → 维持合法性 → 无压力修正激励 |
| 信息-激励恶性循环 | D3×D2 | 坏激励 → 信息过滤 → 更差决策 → 更坏激励 |
| 权力-信息恶性循环 | D7×D3 | 权力集中 → 信息过滤 → 更差决策 → 更集中 |
| 继承-时间挤压 | D7×D4 | 继承不确定 → 时间视野缩短 → 无长期投资 |

这些交互，加上哪些回路闭合、哪个维度结构上最中心，由 `agent/tools/causal_graph.py` 从一组声明的因果边计算得出——不是照抄静态表格。注意**结构中心性不是 Meadows 杠杆等级**：Meadows 排的是干预的种类（参数 < 信息结构 < 规则 < 目标 < 范式），中心性只说明改动它波及面大。把中心维度提为干预目标还需另做可干预性审查（见 `references/methods/decision.md`）。详见下文"分析引擎"一节。

## 关系系统

框架大多数系统类型都是**实体**——一家公司、一个国家、一个 DAO——独立于任何特定对手方而存在。`relational`（关系系统）不同：分析对象是**互动本身**（冲突、对抗、威慑对峙、联盟），任何一方被移除，它就不复存在。伊朗-以色列、中美战略竞争、印巴对峙、1914 年前的欧洲联盟体系都是关系系统；ByteDance 不是（换掉它的竞争对手，它还是 ByteDance）。

七个维度沿用，但被重新诠释：

| 维度 | 实体系统问的是 | 关系系统问的是 |
|------|--------------|--------------|
| D1 | 硬墙与软膜在哪 | **红线与交战规则**——是否清晰、被尊重、在制度化还是在瓦解？ |
| D2 | 奖励是否匹配生存需要 | **克制的收益结构**——升级还是克制更有回报？是否存在先发优势？ |
| D3 | 系统能否感知现实 | **信号保真与误判风险**——危机沟通渠道是否存在且被使用？打击被误读为进攻、克制被误读为软弱的频率有多高？ |
| D4 | 是否透支未来供养现在 | **升级棘轮与可持续性**——每轮交手是否抬高"正常"暴力的基线？有无降级阶梯？ |
| D5 | 系统的故事是否还成立 | **共存叙事**——各方是否还讲一个承认对方合法存在的故事？ |
| D6 | 耦合是否过紧、过松、连错地方 | **纠缠结构与传染通道**——代理人网络和联盟义务是否把局部火花变成系统性大火？ |
| D7 | 谁决定什么，权力如何转移 | **极性与否决结构**——力量对比是对称还是转移中（修昔底德区间）？谁能否决升级？ |

关系系统专属病理：**升级棘轮**（每轮交手把"正常"基线抬高）、**信号反转**（克制被读成软弱、威慑被读成挑衅——1983 年 Able Archer 演习、1914 年七月危机）、**刚性纠缠**（联盟/代理人链条让任何单一行为体都无法单方面降级）、**先发激励**（动员或先发制人的结构惩罚克制）、**共存叙事归零**（一旦对方的合法性被彻底否定，任何一方在国内都无法兜售妥协）。

`relational` 类型的研究采集围绕互动机制组织，而非单一实体的健康状况——升级事件、缓和/外交渠道、各方官方红线、军力对比、第三方斡旋者、代理人网络——升级视角与缓和视角被**设计为同批派发**，确保没有任何一个 sub-agent 只看到互动的一面。

## 历史类比匹配

评分完成后，当前系统的七维评分向量会与 **51 个历史参考案例**（`references/analogy-cases.json`）比对，覆盖 7 种系统类型——包含一个 `relational` 轨道：1914 年七月危机、古巴导弹危机、美苏缓和、埃以冷和平、印巴对峙、2018-2020 中美贸易战、伊以影子战争，以及 2022 年俄乌开战前夕。

匹配采用**量级敏感的欧氏距离**，而非余弦相似度——余弦只比较方向，会让全低的危机向量与全高的健康系统被判定为"完全相同"（两者比例接近，尽管一个在崩溃、一个在兴盛）。同类型系统只获得小幅加性 tiebreaker（+0.08，clamp 到 1.0）而非乘性加成，确保松散匹配的同类型永远不会反超紧密匹配的跨类型。结果呈现 `similarity`、`outcome`、`key_lesson`，以及**相似度是在几个维度上算出来的**与**评分的编码方式**——类比是启发式的背景参考，不是预测："结构上与 X 相似"不等于"会重蹈 X 的覆辙"。

**这个库是教学集，不是验证集。** 每条评分都是在结局已知之后编定的，编码者没有被隔离结局，选样也偏向著名失败案例。文件现在把 `as_of_known` 与 `hindsight` 分开存放，回放时可整块隔离结局（`find_analogies(..., blind=True)` 直接删掉 `outcome` 与 `key_lesson`）——这让污染变得**可见且可机械排除**，但并不等于已有评分被去污染。拿它验证方法有效性，等于用后见之明证明后见之明。

## 分析引擎

三个纯计算工具把分析师声明的判断变成其逻辑后果，而不是每次都靠手工重新推算：

| 引擎 | 输入（分析师的判断） | 输出（计算得出的后果） |
|------|---------------------|----------------------|
| `causal_graph.py` | 一组维度间因果边（`{from, to, sign, strength}`） | 全部闭合反馈回路，分类为恶性/良性/拮抗（回路内任一维度未评分则为 `indeterminate`）；结构中心性排序（**不是** Meadows 杠杆等级）；任意处方在全图上的启发式序数溢出——只给方向与波及范围，不给效果幅度；处方间冲突检测 |
| `ach_score.py` | 2-4 个假说 + 一张带信源层级的 C/I/N 证据矩阵 | 信源层级加权、鉴别力感知的假说排序与状态（`eliminated` / `stressed` / `active` / `untestable`）——一条 T1 不一致证据的权重压过十条 T3 一致证据，对所有假说打同一标记的证据被判定无鉴别力而降权 |
| `history_compare.detect_danger_zones()` | 七维评分向量 | 自动比对 6 个灾难性签名与 4 个生存性签名（如 D5≤2 + D2≤2 = Enron/Theranos/FTX 型合法性-激励崩塌；D4≥4 + D6≥4 = 反脆弱内核） |

分析师仍然决定*有哪些边*、*证据说明了什么*、*评分是多少*——这些工具只确保下游的运算（闭合判定、排序、传播、签名比对）是推导出来的，而不是目测估计的。

## 信源层级体系

所有证据按可信度分级：

| 层级 | 类型 |
|------|------|
| **T1** | 政府文件、法院记录、财务报表、链上数据 |
| **T2** | 路透社、FT、WSJ、BBC、学术论文、智库报告 |
| **T3** | Glassdoor、Reddit、Twitter/X、匿名来源 |
| **⚠️** | 训练知识（仅作背景，不计入评分依据） |

**多语言支持**（6 种语言）：中文(zh)、阿拉伯语(ar)、波斯语(fa)、俄语(ru)、日语(ja)、韩语(ko)。语言检测自动进行——"沙特-伊朗代理战争"会同时触发 `ar` 和 `fa` 查询。每种语言有各自的 T1/T2/T3 信源层级（如中文：gov.cn/财新/微博；阿拉伯语：WAM-SPA/半岛电视台/阿拉伯语 Twitter）。中文输入的外名检测（"伊朗"→fa、"沙特"→ar、"俄乌"→ru）确保当事方本地语言信源不会因为输入是中文而被漏掉。

## 预测与校准系统

每次分析生成 3-5 条**可证伪预测**，包含：
- 具体的证伪条件（"若观察到 X，此预测失败"）
- 绝对时间窗口（如 `2027-03-31`）
- 数值置信度（0.0-1.0）
- 关联的诊断维度（D1-D7）

对同一系统重复分析时，上期预测会自动加载、依据当前证据验证并评分：
- **按事件类型裁定**：哪些提前裁定合法，取决于预测说的是哪类事件。`persistence`（"X 持续到 D"）到期前不能判成立、但可以提前判不成立；`occurrence`（"X 在 D 前发生"）正好相反——可以提前判成立，但**不能**提前判不成立，除非预先定义的不可能条件已被证实；`point_in_time` 两个方向都等目标时点；`conditional` 在触发条件发生前不计分。不合法的提前裁定一律降级为未决并排除出评分——系统既不能用未到期预测炮制"100% 命中率"，也不会把一条还有 73 年才到期的预测算成自己判错了。
- **Brier 分数**——标准 `mean((p - y)^2)`，仅在 ≥3 条真正到期裁定时计算，且始终同时报出**同样本基础率基准**、样本量与未决比例。已裁定样本不足 30 条时工具会明确 flag：少量预测的低 Brier 不构成校准良好的证据。
- **高置信落空**（置信度 ≥0.7 但被证伪——标记为警示）
- 结果同时呈现在 Research Brief 和最终 HTML 报告中

## 可靠性与核验门控

由于分析运行在 LLM 采集的、可能晚于训练截止日期的证据之上，系统层层设防让不确定性**可见且可审计**。每一层都由代码（`agent/store/db.py`）强制执行或暴露，而非依赖记忆：

| 门控 | 做什么 | 能抓住什么 | 抓不住什么 |
|------|--------|-----------|-----------|
| **结构校验**（`validate_analysis`） | 落盘前硬拒绝结构不合法的分析 | 超范围评分、非规范维度键、格式错误的预测、缺 URL 的证据 | 格式正确但内容错误的值 |
| **流程告警**（`process_warnings`） | 对被跳过门控的非阻塞标记 | ACH/Round 2/信源核验/突发事件扫描被跳过；最新信源过期；未佐证的载荷性断言 | （依赖如实记录的 `process_metadata`） |
| **信源核验**（`--verify-plan` → WebFetch） | 对高权重信源（T1/T2 + 定量声明）抽查可达性与标题/数字是否一致 | 失效/伪造的 URL、数字不符 | 依托*真实*信源但综述错误的内容 |
| **断言事实核查**（`--triage-claims` → `fact_check` sub-agent） | 独立重新求证载荷性、佐证单薄的断言 | 自信但张冠李戴的错误（如任职者搞错） | 佐证*充分*但综合错误的内容 |
| **按事件类型校准** | 只允许该事件类型许可的提前裁定 | 用未到期预测炮制虚假"100% 命中率"；把一条还有 73 年到期的预测算成判错 | 事件类型本身是否被如实分类 |
| **证据血缘**（`--lineage`） | 把转载/翻译折叠为来源家族；被反证的断言向所有依赖它的结论传播 | 重复冒充佐证；一条已被推翻的事实仍在悄悄支撑某个机制 | 未标同一家族的改写式转载 |
| **跨期可比性**（`--changes`） | 把每条变化归入 系统状态/机制/**观测口径**/分析修正 | 口径改动被读作系统改善 | 未登记的口径变更——它只看得见被登记的部分 |
| **因果能力入口门**（`--causal-readiness`） | 列出某机制离 L2/L3 还差哪些条件 | 由 L1 箭头与序数分数生成的效果承诺 | 识别策略本身是否真的站得住 |
| **不可变版本** | 每次保存产生新版本，历史不被覆盖 | 同日两次分析静默合并成一次 | — |

**已验证与未验证的边界。** 227 个单元/契约测试通过；`evals/adversarial.py` 跑通 11 条自动对抗用例
（重复证据、口径变更、提前裁定、越权行动、材料中的提示词注入……）；`evals/synthetic.py` 跑通 8 条
**真相由构造决定**的机制案例，并做了消融实验。每条防护都配负控——关掉它，对应用例立刻变红；
消融本身也有负控：一个什么都不破坏的消融会让测试失败，因为零差值意味着那批案例根本没测到那个模块。

证据到此为止，而且它是关于**构造输入上的逻辑**的证据。它没有说明研究准确性、因果识别有效性、
决策有用性，或预测是否优于基线。那些的协议——12 个冻结真实案例、三路径对照、独立盲评、
≥30 条已裁定预测——写在 `evals/protocol.md`，**仪器已建好并通过测试，但尚未执行**，
因为缺的输入是真实研究、人类评审和时间流逝。

**诚实的残余风险。** 这些门控是分诊 + 抽查 + 独立重新求证，**不是**真相保证。一条自信错误但佐证"充分"（≥2 个看似可靠的信源）的断言仍可能通过；fact_check sub-agent 本身也是可能犯错的 LLM。这是让 LLM 分析训练截止之后事件的不可消除的底线。设计目标是**把佐证单薄或存在矛盾的部分暴露给人类判断**，而不是认证正确性——核验完备性是一个人类终点，不是另一道门控。

## 目录结构

```
system-xray/
├── SKILL.md                              # Skill 元数据 + 完整诊断协议
├── agent/
│   ├── agent.py                          # CLI：查询预览、历史记录、持久化、契约校验、审计、信源核验计划、断言分诊、证据血缘
│   ├── prompts/
│   │   ├── system.md                     # Orchestrator 提示词（完整管道 + 质量门控）
│   │   ├── researcher-base.md            # Researcher 通用核心（采集流程 + 英文分级 + schema + 中性框架）
│   │   ├── researcher-sources.md         # 分语言信源层级表（按需粘贴）
│   │   └── researcher-modes.md           # Round 2 + 验证模式：gap_filler / contradiction_resolution / data_anchor / prediction_verification / fact_check
│   ├── validation.py                     # 统一契约校验（结构 / 依赖 / 状态 / 预测语义 / 时效 / 注入扫描）+ L2-L3 因果能力入口门 + 消融开关
│   ├── store/
│   │   ├── db.py                         # 持久化 + validate_analysis + process_warnings + 完整性推导 + 信源审计/核验 + 断言分诊 + 雷达图 SVG
│   │   └── __init__.py
│   ├── tools/
│   │   ├── query_generator.py            # 多视角查询生成 + 语言检测
│   │   ├── history_compare.py            # 评分差值 + 覆盖门控的类比 + 按事件类型裁定的 Brier 校准 + 危险区签名
│   │   ├── causal_graph.py               # 反馈回路检测 + 结构中心性排序 + 启发式干预传播 + 处方交叉检查
│   │   ├── ach_score.py                  # 独立证据家族折叠 + 信源层级加权 ACH 评分 + 留一敏感性
│   │   ├── evidence_lineage.py           # 来源家族、断言支撑画像、反证向依赖结论的传播
│   │   ├── temporal.py                   # 双时间校验 + 按断言类型的时效 + 口径可比性 + 判断变更分类
│   │   ├── forecast_registry.py          # 预测冻结与版本、预先声明的复盘策略、按事件类型的裁定窗口
│   │   ├── stock_flow.py                 # L2 存量—流量局部模型：一阶延迟 + 参数区间角点扫描 + 稳健性判定（缺区间即拒绝出结论）
│   │   ├── causal_adapter.py             # L3 效果估计：后端检测（有 DoWhy 用 DoWhy，否则用明确标注的最小 DiD）+ 安慰剂/留一反驳
│   │   └── __init__.py
│   └── __init__.py
├── references/
│   ├── scoring-calibration.md            # 各维度各系统类型的锚点案例（含 relational），防止评分漂移
│   ├── research-protocol.md              # 按系统类型分类的结构化搜索查询
│   ├── question-banks.md                 # 面向内部人访问用户的访谈问题库
│   ├── report-template.md                # 单一报告骨架（决策摘要 → 审计附录）
│   ├── methods/                          # 按需加载的方法卡：证据 / 机制 / 动态 / 预测 / 决策
│   ├── analogy-cases.json                # 51 个历史参考案例，覆盖 7 种系统类型
│   └── diagnostic-schema.json            # 数据契约的唯一规范：断言 → 机制 → 判断 → 预测/行动
├── evals/
│   ├── adversarial.py                    # §14.3 对抗用例套件——11 条自动 + 1 条诚实标注的提示词层用例
│   ├── synthetic.py                      # 真相由构造决定的合成机制案例 + 消融实验
│   ├── decision_increment.py             # 盲评打包 + §14.2 判据（两人均为 2 才合格，分歧须裁决）
│   ├── cases/                            # 合成案例库、评分表模板
│   ├── protocol.md                       # 对照评估协议——真实案例部分**尚未执行**
│   └── README.md                         # 每个套件证明什么、不证明什么
└── tests/                                # 227 个测试：契约层、跨期更新、能力分层、对抗与合成案例（含负控）、校验逻辑与分析引擎
```

## 安装

这是一个 Claude Code skill——运行在 Claude Code 的 agent 基础设施内，不是独立应用。

### 前置条件

- [Claude Code](https://claude.ai/claude-code)（CLI、桌面应用或 IDE 插件）
- Python 3.10+（用于计算工具）
- 一个配置好路径的 Obsidian 仓库（用于报告输出）

### 安装步骤

1. 把本仓库克隆到 Claude Code 的 skills 目录：

```bash
git clone https://github.com/Eleven1111/system-xray.git ~/.claude/skills/system-xray
```

2. Skill 通过 `SKILL.md` 的 frontmatter 自动注册。无需 `pip install`——所有 Python 工具只用标准库。

3. 把报告输出指向你自己的目录（无需改代码）：

```bash
export SYSTEM_XRAY_OUTPUT_DIR="/your/output/directory"
```

不设置时回落到 `agent/store/db.py` 中硬编码的 Obsidian 仓库路径。

## 使用方法

在 Claude Code 中，直接描述你想诊断的系统：

```
> 诊断中美关系作为一个地缘政治系统
> ByteDance 的组织结构出了什么问题？
> 给 DeFi 生态做一次全面体检
```

Skill 会在系统分析类请求上自动触发。你也可以指定模式：

```
> 精简模式分析伊朗政权
> 把特斯拉和比亚迪作为系统做对比
```

### CLI 参考

Orchestrator 通过 Bash 驱动这些 Python 辅助工具。持久化/核验类命令从文件或 stdin（`--input`）读取 payload，确保含中文引号/HTML 的多 KB 报告不会撞上 shell 转义问题。

```bash
cd ~/.claude/skills/system-xray

# 查询预览与历史记录
python3 -m agent.agent --system "ByteDance" --type public_company --queries-only
python3 -m agent.agent --system "ByteDance" --history
python3 -m agent.agent --list-types
python3 -m agent.agent --system "Iran" --load-predictions   # 上期预测（供校准用）
python3 -m agent.agent --system "Iran" --load-latest        # 上期完整记录

# 校验与持久化（payload 从 --input 文件或 stdin 读取）
python3 -m agent.agent --validate --input analysis.json                          # 仅做 schema 校验 + 流程告警，不落盘
python3 -m agent.agent -s "X" -t public_company --save-analysis --input a.json    # 先校验后持久化 JSON
python3 -m agent.agent -s "X" -t public_company --save-materials --input brief.json
python3 -m agent.agent -s "X" -t public_company --save-html --title "…" --input body.html
python3 -m agent.agent -s "X" -t public_company --save-md --input report.md

# 报告构建组件
python3 -m agent.agent --radar --input scores.json                  # 七维雷达图 SVG
python3 -m agent.agent --build-audit --input brief.json             # 逐条信源审计（含核验徽章）

# 分析引擎（纯计算——把声明的判断变成其逻辑后果）
python3 -m agent.agent --danger-zones --input scores.json           # 自动比对灾难性/生存性签名
python3 -m agent.agent --causal --input graph.json                  # 反馈回路 + 结构中心性 + 处方溢出
python3 -m agent.agent --lineage --input analysis.json              # 来源家族 + 断言支撑 + 反证传播
python3 -m agent.agent --causal-readiness --input analysis.json     # 各机制离 L2/L3 还差哪些入口条件
python3 -m agent.agent --system "X" --versions                      # 列出不可变分析版本
python3 -m agent.agent --system "X" --changes --input new.json      # 判断变更 + 口径可比性
python3 -m agent.agent --staleness --input analysis.json            # 按断言类型的时效体检
python3 -m agent.agent --predictions-due --input analysis.json      # 今天哪些预测可裁定

python3 -m evals.adversarial                                        # §14.3 对抗用例套件
python3 -m agent.agent --ach-score --input ach.json                 # 信源层级加权的竞争假说排序

# 可靠性门控
python3 -m agent.agent --verify-plan --input brief.json --sample 4  # 选出最该 WebFetch 核验的信源
python3 -m agent.agent --triage-claims --input analysis.json        # 分诊出最该独立 fact_check 的载荷性薄佐证断言
```

### 支持的系统类型

| 类型 | 说明 |
|------|------|
| `geopolitical` | 民族国家、贸易集团、国际机构 |
| `government_agency` | 政府机构、部委、监管机构 |
| `public_company` | 上市公司 |
| `private_company` | 私营企业、初创公司 |
| `dao` | DAO、开源社区、合作社 |
| `market` | 行业垂直领域、供应链 |
| `platform` | 平台生态 |
| `relational` | 多行为体互动系统——系统*就是*这段关系，不是任何单一实体：冲突格局（伊朗-美国-以色列）、战略对抗（中美）、联盟、威慑对峙。健康度衡量互动的可管理性，不是友好程度 |

## 输出风格

报告采用 **Brookings/CSIS 智库长文风格**——叙事散文为脊柱，不是仪表盘或要点堆砌。

- **叙事段落**作为主要载体（每个维度 2-4 段）
- **行内引用**自然融入行文（"据路透社 5 月报道……"）
- **评分徽章**作为行内点缀，不单独成表
- **表格/callout** 仅在结构化数据确有必要时使用
- **编辑式标题**：主标题用隐喻/判断，副标题用具体对象
- **可折叠信源审计**位于末尾（即便在精简模式下也不省略）

**完整模式章节顺序：**
上期预测复盘（如适用）→ 执行摘要 → 系统制图 → 竞争假说检验（ACH）→ 七维诊断 → 跨维度分析 → 历史类比 → 关键风险节点 → 演化情景与处方 → 可证伪预测 → 监控仪表板 → 信源审计

## 扩展

### 新增一种语言

在 `agent/tools/query_generator.py` 中完成三步：

1. 在 `LANGUAGE_REGISTRY` 中添加条目（Unicode 范围、话题关键词、信源层级、P0 查询模板）
2. 在 `LOCAL_PERSPECTIVES` 中添加条目（按系统类型的结构性视角）
3. 在 `PERSPECTIVE_LABELS` 中添加条目（每个视角 key 的中文标签）

然后在 `agent/prompts/researcher-sources.md` 中添加对应的信源层级节。

### 新增一种系统类型

按现有模式在 `query_generator.py` 的 `PERSPECTIVE_MATRIX` 字典中添加视角矩阵：`(perspective_key, tier, priority, query_template)`。

## 理论基础

本框架综合了：

- **交易成本经济学**（Coase, Williamson）——边界决策、组织范围
- **可行系统模型**（Beer）——递归子系统结构、自治与控制的平衡
- **耗散结构理论**（Prigogine）——混沌中的秩序、负熵导入、更新
- **有限游戏与无限游戏**（Carse）——战略取向、领导哲学
- **机制设计**（Hurwicz, Myerson）——激励相容、博弈结构
- **反脆弱性**（Taleb）——压力响应分类
- **正常事故理论**（Perrow）——耦合架构、级联风险
- **公地治理**（Ostrom）——自我治理、共享资源管理
- **杠杆点理论**（Meadows）——复杂系统中该在哪里干预
- **危机稳定性与威慑理论**（Schelling, Jervis）——关系系统中的信号、升级动态与误判
- **竞争假说分析法**（Heuer）——针对证据矩阵的结构化假说检验，信源层级加权

## License

MIT
