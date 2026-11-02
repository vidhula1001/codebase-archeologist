"""
Stage 1: Ingestion
Accepts either a git repo URL or a local zip file path, and normalizes
both into a plain directory on disk that the rest of the pipeline can scan.
"""

import subprocess
import tempfile
import zipfile
import shutil
from pathlib import Path


class IngestionError(Exception):
    pass


def ingest_git_repo(repo_url: str, dest_dir: str | None = None) -> Path:
    """
    Clone a git repo (shallow, depth=1 since we only need current code,
    not history) into dest_dir. If dest_dir is None, uses a temp dir.
    Returns the path to the cloned repo.
    """
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="archeologist_repo_")

    dest_path = Path(dest_dir)

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(dest_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as e:
        raise IngestionError(f"git clone failed: {e.stderr}")
    except subprocess.TimeoutExpired:
        raise IngestionError("git clone timed out after 300s")

    return dest_path


def ingest_zip(zip_path: str, dest_dir: str | None = None) -> Path:
    """
    Extract a zip file into dest_dir. If dest_dir is None, uses a temp dir.
    Returns the path to the extracted project root (handles the common case
    where the zip contains a single top-level folder).
    """
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise IngestionError(f"zip file not found: {zip_path}")

    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="archeologist_zip_")
    dest_path = Path(dest_dir)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_path)
    except zipfile.BadZipFile:
        raise IngestionError(f"not a valid zip file: {zip_path}")

    # If the zip contained exactly one top-level directory, treat that as
    # the project root (common for GitHub "Download ZIP" exports).
    entries = [p for p in dest_path.iterdir() if not p.name.startswith("__MACOSX")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]

    return dest_path


def cleanup(path: Path):
    """Remove a temp ingestion directory."""
    shutil.rmtree(path, ignore_errors=True)


# Directories we never want to scan regardless of language
DEFAULT_IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", ".venv", "env",
    "dist", "build", ".next", ".pytest_cache", "site-packages",
    ".mypy_cache", ".tox", "vendor", ".idea", ".vscode",
}


def find_source_files(root: Path, extensions: set[str]) -> list[Path]:
    """
    Walk the project root and return all files matching the given
    extensions (e.g. {'.py'}), skipping common noise directories.
    """
    results = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in DEFAULT_IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix in extensions:
            results.append(path)
    return results
