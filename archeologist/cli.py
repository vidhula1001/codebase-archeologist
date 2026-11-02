"""
CLI entry point for the Codebase Archeologist (Phase 1-4: no LLM yet).

Usage:
    python -m archeologist.cli --path /path/to/project
    python -m archeologist.cli --repo https://github.com/user/repo
    python -m archeologist.cli --zip /path/to/project.zip
    python -m archeologist.cli --path ./sample_project --impact orders.orders
"""

import argparse
import json
import sys
from pathlib import Path

from . import ingest
from .parser_python import parse_project
from .graph_builder import build_dependency_graph
from .analysis import find_cycles, compute_blast_radius, find_orphans, graph_summary


def run(project_root: Path, impact_target: str | None = None, output_json: bool = False,
        ask_question: str | None = None, changed_symbol: str | None = None,
        model: str = "deepseek-coder:6.7b"):
    py_files = ingest.find_source_files(project_root, {".py"})

    if not py_files:
        print(f"No Python files found under {project_root}", file=sys.stderr)
        sys.exit(1)

    parse_results = parse_project(py_files, project_root)

    errors = [r for r in parse_results if r.parse_error]
    graph = build_dependency_graph(parse_results)

    summary = graph_summary(graph)

    if output_json:
        payload = {"summary": summary, "parse_errors": [
            {"file": str(e.file_path), "error": e.parse_error} for e in errors
        ]}
        if impact_target:
            br = compute_blast_radius(graph, impact_target)
            payload["impact"] = {
                "module": br.module,
                "directly_depends_on": br.directly_depends_on,
                "directly_depended_on_by": br.directly_depended_on_by,
                "transitively_depended_on_by": br.transitively_depended_on_by,
                "in_a_cycle": br.in_a_cycle,
            }
        print(json.dumps(payload, indent=2))
        return

    # Human-readable report
    print(f"\n{'='*60}")
    print(f"  CODEBASE ARCHEOLOGIST — Dependency Report")
    print(f"  Project: {project_root}")
    print(f"{'='*60}\n")

    print(f"Modules parsed:        {summary['total_modules']}")
    print(f"Dependency edges:      {summary['total_dependency_edges']}")

    if errors:
        print(f"\n⚠️  {len(errors)} file(s) failed to parse:")
        for e in errors:
            print(f"   - {e.file_path}: {e.parse_error}")

    print(f"\n{'—'*60}")
    print(f"CYCLIC DEPENDENCIES: {summary['cycles_found']} found")
    print(f"{'—'*60}")
    if summary["cycles"]:
        for c in summary["cycles"]:
            print(f"  🔴 {c}")
    else:
        print("  ✅ No circular dependencies detected.")

    print(f"\n{'—'*60}")
    print(f"MOST DEPENDED-ON MODULES (highest blast radius risk)")
    print(f"{'—'*60}")
    for module, count in summary["most_depended_on"]:
        if count > 0:
            print(f"  {module:<30} depended on by {count} module(s) directly")

    print(f"\n{'—'*60}")
    print(f"ORPHAN MODULES (nothing imports these — review for dead code)")
    print(f"{'—'*60}")
    if summary["orphan_modules"]:
        for m in summary["orphan_modules"]:
            print(f"  ⚪ {m}")
    else:
        print("  None found.")

    if impact_target:
        print(f"\n{'—'*60}")
        print(f"IMPACT ANALYSIS: {impact_target}")
        print(f"{'—'*60}")
        try:
            br = compute_blast_radius(graph, impact_target)
        except ValueError as e:
            print(f"  ⚠️  {e}")
        else:
            print(f"  Directly depends on:        {br.directly_depends_on or '(none)'}")
            print(f"  Directly depended on by:    {br.directly_depended_on_by or '(none)'}")
            print(f"  FULL blast radius (transitive downstream impact):")
            if br.transitively_depended_on_by:
                for m in br.transitively_depended_on_by:
                    print(f"    -> {m}")
            else:
                print(f"    (nothing depends on this module, directly or transitively)")
            if br.in_a_cycle:
                print(f"  🔴 Note: this module is part of a circular dependency.")

            if ask_question:
                from .llm_query import answer_impact_question
                print(f"\n{'—'*60}")
                print(f"AI EXPLANATION (Ollama, grounded in evidence above)")
                print(f"{'—'*60}")
                try:
                    answer = answer_impact_question(
                        ask_question, br, graph, changed_symbol=changed_symbol, model=model
                    )
                    print(f"  {answer}")
                except RuntimeError as e:
                    print(f"  ⚠️  {e}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Codebase Archeologist: dependency graph & impact analysis")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", help="Path to a local project directory")
    source.add_argument("--repo", help="Git repo URL to clone and analyze")
    source.add_argument("--zip", help="Path to a zip file to extract and analyze")

    parser.add_argument("--impact", help="Module to run impact/blast-radius analysis on, e.g. orders.orders")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of human-readable report")
    parser.add_argument("--ask", help="Natural-language question about the impact of a change (requires --impact). Needs Ollama running locally.")
    parser.add_argument("--symbol", help="Specific function/symbol being changed, to pull relevant code snippets (optional, used with --ask)")
    parser.add_argument("--model", default="qwen2.5-coder:1.5b", help="Ollama model to use for --ask (default: deepseek-coder:6.7b). Run `ollama list` to see what you have installed.")

    args = parser.parse_args()

    cleanup_path = None
    if args.path:
        project_root = Path(args.path).resolve()
    elif args.repo:
        project_root = ingest.ingest_git_repo(args.repo)
        cleanup_path = project_root
    else:
        project_root = ingest.ingest_zip(args.zip)
        cleanup_path = project_root

    try:
        run(project_root, impact_target=args.impact, output_json=args.json,
            ask_question=args.ask, changed_symbol=args.symbol, model=args.model)
    finally:
        if cleanup_path:
            ingest.cleanup(cleanup_path)


if __name__ == "__main__":
    main()