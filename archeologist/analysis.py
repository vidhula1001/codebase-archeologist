"""
Stage 4: Graph analysis (deterministic — no LLM involved here)
  - Cycle detection: find circular import chains
  - Blast radius: for a given module, what transitively depends on it
    (reverse reachability) and what it transitively depends on
  - Orphan detection: modules nothing else imports (possible dead code,
    or legitimate entry points like main.py — flagged for review either way)
"""

import networkx as nx
from dataclasses import dataclass


@dataclass
class Cycle:
    modules: list[str]  # the cycle path, e.g. ["orders", "inventory", "pricing", "orders"]

    def __str__(self):
        return " -> ".join(self.modules)


@dataclass
class BlastRadius:
    module: str
    directly_depends_on: list[str]       # modules this one imports directly
    directly_depended_on_by: list[str]   # modules that directly import this one
    transitively_depended_on_by: list[str]  # full downstream impact (reverse reachability)
    in_a_cycle: bool


def find_cycles(graph: nx.DiGraph) -> list[Cycle]:
    """
    Find all elementary cycles in the dependency graph using networkx's
    simple_cycles (Johnson's algorithm). Each cycle is reported as the
    actual path, e.g. A -> B -> C -> A, so it's directly actionable.
    """
    cycles = []
    for cycle_nodes in nx.simple_cycles(graph):
        if len(cycle_nodes) < 2:
            continue  # skip self-loops of length 1 unless it's a true self-import
        path = cycle_nodes + [cycle_nodes[0]]
        cycles.append(Cycle(modules=path))
    return cycles


def compute_blast_radius(graph: nx.DiGraph, module: str) -> BlastRadius:
    """
    For a given module, compute:
      - what it directly imports
      - what directly imports it
      - everything downstream that would be affected by a change to it
        (transitive reverse reachability — i.e. "blast radius")
    """
    if module not in graph:
        raise ValueError(f"module '{module}' not found in dependency graph")

    directly_depends_on = list(graph.successors(module))
    directly_depended_on_by = list(graph.predecessors(module))

    # Reverse reachability: everything that can reach `module` by following
    # import edges backwards, i.e. everything that would be impacted if
    # `module` changes.
    reversed_graph = graph.reverse(copy=False)
    transitively_depended_on_by = sorted(
        n for n in nx.descendants(reversed_graph, module) if n != module
    )

    cycles = find_cycles(graph)
    in_a_cycle = any(module in c.modules for c in cycles)

    return BlastRadius(
        module=module,
        directly_depends_on=directly_depends_on,
        directly_depended_on_by=directly_depended_on_by,
        transitively_depended_on_by=transitively_depended_on_by,
        in_a_cycle=in_a_cycle,
    )


def find_orphans(graph: nx.DiGraph) -> list[str]:
    """
    Modules that nothing else in the project imports (in-degree 0) AND
    that don't look like conventional entry points (main, __init__, app,
    manage, etc.) — flagged as possible dead code for the user to review.

    Package __init__.py files are excluded: it's normal for nothing to
    import a package by its bare name (e.g. `orders`) when everything
    imports its submodules directly (e.g. `orders.orders`) — that's not
    dead code, just how Python packages are commonly used.
    """
    likely_entrypoint_names = {"main", "app", "manage", "run", "__main__", "wsgi", "asgi", "setup"}

    orphans = []
    for node, data in graph.nodes(data=True):
        if graph.in_degree(node) == 0:
            file_path = data.get("file_path", "")
            if file_path.endswith("__init__.py"):
                continue
            leaf_name = node.split(".")[-1]
            if leaf_name not in likely_entrypoint_names:
                orphans.append(node)
    return sorted(orphans)


def graph_summary(graph: nx.DiGraph) -> dict:
    """High-level stats about the dependency graph for a quick overview."""
    cycles = find_cycles(graph)
    orphans = find_orphans(graph)
    return {
        "total_modules": graph.number_of_nodes(),
        "total_dependency_edges": graph.number_of_edges(),
        "cycles_found": len(cycles),
        "cycles": [str(c) for c in cycles],
        "orphan_modules": orphans,
        "most_depended_on": _top_n_by_indegree(graph, 5),
        "most_dependencies": _top_n_by_outdegree(graph, 5),
    }


def graph_to_json(graph: nx.DiGraph) -> dict:
    """
    Serialize the full graph into plain JSON for the frontend: nodes + edges,
    with cycle membership flagged on each node/edge so the UI can highlight
    them without recomputing anything client-side.
    """
    cycles = find_cycles(graph)
    nodes_in_cycles = set()
    edges_in_cycles = set()
    for c in cycles:
        for i in range(len(c.modules) - 1):
            nodes_in_cycles.add(c.modules[i])
            edges_in_cycles.add((c.modules[i], c.modules[i + 1]))

    orphans = set(find_orphans(graph))

    nodes = []
    for node, data in graph.nodes(data=True):
        nodes.append({
            "id": node,
            "file_path": data.get("file_path"),
            "functions": data.get("functions", []),
            "classes": data.get("classes", []),
            "parse_error": data.get("parse_error"),
            "in_degree": graph.in_degree(node),
            "out_degree": graph.out_degree(node),
            "in_cycle": node in nodes_in_cycles,
            "is_orphan": node in orphans,
        })

    edges = []
    for source, target, data in graph.edges(data=True):
        edges.append({
            "source": source,
            "target": target,
            "imports": data.get("imports", []),
            "in_cycle": (source, target) in edges_in_cycles,
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": graph_summary(graph),
    }


def _top_n_by_indegree(graph: nx.DiGraph, n: int) -> list[tuple[str, int]]:
    return sorted(graph.in_degree, key=lambda x: x[1], reverse=True)[:n]


def _top_n_by_outdegree(graph: nx.DiGraph, n: int) -> list[tuple[str, int]]:
    return sorted(graph.out_degree, key=lambda x: x[1], reverse=True)[:n]