# Scoring Calibration: Anchor Cases

Use these real-world anchors to calibrate the 1-5 health scores consistently across analyses.
Each score level is anchored to observable, verifiable characteristics.

---

## Dimension 1: Boundary Topology

| Score | Anchor Case | Observable Characteristics |
|-------|------------|---------------------------|
| **5** | Berkshire Hathaway (2010s) | Crystal-clear operating subsidiary autonomy, hard financial discipline (never crosses into subsidiaries' debt), strong cultural soft constraints via annual letters, low transaction costs from long-term relationships |
| **4** | Apple (Cook era, pre-2023) | Clear product boundary, strong ecosystem walls, some soft constraint erosion as culture diversifies but still functional |
| **3** | General Electric (2015) | Boundary confusion between industrial and financial businesses, soft constraints degrading (culture diluted by M&A), transaction costs rising from complexity |
| **2** | WeWork (2019) | Boundary dissolution (what business are we in?), soft constraints effectively gone (founder narrative replacing institutional norms), massive hidden transaction costs |
| **1** | Enron (2001) | Hard constraint violation (regulatory/legal), complete soft constraint collapse, off-balance-sheet structures = boundary fraud |

---

## Dimension 2: Incentive Architecture

| Score | Anchor Case | Observable Characteristics |
|-------|------------|---------------------------|
| **5** | Costco (ongoing) | Employee incentives aligned with customer value (low turnover → service quality → margins), executive pay moderate vs. worker pay, positive-sum dynamics with suppliers |
| **4** | Toyota Production System | Strong incentive-compatibility in operations, some principal-agent issues at corporate governance level, generally cooperative supply chain dynamics |
| **3** | McKinsey & Company (post-2010) | Revenue-oriented incentives gradually overtaking professional standards, partner compensation creating short-termism, but professional norms still partially constraining |
| **2** | Wells Fargo (2016) | Famous case of incentive inversion: sales quotas → 3.5M fake accounts. Stated values = customer service; actual rewards = raw account numbers |
| **1** | FTX (2022) | Complete incentive-compatibility failure: customer funds treated as internal treasury, no separation of interests, principal-agent collapse at every level |

---

## Dimension 3: Information Neurology

| Score | Anchor Case | Observable Characteristics |
|-------|------------|---------------------------|
| **5** | Amazon (Working Backwards process) | Structured pre-mortem via PR/FAQ before projects start, metrics-driven decision culture, high information velocity, adversarial debate normalized |
| **4** | Netflix (Culture Deck era) | Strong information culture ("sunshining" disagreements), context over control, some blind spots in content decision-making |
| **3** | Boeing (2015-2018) | Engineering feedback channels still functional but increasingly overridden by financial/schedule signals; MCAS warning signs ignored |
| **2** | Boeing (2019-2020) | 737 MAX crisis: safety feedback systematically suppressed, decision-makers in partial fantasy world, positive feedback loop (schedule pressure → safety cutting → more pressure) fully established |
| **1** | Soviet Gosplan (late 1980s) | Classic fantasy world: planners receiving fabricated output numbers from enterprises, completely decoupled from reality, negative feedback loops fully disabled |

---

## Dimension 4: Temporal Metabolism

| Score | Anchor Case | Observable Characteristics |
|-------|------------|---------------------------|
| **5** | TSMC (ongoing) | Massive capex investment cycles that sacrifice short-term margins for long-term capability moats, deliberate renewal of process technology every 2 years, patience capital from founder culture |
| **4** | Microsoft (Nadella era) | Significant temporal reorientation from Ballmer's finite game (beat competitors) to Nadella's infinite game (grow the cloud ecosystem), substantial investment in future capabilities |
| **3** | IBM (2015-2020) | Declining core, acquisitions as renewal theater, Red Hat acquisition possibly too late, still harvesting mainframe and services cash |
| **2** | GE (Immelt era) | Classic temporal cannibalism: financial engineering masking industrial decline, stock buybacks instead of R&D, divesting future for present EPS |
| **1** | Toys "R" Us (2017) | LBO debt structure made temporal investment impossible, forced to optimize for debt service at expense of store refresh, e-commerce investment, talent — consumed its own future |

---

## Dimension 5: Legitimacy & Narrative

| Score | Anchor Case | Observable Characteristics |
|-------|------------|---------------------------|
| **5** | Patagonia (ongoing) | Internally coherent narrative (environmental mission) that employees live, customers validate, and ownership structure (donated to trust) now proves permanently. Near-zero narrative-reality gap. |
| **4** | Salesforce (early 2020s) | 1-1-1 model creates coherent narrative of stakeholder capitalism, some legitimacy strain from workforce reductions while CEO preaches social responsibility |
| **3** | Twitter/X (Musk era, 2022-2023) | Massive narrative disruption, partial legitimacy collapse among previous user base, new narrative forming but unstable, internal cynicism widespread |
| **2** | WeWork (2019) | Adam Neumann's "elevate the world's consciousness" narrative entirely disconnected from a real estate subletting business; internal eye-rolling rampant; IPO collapse = legitimacy debt called |
| **1** | Theranos (2015-2018) | Total narrative fraud: stated capabilities (blood testing revolution) fabricated, legitimacy built entirely on false claims, complete narrative-reality inversion |

---

## Dimension 6: Coupling Architecture

| Score | Anchor Case | Observable Characteristics |
|-------|------------|---------------------------|
| **5** | Amazon Web Services (multi-region architecture) | Deliberately designed for failure: fault isolation, circuit breakers, graceful degradation. Internal "two-pizza teams" = loose coupling in org structure matching loose coupling in systems. |
| **4** | Switzerland (political system) | Federalist architecture creates natural fault isolation, direct democracy = distributed decision-making, cantonal diversity = redundancy. Some tight coupling in financial sector (UBS/Credit Suisse risk) |
| **3** | Apple supply chain (2020) | High efficiency but concentrated in TSMC and China manufacturing = tight coupling by design; COVID and geopolitics exposed fragility; now actively decoupling |
| **2** | Global financial system (2008) | Mortgage securitization created hidden tight coupling across nominally independent institutions; failure of one triggered cascade across all; no adequate buffers |
| **1** | Fukushima Daiichi (2011) | Perrow's normal accident in pure form: tight coupling (diesel backup generators in flood zone) + complexity (multiple simultaneous failure modes) = unavoidable catastrophic cascade |

---

## Cross-Reference: When Scores Interact

**High-confidence danger zones** (patterns that reliably predict catastrophic failure):

| Pattern | Dimensional Signature | Historical Examples |
|---------|----------------------|---------------------|
| Legitimacy-incentive collapse | D5≤2 + D2≤2 | Enron, Theranos, FTX |
| Information-boundary dysfunction | D3≤2 + D1≤2 | Soviet enterprises, Wirecard |
| Temporal-coupling catastrophe | D4≤2 + D6≤2 | Toys R Us, heavily LBO'd retailers |
| Narrative-feedback death spiral | D5≤2 + D3≤2 | WeWork, many unicorn busts |

**High-confidence survival zone** (systems that can absorb significant shocks):

| Pattern | Dimensional Signature |
|---------|----------------------|
| Anti-fragile core | D4≥4 + D6≥4 |
| Trust-information flywheel | D5≥4 + D3≥4 |
| Incentive-boundary alignment | D2≥4 + D1≥4 |

---

## Scoring Discipline Rules

1. **Never average across stakeholders**: A company scoring 5/5 for investors and 1/5 for employees should be scored 2/5, not 3/5 — the low score is the structural risk
2. **Score current state, not potential**: A founder's vision doesn't change today's score
3. **Trajectory matters as much as score**: A system at 3/5 declining is more dangerous than a system at 2/5 improving
4. **Calibrate to sector norms when relevant**: A 3/5 for information quality in a fast-moving startup is different from a 3/5 in a nuclear power plant
5. **Never score above 4 without specific evidence**: 5/5 is for exemplars only, not "seems fine"
