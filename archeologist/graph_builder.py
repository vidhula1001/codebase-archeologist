"""
Stage 3: Graph builder
Takes parsed file results and builds a directed graph where:
  - nodes = project modules (files)
  - edges = "A imports B", labeled with line number and imported names

Uses networkx so cycle detection / reachability come for free in Stage 4.

Only edges to modules that actually exist INSIDE the project are kept.
Imports of external/third-party libraries (requests, numpy, os, etc.)
are recorded separately as "external_dependencies" per node, since they're
not part of the internal dependency graph but are still useful metadata.
"""

import networkx as nx
from .parser_python import FileParseResult


def build_dependency_graph(parse_results: list[FileParseResult]) -> nx.DiGraph:
    graph = nx.DiGraph()

    # Map of module_name -> parse result, for resolving imports to real nodes
    module_map = {r.module_name: r for r in parse_results}

    # Add all nodes first (even ones with no edges yet, e.g. orphans)
    for result in parse_results:
        graph.add_node(
            result.module_name,
            file_path=str(result.file_path),
            functions=result.functions,
            classes=result.classes,
            parse_error=result.parse_error,
            external_dependencies=set(),
        )

    for result in parse_results:
        for imp in result.imports:
            target_module = _resolve_import(imp.imported_module, module_map)

            if target_module is not None:
                # Internal edge: this file depends on another file in the project
                if graph.has_edge(result.module_name, target_module):
                    graph[result.module_name][target_module]["imports"].append(
                        {"names": imp.imported_names, "line": imp.line}
                    )
                else:
                    graph.add_edge(
                        result.module_name,
                        target_module,
                        imports=[{"names": imp.imported_names, "line": imp.line}],
                    )
            else:
                # External dependency (third-party or stdlib) — track but don't
                # create a graph edge for it, since it's outside the project.
                graph.nodes[result.module_name]["external_dependencies"].add(
                    imp.imported_module.split(".")[0]
                )

    return graph


def _resolve_import(imported_module: str, module_map: dict) -> str | None:
    """
    Try to resolve a dotted import string to an actual module in the project.
    Handles the common cases:
      - exact match: "orders.checkout" -> "orders.checkout"
      - imported the package's __init__: "orders" -> "orders" (if it exists as
        a package, i.e. orders/__init__.py was parsed as module "orders")
      - "from orders.checkout import calculate_total" — imported_module is
        already "orders.checkout", exact match handles this.
    """
    if not imported_module:
        return None

    if imported_module in module_map:
        return imported_module

    # Try progressively shorter prefixes (handles "from pkg.sub import X"
    # where only "pkg.sub" exists as __init__, or partial resolution)
    parts = imported_module.split(".")
    while len(parts) > 1:
        parts = parts[:-1]
        candidate = ".".join(parts)
        if candidate in module_map:
            return candidate

    return None
