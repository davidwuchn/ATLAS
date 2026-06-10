"""Tree-sitter extraction: Python source → CodeGraph facts.

Mirrors the `walkPython` extractor in chiasmus `src/graph/extractor.ts`,
reimplemented on the Python tree-sitter bindings that v3-service already
depends on (tree_sitter + tree_sitter_python). Emits defines / calls / imports /
exports / contains facts. Python-first (issue #39); other languages plug in via
the same shape later.

Extraction is best-effort: if tree-sitter is unavailable or a file fails to
parse, that file contributes nothing rather than raising.
"""

from __future__ import annotations

import re
from typing import List, Optional, Set

from .types import (
    CallsFact,
    CodeGraph,
    ContainsFact,
    DefinesFact,
    ExportsFact,
    FileNode,
    ImportsFact,
)

try:
    import tree_sitter as _ts
    import tree_sitter_python as _tsp

    _PY_LANG = _ts.Language(_tsp.language())
    _AVAILABLE = True
except Exception:  # pragma: no cover - exercised only where grammar is absent
    _PY_LANG = None
    _AVAILABLE = False


def available() -> bool:
    return _AVAILABLE


def _text(node) -> str:
    t = node.text
    return t.decode("utf-8", "replace") if isinstance(t, (bytes, bytearray)) else str(t)


def _collapse_signature(sig: str) -> str:
    return re.sub(r"\s+", " ", sig).strip()


def _extract_python_signature(node) -> Optional[str]:
    params = node.child_by_field_name("parameters")
    if params is None:
        return None
    sig = _text(params)
    ret = node.child_by_field_name("return_type")
    if ret is not None:
        sig += " -> " + _text(ret)
    return _collapse_signature(sig)


def _find_enclosing_class(node) -> Optional[str]:
    current = node.parent
    while current is not None:
        if current.type == "class_definition":
            name = current.child_by_field_name("name")
            return _text(name) if name is not None else None
        current = current.parent
    return None


def _resolve_callee(call_node) -> Optional[str]:
    fn = call_node.child_by_field_name("function")
    if fn is None:
        return None
    if fn.type == "identifier":
        return _text(fn)
    if fn.type == "attribute":
        # obj.method() -> method (bare name, matching chiasmus)
        attr = fn.child_by_field_name("attribute")
        return _text(attr) if attr is not None else None
    return None


def _walk(node, file_path: str, scope: List[str], g: CodeGraph, call_set: Set[str]) -> None:
    t = node.type

    if t == "function_definition":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            name = _text(name_node)
            enclosing = _find_enclosing_class(node)
            kind = "method" if enclosing else "function"
            g.defines.append(DefinesFact(
                file=file_path, name=name, kind=kind,
                line=node.start_point[0] + 1,
                signature=_extract_python_signature(node),
            ))
            if enclosing:
                g.contains.append(ContainsFact(parent=enclosing, child=name))
            scope.append(name)
            for i in range(node.child_count):
                _walk(node.child(i), file_path, scope, g, call_set)
            scope.pop()
            return

    elif t == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            name = _text(name_node)
            g.defines.append(DefinesFact(
                file=file_path, name=name, kind="class",
                line=node.start_point[0] + 1,
            ))
            scope.append(name)
            for i in range(node.child_count):
                _walk(node.child(i), file_path, scope, g, call_set)
            scope.pop()
            return

    elif t == "call":
        callee = _resolve_callee(node)
        caller = scope[-1] if scope else None
        if callee and caller:
            key = f"{caller}->{callee}"
            if key not in call_set:
                call_set.add(key)
                g.calls.append(CallsFact(caller=caller, callee=callee))
        # fall through to children to catch nested calls in args

    elif t == "import_statement":
        for i in range(node.child_count):
            child = node.child(i)
            if child.type == "dotted_name":
                txt = _text(child)
                g.imports.append(ImportsFact(file=file_path, name=txt, source=txt))
            elif child.type == "aliased_import":
                dotted = child.child_by_field_name("name")
                if dotted is not None:
                    alias_node = child.child_by_field_name("alias")
                    alias = _text(alias_node) if alias_node is not None else _text(dotted)
                    g.imports.append(ImportsFact(file=file_path, name=alias, source=_text(dotted)))
        return

    elif t == "import_from_statement":
        module_node = node.child_by_field_name("module_name")
        source = _text(module_node) if module_node is not None else ""
        # `from mod import *` -> record a wildcard so the veto can resolve it to
        # the module's actual exports (or stay lenient if the module is opaque).
        if any(node.child(i).type == "wildcard_import" for i in range(node.child_count)):
            g.imports.append(ImportsFact(file=file_path, name="*", source=source))
            return
        name_node = node.child_by_field_name("name")
        if name_node is not None and name_node.type in ("dotted_name", "identifier"):
            g.imports.append(ImportsFact(file=file_path, name=_text(name_node), source=source))
        for i in range(node.child_count):
            child = node.child(i)
            if child.type == "dotted_name" and child != module_node and child != name_node:
                g.imports.append(ImportsFact(file=file_path, name=_text(child), source=source))
            elif child.type == "aliased_import":
                imp = child.child_by_field_name("name")
                alias = child.child_by_field_name("alias")
                if imp is not None:
                    nm = _text(alias) if alias is not None else _text(imp)
                    g.imports.append(ImportsFact(file=file_path, name=nm, source=source))
        return

    for i in range(node.child_count):
        _walk(node.child(i), file_path, scope, g, call_set)


def _module_exports(g: CodeGraph, file_path: str) -> None:
    """Python has no explicit export syntax; treat top-level (non-method)
    defines as the file's exported names so entry-point / dead-code analysis
    has a sensible default set."""
    methods = {d.name for d in g.defines if d.file == file_path and d.kind == "method"}
    seen: Set[str] = set()
    for d in g.defines:
        if d.file != file_path or d.kind == "method":
            continue
        if d.name in seen:
            continue
        seen.add(d.name)
        g.exports.append(ExportsFact(file=file_path, name=d.name))
    # methods captured above only to exclude them; reference to satisfy linters
    _ = methods


def extract_file(file_path: str, content: str) -> CodeGraph:
    """Extract a CodeGraph for a single Python file. Returns an empty graph when
    tree-sitter is unavailable or the source cannot be parsed."""
    g = CodeGraph()
    if not _AVAILABLE or not content:
        return g
    try:
        parser = _ts.Parser(_PY_LANG)
        tree = parser.parse(bytes(content, "utf-8"))
    except Exception:
        return g
    # Best-effort: a deeply nested file can blow the recursion limit in _walk;
    # if extraction fails partway, that file contributes nothing rather than
    # taking down the whole batch (per the module contract).
    try:
        walk_graph = CodeGraph()
        _walk(tree.root_node, file_path, [], walk_graph, set())
    except Exception:  # incl. RecursionError on pathologically deep files
        return g
    g.merge(walk_graph)
    g.files.append(FileNode(path=file_path, language="python",
                            line_count=content.count("\n") + 1))
    _module_exports(g, file_path)
    return g


def is_python(path: str) -> bool:
    return path.endswith((".py", ".pyi", ".pyx"))
