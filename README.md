# System Pathology

A six-dimensional diagnostic framework for complex systems — corporations, governments, DAOs, markets, geopolitical entities, and platform ecosystems. Built as a [Claude Code](https://claude.ai/claude-code) skill with an Orchestrator + parallel Researcher sub-agent architecture.

Think of it as a pathologist's toolkit for organizations: instead of examining cells under a microscope, it examines boundary topology, incentive architecture, information neurology, temporal metabolism, legitimacy narratives, and coupling architecture — then cross-references them to find the systemic pathologies that surface-level analysis misses.

## What It Does

**Input**: A system name + type (e.g., "中美关系" / geopolitical, "ByteDance" / public_company)

**Process**:
1. Auto-generates multi-perspective search queries (official, opposition, media, think tanks, regional, local-language)
2. Dispatches parallel Researcher sub-agents for web-sourced evidence collection
3. Applies three quality gates (freshness, coverage, source verification)
4. Conditionally triggers Round 2 deep research (contradiction resolution, data anchoring, gap filling)
5. Runs six-dimensional diagnostic with calibrated scoring (1-5 per dimension)
6. Generates falsifiable predictions and tracks calibration across iterations

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
  ├─ ROUND 1: PARALLEL RESEARCHER DISPATCH
  │   ├─ Researcher A: Batch 0 (recent events scan)
  │   ├─ Researcher B: Batch 1 (structural perspectives)
  │   ├─ Researcher C: Batch 2 (local-language perspectives)
  │   └─ ...
  │         ↓ Each returns structured JSON: sources + findings + contradictions
  │
  ├─ Three Quality Gates (Freshness / Coverage / Source Verification)
  │
  ├─ [Conditional] ROUND 2: DEEP RESEARCH (max 5 Researchers)
  │   ├─ contradiction_resolution: independent third-party verification
  │   ├─ data_anchor: trace quantitative claims to primary sources
  │   └─ gap_filler: variant queries for missing perspectives
  │
  ├─ [Conditional] PREDICTION VERIFICATION
  │   └─ Verify prior predictions against current evidence
  │
  ├─ Research Brief → user confirmation
  ├─ Six-dimensional diagnosis (scored against calibration anchors)
  ├─ Generate 3-5 falsifiable predictions
  ├─ history_compare() + calculate_prediction_accuracy()
  └─ save_analysis() → JSON + MD + HTML
```

**Design principles:**
- Orchestrator orchestrates, never searches. Researchers search, never analyze.
- All Researchers in a round dispatch simultaneously (single message, parallel Agent calls).
- Tools are pure-computation Python called via Bash — no LLM in the loop for query generation, scoring comparison, or persistence.
- Round 2 is conditional and capped (max 5 Researchers, no Round 3).
- Each analysis generates falsifiable predictions; the next analysis auto-verifies and computes Brier-score calibration.

## Six Diagnostic Dimensions

| # | Dimension | Core Question | Example Pathologies |
|---|-----------|---------------|---------------------|
| D1 | **Boundary Topology** | Where are the hard walls and soft membranes? | Boundary erosion, Fortress syndrome, Parasite load |
| D2 | **Incentive Architecture** | Do rewards produce survival-compatible behavior? | Incentive inversion, Moral hazard cascade, Cobra effect, Nash trap |
| D3 | **Information Neurology** | Can the system perceive reality and act on it? | Fantasy world syndrome, Positive feedback death spiral, Ashby violation |
| D4 | **Temporal Metabolism** | Is it consuming its future to fund its present? | Temporal cannibalism, Evolutionary lock-in, Heat death trajectory |
| D5 | **Legitimacy & Narrative** | Does the system's story still work? | Narrative collapse, Legitimacy debt, Cargo cult performance |
| D6 | **Coupling Architecture** | Connected too tightly, too loosely, or in the wrong places? | Tight coupling catastrophe, Dependency trap, Cascade architecture |

Cross-dimensional interactions are where the most dangerous pathologies hide:

| Pattern | Dimensions | Mechanism |
|---------|-----------|-----------|
| Trust death spiral | D1×D2×D5 | Boundary erosion → incentive gaming → narrative collapse → further erosion |
| Innovation theater trap | D4×D5×D2 | Renewal theater → maintained legitimacy → no pressure to fix incentives |
| Information-incentive doom loop | D3×D2 | Bad incentives → filtered information → worse decisions → worse incentives |

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
- Linked diagnostic dimension (D1-D6)

On repeat analysis of the same system, prior predictions are automatically loaded, verified against current evidence, and scored:
- **Brier score** (confidence-weighted, computed when ≥3 predictions resolved)
- **High-confidence misses** (confidence ≥0.7 but falsified — flagged as warnings)
- Results rendered in both the Research Brief and the final HTML report

## Directory Structure

```
system-xray/
├── SKILL.md                              # Skill metadata + full diagnostic protocol
├── agent/
│   ├── agent.py                          # CLI entry point (query preview, history)
│   ├── prompts/
│   │   ├── system.md                     # Orchestrator prompt (8-step pipeline)
│   │   ├── researcher-base.md            # Researcher universal core (workflow + EN tiers + schema)
│   │   ├── researcher-sources.md         # Per-language source tier tables (paste relevant only)
│   │   └── researcher-modes.md           # 4 Round 2 modes (paste relevant only)
│   ├── store/
│   │   ├── db.py                         # Persistence: JSON, MD, HTML, radar SVG, predictions
│   │   └── __init__.py
│   ├── tools/
│   │   ├── query_generator.py            # Multi-perspective query generation + language detection
│   │   ├── history_compare.py            # Cross-iteration scoring delta + Brier calibration
│   │   └── __init__.py
│   └── __init__.py
└── references/
    ├── scoring-calibration.md            # Anchor cases (Berkshire=5, Enron=1) to prevent score drift
    ├── research-protocol.md              # Structured search queries by system type
    ├── question-banks.md                 # Interview questions for insider-access users
    └── diagnostic-schema.json            # Machine-readable JSON schema for structured output
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

### CLI Preview (for query debugging)

```bash
cd ~/.claude/skills/system-xray
python3 -m agent.agent --system "ByteDance" --type public_company --queries-only
python3 -m agent.agent --system "ByteDance" --history
python3 -m agent.agent --list-types
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

## Output Style

Reports use **Brookings/CSIS think-tank long-form article style** — narrative prose as the spine, not dashboards or bullet-point decks.

- **Narrative paragraphs** as the primary vehicle (2-4 paragraphs per dimension)
- **Inline citations** woven into prose ("Reuters reported in May that...")
- **Score badges** as inline accents, not standalone tables
- **Tables/callouts** only when structured data genuinely requires them
- **Editorial titles** with metaphor/judgment as main title, specific object as subtitle
- **Collapsible source audit** at the end (never omitted, even in brief mode)

**Full mode chapter sequence:**
Prior Prediction Review (if applicable) → Executive Summary → System Cartography → Six-Dimensional Diagnosis → Cross-Dimensional Analysis → Critical Risk Nodes → Evolution Scenarios & Prescriptions → Falsifiable Predictions → Monitoring Dashboard → Source Audit

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

## License

MIT
