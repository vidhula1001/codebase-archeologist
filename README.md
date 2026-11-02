# Codebase Archeologist

A tool that builds a real dependency graph from your codebase (static AST parsing,
not guesses), detects circular dependencies, and answers "if I change this, what
breaks?" using a local LLM (Ollama) grounded strictly in the verified graph data.

**Status: Phase 1–3 working (Python only).** See `SPEC.md` for the full project plan.

## What's implemented right now

- ✅ Ingestion: local folder, git repo URL (clones it), or a zip file
- ✅ Python parsing via the `ast` module (real AST parsing, handles relative imports)
- ✅ Dependency graph construction (`networkx`)
- ✅ Cycle detection (reports the actual cycle path, e.g. `A -> B -> C -> A`)
- ✅ Blast radius / impact analysis (what directly + transitively depends on a module)
- ✅ Orphan/dead-code detection
- ✅ Natural-language impact questions via local Ollama, grounded in the real graph
  + real code snippets (not the LLM guessing)

## Not yet built (see SPEC.md for the roadmap)

- JS/TS and other language parsers (only Python works right now)
- Web dashboard / graph visualization (currently CLI-only, human-readable or `--json`)
- Function-level granularity (currently file-level only)
- Patch generation

## Setup

```bash
cd codebase-archeologist
pip install -r requirements.txt
```

For the `--ask` feature, you need Ollama running locally with a model pulled:

```bash
ollama serve          # in a separate terminal, if not already running
ollama pull llama3.1  # or whichever model you prefer
```

## Usage

Analyze a local folder:
```bash
python -m archeologist.cli --path ./sample_project
```

Analyze a git repo (clones it, shallow):
```bash
python -m archeologist.cli --repo https://github.com/someuser/somerepo
```

Analyze a zip upload:
```bash
python -m archeologist.cli --zip ./my_project.zip
```

Run impact/blast-radius analysis on a specific module:
```bash
python -m archeologist.cli --path ./sample_project --impact pricing.pricing
```

Ask a natural-language question about a change (requires Ollama running):
```bash
python -m archeologist.cli --path ./sample_project \
  --impact pricing.pricing \
  --symbol calculate_total \
  --ask "If I change calculate_total to return a Decimal instead of an int, what breaks?"
```

Get JSON output instead (for feeding into a future dashboard):
```bash
python -m archeologist.cli --path ./sample_project --json
```

## Try it on the included sample project

`sample_project/` is a deliberately small Python project with:
- A real 3-way circular dependency (`orders` ↔ `inventory` ↔ `pricing`)
- An orphan file (`legacy_utils.py`) nothing imports
- A normal (non-cyclic) dependency (`currency.py`)

Run the commands above against it to see the tool correctly catch all three.

## Project layout

```
archeologist/
  ingest.py          # Stage 1: git clone / zip extract / file discovery
  parser_python.py   # Stage 2: AST-based Python import/def extraction
  graph_builder.py   # Stage 3: builds the networkx dependency graph
  analysis.py         # Stage 4: cycle detection, blast radius, orphans
  llm_query.py        # Stage 6: Ollama query layer, grounded in analysis.py output
  cli.py              # wires it all together
sample_project/       # test fixture with a real cycle, for verifying the pipeline
SPEC.md                # full project spec (problem, why, architecture, roadmap)
```

## Next steps (recommended build order)

1. Add a JS/TS parser adapter (mirror `parser_python.py`'s shape) — this is the
   next highest-value addition since most real projects are multi-language.
2. Build the web dashboard (React + a graph viz lib like `cytoscape.js`) reading
   the `--json` output — this is what turns it from a CLI tool into the product.
3. Move `--ask` from "specify --impact manually" to genuinely parsing free-form
   questions ("what happens if I change X in file Y") into a graph query — right
   now the user has to name the module explicitly, which works but isn't the
   full vision from the spec.
4. Function-level granularity for finer-grained impact analysis.
