"""Structural call-graph reasoning (issue #39).

A faithful Python port of the chiasmus call-graph engine
(https://github.com/yogthos/chiasmus, `src/graph/`), scoped to what the four
shipped #39 integration points need. Builds a precomputed CodeGraph from
tree-sitter extraction and answers callers / callees / reachability / path /
impact / cycles / dead-code / entry-points natively (O(V+E), no solver), with a
per-file-hash cache for incremental recompute. Prolog facts are emitted (facts.py)
for the optional Phase 5 solver layer.

Provenance (ported behavior-for-behavior):
  types.py    <- src/graph/types.ts
  extract.py  <- src/graph/extractor.ts (walkPython)
  analyses.py <- src/graph/native-analyses.ts + entry-points.ts
  facts.py    <- src/graph/facts.ts
  resolve.py  <- src/graph/suffix-index.ts (adapted to Python modules)
  cache.py    <- src/graph/cache.ts (in-process)

See docs/reports/CALL_GRAPH_REASONING_V3.md.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .types import (
    CodeGraph,
    DefinesFact,
    CallsFact,
    ImportsFact,
    ExportsFact,
    ContainsFact,
    FileNode,
)
from .extract import extract_file, is_python, available as extraction_available
from .resolve import resolve_imports
from .cache import FileGraphCache, default_cache, file_hash
from .analyses import (
    callers,
    callees,
    reachability,
    path,
    impact,
    cycles,
    dead_code,
    detect_entry_points,
    run_analysis,
)
from .facts import graph_to_prolog, escape_atom
from .resolve_calls import unresolved_calls, direct_call_names
from .flags import call_graph_enabled, ENV_VAR as CALL_GRAPH_ENV_VAR


def build_graph(file_map: Dict[str, str], cache: Optional[FileGraphCache] = None) -> CodeGraph:
    """Build a project CodeGraph from {rel_path: content}.

    Only Python files contribute today. Per-file extraction is cached on a
    content hash (incremental recompute), then imports are resolved across the
    whole batch. Pass a FileGraphCache to reuse extraction across calls; omit it
    for a one-shot (uses the process-default cache)."""
    cache = cache or default_cache()
    graph = CodeGraph()
    py_paths: List[str] = []
    for rel, content in file_map.items():
        if not is_python(rel):
            continue
        py_paths.append(rel)
        graph.merge(cache.get_or_extract(rel, content))
    resolve_imports(graph, py_paths)
    return graph


__all__ = [
    "CodeGraph", "DefinesFact", "CallsFact", "ImportsFact", "ExportsFact",
    "ContainsFact", "FileNode",
    "extract_file", "is_python", "extraction_available",
    "resolve_imports",
    "FileGraphCache", "default_cache", "file_hash",
    "callers", "callees", "reachability", "path", "impact", "cycles",
    "dead_code", "detect_entry_points", "run_analysis",
    "graph_to_prolog", "escape_atom",
    "unresolved_calls", "direct_call_names",
    "call_graph_enabled", "CALL_GRAPH_ENV_VAR",
    "build_graph",
]
