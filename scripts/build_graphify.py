from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / ".graphify"
MAX_TEXT_BYTES = 200_000
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
}
MEDIA_SUFFIXES = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
}
SKIP_DIRS = {
    ".git",
    ".graphify",
    "__pycache__",
}
SKIP_FILE_NAMES = {
    ".DS_Store",
}


def build_node_id(kind: str, relative_path: str) -> str:
    return f"{kind}:{relative_path}"


def build_symbol_id(file_path: str, symbol_name: str) -> str:
    return f"symbol:{file_path}::{symbol_name}"


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def is_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_SUFFIXES


def relative_string(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def summarize_markdown(text: str) -> dict[str, object]:
    headings = [line.strip() for line in text.splitlines() if line.startswith("#")]
    return {"headings": headings[:20]}


def summarize_html(text: str) -> dict[str, object]:
    title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    ids = re.findall(r'id="([^"]+)"', text)
    scripts = re.findall(r"<script[^>]*src=\"([^\"]+)\"", text, re.IGNORECASE)
    return {
        "title": title_match.group(1).strip() if title_match else None,
        "dom_ids": ids[:20],
        "script_refs": scripts[:20],
    }


def summarize_javascript(text: str) -> dict[str, object]:
    functions = re.findall(r"function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)
    const_functions = re.findall(
        r"(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(",
        text,
    )
    classes = re.findall(r"class\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    dom_queries = re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", text)
    fetch_calls = re.findall(r"fetch\(['\"]([^'\"]+)['\"]", text)
    return {
        "functions": sorted(set(functions + const_functions))[:40],
        "classes": sorted(set(classes))[:20],
        "dom_ids": sorted(set(dom_queries))[:30],
        "fetch_calls": fetch_calls[:20],
    }


def summarize_python(text: str, file_path: str, nodes: list[dict[str, object]], edges: list[dict[str, object]]) -> dict[str, object]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {"parse_error": str(exc)}

    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    module_docstring = ast.get_docstring(tree)

    for item in tree.body:
        if isinstance(item, ast.Import):
            for alias in item.names:
                imports.append(alias.name)
        elif isinstance(item, ast.ImportFrom):
            module = item.module or ""
            imports.append("." * item.level + module)
        elif isinstance(item, ast.ClassDef):
            classes.append(item.name)
            symbol_id = build_symbol_id(file_path, item.name)
            nodes.append(
                {
                    "id": symbol_id,
                    "kind": "symbol",
                    "name": item.name,
                    "symbol_type": "class",
                    "file_path": file_path,
                }
            )
            edges.append({"source": build_node_id("file", file_path), "target": symbol_id, "type": "defines"})
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(item.name)
            symbol_id = build_symbol_id(file_path, item.name)
            nodes.append(
                {
                    "id": symbol_id,
                    "kind": "symbol",
                    "name": item.name,
                    "symbol_type": "function",
                    "file_path": file_path,
                }
            )
            edges.append({"source": build_node_id("file", file_path), "target": symbol_id, "type": "defines"})

    return {
        "module_docstring": module_docstring.splitlines()[0] if module_docstring else None,
        "imports": imports[:50],
        "classes": classes[:30],
        "functions": functions[:50],
    }


def summarize_file(path: Path, relative_path: str, nodes: list[dict[str, object]], edges: list[dict[str, object]]) -> dict[str, object]:
    size_bytes = path.stat().st_size
    summary: dict[str, object] = {
        "size_bytes": size_bytes,
        "suffix": path.suffix.lower(),
    }
    if not is_text_file(path):
        summary["content_type"] = "media" if is_media_file(path) else "binary"
        return summary
    if size_bytes > MAX_TEXT_BYTES:
        summary["content_type"] = "text"
        summary["truncated"] = True
        return summary

    text = read_text(path)
    summary["content_type"] = "text"
    summary["line_count"] = text.count("\n") + 1

    if path.suffix == ".py":
        summary.update(summarize_python(text, relative_path, nodes, edges))
    elif path.suffix == ".md":
        summary.update(summarize_markdown(text))
    elif path.suffix == ".html":
        summary.update(summarize_html(text))
    elif path.suffix == ".js":
        summary.update(summarize_javascript(text))
    elif path.suffix == ".json":
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                summary["top_level_keys"] = list(payload.keys())[:40]
            elif isinstance(payload, list):
                summary["top_level_type"] = "list"
                summary["list_length"] = len(payload)
        except json.JSONDecodeError as exc:
            summary["parse_error"] = str(exc)
    return summary


def add_directory_nodes(nodes: list[dict[str, object]], edges: list[dict[str, object]]) -> None:
    seen_dirs = {PROJECT_ROOT}
    for path in PROJECT_ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_dir():
            seen_dirs.add(path)

    for directory in sorted(seen_dirs):
        relative_path = "." if directory == PROJECT_ROOT else relative_string(directory)
        node_id = build_node_id("dir", relative_path)
        nodes.append({"id": node_id, "kind": "directory", "path": relative_path})
        if directory != PROJECT_ROOT:
            parent = directory.parent
            parent_relative = "." if parent == PROJECT_ROOT else relative_string(parent)
            edges.append(
                {
                    "source": build_node_id("dir", parent_relative),
                    "target": node_id,
                    "type": "contains",
                }
            )


def build_graph() -> dict[str, object]:
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    add_directory_nodes(nodes, edges)

    file_type_counter: Counter[str] = Counter()
    important_files: list[str] = []

    for path in sorted(PROJECT_ROOT.rglob("*")):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILE_NAMES:
            continue

        relative_path = relative_string(path)
        file_type_counter[path.suffix.lower() or "<none>"] += 1
        if relative_path in {"README.md", "ARCHITECTURE.md", "database_schema.md", "api/app.py", "api/database.py"}:
            important_files.append(relative_path)

        summary = summarize_file(path, relative_path, nodes, edges)
        file_node_id = build_node_id("file", relative_path)
        nodes.append(
            {
                "id": file_node_id,
                "kind": "file",
                "path": relative_path,
                **summary,
            }
        )
        parent = path.parent
        parent_relative = "." if parent == PROJECT_ROOT else relative_string(parent)
        edges.append(
            {
                "source": build_node_id("dir", parent_relative),
                "target": file_node_id,
                "type": "contains",
            }
        )

        if path.suffix == ".py" and "imports" in summary:
            for imported in summary["imports"]:
                edges.append(
                    {
                        "source": file_node_id,
                        "target": f"module:{imported}",
                        "type": "imports",
                    }
                )
                nodes.append({"id": f"module:{imported}", "kind": "module", "name": imported})

    unique_nodes = {node["id"]: node for node in nodes}
    unique_edges = []
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        edge_key = (str(edge["source"]), str(edge["target"]), str(edge["type"]))
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        unique_edges.append(edge)

    stats = {
        "total_nodes": len(unique_nodes),
        "total_edges": len(unique_edges),
        "file_count": sum(1 for node in unique_nodes.values() if node["kind"] == "file"),
        "directory_count": sum(1 for node in unique_nodes.values() if node["kind"] == "directory"),
        "symbol_count": sum(1 for node in unique_nodes.values() if node["kind"] == "symbol"),
        "file_types": dict(sorted(file_type_counter.items())),
        "important_files": important_files,
    }
    return {
        "project": "BrainGain",
        "root": str(PROJECT_ROOT),
        "stats": stats,
        "nodes": list(unique_nodes.values()),
        "edges": unique_edges,
    }


def build_project_map(graph: dict[str, object]) -> str:
    stats = graph["stats"]
    lines = [
        "# BrainGain Graphify Pack",
        "",
        "This folder is the high-signal project map for LLM consumption.",
        "",
        "## Project Shape",
        f"- files indexed: {stats['file_count']}",
        f"- directories indexed: {stats['directory_count']}",
        f"- symbols indexed: {stats['symbol_count']}",
        f"- graph edges: {stats['total_edges']}",
        "",
        "## Key Files",
    ]
    for file_path in stats["important_files"]:
        lines.append(f"- `{file_path}`")
    lines.extend(
        [
            "",
            "## Primary Domains",
            "- backend API and orchestration in `api/`",
            "- database schema/bootstrap in `api/database.py` and `database_schema.md`",
            "- admin and student UI in `web/`",
            "- prompts and ingestion assets in `prompts/`, `Books/`, and `OCR_Output/`",
            "",
            "## Use With An LLM",
            "1. Read `llm_context.md` first.",
            "2. Inspect `graph.json` for concrete file, symbol, and import relationships.",
            "3. Open raw files only after locating the relevant nodes here.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_llm_context(graph: dict[str, object]) -> str:
    file_nodes = [node for node in graph["nodes"] if node["kind"] == "file"]
    doc_files = [node["path"] for node in file_nodes if str(node["path"]).endswith(".md")]
    python_files = [node["path"] for node in file_nodes if str(node["path"]).endswith(".py")]
    web_files = [node["path"] for node in file_nodes if "/web/" in f"/{node['path']}"]
    lines = [
        "# LLM Context For BrainGain",
        "",
        "Start here before reading raw project files.",
        "",
        "## What BrainGain Is",
        "BrainGain is a FastAPI + SQLite prototype for question-bank ingestion, published test generation, and student attempts.",
        "",
        "## Where To Look First",
        "- App routes and workflow: `api/app.py`",
        "- DB schema/bootstrap: `api/database.py`",
        "- Canonical schema notes: `database_schema.md`",
        "- Product overview: `README.md`",
        "- System flow: `ARCHITECTURE.md`",
        "",
        "## Indexed Coverage",
        f"- python files: {len(python_files)}",
        f"- markdown/docs files: {len(doc_files)}",
        f"- web files: {len(web_files)}",
        "",
        "## Query Strategy",
        "- Use `graph.json` to find file and symbol nodes related to your task.",
        "- Follow `contains`, `defines`, and `imports` edges before opening source files.",
        "- Treat PDFs and media as metadata nodes unless you need the raw asset.",
        "",
        "## Important Paths",
    ]
    for path in sorted(set(doc_files + python_files[:8] + web_files[:8]))[:20]:
        lines.append(f"- `{path}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    graph = build_graph()
    (OUTPUT_DIR / "graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "project_map.md").write_text(build_project_map(graph), encoding="utf-8")
    (OUTPUT_DIR / "llm_context.md").write_text(build_llm_context(graph), encoding="utf-8")


if __name__ == "__main__":
    main()
