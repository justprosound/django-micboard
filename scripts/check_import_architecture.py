#!/usr/bin/env python3
"""Detect internal import cycles and enforce Micboard dependency direction."""

from __future__ import annotations

import argparse
import ast
import sys
from collections import deque
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path


@dataclass(frozen=True, order=True)
class ImportEdge:
    """One statically discoverable import between modules in the package."""

    source: str
    target: str
    path: Path
    line: int


@dataclass(frozen=True)
class ImportArchitectureReport:
    """Internal imports plus any direction or cycle violations."""

    modules: tuple[str, ...]
    edges: tuple[ImportEdge, ...]
    forbidden_edges: tuple[ImportEdge, ...]
    cycles: tuple[tuple[str, ...], ...]

    @property
    def is_valid(self) -> bool:
        """Return whether the package follows the enforced architecture."""
        return not self.forbidden_edges and not self.cycles


type ImportGraph = dict[str, set[str]]


def _module_name(*, path: Path, package_root: Path, package_name: str) -> str:
    """Convert a file path to its fully qualified Python module name."""
    relative = path.relative_to(package_root)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join((package_name, *parts)) if parts else package_name


def _resolve_module(candidate: str, modules: set[str]) -> str | None:
    """Resolve an imported symbol or module to the longest local module prefix."""
    current = candidate
    while current:
        if current in modules:
            return current
        current = current.rpartition(".")[0]
    return None


def _relative_import_base(*, source: str, is_package: bool, node: ast.ImportFrom) -> str:
    """Resolve the base module path for a relative import AST node."""
    package = source if is_package else source.rpartition(".")[0]
    package_parts = package.split(".") if package else []
    keep = len(package_parts) - node.level + 1
    if keep <= 0:
        return ""
    prefix = ".".join(package_parts[:keep])
    return ".".join(part for part in (prefix, node.module or "") if part)


def _import_candidates(
    *,
    source: str,
    is_package: bool,
    node: ast.Import | ast.ImportFrom,
) -> tuple[str, ...]:
    """Extract all potential target module names from an import AST node."""
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)

    if node.level:
        base = _relative_import_base(source=source, is_package=is_package, node=node)
    else:
        base = node.module or ""

    candidates = [base] if base else []
    candidates.extend(
        ".".join(part for part in (base, alias.name) if part)
        for alias in node.names
        if alias.name != "*"
    )
    return tuple(candidates)


def build_import_graph(
    package_root: Path,
    *,
    package_name: str | None = None,
) -> tuple[ImportGraph, tuple[ImportEdge, ...]]:
    """Parse a Python package and return its internal static import graph."""
    package_root = package_root.resolve()
    package_name = package_name or package_root.name
    module_paths = {
        _module_name(path=path, package_root=package_root, package_name=package_name): path
        for path in package_root.rglob("*.py")
    }
    modules = set(module_paths)
    graph: ImportGraph = {module: set() for module in modules}
    edges: set[ImportEdge] = set()

    for source, path in module_paths.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        is_package = path.name == "__init__.py"
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            for candidate in _import_candidates(
                source=source,
                is_package=is_package,
                node=node,
            ):
                if candidate != package_name and not candidate.startswith(f"{package_name}."):
                    continue
                target = _resolve_module(candidate, modules)
                if target is None or target == source:
                    continue
                graph[source].add(target)
                edges.add(
                    ImportEdge(
                        source=source,
                        target=target,
                        path=path,
                        line=node.lineno,
                    )
                )

    return graph, tuple(sorted(edges))


class _ComponentFinder:
    """Stateful graph traversal class implementing Tarjan's strongly connected components algorithm."""

    def __init__(self, graph: ImportGraph) -> None:
        """Initialize the finder with the provided import graph."""
        self.graph = graph
        self.index = 0
        self.indices: dict[str, int] = {}
        self.lowlinks: dict[str, int] = {}
        self.stack: list[str] = []
        self.on_stack: set[str] = set()
        self.components: list[tuple[str, ...]] = []

    def find(self) -> tuple[tuple[str, ...], ...]:
        """Execute Tarjan's algorithm to find all strongly connected components in the graph."""
        for module in sorted(self.graph):
            if module not in self.indices:
                self._visit(module)
        return tuple(sorted(self.components, key=lambda component: (-len(component), component)))

    def _visit(self, module: str) -> None:
        """Recursively visit nodes to compute index and lowlink values for cycle detection."""
        self.indices[module] = self.index
        self.lowlinks[module] = self.index
        self.index += 1
        self.stack.append(module)
        self.on_stack.add(module)

        for target in sorted(self.graph[module]):
            if target not in self.indices:
                self._visit(target)
                self.lowlinks[module] = min(self.lowlinks[module], self.lowlinks[target])
            elif target in self.on_stack:
                self.lowlinks[module] = min(self.lowlinks[module], self.indices[target])

        if self.lowlinks[module] != self.indices[module]:
            return
        component = self._pop_component(module)
        if len(component) > 1:
            self.components.append(tuple(sorted(component)))

    def _pop_component(self, root: str) -> list[str]:
        """Pop nodes from the stack to form a strongly connected component."""
        component: list[str] = []
        while True:
            module = self.stack.pop()
            self.on_stack.remove(module)
            component.append(module)
            if module == root:
                return component


def _strongly_connected_components(graph: ImportGraph) -> tuple[tuple[str, ...], ...]:
    """Find all strongly connected components (cycles) in the given import graph."""
    return _ComponentFinder(graph).find()


def _is_forbidden(edge: ImportEdge, *, package_name: str) -> bool:
    """Check if an import edge violates architectural layering constraints."""
    model_prefix = f"{package_name}.models"
    multitenancy_models = f"{package_name}.multitenancy.models"
    service_prefix = f"{package_name}.services"
    task_prefix = f"{package_name}.tasks"
    app_module = f"{package_name}.apps"

    source_is_model = edge.source == model_prefix or edge.source.startswith(f"{model_prefix}.")
    source_is_model = source_is_model or edge.source == multitenancy_models
    target_is_upper_layer = edge.target == service_prefix or edge.target.startswith(
        f"{service_prefix}."
    )
    target_is_upper_layer = target_is_upper_layer or edge.target == task_prefix
    target_is_upper_layer = target_is_upper_layer or edge.target.startswith(f"{task_prefix}.")
    if source_is_model and target_is_upper_layer:
        return True

    source_is_service = edge.source == service_prefix or edge.source.startswith(
        f"{service_prefix}."
    )
    target_is_task = edge.target == task_prefix or edge.target.startswith(f"{task_prefix}.")
    return source_is_service and (target_is_task or edge.target == app_module)


def analyze_import_architecture(
    package_root: Path,
    *,
    package_name: str | None = None,
) -> ImportArchitectureReport:
    """Return all cycle and dependency-direction violations for a package."""
    resolved_name = package_name or package_root.name
    graph, edges = build_import_graph(package_root, package_name=resolved_name)
    forbidden_edges = tuple(
        edge for edge in edges if _is_forbidden(edge, package_name=resolved_name)
    )
    return ImportArchitectureReport(
        modules=tuple(sorted(graph)),
        edges=edges,
        forbidden_edges=forbidden_edges,
        cycles=_strongly_connected_components(graph),
    )


def _path_within_component(
    *,
    graph: ImportGraph,
    start: str,
    destination: str,
    component: set[str],
) -> list[str] | None:
    """Find the shortest import path between two modules within a connected component using BFS."""
    queue: deque[list[str]] = deque([[start]])
    seen = {start}
    while queue:
        path = queue.popleft()
        module = path[-1]
        if module == destination:
            return path
        for target in sorted(graph[module] & component):
            if target not in seen:
                seen.add(target)
                queue.append([*path, target])
    return None


def _representative_cycle(component: tuple[str, ...], graph: ImportGraph) -> tuple[str, ...]:
    """Extract a simple cycle from a strongly connected component for reporting."""
    members = set(component)
    candidates: list[tuple[str, ...]] = []
    for source in component:
        for target in sorted(graph[source] & members):
            return_path = _path_within_component(
                graph=graph,
                start=target,
                destination=source,
                component=members,
            )
            if return_path is not None:
                candidates.append((source, *return_path))
    return min(candidates, key=lambda path: (len(path), path))


def format_report(report: ImportArchitectureReport) -> str:
    """Format violations with concrete import locations and cycle paths."""
    if report.is_valid:
        return (
            f"Import architecture OK: {len(report.modules)} modules, "
            f"{len(report.edges)} internal import edges"
        )

    lines = ["Import architecture violations:"]
    if report.forbidden_edges:
        lines.append("Forbidden dependency edges:")
        for edge in report.forbidden_edges:
            lines.append(f"  {edge.path}:{edge.line}: {edge.source} -> {edge.target}")

    if report.cycles:
        graph: ImportGraph = {module: set() for module in report.modules}
        locations: dict[tuple[str, str], ImportEdge] = {}
        for edge in report.edges:
            graph[edge.source].add(edge.target)
            locations.setdefault((edge.source, edge.target), edge)
        lines.append("Import cycles:")
        for component in report.cycles:
            cycle = _representative_cycle(component, graph)
            lines.append(f"  {len(component)}-module component; representative cycle:")
            for source, target in pairwise(cycle):
                edge = locations[(source, target)]
                lines.append(f"    {edge.path}:{edge.line}: {source} -> {target}")

    return "\n".join(lines)


def main() -> int:
    """Run the architecture check for a package supplied on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", nargs="?", type=Path, default=Path("micboard"))
    parser.add_argument("--package-name")
    arguments = parser.parse_args()

    report = analyze_import_architecture(
        arguments.package_root,
        package_name=arguments.package_name,
    )
    sys.stdout.write(f"{format_report(report)}\n")
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
