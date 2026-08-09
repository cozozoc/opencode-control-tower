"""Injected read models for the handoff §26-§27 Textual control room."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import anyio

from octower.discovery.tree import SessionTree
from octower.models import AgentState, SessionEvidence, SessionNode
from octower.omo.doctor import DoctorReport
from octower.recovery.journal import RecoveryJournal, RecoveryRecord
from octower.state.classifier import AgentStateClassifier


@dataclass(frozen=True, slots=True)
class AgentSnapshot:
    """Immutable card and detail data keyed by OpenCode session ID."""

    session_id: str
    parent_id: str | None
    title: str
    state: AgentState
    output_preview: str
    output_history: tuple[str, ...] = ()
    state_history: tuple[AgentState, ...] = ()


@dataclass(frozen=True, slots=True)
class BoardSnapshot:
    """One coherent board refresh applied as an incremental UI transaction."""

    agents: tuple[AgentSnapshot, ...]

    @property
    def done_count(self) -> int:
        return sum(agent.state is AgentState.DONE for agent in self.agents)


class BoardEvent(str, Enum):
    """SSE-derived invalidation signal; payload reads remain pull-based."""

    REFRESH = "refresh"


class BoardDataSource(Protocol):
    """Fully injectable asynchronous boundary used by the Textual app."""

    async def fetch_board(self) -> BoardSnapshot: ...

    async def fetch_agent(self, session_id: str) -> AgentSnapshot | None: ...

    async def fetch_history(self) -> tuple[RecoveryRecord, ...]: ...

    async def fetch_doctor(self) -> DoctorReport: ...

    async def events(self) -> AsyncIterator[BoardEvent]: ...


@dataclass(frozen=True, slots=True)
class SessionObservation:
    """Reconciled discovery node plus classifier and visible output evidence."""

    node: SessionNode
    evidence: SessionEvidence
    output_history: tuple[str, ...] = ()


class CoreDataFeeds(Protocol):
    """Adapters that reconcile OpenCode/OmO observations without UI coupling."""

    async def reconcile(self) -> tuple[SessionObservation, ...]: ...

    async def doctor_report(self) -> DoctorReport: ...

    async def events(self) -> AsyncIterator[BoardEvent]: ...


class CoreBoardDataSource:
    """Compose discovery, classification, journal, and doctor layers for Phase 7."""

    def __init__(
        self,
        root_session_id: str,
        feeds: CoreDataFeeds,
        classifier: AgentStateClassifier,
        journal: RecoveryJournal,
    ) -> None:
        self._root_session_id = root_session_id
        self._feeds = feeds
        self._classifier = classifier
        self._journal = journal
        self._agents: dict[str, AgentSnapshot] = {}

    async def fetch_board(self) -> BoardSnapshot:
        observations = await self._feeds.reconcile()
        observation_by_id = {
            observation.node.session_id: observation for observation in observations
        }
        tree = SessionTree.from_nodes(
            self._root_session_id,
            (observation.node for observation in observations),
        )
        ordered_ids = [self._root_session_id]
        ordered_ids.extend(node.session_id for node in tree.descendants())
        ordered_ids.extend(
            session_id for session_id in observation_by_id if session_id not in ordered_ids
        )
        refreshed: dict[str, AgentSnapshot] = {}
        for session_id in ordered_ids:
            observation = observation_by_id.get(session_id)
            if observation is None:
                continue
            previous = self._agents.get(session_id)
            prior_state = previous.state if previous is not None else AgentState.DISCOVERED
            state = self._classifier.classify(observation.evidence, prior_state).state
            state_history = previous.state_history if previous is not None else ()
            if not state_history or state_history[-1] is not state:
                state_history = (*state_history, state)
            output = observation.output_history[-1] if observation.output_history else "No output yet"
            refreshed[session_id] = AgentSnapshot(
                session_id,
                observation.node.parent_id,
                observation.node.title or session_id,
                state,
                output,
                observation.output_history,
                state_history,
            )
        self._agents = refreshed
        return BoardSnapshot(tuple(refreshed.values()))

    async def fetch_agent(self, session_id: str) -> AgentSnapshot | None:
        agent = self._agents.get(session_id)
        if agent is not None:
            return agent
        await self.fetch_board()
        return self._agents.get(session_id)

    async def fetch_history(self) -> tuple[RecoveryRecord, ...]:
        return await anyio.to_thread.run_sync(self._journal.read)

    async def fetch_doctor(self) -> DoctorReport:
        return await self._feeds.doctor_report()

    async def events(self) -> AsyncIterator[BoardEvent]:
        async for event in self._feeds.events():
            yield event
