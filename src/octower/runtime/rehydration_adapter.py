"""Real R11 backend-restart rehydration composition."""

from __future__ import annotations

from typing import Final

import anyio

from octower.adapters.native_opencode import NativeOpenCodeAdapter
from octower.api.opencode import OpenCodeClient
from octower.discovery.reconciliation import SessionReconciler
from octower.models import AgentState, SessionEvidence
from octower.recovery.journal import RecoveryJournal
from octower.state.classifier import AgentStateClassifier
from octower.supervisor.rehydration import RehydratedSession, RootRestoreState


_EVIDENCE_ATTEMPTS: Final = 4
_EVIDENCE_RETRY_SECONDS: Final = 20.0
_RESUME_PROMPT: Final = "Continue your work."


class RehydrationAdapter:
    """Compose existing discovery, evidence, journal, and classifier APIs (§12)."""

    def __init__(
        self,
        client: OpenCodeClient,
        reconciler: SessionReconciler,
        classifier: AgentStateClassifier,
        journal: RecoveryJournal,
        root_session_id: str,
    ) -> None:
        self._client = client
        self._reconciler = reconciler
        self._classifier = classifier
        self._journal = journal
        self._root_session_id = root_session_id
        self._evidence = NativeOpenCodeAdapter(client)

    async def reenumerate_sessions(self) -> tuple[str, ...]:
        sessions = await anyio.to_thread.run_sync(self._client.list_sessions)
        return tuple(session.id for session in sessions)

    async def restore_root(
        self, root_id: str, sessions: tuple[str, ...]
    ) -> RootRestoreState:
        if root_id not in sessions or root_id != self._root_session_id:
            return RootRestoreState.MISSING
        diff = await anyio.to_thread.run_sync(self._reconciler.reconcile)
        if diff.degraded:
            return RootRestoreState.DEGRADED
        if diff.root_exists is False:
            return RootRestoreState.MISSING
        return RootRestoreState.READY

    async def reload_journal(self) -> tuple[str, ...]:
        records = await anyio.to_thread.run_sync(self._journal.read)
        return tuple(dict.fromkeys(record.session_id for record in records))

    async def reclassify(
        self, sessions: tuple[str, ...], recovering_sessions: tuple[str, ...]
    ) -> tuple[RehydratedSession, ...]:
        recovering = frozenset(recovering_sessions)
        classified: list[RehydratedSession] = []
        for session_id in sessions:
            evidence = await self._refetch_evidence(session_id)
            initial = self._classifier.classify(evidence)
            prior_state = (
                AgentState.RECOVERING if session_id in recovering else initial.state
            )
            current = self._classifier.classify(evidence, prior_state)
            classified.append(
                RehydratedSession(
                    session_id,
                    prior_state,
                    current.state,
                    not current.completion.terminal,
                )
            )
        return tuple(classified)

    async def resume(self, session_id: str) -> None:
        await anyio.to_thread.run_sync(
            self._client.prompt_async, session_id, _RESUME_PROMPT
        )

    async def _refetch_evidence(self, session_id: str) -> SessionEvidence:
        for attempt in range(_EVIDENCE_ATTEMPTS):
            evidence = await anyio.to_thread.run_sync(
                self._evidence.get_evidence, session_id
            )
            if _evidence_healthy(evidence) or attempt == _EVIDENCE_ATTEMPTS - 1:
                return evidence
            await anyio.sleep(_EVIDENCE_RETRY_SECONDS)
        raise AssertionError("evidence retry loop did not return")


def _evidence_healthy(evidence: SessionEvidence) -> bool:
    return (
        evidence.backend_available
        and evidence.api_healthy
        and evidence.semantic_data_complete
        and evidence.data_consistent
    )
