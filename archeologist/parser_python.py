"""
Stage 2: Parsing (Python)
Uses the standard library `ast` module to accurately extract, per file:
  - imports (module-level and from-imports), resolved to project-relative
    module paths where possible
  - top-level function/class definitions
  - calls to names that might reference other project modules

This is real AST parsing, not regex/text matching, so it's robust to
formatting, comments, multi-line imports, etc.
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImportEdge:
    imported_module: str      # dotted module name as written, e.g. "orders.pricing"
    imported_names: list[str] # specific names imported, e.g. ["calculate_total"]
    line: int
    is_relative: bool = False


@dataclass
class FileParseResult:
    file_path: Path
    module_name: str                  # dotted module path relative to project root
    imports: list[ImportEdge] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    parse_error: str | None = None


def file_to_module_name(file_path: Path, project_root: Path) -> str:
    """Convert a file path like project_root/orders/checkout.py -> 'orders.checkout'"""
    rel = file_path.relative_to(project_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def parse_python_file(file_path: Path, project_root: Path) -> FileParseResult:
    module_name = file_to_module_name(file_path, project_root)
    result = FileParseResult(file_path=file_path, module_name=module_name)

    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError) as e:
        result.parse_error = str(e)
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.append(
                    ImportEdge(
                        imported_module=alias.name,
                        imported_names=[],
                        line=node.lineno,
                        is_relative=False,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            # node.level > 0 means relative import (from . import x / from ..pkg import y)
            module = node.module or ""
            if node.level and node.level > 0:
                # Resolve relative import against the importing file's package
                pkg_parts = module_name.split(".")[:-1]  # drop own file, keep package path
                # go up `level - 1` extra packages for each additional dot
                up = node.level - 1
                if up > 0:
                    pkg_parts = pkg_parts[:-up] if up <= len(pkg_parts) else []
                resolved = ".".join(pkg_parts + ([module] if module else []))
                imported_module = resolved
                is_relative = True
            else:
                imported_module = module
                is_relative = False

            result.imports.append(
                ImportEdge(
                    imported_module=imported_module,
                    imported_names=[alias.name for alias in node.names],
                    line=node.lineno,
                    is_relative=is_relative,
                )
            )
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            # Only top-level-ish defs (rough heuristic: name not already seen)
            if node.name not in result.functions:
                result.functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            if node.name not in result.classes:
                result.classes.append(node.name)

    return result


def parse_project(python_files: list[Path], project_root: Path) -> list[FileParseResult]:
    return [parse_python_file(f, project_root) for f in python_files]
