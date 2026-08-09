"""In-memory parentID session tree supporting dynamic child discovery (R1, §8)."""

from __future__ import annotations

from collections.abc import Iterable

from octower.models import SessionNode


class SessionTree:
    """Maintain a recursive session tree as parentID observations arrive in any order."""

    def __init__(self, root_id: str) -> None:
        self.root_id = root_id
        self._nodes: dict[str, SessionNode] = {}

    @classmethod
    def from_nodes(cls, root_id: str, nodes: Iterable[SessionNode]) -> "SessionTree":
        """Build a tree from a batch while retaining the same dynamic-add behavior."""
        tree = cls(root_id)
        for node in nodes:
            tree.add(node)
        return tree

    def add(self, node: SessionNode) -> None:
        """Add or update a node and attach it when its parent is known (R1)."""
        existing = self._nodes.get(node.session_id)
        if existing is not None and existing.parent_id and existing.parent_id in self._nodes:
            self._nodes[existing.parent_id].child_ids.discard(node.session_id)
        node.child_ids = set(existing.child_ids) if existing is not None else set(node.child_ids)
        self._nodes[node.session_id] = node
        self._attach(node.session_id)
        for child_id, child in self._nodes.items():
            if child.parent_id == node.session_id:
                node.child_ids.add(child_id)
        self._ensure_acyclic(node.session_id)

    def get(self, session_id: str) -> SessionNode | None:
        """Return a known node without exposing a separate discovery mechanism."""
        return self._nodes.get(session_id)

    def remove(self, session_id: str) -> tuple[SessionNode, ...]:
        """Detach a node and all of its known descendants after a deletion event (§8)."""
        node = self._nodes.get(session_id)
        if node is None:
            return ()
        removed: list[SessionNode] = []
        for child_id in tuple(node.child_ids):
            removed.extend(self.remove(child_id))
        if node.parent_id and node.parent_id in self._nodes:
            self._nodes[node.parent_id].child_ids.discard(session_id)
        removed.append(self._nodes.pop(session_id))
        return tuple(removed)

    def nodes(self) -> tuple[SessionNode, ...]:
        """Return the known nodes for reconciliation without exposing mutable storage."""
        return tuple(self._nodes.values())

    def descendants(self, session_id: str | None = None) -> tuple[SessionNode, ...]:
        """Return recursive descendants in parent-before-child order (§8)."""
        start_id = self.root_id if session_id is None else session_id
        result: list[SessionNode] = []

        def visit(node_id: str) -> None:
            node = self._nodes.get(node_id)
            if node is None:
                return
            for child_id in sorted(node.child_ids):
                child = self._nodes.get(child_id)
                if child is not None:
                    result.append(child)
                    visit(child_id)

        visit(start_id)
        return tuple(result)

    def _attach(self, session_id: str) -> None:
        node = self._nodes[session_id]
        if node.parent_id and node.parent_id in self._nodes:
            self._nodes[node.parent_id].child_ids.add(session_id)

    def _ensure_acyclic(self, session_id: str) -> None:
        seen: set[str] = set()
        current_id: str | None = session_id
        while current_id is not None:
            if current_id in seen:
                raise ValueError("session parentID graph contains a cycle")
            seen.add(current_id)
            current = self._nodes.get(current_id)
            current_id = current.parent_id if current is not None else None
