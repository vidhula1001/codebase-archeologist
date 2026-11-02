# Codebase Archeologist — Project Spec (v2: Dependency & Impact Analysis)

> This replaces the earlier git-history-based direction. New core idea: analyze the *current* code's actual structure — imports, calls, dependencies — build a real dependency graph, and let users ask "if I change X, what breaks?"

## 1. Problem Statement

In any codebase past a certain size, nobody has a full mental map of how files and modules depend on each other. This causes real, everyday pain:

- A developer changes one file, ships it, and something unrelated-looking breaks — because of a dependency they didn't know existed.
- Onboarding a new codebase means slowly, manually piecing together "what calls what" by reading code for days.
- Circular dependencies quietly cause bugs, bloated bundles, or import-order failures, and often go unnoticed until they cause a hard-to-debug error.
- Before making a change, developers *guess* at blast radius instead of knowing it. This leads to either over-cautious changes (slow) or under-cautious changes (breakage).

Existing tools address pieces of this (e.g. `madge` for JS import graphs, `pydeps` for Python) but they're single-language, produce a picture and stop there, and don't answer plain-language questions like *"I want to change this function's return type — what actually breaks?"*

## 2. What We're Building

A tool where a user:

1. **Uploads a project** — either a git repo URL or a zipped folder.
2. Gets back an **accurate dependency graph** of the codebase — which files/modules depend on which, across multiple languages.
3. Gets **cyclic dependencies automatically flagged** — a real, common source of bugs.
4. Can **ask natural-language questions about the impact of a change** — e.g. *"I want to change the `validatePayment` function in `payment.py` — what files/modules are affected, and how?"* — and get a real, grounded answer based on the actual dependency graph and code logic, not a guess.

In one sentence: **it turns "what depends on what" from a guess into a queryable, visual, evidence-backed map — with an AI layer that can reason about the actual impact of a specific change.**

## 3. Why This Approach

- **Static structure is unambiguous ground truth.** Unlike git history (which requires inference), imports/requires/calls are explicit in code. A dependency graph built from real parsing is *verifiable* — not a guess, not an LLM hallucination. This is the strongest possible foundation to reason on top of.
- **Impact analysis is what developers actually need day to day.** "What breaks if I touch this" is one of the most common — and most poorly served — questions in software engineering. Answering it well is high-value on its own, without needing history or organizational signals.
- **LLM's job is reasoning over a known-correct graph, not guessing at structure.** The graph itself is built by deterministic parsing (AST-based), so it's always accurate. The LLM (via Ollama, local) is used *on top of* that graph — to translate a plain-language question into a graph query, and to explain *why* something is affected (e.g. "this function's return value is used directly in `X`, so changing its shape breaks that call site") in a way a person can actually read. This mirrors the same principle as before: **deterministic detection, AI explanation** — never AI guessing at structure.
- **Multi-language matters because real projects aren't single-language.** A backend in Python calling into a JS frontend, or a monorepo with several services, is normal — the tool needs cross-language awareness (at least at a "these two services talk over this API" level) to be genuinely useful, not just a fancy `import` grep for one language.

## 4. How It Works — Architecture

```
┌───────────────┐     ┌────────────────────┐     ┌─────────────────────┐
│ 1. Ingestion    │ --> │ 2. Parsing           │ --> │ 3. Graph builder      │
│ repo URL clone  │     │ language-specific     │     │ nodes = files/modules │
│ or zip extract  │     │ AST parsers per lang   │     │ edges = imports/calls │
└───────────────┘     └────────────────────┘     └─────────────────────┘
                                                              │
                                                              v
                                                ┌─────────────────────────────┐
                                                │ 4. Graph analysis             │
                                                │ - cycle detection             │
                                                │ - "blast radius" per node      │
                                                │ - orphan/dead file detection   │
                                                └─────────────────────────────┘
                                                              │
                                          ┌───────────────────┴────────────────────┐
                                          v                                        v
                                ┌────────────────────┐               ┌──────────────────────┐
                                │ 5. Graph dashboard    │               │ 6. LLM query layer      │
                                │ interactive graph viz, │               │ (Ollama, local)          │
                                │ cycles highlighted     │               │ translates NL question   │
                                │                        │               │ -> graph query -> answer │
                                └────────────────────┘               └──────────────────────┘
```

### Stage 1 — Ingestion
Accept either a public git repo URL (clone it) or a zip upload (extract it). Normalize into a local file tree to analyze.

### Stage 2 — Parsing
For each supported language, use a real parser (not regex) to extract:
- Imports/requires/includes.
- Function and class definitions.
- Function calls and references across files.

Language-specific tools, e.g.:
- **JS/TS**: `@babel/parser` or TypeScript's own compiler API for accurate AST parsing.
- **Python**: built-in `ast` module.
- Additional languages added the same way — one parser adapter per language, all feeding a common graph format.

### Stage 3 — Graph builder
Build a directed graph:
- **Nodes** = files (v1) and, later, individual functions/classes (v2 granularity).
- **Edges** = "imports," "calls," or "references," labeled with the relationship type and location (line number).

This graph is the single source of truth everything else reasons over.

### Stage 4 — Graph analysis (deterministic, no LLM)
- **Cycle detection**: standard graph algorithms (e.g. Tarjan's SCC) to find circular dependencies, reported as the actual cycle path (A → B → C → A).
- **Blast radius**: for any node, compute everything that transitively depends on it (reverse reachability) — this is the backbone of impact analysis.
- **Orphan detection**: files nothing imports (possible dead code) — useful bonus signal.

### Stage 5 — Graph dashboard
Interactive visual graph (nodes = files, edges = dependencies), with:
- Cycles visually highlighted.
- Click a node to see everything upstream (what it depends on) and downstream (what depends on it).
- Search/filter by file or module.

### Stage 6 — LLM query layer (Ollama)
This is where natural-language questions get answered. The flow per question:
1. User asks: *"If I change `validatePayment` in `payment.py`, what's affected?"*
2. The LLM's job is **not** to guess the answer from reading code blindly — it's to identify the relevant node(s) in the graph, pull the real blast-radius data (deterministic, from Stage 4) plus the actual code of the affected call sites, and then **explain** the impact in plain language, grounded in that real data.
3. Answer includes: which files/functions are affected, *why* (e.g. "this return value is destructured here"), and a rough severity (direct call site vs. deeply transitive).

This mirrors the earlier design principle: **the graph/impact data is always deterministic and correct; the LLM's role is retrieval + explanation, not invention.**

## 5. Example Output

**Dependency graph view:**
- Visual graph, `payment.py` shown with arrows in from `checkout.py`, `refund.py`; arrows out to `db_client.py`, `currency.py`.
- 🔴 Cycle flagged: `orders.py → inventory.py → pricing.py → orders.py`

**Impact query:**

> **You asked:** "I want to change `validatePayment`'s return type from a boolean to an object. What breaks?"

> **Direct impact (3 files):**
> - `checkout.py:142` — uses the return value as a boolean in an `if` check. **Breaks** — needs updating to check a property instead.
> - `refund.py:88` — same pattern. **Breaks.**
> - `tests/test_payment.py:20` — asserts `== True`. **Breaks.**
>
> **Indirect impact (1 file):**
> - `analytics.py` calls `checkout.py`'s result downstream but doesn't touch the boolean directly — **likely safe**, but review recommended since `checkout.py` itself is changing.
>
> **No cyclic dependency involved in this change.**

## 6. Tech Stack

- **Ingestion**: `git clone` for URLs; standard zip extraction for uploads.
- **Parsing**: AST-based, per language —
  - JS/TS: `@babel/parser` / TypeScript compiler API.
  - Python: `ast` (standard library).
  - Additional languages: same pattern, added incrementally.
- **Graph**: build with a graph library (e.g. Python `networkx`) — gives cycle detection and reachability algorithms for free.
- **Storage**: SQLite or just an in-memory graph + JSON export, depending on project size.
- **LLM layer**: **Ollama, local**, as you already have — used for the NL query layer (Stage 6) only, never for building the graph itself.
- **Dashboard**: Web app (React) with a graph visualization library (e.g. `react-flow`, `d3`, or `cytoscape.js` — cytoscape is particularly strong for large dependency graphs with built-in layout algorithms).

## 7. Build Phases

1. **Ingestion + single-language parsing** — start with Python or JS (pick one), get real import extraction working.
2. **Graph builder + cycle detection** — turn parsed imports into a graph, detect and report cycles. This alone is a useful, shippable tool.
3. **Blast-radius / impact computation** — deterministic "what depends on this file" logic.
4. **Dashboard v1** — visualize the graph, click-through for upstream/downstream, cycles highlighted.
5. **Multi-language support** — add the second/third language parser adapters.
6. **LLM query layer** — wire Ollama to translate NL questions into graph queries and explain results, grounded in Stage 3 data.
7. **Function-level granularity** — extend nodes from file-level to function/class-level for finer-grained impact analysis.

## 8. Open Design Questions

- **Zip/repo size limits**: any cap on repo size for v1, or should huge monorepos be a "later" problem?
- **Cross-language edges**: for v1, is it enough to detect dependencies *within* each language, or do you also want to catch cross-language links (e.g. a Python backend's route called by a JS frontend fetch)? That's harder — likely a v2 feature.
- **Function-level vs. file-level default**: file-level first is the plan — confirm impact-analysis answers are still useful enough at that granularity for MVP, or if function-level is needed sooner for the query feature to feel good.
- **Ollama model choice**: which local model do you have pulled / plan to use? This affects how much you can lean on it for code-reasoning quality (bigger/coder-tuned models will do noticeably better at "why does this call site break").

## 9. Definition of Done for v1 (MVP)

- User can upload a zip or paste a repo URL.
- Tool parses at least one language accurately (real AST-based import graph, not regex).
- Dependency graph is built and visualized.
- Cyclic dependencies are detected and shown as actual cycle paths.
- User can click any file and see full upstream/downstream dependencies (blast radius).
- User can ask a natural-language impact question about a file, and get an answer grounded in the real graph (via Ollama).
