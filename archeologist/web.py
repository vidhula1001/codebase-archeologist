"""
Web dashboard backend.

Run with:  python -m archeologist.web
Then open: http://localhost:5000

Reuses the exact same pipeline as the CLI (ingest -> parse -> graph -> analysis),
just exposes it over HTTP so the frontend can render an interactive graph
instead of reading terminal text.
"""

from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path

from . import ingest
from .parser_python import parse_project
from .graph_builder import build_dependency_graph
from .analysis import compute_blast_radius, graph_to_json

app = Flask(__name__, static_folder="static", static_url_path="")

# Holds the most recently analyzed graph in memory, so impact/ask requests
# don't need to re-parse the whole project every time.
_state = {"graph": None, "project_root": None}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Body: { "path": "..." } OR { "repo": "..." } OR provide a "zip" via
    multipart upload under form field "file".
    """
    cleanup_path = None

    if request.content_type and "multipart/form-data" in request.content_type:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file uploaded"}), 400
        tmp_zip = Path(ingest.tempfile.mkdtemp()) / "upload.zip"
        file.save(tmp_zip)
        try:
            project_root = ingest.ingest_zip(str(tmp_zip))
        except ingest.IngestionError as e:
            return jsonify({"error": str(e)}), 400
        cleanup_path = project_root
    else:
        data = request.get_json(force=True, silent=True) or {}
        if data.get("repo"):
            try:
                project_root = ingest.ingest_git_repo(data["repo"])
            except ingest.IngestionError as e:
                return jsonify({"error": str(e)}), 400
            cleanup_path = project_root
        elif data.get("path"):
            project_root = Path(data["path"]).resolve()
            if not project_root.exists():
                return jsonify({"error": f"Path does not exist: {project_root}"}), 400
        else:
            return jsonify({"error": "Provide 'path', 'repo', or a zip file upload"}), 400

    py_files = ingest.find_source_files(project_root, {".py"})
    if not py_files:
        return jsonify({"error": f"No Python files found under {project_root}"}), 400

    parse_results = parse_project(py_files, project_root)
    graph = build_dependency_graph(parse_results)

    _state["graph"] = graph
    _state["project_root"] = str(project_root)

    payload = graph_to_json(graph)
    payload["project_root"] = str(project_root)

    # Note: we deliberately do NOT clean up cloned/extracted temp dirs here,
    # since file_path references inside the graph point into them and the
    # user may want to inspect snippets later via /api/ask. A production
    # version would copy needed source into persistent storage instead.

    return jsonify(payload)


@app.route("/api/impact/<path:module>", methods=["GET"])
def impact(module):
    graph = _state["graph"]
    if graph is None:
        return jsonify({"error": "No project analyzed yet. Call /api/analyze first."}), 400
    try:
        br = compute_blast_radius(graph, module)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    return jsonify({
        "module": br.module,
        "directly_depends_on": br.directly_depends_on,
        "directly_depended_on_by": br.directly_depended_on_by,
        "transitively_depended_on_by": br.transitively_depended_on_by,
        "in_a_cycle": br.in_a_cycle,
    })


@app.route("/api/ask", methods=["POST"])
def ask():
    """
    Body: { "module": "...", "question": "...", "symbol": "...", "model": "..." }
    """
    graph = _state["graph"]
    if graph is None:
        return jsonify({"error": "No project analyzed yet. Call /api/analyze first."}), 400

    data = request.get_json(force=True, silent=True) or {}
    module = data.get("module")
    question = data.get("question")
    symbol = data.get("symbol")
    model = data.get("model", "qwen2.5-coder:1.5b")

    if not module or not question:
        return jsonify({"error": "Provide 'module' and 'question'"}), 400

    try:
        br = compute_blast_radius(graph, module)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    from .llm_query import answer_impact_question
    try:
        answer = answer_impact_question(question, br, graph, changed_symbol=symbol, model=model)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({"answer": answer})


def main():
    print("\nCodebase Archeologist dashboard running at http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()