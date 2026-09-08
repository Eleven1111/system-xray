# 固定材料快照 · PILOT-RF

**对象：** Rust Foundation（基金会治理 + crates.io 可持续性）
**采集时刻：** 2026-09-08
**采集方式：** 4 次 WebSearch（预登记上限 6 次）
**信息截止：** 2026-09-08。此后发生的事一律不得进入本案分析。

> 三条路径读**同一份**材料。这是"固定材料轮"的定义：测的是推理，不是检索。

---

## M1 · 治理结构与人事

- 董事会由 Member Directors（会员机构代表）与 Project Directors（Rust Project 代表）组成，
  **两类投票权相等**。Project Director 承担法律责任与部分法律责任风险，须为 Rust Project 在册成员。
- 董事会定方向，含聘任与监督 Executive Director；ED 负责日常运营。
- Rebecca Rumbul 任 Executive Director & CEO。Nell Shamrell-Harrington 同时是董事会主席
  与 Microsoft（白金会员）的 Member Director，本职为 Microsoft Principal Software Engineer。
- 其他董事包括 Google 的 Jeffrey Vander Stoep、布加勒斯特理工的 Alexandru Radovici。
- 近期职务变动：AWS 代表 Seth Markle 当选 Treasurer；Project Director David Wood 当选 Secretary；
  此前 Project Director Ryan Levick 当选 Vice Chair。
- 来源：rustfoundation.org/about/，Inside Rust 各期 Project Director Update。

## M2 · Rust Project 侧治理（Leadership Council）

- Leadership Council 由 RFC 3392 确立，2023-06-20 合并，终结 Core Team 与临时 Leadership Chat。
- 成立动因是**结构性 burnout**：旧 Core Team 既要识别与排序团队职权外的工作、又要亲自做，
  不可扩展。JT Turner："no way we can wear this many hats and do this many things."
- 新设计：Council 只识别与排序，**主要靠委派**而非亲自执行（Josh Triplett 描述为代表制结构，
  九个顶级团队各派代表）。日常职责（编译器维护、语言与库演进、基础设施）仍在九个顶级团队。
- 防 burnout 写进规则：代表可连任但**软上限三届**，鼓励轮换以扩散经验。
- 防俘获条款：**同一公司或法律实体最多两人**同时在 Council，遴选时权衡 affiliation。
- 轮换在运行中：2026-03-20 确认截止、3-27 起参会；下一轮 2026-09-23 确认、9-25 起参会。
- RFC 单独点名 moderation 是高 burnout 活动，允许 moderator 随时退出，由 moderation team 补位。
  此条可追溯到 2021-11 moderation team 集体辞职事件。
- 来源：rust-lang.github.io/rfcs/3392-leadership-council.html，Inside Rust 代表遴选公告，
  The New Stack 报道。

## M3 · 财务与会员结构

- 2025 年募得 **$5.1M**，其中 **$2.7M** 直接投入 Rust Project 与社区支持；
  含 **$2.0M** 用于全职维护工作的总成本/工具/开支，另有基础设施、资助与生态活动经费。
  其余覆盖治理、安全、财务与运营系统（非工程岗薪酬、审计等）。
- 会员五档：Platinum / Gold / Silver / Associate / Individual。
  Platinum 附带**董事会专属席位**。Associate 面向非营利与教育机构，**免费**，不贡献会费收入。
- 2025-09-03 RustConf：Arm 由 Silver 升级为 **Platinum**，报道特意点出
  "此时部分组织正在收缩开源投入"。
- 其他白金会员包括 AWS（创始白金，另有对 Security Initiative 的现金与实物捐赠）、Google（创始白金）。
- 搜索结果未给出分档收入拆分；完整年报在基金会 publications 页。
- 来源：rustfoundation.org/2025/，rustfoundation.org/media/annual-report-strategy-2025/，
  Arm 白金会员公告。

## M4 · crates.io 成本与可持续性

- crates.io 经 CloudFront 的请求**消耗 AWS 捐赠额度快于预期**（2025-12 董事会），
  基金会在找短期与长期办法；同次会议批准 2026 年预算。
- crates.io 已增加更多分析埋点以识别流量异常——与控制带宽驱动的成本直接相关。
- 2025 年下半年起进入议程：基金会签署 Joint Statement on Sustainable Stewardship
  （对应 2025-09 的 OpenSSF 声明），开启关于如何可持续资助关键开源基础设施的社区讨论。
- 2026-03-10 董事会：讨论基金会员工提出的 crates.io 运营可持续化**早期想法**。
- 同次会议：Futurewei 的 Sid Askary 提出在基金会内设立 AI 研究倡议，董事会将在其成熟后再议；
  Symposium 项目申请加入 RIL 获通过；批准启动面向培训机构的**认证项目**（优先于个人培训课程）。
- 相关资金流：crates.io 新的 security advisories tab 由 OpenSSF 出资、Dirkjan Ochtman 实现。
- Maintainers Fund 在成熟：由 Leadership Council 设立的 funding team 管理，
  依 RFC #3931 先做 Maintainer in Residence（MiR）项目；费率参考调查数据与 Zig 等基金会做法，
  定为**按月固定**而非按小时。
- 来源：Inside Rust 2026-05-04 / 2026-02-09 Project Director Update，
  2026-01-21 crates.io development update，2026-08-04 funding team progress update，
  The Register 2025-11-05。

## M5 · 检索中的一条否定性发现

- 针对"2026 年治理危机/公开冲突"的检索**没有找到**相应报道。
  2026 年的材料显示的是结构在按设计常规运转（按期轮换、防 burnout 规则生效）。
  "危机"叙事属于 2021–2023 那一段，不属于 2026。
- 这条否定性发现与正面材料同等重要：它约束了"当前处于治理危机"这类假说。
