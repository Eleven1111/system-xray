# 固定材料快照 · R-01

**对象：** Rust-for-Linux 与 Linux 内核维护者的**互动格局**（关系系统）
**采集时刻：** 2026-09-09 ｜ **as_of：** 2026-09-09
**采集方式：** 2 次 WebSearch ｜ **信息截止：** 2026-09-09，此后发生的事不得进入分析

> 注意分析对象：**不是 Rust 语言，也不是 Linux 内核**，而是两个社区的互动关系本身。
> 换掉任何一方这个系统就不存在。三条路径读同一份材料，**禁止再检索**。

---

## M1 · 2025 年的政策争议（张力最集中的一段）

- 争议围绕 Rust-for-Linux 负责人 Miguel Ojeda 发布的一份**政策文档**展开。
  文档强调子系统可以出于"带宽原因"选择不采用 Rust。
- 资深内核开发者 **Christoph Hellwig 立即质疑其效力**：认为一个网页没有用，
  要生效必须进入内核树并获得广泛同意，并指该文档存在事实性错误。
- Hellwig 的核心反对：文档"没有任何子系统被强迫"的说法与 Torvalds 的**私下立场**冲突。
  他写道该说法"被 Linus 证明是错的"，并称这种表述方式不诚实；
  还抱怨 Linus"在公开场合躲在'实验'这个说法后面"，私下却另作决定。
- 他的结构性担忧是 **binding creep**：最终每个非叶子子系统都会被波及。
  他把 Rust wrapper 比作在子系统间扩散、造成碎片化的"癌性肿瘤"。

## M2 · Torvalds 的立场与一处关键的框架分歧

- Torvalds 的立场：**没有维护者被强迫**学习或使用 Rust，可以继续只写 C；
  但选择不参与的维护者，**同时放弃**对影响其子系统的 binding 与集成如何开发的影响力。
- **框架分歧**：Hellwig 认为 DMA 被迫接受 Rust；
  Linus 与 R4L 开发者则认为 DMA 的 Rust binding 只是 DMA 的又一个**使用者**，
  不属于 DMA 子系统本身。同一事实，两种归类，冲突由此产生。

## M3 · 2025 年底的结局

- Miguel Ojeda 于 2025-12 提交补丁 "rust: conclude the Rust experiment"：
  Rust 支持在 v6.1 合入以判断该语言在技术、流程与**社会**层面是否值得，
  2025 年 Linux Kernel Maintainers Summit（东京）认定实验结束。
- LWN 报道：与会开发者共识是内核中的 Rust 不再是实验性的，已成为内核的核心组成部分。
- Ojeda 同时**告诫**：这不代表在每种内核配置、架构或工具链下都能工作，
  内核、上游 Rust、GCC 等仍有大量工作。
- Torvalds 明确：Rust 是**增补而非替代**；新驱动与新子系统可用 Rust，
  既有 C 代码不会被整体重写。乐观估计到 2030 年 Rust 也不到内核代码的 5%，
  现实是数十年共存。

## M4 · 子系统层面的采纳信号

- 峰会上 DRM（图形栈）维护者 Dave Airlie 说 DRM 大约**再有一年**就会要求新驱动用 Rust、
  不再接受 C。
- Greg Kroah-Hartman 在讨论中说 Rust 驱动被证明比 C 驱动更安全，
  且 Rust/C 交互的问题比预期少。2026-07-15 他在孟买 Open Source Summit India 重申
  Rust 是永久组成部分，某些子系统很快将只接受 Rust 新代码，同时强调既有 C 代码保持不变。
- 官方政策页持续强调**子系统自治**：如何处理 Rust 由各子系统自行决定，
  目标是让维护者逐步参与，不同子系统采取了不同做法。
- Rust 代码实际所在：驱动是既定入口；Apple silicon 驱动有 Rust 贡献，
  Google 贡献了 Android 专用驱动，Nova（Rust 的 NVIDIA GPU 驱动）在开发中；
  `rust/` 目录存放核心基础设施；NVMe 子系统有 Rust 贡献；GPIO 抽象已进主线。

## M5 · 材料自带的可靠性警示（原样保留）

- 检索结果中关于"Linux 7.0 于 2026-04-12 发布并正式移除 experimental 标签、
  Rust NVMe 与高速网络驱动进入主线稳定树"的说法，**检索工具自己标注了警告**：
  "Treat these specific release claims with caution — they come from a secondary blog,
  not kernel sources."（这些具体发布声明来自二手博客而非内核源，需谨慎对待。）
- 另有下游动向的零散说法：Debian 称 APT 自 2026-05 起有"hard Rust requirements"；
  Android 16 在 6.12 内核上使用 Rust 内存分配器；Ubuntu 25.10 默认使用 Rust coreutils。
  这些同样来自二手来源。

## M6 · 一条否定性发现

- 检索**没有**找到 2026 年 Maintainers Summit 的结果。
  永久化决定来自 **2025** 年的峰会。把它写成"2026 年峰会决定"是错的。
- 也没有找到 2026 年内该关系出现新一轮公开冲突的报道。
