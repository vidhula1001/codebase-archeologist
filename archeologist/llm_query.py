"""
Stage 6: LLM query layer (Ollama, local)

Design principle: the LLM NEVER invents the dependency structure. It is only
ever given:
  1. The deterministic blast-radius data already computed in analysis.py
     (which modules are actually affected, and how — direct vs transitive).
  2. The actual source code of the affected call sites (real text, not
     paraphrased).

Its job is purely to explain that real evidence in plain language and
answer a specific "what if I change X" question. If it doesn't have enough
evidence to answer something, it should say so rather than guess.
"""

import json
import urllib.request
import urllib.error
from pathlib import Path

from .analysis import BlastRadius

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:1.5b"


def call_ollama(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 300) -> str:
    """Send a prompt to a local Ollama instance and return the generated text."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "").strip()
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_URL} — is `ollama serve` running? ({e})"
        )


def _grab_snippet(file_path: str, keyword: str | None, context_lines: int = 3) -> str:
    """Pull a small snippet of real source code around a keyword (e.g. the
    changed function name) so the LLM explains against real text, not memory."""
    try:
        lines = Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(source unavailable)"

    if not keyword:
        return "\n".join(lines[:10])

    for i, line in enumerate(lines):
        if keyword in line:
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            numbered = [f"{n+1}: {lines[n]}" for n in range(start, end)]
            return "\n".join(numbered)

    return "(keyword not found in file — showing top of file)\n" + "\n".join(lines[:10])


def build_grounded_prompt(
    question: str,
    blast_radius: BlastRadius,
    graph,
    changed_symbol: str | None = None,
) -> str:
    """
    Build a prompt that hands the LLM ONLY real, verified evidence:
    the actual dependency facts and real code snippets of affected files.
    """
    evidence_lines = [
        f"Module being changed: {blast_radius.module}",
        f"Directly depends on: {blast_radius.directly_depends_on or 'none'}",
        f"Directly depended on by (these WILL be affected first): {blast_radius.directly_depended_on_by or 'none'}",
        f"Full transitive downstream impact (blast radius): {blast_radius.transitively_depended_on_by or 'none'}",
        f"Part of a circular dependency: {blast_radius.in_a_cycle}",
        "",
    ]

    snippet_lines = ["Relevant real code from directly affected files:", ""]
    MAX_SNIPPETS = 5  # cap prompt size so real-world modules with many
                       # dependents don't produce a huge, slow prompt
    dependents_to_show = blast_radius.directly_depended_on_by[:MAX_SNIPPETS]
    for dep in dependents_to_show:
        file_path = graph.nodes[dep].get("file_path")
        if file_path:
            snippet = _grab_snippet(file_path, changed_symbol)
            snippet_lines.append(f"--- {dep} ({file_path}) ---")
            snippet_lines.append(snippet)
            snippet_lines.append("")
    remaining = len(blast_radius.directly_depended_on_by) - len(dependents_to_show)
    if remaining > 0:
        snippet_lines.append(
            f"(plus {remaining} more directly-affected file(s) not shown here for brevity — "
            f"listed by name in the evidence above, but their code wasn't included in this prompt)"
        )

    prompt = f"""You are analyzing the real, verified dependency structure of a codebase.
The dependency facts below come from static AST parsing of the actual project — they are
ground truth, not guesses. Do NOT invent any files, functions, or dependencies that are not
listed below. If the evidence given isn't enough to fully answer, say so explicitly instead
of guessing.

EVIDENCE:
{chr(10).join(evidence_lines)}
{chr(10).join(snippet_lines)}

USER QUESTION:
{question}

Answer the question using ONLY the evidence above. For each affected file, explain concretely
WHY it's affected (what it actually does with the changed module/symbol, based on the code
shown) and how confident you are (direct usage = high confidence; transitive/indirect = flag
as "review recommended" rather than a certain break). Be concise and concrete.
"""
    return prompt


def answer_impact_question(
    question: str,
    blast_radius: BlastRadius,
    graph,
    changed_symbol: str | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    prompt = build_grounded_prompt(question, blast_radius, graph, changed_symbol)
    return call_ollama(prompt, model=model)