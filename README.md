# System Pathology

*[中文版 README](README.zh-CN.md)*

A **seven-dimensional** diagnostic framework for complex systems — corporations, governments, DAOs, markets, geopolitical entities, and platform ecosystems, plus **relational systems** where the system *is* the interaction itself (conflicts, rivalries, alliances) rather than any single entity. Built as a [Claude Code](https://claude.ai/claude-code) skill with an Orchestrator + parallel Researcher sub-agent architecture.

Think of it as a pathologist's toolkit for organizations: instead of examining cells under a microscope, it examines boundary topology, incentive architecture, information neurology, temporal metabolism, legitimacy narratives, coupling architecture, and power topology — then cross-references them to find the systemic pathologies that surface-level analysis misses. The same seven questions are reinterpreted for relational systems (see "Relational Systems" below) — health there means the interaction's *manageability*, not its friendliness.

> **On reliability (read this first).** This tool has an LLM analyze events that may post-date its training cutoff, using web-sourced evidence gathered by sub-agents. It can be wrong, and so can its own checkers. The system is built to **make its uncertainty visible, not to guarantee truth**: it tiers and verifies sources, records which process gates ran, calibrates its own past predictions, and independently re-derives load-bearing claims — then surfaces what remains thinly-attested for human judgment. Treat its output as a structured, self-audited analyst draft, not an oracle.

## What It Does

**Input**: A system name + type (e.g., "伊朗-美国-以色列冲突" / relational, "ByteDance" / public_company). Entity systems (companies, states, DAOs) and relational systems (conflicts, rivalries, alliances — where the *relationship itself* is the system) both supported; the seven dimensions are reinterpreted per type (see SKILL.md).

**Process**:
1. Auto-generates multi-perspective search queries (official, opposition, media, think tanks, regional, local-language)
2. Dispatches parallel Researcher sub-agents (model-tiered: `haiku` for English/recent-event batches, `sonnet` for non-Latin local-language and sensitive-topic batches)
3. Applies quality gates — freshness + **breaking-event sweep**, coverage, and **source verification that actually runs** (WebFetch spot-checks of high-stakes sources)
4. Conditionally triggers Round 2 deep research (contradiction resolution, data anchoring, gap filling)
5. Runs **seven-dimensional** diagnostic with calibrated scoring (1-5 per dimension, anchored to reference cases)
6. Mechanically checks the score vector against **danger/survival-zone signatures** (e.g., D5≤2 + D2≤2 = the Enron/Theranos legitimacy-incentive collapse) and computes **feedback loops, leverage points, and prescription spillovers** from a declared causal graph — the logical consequences of the analyst's judgments are derived by code, not bookkeeping
7. Independently re-derives load-bearing factual claims (fact-check sub-agent) to catch confident-but-wrong synthesis
8. Generates falsifiable predictions and tracks **time-valid** calibration across iterations

**Output**: Three files saved to Obsidian vault —

| File | Format | Content |
|------|--------|---------|
| `{date} {name} 研究素材.md` | Markdown | Raw sources, contradictions, coverage gaps |
| `{date} {name} 诊断报告.html` | HTML | Brookings/CSIS think-tank style long-form article with inline radar chart |
| `{date} {name} 系统诊断.md` | Markdown | Full report backup |

Plus a structured JSON persisted to `~/.system_pathology/data/` for longitudinal tracking.

## Architecture

```
User Request
  │
  ▼
Orchestrator (Claude Code main agent)
  ├─ generate_queries() + group_into_batches()     ← Python tools via Bash
  │
  ├─ ROUND 1: PARALLEL RESEARCHER DISPATCH (model-tiered: haiku / sonnet)
  │   ├─ Researcher A: Batch 0 (recent events scan, incl. past 24-48h)
  │   ├─ Researcher B: Batch 1 (structural perspectives)
  │   ├─ Researcher C: Batch 2 (local-language perspectives → sonnet)
  │   └─ ...
  │         ↓ Each returns structured JSON: sources + findings + contradictions
  │
  ├─ Quality Gates: Freshness + Breaking-event sweep / Coverage / Source Verification
  │
  ├─ [Conditional] ROUND 2: DEEP RESEARCH (max 5 Researchers)
  │   ├─ contradiction_resolution / data_anchor / gap_filler
  │
  ├─ [Conditional] PREDICTION VERIFICATION (time-valid: no early "confirmed")
  ├─ Research Brief → user confirmation
  ├─ Competing Hypotheses Analysis (ACH, full mode, tier-weighted scoring via ach_score)
  ├─ Seven-dimensional diagnosis (scored against calibration anchors)
  ├─ detect_danger_zones() — auto-check against catastrophic/survival signatures
  ├─ causal_graph: feedback loops + leverage ranking + prescription spillover simulation
  ├─ Claims ledger → triage thinly-attested → fact_check sub-agent re-derivation
  ├─ Generate 3-5 falsifiable predictions
  ├─ history_compare() + find_analogies() + calculate_prediction_accuracy(as_of_date)
  └─ validate_analysis() gate → save_analysis() → JSON + MD + HTML (+ source audit)
```

**Design principles:**
- Orchestrator orchestrates, never searches. Researchers search, never analyze.
- All Researchers in a round dispatch simultaneously (single message, parallel Agent calls), model-tiered to cost (haiku) vs. multilingual/sensitive capability (sonnet).
- Tools are pure-computation Python called via Bash — no LLM in the loop for query generation, scoring comparison, persistence, or validation.
- Round 2 is conditional and capped (max 5 Researchers, no Round 3).
- **Skips are made visible, not impossible**: a `validate_analysis()` gate hard-rejects malformed/out-of-range data before persistence; `process_warnings()` flags any gate that was skipped (ACH, Round 2, source verification, breaking-event sweep) — turning silent omissions into recorded decisions.
- Each analysis generates falsifiable predictions; the next analysis auto-verifies (time-valid) and computes Brier-score calibration.

## Seven Diagnostic Dimensions

| # | Dimension | Core Question | Example Pathologies |
|---|-----------|---------------|---------------------|
| D1 | **Boundary Topology** | Where are the hard walls and soft membranes? | Boundary erosion, Fortress syndrome, Parasite load |
| D2 | **Incentive Architecture** | Do rewards produce survival-compatible behavior? | Incentive inversion, Moral hazard cascade, Cobra effect, Nash trap |
| D3 | **Information Neurology** | Can the system perceive reality and act on it? | Fantasy world syndrome, Positive feedback death spiral, Ashby violation |
| D4 | **Temporal Metabolism** | Is it consuming its future to fund its present? | Temporal cannibalism, Evolutionary lock-in, Heat death trajectory |
| D5 | **Legitimacy & Narrative** | Does the system's story still work? | Narrative collapse, Legitimacy debt, Cargo cult performance |
| D6 | **Coupling Architecture** | Connected too tightly, too loosely, or in the wrong places? | Tight coupling catastrophe, Dependency trap, Cascade architecture |
| D7 | **Power Topology** | Who decides what; how is power distributed and transferred? | Shadow power structure, Veto trap, Power vacuum, Winner-take-all cascade |

> D7 (Power Topology) was added after the original six-dimensional design. The framework remains backward-compatible: legacy six-dimension analyses and tools that accept 6- or 7-dimension score vectors both work.

Cross-dimensional interactions are where the most dangerous pathologies hide:

| Pattern | Dimensions | Mechanism |
|---------|-----------|-----------|
| Trust death spiral | D1×D2×D5 | Boundary erosion → incentive gaming → narrative collapse → further erosion |
| Innovation theater trap | D4×D5×D2 | Renewal theater → maintained legitimacy → no pressure to fix incentives |
| Information-incentive doom loop | D3×D2 | Bad incentives → filtered information → worse decisions → worse incentives |
| Power-information doom loop | D7×D3 | Power concentration → information filtering → worse decisions → more concentration |
| Succession-temporal squeeze | D7×D4 | Uncertain succession → shortened time horizons → no long-term investment |

These interactions, plus the two Meadows-style outputs analysts actually need (which loops close, and which dimension is the highest-leverage intervention point), are computed by `agent/tools/causal_graph.py` from a declared set of causal edges — not read off a static table. See "Analytical Engines" below.

## Relational Systems

Most of the framework's system types are **entities** — a company, a state, a DAO — that persist independent of any specific counterpart. `relational` is different: the object of analysis is the **interaction itself** (a conflict, a rivalry, a deterrence standoff, an alliance), and it stops existing the moment any party is removed. Iran–Israel, US–China strategic competition, India–Pakistan, and the pre-1914 alliance system are relational systems; ByteDance is not (swap out its competitors and it's still ByteDance).

The seven dimensions carry over, reinterpreted:

| Dim | Entity-system question | Relational-system question |
|-----|------------------------|------------------------------|
| D1 | Hard walls / soft membranes | **Red lines & rules of engagement** — are they clear, respected, institutionalizing or eroding? |
| D2 | Do rewards match survival needs? | **Payoff structure of restraint** — does escalating or holding back pay off? Is there a first-mover incentive? |
| D3 | Can the system perceive reality? | **Signal fidelity & misperception risk** — do crisis channels exist and get used? How often is a strike misread as an attack, or restraint as weakness? |
| D4 | Consuming the future to fund the present? | **Escalation ratchet & sustainability** — does each round raise the baseline of "normal" violence? Are there de-escalation off-ramps? |
| D5 | Does the system's story hold? | **Coexistence narrative** — does each side still tell a story in which the other legitimately exists? |
| D6 | Coupling too tight, too loose, misplaced? | **Entanglement & contagion channels** — do proxy networks and alliance obligations turn local sparks into systemic fires? |
| D7 | Who decides, how does power transfer? | **Polarity & veto structure** — is the balance symmetric or shifting (Thucydides zone)? Who can veto an escalation? |

Relational-specific pathologies: **escalation ratchet** (each round resets the "normal" baseline higher), **signal inversion** (restraint read as weakness, deterrence read as provocation — Able Archer 1983, July 1914), **rigid entanglement** (alliance/proxy chains that no single actor can unilaterally de-escalate), **first-mover incentive** (mobilization or strike-first structures that punish restraint), **coexistence narrative collapse** (neither side can sell compromise domestically once the other's legitimacy is fully denied).

Research collection for `relational` is organized around interaction mechanics rather than single-entity health — escalation events, de-escalation/diplomatic channels, each party's official red lines, military balance, third-party mediators, and proxy linkages — with escalation and de-escalation perspectives **dispatched in the same Researcher batch** by design, so no single sub-agent sees only one side of the picture.

## Historical Analogy Matching

After scoring, the current system's seven-dimensional vector is matched against **51 historical reference cases** (`references/analogy-cases.json`) spanning 7 system types — including a `relational` track: the July Crisis of 1914, the Cuban Missile Crisis, US–USSR détente, Egypt–Israel's cold peace, India–Pakistan, the 2018–2020 US–China trade war, the Iran–Israel shadow war, and the eve of the 2022 Russia–Ukraine war.

Matching uses a **magnitude-aware Euclidean distance**, not cosine similarity — cosine only compares direction, so an all-low crisis vector and an all-high healthy system can score as "identical" (they're proportionally similar even though one is failing and one is thriving). Same-system-type matches get a small additive tiebreaker (+0.08, clamped to 1.0) rather than a multiplicative boost, so a loose same-type match never beats a tight cross-type one. Results surface `similarity`, `outcome`, and `key_lesson` — analogies are heuristic context, not predictions: "structurally similar to X" doesn't mean "will follow X's trajectory."

## Analytical Engines

Three pure-computation tools turn the analyst's declared judgments into their logical consequences, rather than leaving that arithmetic to be redone by hand each time:

| Engine | Input (analyst judgment) | Output (computed consequence) |
|--------|---------------------------|-------------------------------|
| `causal_graph.py` | A set of causal edges between dimensions (`{from, to, sign, strength}`) | All closed feedback loops, classified vicious/virtuous/antagonistic; Meadows-style leverage-point ranking; propagated spillover of any prescription across the whole graph; cross-prescription conflict detection |
| `ach_score.py` | A 2–4 hypothesis set + a C/I/N evidence matrix with source tiers | Tier-weighted, diagnosticity-aware hypothesis ranking and status (`eliminated` / `stressed` / `active` / `untestable`) — a single Tier-1 inconsistency outweighs ten Tier-3 consistencies, and evidence that rates every hypothesis identically is down-weighted as non-diagnostic |
| `history_compare.detect_danger_zones()` | The seven-dimensional score vector | Automatic check against 6 catastrophic and 4 survival dimensional signatures (e.g., D5≤2 + D2≤2 = the Enron/Theranos/FTX legitimacy-incentive collapse; D4≥4 + D6≥4 = an anti-fragile core) |

The analyst still decides *what edges exist*, *what the evidence shows*, and *what the scores are* — these tools only make sure the downstream math (closure, ranking, propagation, signature matching) is derived rather than eyeballed.

## Source Tier System

All evidence is classified by credibility:

| Tier | Type |
|------|------|
| **T1** | Government documents, court records, financial filings, on-chain data |
| **T2** | Reuters, FT, WSJ, BBC, academic papers, think tank reports |
| **T3** | Glassdoor, Reddit, Twitter/X, anonymous sources |
| **⚠️** | Training knowledge (background only, never scores evidence) |

**Multi-language support** (6 languages): Chinese (zh), Arabic (ar), Persian (fa), Russian (ru), Japanese (ja), Korean (ko). Language detection is automatic — "Saudi-Iran proxy war" triggers both `ar` and `fa` queries simultaneously. Each language has its own T1/T2/T3 source hierarchy (e.g., Chinese: gov.cn/Caixin/Weibo; Arabic: WAM-SPA/Al Jazeera/Twitter-ar).

## Prediction & Calibration System

Each analysis generates 3-5 **falsifiable predictions** with:
- Concrete falsification conditions ("if X is observed, this prediction fails")
- Absolute time horizons (e.g., `2027-03-31`)
- Numerical confidence (0.0-1.0)
- Linked diagnostic dimension (D1-D7)

On repeat analysis of the same system, prior predictions are automatically loaded, verified against current evidence, and scored:
- **Time-valid resolution**: a "X holds through date D" prediction *cannot* be marked `confirmed` before D (it can still break) — only `falsified` early or `on_track`. `calculate_prediction_accuracy(as_of_date=...)` auto-downgrades any premature "confirmed" to `on_track` and excludes it from scoring, so the system can't manufacture a fake "100% hit rate" from unresolved predictions.
- **Brier score** (confidence-weighted, computed only when ≥3 predictions have genuinely resolved)
- **High-confidence misses** (confidence ≥0.7 but falsified — flagged as warnings)
- Results rendered in both the Research Brief and the final HTML report

## Reliability & Verification Gates

Because the analysis runs on LLM-gathered, possibly post-cutoff evidence, the system layers defenses that make uncertainty **visible and auditable**. Each is enforced or surfaced by code (`agent/store/db.py`), not left to memory:

| Gate | What it does | What it catches | What it does **not** catch |
|------|--------------|-----------------|----------------------------|
| **Schema validation** (`validate_analysis`) | Hard-rejects malformed analysis before persistence | Out-of-range scores, non-canonical dimension keys, malformed predictions, evidence missing URLs | Wrong-but-well-formed values |
| **Process warnings** (`process_warnings`) | Non-blocking flags for skipped gates | ACH/Round-2/source-verification/breaking-event sweep skipped; stale latest-source; uncorroborated load-bearing claims | (Relies on honestly-recorded `process_metadata`) |
| **Source verification** (`--verify-plan` → WebFetch) | Spot-checks high-stakes sources (T1/T2 + quantitative) for reachability and title/number match | Dead/fabricated URLs, mismatched specific numbers | Plausible-but-wrong synthesis on a *real* source |
| **Claims fact-check** (`--triage-claims` → `fact_check` sub-agent) | Independently re-derives load-bearing thinly-attested claims from fresh search | Confident misattribution single/thinly-sourced (e.g. wrong office-holder) | Wrong synthesis that happens to be *well*-attested |
| **Time-valid calibration** | Forbids confirming a prediction before its horizon | Fake "100% hit rate" from unresolved predictions | — |

**The honest residual.** These gates are triage + spot-check + independent re-derivation, **not** a truth guarantee. A confident-wrong claim that is well-attested (≥2 plausible sources) can still pass; the fact-check sub-agent is itself a fallible LLM. This is the irreducible floor of having an LLM analyze post-cutoff events. The design goal is **surfacing what is thin or contradicted for human judgment**, not certifying correctness — verification-completeness is a human endpoint, not another gate.

## Directory Structure

```
system-xray/
├── SKILL.md                              # Skill metadata + full diagnostic protocol
├── agent/
│   ├── agent.py                          # CLI: query preview, history, persistence, validation, audit, verify-plan, triage-claims
│   ├── prompts/
│   │   ├── system.md                     # Orchestrator prompt (full pipeline + quality gates)
│   │   ├── researcher-base.md            # Researcher universal core (workflow + EN tiers + schema + neutral framing)
│   │   ├── researcher-sources.md         # Per-language source tier tables (paste relevant only)
│   │   └── researcher-modes.md           # Round 2 + verification modes: gap_filler / contradiction_resolution / data_anchor / prediction_verification / fact_check
│   ├── store/
│   │   ├── db.py                         # Persistence + validate_analysis + process_warnings + source-audit/verification + claims triage + radar SVG
│   │   └── __init__.py
│   ├── tools/
│   │   ├── query_generator.py            # Multi-perspective query generation + language detection
│   │   ├── history_compare.py            # Scoring delta + magnitude-aware analogies + time-valid Brier calibration + danger-zone signatures
│   │   ├── causal_graph.py               # Feedback loop detection + leverage ranking + intervention propagation + prescription cross-check
│   │   ├── ach_score.py                  # Tier-weighted ACH hypothesis scoring (diagnosticity-aware)
│   │   └── __init__.py
│   └── __init__.py
├── references/
│   ├── scoring-calibration.md            # Anchor cases (Berkshire=5, Enron=1) per dimension per system type, incl. relational
│   ├── research-protocol.md              # Structured search queries by system type
│   ├── question-banks.md                 # Interview questions for insider-access users
│   ├── analogy-cases.json                # 51 historical reference cases across 7 system types
│   └── diagnostic-schema.json            # Machine-readable JSON schema for structured output
└── tests/                                # 104 tests covering validation, tools, and the three analytical engines
```

## Installation

This is a Claude Code skill — it runs inside Claude Code's agent infrastructure, not as a standalone application.

### Prerequisites

- [Claude Code](https://claude.ai/claude-code) (CLI, desktop app, or IDE extension)
- Python 3.10+ (for the computation tools)
- An Obsidian vault at the configured path (for report output)

### Setup

1. Clone this repo into your Claude Code skills directory:

```bash
git clone https://github.com/Eleven1111/system-xray.git ~/.claude/skills/system-xray
```

2. The skill auto-registers via `SKILL.md` frontmatter. No `pip install` needed — all Python tools use only the standard library.

3. (Optional) Adjust the Obsidian vault path in `agent/store/db.py` if yours differs from the default:

```python
OBSIDIAN_DIR = Path('/your/obsidian/vault/System Pathology')
```

## Usage

Inside Claude Code, just describe the system you want diagnosed:

```
> Diagnose the US-China relationship as a geopolitical system
> What's wrong with ByteDance's organizational structure?
> Run a full check-up on the DeFi ecosystem
```

The skill triggers automatically on system-analysis requests. You can also specify mode:

```
> 精简模式分析伊朗政权
> Compare Tesla and BYD as systems
```

### CLI Reference

The Orchestrator drives these Python helpers via Bash. Persistence/verification commands read their payload from a file or stdin (`--input`), so multi-KB reports with Chinese quotes/HTML never hit shell-escaping issues.

```bash
cd ~/.claude/skills/system-xray

# Query preview & history
python3 -m agent.agent --system "ByteDance" --type public_company --queries-only
python3 -m agent.agent --system "ByteDance" --history
python3 -m agent.agent --list-types
python3 -m agent.agent --system "Iran" --load-predictions   # prior predictions (for calibration)
python3 -m agent.agent --system "Iran" --load-latest        # prior full record

# Validation & persistence (payload via --input file or stdin)
python3 -m agent.agent --validate --input analysis.json                          # schema check + process warnings, no write
python3 -m agent.agent -s "X" -t public_company --save-analysis --input a.json    # validate-then-persist JSON
python3 -m agent.agent -s "X" -t public_company --save-materials --input brief.json
python3 -m agent.agent -s "X" -t public_company --save-html --title "…" --input body.html
python3 -m agent.agent -s "X" -t public_company --save-md --input report.md

# Report building blocks
python3 -m agent.agent --radar --input scores.json                  # seven-dim radar SVG
python3 -m agent.agent --build-audit --input brief.json             # itemized source audit (+ verification badges)

# Analytical engines (pure computation — the logical consequences of declared judgments)
python3 -m agent.agent --danger-zones --input scores.json           # auto-check catastrophic/survival signatures
python3 -m agent.agent --causal --input graph.json                  # feedback loops + leverage + prescription spillover
python3 -m agent.agent --ach-score --input ach.json                 # tier-weighted competing-hypothesis ranking

# Reliability gates
python3 -m agent.agent --verify-plan --input brief.json --sample 4  # pick sources to WebFetch-verify
python3 -m agent.agent --triage-claims --input analysis.json        # pick load-bearing thin claims for fact_check
```

### Supported System Types

| Type | Description |
|------|-------------|
| `geopolitical` | Nation-states, trade blocs, international institutions |
| `government_agency` | Agencies, ministries, regulatory bodies |
| `public_company` | Listed companies |
| `private_company` | Private enterprises, startups |
| `dao` | DAOs, open-source communities, cooperatives |
| `market` | Industry verticals, supply chains |
| `platform` | Platform ecosystems |
| `relational` | Multi-actor interaction systems — the system *is* the relationship, not any single entity: conflict constellations (Iran–US–Israel), strategic rivalries (US–China), alliances, deterrence standoffs. Health = manageability of the interaction, not friendliness |

## Output Style

Reports use **Brookings/CSIS think-tank long-form article style** — narrative prose as the spine, not dashboards or bullet-point decks.

- **Narrative paragraphs** as the primary vehicle (2-4 paragraphs per dimension)
- **Inline citations** woven into prose ("Reuters reported in May that...")
- **Score badges** as inline accents, not standalone tables
- **Tables/callouts** only when structured data genuinely requires them
- **Editorial titles** with metaphor/judgment as main title, specific object as subtitle
- **Collapsible source audit** at the end (never omitted, even in brief mode)

**Full mode chapter sequence:**
Prior Prediction Review (if applicable) → Executive Summary → System Cartography → Competing Hypotheses (ACH) → Seven-Dimensional Diagnosis → Cross-Dimensional Analysis → Historical Analogies → Critical Risk Nodes → Evolution Scenarios & Prescriptions → Falsifiable Predictions → Monitoring Dashboard → Source Audit

## Extending

### Adding a new language

Three steps in `agent/tools/query_generator.py`:

1. Add entry to `LANGUAGE_REGISTRY` (Unicode pattern, topic keywords, source tiers, P0 query templates)
2. Add entry to `LOCAL_PERSPECTIVES` (per-system-type structural perspectives)
3. Add entry to `PERSPECTIVE_LABELS` (Chinese labels for each perspective key)

Then add a source tier section in `agent/prompts/researcher-sources.md`.

### Adding a new system type

Add perspective matrix in `query_generator.py`'s `PERSPECTIVE_MATRIX` dict following the existing pattern: `(perspective_key, tier, priority, query_template)`.

## Theoretical Foundations

The framework synthesizes:

- **Transaction Cost Economics** (Coase, Williamson) — boundary decisions, organizational scope
- **Viable System Model** (Beer) — recursive subsystem structure, autonomy-vs-control
- **Dissipative Structures** (Prigogine) — order from chaos, negentropy import, renewal
- **Finite & Infinite Games** (Carse) — strategy orientation, leadership philosophy
- **Mechanism Design** (Hurwicz, Myerson) — incentive compatibility, game structure
- **Antifragility** (Taleb) — stress response classification
- **Normal Accidents** (Perrow) — coupling architecture, cascade risk
- **Governing the Commons** (Ostrom) — self-governance, shared resource management
- **Leverage Points** (Meadows) — where to intervene in complex systems
- **Crisis Stability & Deterrence Theory** (Schelling, Jervis) — signaling, escalation dynamics, and misperception in relational systems
- **Analysis of Competing Hypotheses** (Heuer) — structured hypothesis testing against an evidence matrix, tier-weighted

## License

MIT
