# Research Protocol: Automated Information Gathering

> **年份占位符**：本文件中 `{current_year}` = 当前年份，`{prev_year}` = 上一年。由 `query_generator.py` 动态注入。手动参考本文件时，自行替换为实际年份。

## Phase 1: Rapid Classification (before any searches)

Determine system type to select the right search template:

| Type | Signals | Protocol |
|------|---------|----------|
| **Public Company** | Stock ticker, SEC filings, earnings calls | Protocol A |
| **Private Company** | Funded startup, PE-backed, family business | Protocol B |
| **Government / Regulator** | Agency, ministry, public institution | Protocol C |
| **DAO / Web3** | On-chain governance, token holders, multisig | Protocol D |
| **Platform Ecosystem** | Marketplace, two-sided network, API economy | Protocol E |
| **Industry / Market** | Sector-level, not single org | Protocol F |

---

## Protocol A: Public Company

Run these searches **in parallel** (3 agents simultaneously):

**Agent 1 — Financial & Governance Signals**
```
Search queries (run all, pick most informative results):
1. "[Company] annual report {current_year} OR 10-K"
2. "[Company] proxy statement shareholder {current_year}"
3. "[Company] CEO compensation vs performance"
4. "[Company] insider selling OR buyback"
5. "[Company] credit rating downgrade OR upgrade"
```

**Agent 2 — Operational & Cultural Signals**
```
1. "[Company] layoffs OR restructuring {prev_year} {current_year}"
2. "[Company] Glassdoor CEO approval rating"
3. "[Company] employee lawsuit OR EEOC complaint"
4. "[Company] product recall OR regulatory fine"
5. "[Company] innovation lab OR R&D investment"
```

**Agent 3 — Competitive & Narrative Signals**
```
1. "[Company] market share loss OR gain {current_year}"
2. "[Company] activist investor OR short seller report"
3. "[Company] analyst downgrade OR 'avoid'"
4. "[Company] brand perception OR NPS survey"
5. "[Company] antitrust OR regulatory investigation"
```

**Credibility ranking for sources:**
- Tier 1 (high): SEC filings, audited financials, regulatory orders, court records
- Tier 2 (medium): Bloomberg/FT/WSJ analysis, analyst reports, earnings transcripts
- Tier 3 (low): Press releases, company blog, CEO interviews
- Tier 4 (signal only): Glassdoor, Reddit, Twitter/X, anonymous leaks

---

## Protocol B: Private Company

Private companies have less mandatory disclosure — use triangulation:

**Agent 1 — Funding & Investor Signals**
```
1. "[Company] funding round Crunchbase OR PitchBook"
2. "[Company] valuation down round OR flat round"
3. "[Company] investor [lead VC name] portfolio update"
4. "[Company] acqui-hire OR acquiree"
5. "[Company] runway OR burn rate"
```

**Agent 2 — People & Culture Signals**
```
1. "[Company] LinkedIn headcount growth OR decline"
2. "[Company] CTO OR CPO departure"
3. "[Company] Glassdoor reviews culture"
4. "[Company] hiring freeze OR layoffs"
5. "[Company] founder conflict OR co-founder departure"
```

**Agent 3 — Market & Product Signals**
```
1. "[Company] customer reviews G2 OR Capterra OR Trustpilot"
2. "[Company] pricing change OR freemium pivot"
3. "[Company] competitors beating OR losing to"
4. "[Company] product launch failed OR delayed"
5. "[Company] legal dispute customer OR partner"
```

**Additional technique for private companies:**
- Check LinkedIn for organizational structure signals (how many layers, team sizes)
- Check job postings for strategic signals (what roles are they hiring/not hiring?)
- Check former employee LinkedIn profiles for departure patterns

---

## Protocol C: Government / Public Institution

**Agent 1 — Accountability & Oversight Signals**
```
1. "[Agency] inspector general report OR audit finding"
2. "[Agency] GAO report OR parliamentary inquiry"
3. "[Agency] budget cut OR sequester impact"
4. "[Agency] mission creep OR scope expansion"
5. "[Agency] FOIA request revelations"
```

**Agent 2 — Performance & Delivery Signals**
```
1. "[Agency] backlog OR processing time increase"
2. "[Agency] program failure OR cost overrun"
3. "[Agency] employee morale survey OR union grievance"
4. "[Agency] leadership turnover OR acting director"
5. "[Agency] Congressional testimony criticism"
```

**Agent 3 — Political & Legitimacy Signals**
```
1. "[Agency] political appointee vs career staff conflict"
2. "[Agency] mandate ambiguity OR conflicting legislation"
3. "[Agency] public trust survey OR polling"
4. "[Agency] media criticism OR editorial board"
5. "[Agency] industry capture OR revolving door"
```

---

## Protocol D: DAO / Web3 Organization

**On-chain data (highest credibility for DAOs):**
```
1. Check governance forum (Discourse/Commonwealth): proposal pass rates, voter turnout, debate quality
2. Check on-chain: treasury diversification, token concentration (Gini coefficient)
3. Check Dune Analytics dashboards for the protocol
4. Check Snapshot: voter participation trends over time
5. Check GitHub: contributor diversity, commit frequency, core team size
```

**Agent 1 — Governance Health**
```
1. "[DAO] governance attack OR hostile proposal"
2. "[DAO] voter apathy OR quorum failure"
3. "[DAO] multisig signers concentration"
4. "[DAO] core team vs community conflict"
5. "[DAO] token whale voting dominance"
```

**Agent 2 — Protocol & Treasury Signals**
```
1. "[Protocol] TVL decline OR exploit"
2. "[DAO] treasury runway months"
3. "[Protocol] fee revenue vs token incentive dependency"
4. "[DAO] contributor attrition OR grants program failure"
5. "[Protocol] competitive positioning vs forks"
```

---

## Protocol E: Platform Ecosystem

**Agent 1 — Ecosystem Health**
```
1. "[Platform] developer exodus OR API deprecation anger"
2. "[Platform] third-party app banned OR removed"
3. "[Platform] take rate increase OR policy change"
4. "[Platform] network effects weakening OR multi-homing"
5. "[Platform] complement vs substitute dynamic"
```

**Agent 2 — Supply & Demand Side**
```
1. "[Platform] seller OR creator complaints {current_year}"
2. "[Platform] buyer OR user trust issues"
3. "[Platform] liquidity crisis OR GMV decline"
4. "[Platform] quality degradation OR spam problem"
5. "[Platform] regulatory antitrust concern"
```

---

## Protocol F: Industry / Market

```
Agent 1 — Industry Structure:
1. "[Industry] consolidation OR fragmentation trend"
2. "[Industry] entry barriers increasing OR decreasing"
3. "[Industry] Porter five forces analysis {current_year}"
4. "[Industry] dominant design OR standards war"

Agent 2 — Disruption Signals:
1. "[Industry] startup disrupting OR incumbent threat"
2. "[Industry] technology substitution OR obsolescence"
3. "[Industry] regulatory shock OR deregulation"
4. "[Industry] commodity trap OR margin compression"
```

---

---

## Protocol G: Chinese-Language Source Supplement (双语协议)

> 当 `query_generator.py` 检测到中文语境相关性（CJK 字符或 China-related 关键词），自动追加此协议。

**中文一级信源（T1）：**
- `gov.cn` — 国务院、各部委官方公告
- `pbc.gov.cn` — 中国人民银行政策/利率
- `csrc.gov.cn` — 证监会处罚、问询函
- `wenshu.court.gov.cn` — 裁判文书网
- `cninfo.com.cn` — 巨潮资讯（上市公司公告）

**中文二级信源（T2）：**
- `caixin.com` — 财新，调查报道质量最高
- `thepaper.cn` — 澎湃新闻，时政深度
- `ftchinese.com` — FT 中文网，国际视角中文报道
- `yicai.com` — 第一财经，财经数据
- `cls.cn` — 财联社，快讯时效性强
- `jiemian.com` — 界面新闻
- CIIS / 中国社科院 / 清华大学国际关系研究院 — 中方智库

**中文三级信源（T3 — 仅作信号）：**
- `weibo.com` — 舆论走向、官方账号声明
- `zhihu.com` — 专业人士分析（需甄别）
- `maimai.cn` — 职场信号（内部人消息）
- `36kr.com` — 科技/创投报道
- 微信公众号 — 除非作者为已知专家

**中文信源采集规则：**
1. 新华社/人民日报的事实报道（日期、数字、官方决定）按 T1 处理；社论/评论按 T2 处理
2. 中文查询和英文查询的结果必须交叉比对：同一事件的中英报道差异本身就是有价值的矛盾信号
3. 涉及中国国内政策的分析，中文 T1 信源权重高于英文 T2（因英文媒体可能翻译/理解偏差）
4. 涉及国际关系/地缘政治的分析，英文和中文信源权重相当，矛盾之处必须显式标注

---

## Protocol H: Arabic-Language Source Supplement (阿拉伯语协议)

> 当 `detect_languages()` 检测到阿拉伯语相关性（阿拉伯文字符或中东关键词），自动追加此协议。

**阿拉伯语一级信源（T1）：**
- WAM (UAE), SPA (Saudi), KUNA (Kuwait) — 海湾国家官方通讯社
- GCC 秘书处公报
- 各国政府官方网站声明

**阿拉伯语二级信源（T2）：**
- `aljazeera.net` — 半岛电视台（卡塔尔视角，对沙特/阿联酋立场需注意偏差）
- `alarabiya.net` — 阿拉比亚（沙特视角）
- `asharqalawsat.com` — 中东报（泛阿拉伯，偏沙特）
- `independentarabia.com` — 独立阿拉伯
- Al-Ahram — 埃及官方倾向

**阿拉伯语三级信源（T3）：**
- Twitter/X 阿拉伯语账号（需识别官方 vs 民间）
- 阿拉伯语论坛/社区

**阿拉伯语信源特殊规则：**
1. 半岛电视台和阿拉比亚的叙事差异常反映海湾内部分歧，本身就是信号
2. 沙特官方媒体对 MBS 改革的报道需与独立信源交叉验证

---

## Protocol I: Persian-Language Source Supplement (波斯语协议)

> 当 `detect_languages()` 检测到波斯语相关性（伊朗相关关键词），自动追加此协议。

**波斯语一级信源（T1）：**
- `irna.ir` — IRNA 伊朗国家通讯社
- `leader.ir` — 最高领袖办公室（最高决策信号）
- `dolat.ir` — 总统府

**波斯语二级信源（T2）：**
- `isna.ir` — ISNA 伊朗学生通讯社（比 IRNA 稍独立）
- `farsnews.ir` — 法尔斯通讯社（IRGC 关联）
- `entekhab.ir` — 选择报
- Shargh Daily — 改革派倾向
- Bourse & Bazaar — 经济/制裁分析（英波双语）

**波斯语三级信源（T3）：**
- Twitter/X 波斯语（海外伊朗人视角，国内 VPN 用户）
- Telegram 频道（伊朗主要社交平台）
- Clubhouse 波斯语讨论

**波斯语信源特殊规则：**
1. IRNA/Fars News 代表强硬派视角，Shargh 代表改革派视角——两者叙事差异是政治分歧的直接信号
2. 伊朗海外媒体（如 BBC 波斯语、Iran International）立场与国内媒体显著不同，需标注来源位置

---

## Protocol J: Russian-Language Source Supplement (俄语协议)

> 当 `detect_languages()` 检测到俄语相关性（俄罗斯/乌克兰关键词），自动追加此协议。

**俄语一级信源（T1）：**
- `kremlin.ru` — 克里姆林宫
- `government.ru` — 俄联邦政府
- `duma.gov.ru` — 国家杜马
- `cbr.ru` — 俄罗斯央行

**俄语二级信源（T2）：**
- `kommersant.ru` — 生意人报（俄罗斯最可靠商业媒体）
- `rbc.ru` — RBC（商业/金融）
- `meduza.io` — Meduza（独立媒体，总部拉脱维亚，俄政府已列为"不受欢迎组织"）
- `novayagazeta.eu` — 新报欧洲版（独立调查）
- Carnegie Russia/Eurasia Center — 智库分析

**俄语三级信源（T3）：**
- Telegram 频道（俄罗斯主要信息流通平台）
- VK（俄罗斯社交平台）

**俄语信源特殊规则：**
1. 官方 vs 独立媒体的叙事鸿沟极大——克里姆林宫说法与 Meduza/Novaya Gazeta 的报道可能完全矛盾，这本身是关键信号
2. Kommersant 和 RBC 在经济/商业报道方面相对可靠，但政治话题受压

---

## Protocol K: Japanese-Language Source Supplement (日语协议)

> 当 `detect_languages()` 检测到日语相关性（日本关键词或日文字符），自动追加此协议。

**日语一级信源（T1）：**
- `kantei.go.jp` — 首相官邸
- `mof.go.jp` — 财务省
- `boj.or.jp` — 日本银行
- `mofa.go.jp` — 外务省

**日语二级信源（T2）：**
- `nikkei.com` — 日经新闻（日本最权威商业媒体）
- `asahi.com` — 朝日新闻（偏自由派）
- `nhk.or.jp` — NHK（公共广播，相对中立）
- `mainichi.jp` — 每日新闻
- `toyokeizai.net` — 东洋经济（深度商业分析）

**日语三级信源（T3）：**
- Twitter/X 日语
- 5ch/2ch（匿名论坛）
- Yahoo! Japan 评论

**日语信源特殊规则：**
1. 日经在经济/企业报道方面可靠度最高
2. 朝日与产经在政治议题上立场对立（自由派 vs 保守派），叙事差异是信号

---

## Protocol L: Korean-Language Source Supplement (韩语协议)

> 当 `detect_languages()` 检测到韩语相关性（韩国/朝鲜关键词或韩文字符），自动追加此协议。

**韩语一级信源（T1）：**
- `president.go.kr` — 总统府（龙山）
- `mofa.go.kr` — 外交部
- `bok.or.kr` — 韩国银行
- KIEP / KINU — 对外经济政策研究院 / 统一研究院

**韩语二级信源（T2）：**
- `chosun.com` — 朝鲜日报（保守派）
- `hani.co.kr` — 韩民族日报（进步派）
- `donga.com` — 东亚日报
- `mk.co.kr` — 每日经济新闻
- KBS / MBC — 公共广播

**韩语三级信源（T3）：**
- Naver 评论（韩国最大门户）
- DC Inside（韩国论坛/社区）

**韩语信源特殊规则：**
1. 朝鲜日报（保守）vs 韩民族（进步）的叙事差异直接反映韩国政治光谱
2. 涉及朝鲜问题：韩国媒体的准确性通常高于西方媒体，但可能带有统一/对抗政策偏向

---

## 跨语言通用规则

1. 同一事件的不同语言报道差异本身就是有价值的矛盾信号——必须在 Research Brief 中标注
2. 涉及国内政策：本国语言 T1 信源权重高于英文 T2（本地信源更接近决策现场）
3. 涉及国际关系：各语言信源权重相当，矛盾之处必须显式标注
4. 官方媒体的事实报道（日期、数字、官方决定）按 T1 处理；社论/评论降至 T2
5. 检测到多个本地语言时（如 Saudi-Iran → ar + fa），每种语言独立采集，分别标注信源

---

## Phase 2: Information Synthesis Protocol

After gathering raw data, before analysis:

1. **Contradiction detection**: Flag any sources that directly contradict each other — this itself is a signal
2. **Recency weighting**: Weight recent signals 3x more than signals >18 months old
3. **Source diversity check**: If all signals come from one source type (e.g., only press releases), flag as incomplete
4. **Gap inventory**: List what you couldn't find — absence of information is data
5. **Confidence calibration**:
   - High confidence: Multiple independent Tier 1-2 sources agree
   - Medium confidence: Single strong source OR multiple weak sources
   - Low confidence: Only Tier 3-4 sources OR contradictory signals
   - No data: Must flag explicitly, cannot analyze what you cannot observe

## Phase 3: Research Completeness Checklist

Before proceeding to diagnosis, confirm:
- [ ] Financial/resource flows can be characterized (even roughly)
- [ ] Key decision-makers identified
- [ ] At least one signal per dimension gathered
- [ ] Source diversity adequate (not all from same angle)
- [ ] Time range covered (recent + historical context)
- [ ] Contradictions flagged and noted

If fewer than 4 of these are met, ask user for additional context before proceeding.
