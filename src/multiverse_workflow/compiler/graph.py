from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from multiverse_workflow.protocol.diagnostics import Diagnostic


def node_edges(node_id: str, node: Any) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    node_type = node.type
    if node_type in {"call", "workflow", "parallel", "repeat"}:
        edges.append((node_id, node.next))
    elif node_type == "switch":
        edges.extend((node_id, case.next) for case in node.cases)
        edges.append((node_id, node.default))
    if node.on_error is not None:
        edges.append((node_id, node.on_error))
    return edges


def graph_edges(nodes: Mapping[str, Any]) -> list[tuple[str, str]]:
    return [edge for node_id, node in nodes.items() for edge in node_edges(node_id, node)]


def validate_graph(nodes: Mapping[str, Any], entry: str, file: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    edges = graph_edges(nodes)
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for source, target in edges:
        if target not in nodes:
            diagnostics.append(
                Diagnostic(
                    code="INVALID_EDGE",
                    file=file,
                    pointer=f"/spec/nodes/{_escape(source)}/next",
                    message=f"节点 {source} 指向不存在的节点 {target}。",
                    suggestion="将边指向已定义节点。",
                )
            )
            continue
        adjacency[source].append(target)

    if entry not in nodes:
        diagnostics.append(
            Diagnostic(
                code="INVALID_ENTRY",
                file=file,
                pointer="/spec/entry",
                message=f"入口节点不存在：{entry}。",
            )
        )
        return diagnostics

    reachable = _reachable(adjacency, entry)
    for node_id in nodes:
        if node_id not in reachable:
            diagnostics.append(
                Diagnostic(
                    code="UNREACHABLE_NODE",
                    file=file,
                    pointer=f"/spec/nodes/{_escape(node_id)}",
                    message=f"节点不可从入口到达：{node_id}。",
                )
            )
            break

    cycle = _find_cycle(adjacency)
    if cycle:
        diagnostics.append(
            Diagnostic(
                code="GRAPH_CYCLE",
                file=file,
                pointer=f"/spec/nodes/{_escape(cycle[0])}",
                message=f"同级 Workflow 图包含环：{' -> '.join(cycle)}。",
                suggestion="使用 repeat 表达有界循环。",
            )
        )

    end_nodes = {node_id for node_id, node in nodes.items() if node.type == "end"}
    if not end_nodes:
        diagnostics.append(
            Diagnostic(
                code="NO_TERMINAL_NODE",
                file=file,
                pointer="/spec/nodes",
                message="Workflow 必须至少包含一个 end 节点。",
            )
        )
    else:
        for node_id in reachable:
            if not _can_reach_end(node_id, adjacency, end_nodes):
                diagnostics.append(
                    Diagnostic(
                        code="PATH_WITHOUT_END",
                        file=file,
                        pointer=f"/spec/nodes/{_escape(node_id)}",
                        message=f"节点存在无法到达 end 的路径：{node_id}。",
                    )
                )
                break
    return diagnostics


def _reachable(adjacency: Mapping[str, Iterable[str]], entry: str) -> set[str]:
    result: set[str] = set()
    stack = [entry]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(adjacency.get(current, []))
    return result


def _find_cycle(adjacency: Mapping[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(node_id: str) -> list[str] | None:
        if node_id in visiting:
            start = path.index(node_id)
            return path[start:] + [node_id]
        if node_id in visited:
            return None
        visiting.add(node_id)
        path.append(node_id)
        for target in adjacency.get(node_id, []):
            cycle = visit(target)
            if cycle:
                return cycle
        path.pop()
        visiting.remove(node_id)
        visited.add(node_id)
        return None

    for node_id in adjacency:
        cycle = visit(node_id)
        if cycle:
            return cycle
    return None


def _can_reach_end(node_id: str, adjacency: Mapping[str, list[str]], end_nodes: set[str]) -> bool:
    return bool(_reachable(adjacency, node_id) & end_nodes)


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
