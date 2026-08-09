"""Periodic API reconciliation that repairs missed OpenCode SSE discovery events (§8)."""

from __future__ import annotations

from dataclasses import dataclass

from octower.api.events import OpenCodeEvent
from octower.api.opencode import OpenCodeClient, OpenCodeError, Session
from octower.discovery.tree import SessionTree
from octower.models import SessionNode


@dataclass(frozen=True, slots=True)
class ReconciliationDiff:
    """Observable membership changes from one pure discovery reconciliation (§8)."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    root_exists: bool | None = True
    degraded: bool = False


class SessionReconciler:
    """Refresh a selected root's recursive session tree without taking recovery actions."""

    def __init__(self, root_id: str, client: OpenCodeClient, tree: SessionTree | None = None) -> None:
        self.root_id = root_id
        self._client = client
        self.tree = tree or SessionTree(root_id)

    def reconcile(self) -> ReconciliationDiff:
        """Use listing plus children reads to repair missed events and verify the root (§8)."""
        try:
            listed = {session.id: session for session in self._client.list_sessions()}
        except OpenCodeError:
            return ReconciliationDiff(root_exists=None, degraded=True)
        if self.root_id not in listed:
            return ReconciliationDiff(root_exists=False)
        desired = self._collect_descendants(listed)
        existing = {node.session_id: node for node in self.tree.nodes()}
        added = tuple(session_id for session_id in desired if session_id not in existing)
        updated = tuple(
            session_id
            for session_id, session in desired.items()
            if session_id in existing and _changed(existing[session_id], session)
        )
        removed = tuple(session_id for session_id in existing if session_id not in desired)
        for session in desired.values():
            self.tree.add(_node(session))
        removed_nodes: list[str] = []
        for session_id in removed:
            removed_nodes.extend(node.session_id for node in self.tree.remove(session_id))
        return ReconciliationDiff(added, tuple(removed_nodes), updated, True)

    def handle_event(self, event: OpenCodeEvent) -> bool:
        """Apply a ``session.created`` SSE event immediately when it belongs to this root (R1)."""
        if event.type != "session.created":
            return False
        session = _event_session(event)
        if session is None or not self._belongs_to_root(session):
            return False
        self.tree.add(_node(session))
        return True

    def _collect_descendants(self, listed: dict[str, Session]) -> dict[str, Session]:
        desired = {self.root_id: listed[self.root_id]}
        pending = [self.root_id]
        while pending:
            parent_id = pending.pop()
            try:
                children = self._client.get_children(parent_id)
            except OpenCodeError:
                children = [session for session in listed.values() if session.parent_id == parent_id]
            for child in children:
                if child.id not in desired:
                    desired[child.id] = child
                    pending.append(child.id)
        return desired

    def _belongs_to_root(self, session: Session) -> bool:
        if session.parent_id == self.root_id:
            return True
        parent = self.tree.get(session.parent_id or "")
        return parent is not None


def _node(session: Session) -> SessionNode:
    return SessionNode(session.id, session.parent_id, session.title)


def _changed(node: SessionNode, session: Session) -> bool:
    return node.parent_id != session.parent_id or node.title != session.title


def _event_session(event: OpenCodeEvent) -> Session | None:
    data = event.properties
    for key in ("session", "info"):
        candidate = event.properties.get(key)
        if isinstance(candidate, dict):
            data = candidate
            break
    if not isinstance(data.get("id"), str):
        return None
    return Session(
        id=data["id"],
        directory=str(data.get("directory", "")),
        title=str(data.get("title", "")),
        time=data.get("time") if isinstance(data.get("time"), dict) else None,
        parent_id=data.get("parentID") if isinstance(data.get("parentID"), str) else None,
    )
