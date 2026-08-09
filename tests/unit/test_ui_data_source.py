from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import anyio

from octower.models import AgentState, SessionEvidence, SessionNode
from octower.omo.doctor import (
    DoctorReport,
    OpenCodeApiCompatibility,
    ServerHealth,
    TmuxIntegration,
)
from octower.omo.policy import OmoPolicyConflict
from octower.recovery.journal import RecoveryJournal, RecoveryPhase
from octower.state.classifier import AgentStateClassifier
from octower.ui.data_source import (
    BoardEvent,
    CoreBoardDataSource,
    SessionObservation,
)


class StaticClock:
    def now(self) -> float:
        return 0.0


class FakeCoreFeeds:
    async def reconcile(self) -> tuple[SessionObservation, ...]:
        return (
            SessionObservation(
                SessionNode("ses-root", title="Root"),
                SessionEvidence("ses-root", "busy", 0.0),
                ("orchestrating",),
            ),
            SessionObservation(
                SessionNode("ses-child", "ses-root", "Child"),
                SessionEvidence("ses-child", "busy", 0.0),
                ("working",),
            ),
            SessionObservation(
                SessionNode("ses-grandchild", "ses-child", "Grandchild"),
                SessionEvidence(
                    "ses-grandchild",
                    "idle",
                    0.0,
                    final_assistant_completed=True,
                ),
                ("complete",),
            ),
        )

    async def doctor_report(self) -> DoctorReport:
        return DoctorReport(
            "1.18.15",
            OpenCodeApiCompatibility.SUPPORTED,
            True,
            "4.19.4",
            Path("C:/omo.jsonc"),
            180_000,
            OmoPolicyConflict.CONFLICT_CRITICAL,
            TmuxIntegration.DISABLED,
            "ses-root",
            Path("C:/project"),
            ServerHealth.HEALTHY,
            ">=3.11",
            ">=0.80",
        )

    async def events(self) -> AsyncIterator[BoardEvent]:
        await anyio.sleep_forever()
        yield BoardEvent.REFRESH


def test_core_data_source_composes_tree_classifier_journal_and_doctor(tmp_path: Path) -> None:
    async def scenario() -> None:
        journal = RecoveryJournal(tmp_path / "recovery.jsonl")
        record = journal.start(
            session_id="ses-child",
            root_session_id="ses-root",
            parent_id="ses-root",
            reason="confirmed stall",
            attempt=1,
            created_at=10.0,
            last_activity_before=0.0,
            adapter="native",
        )
        journal.advance(record, RecoveryPhase.RECOVERING, 11.0)
        source = CoreBoardDataSource(
            "ses-root",
            FakeCoreFeeds(),
            AgentStateClassifier(StaticClock()),
            journal,
        )

        board = await source.fetch_board()
        history = await source.fetch_history()
        doctor = await source.fetch_doctor()

        assert [agent.session_id for agent in board.agents] == [
            "ses-root",
            "ses-child",
            "ses-grandchild",
        ]
        assert [agent.state for agent in board.agents] == [
            AgentState.RUNNING,
            AgentState.RUNNING,
            AgentState.DONE,
        ]
        assert board.done_count == 1
        assert history[-1].phase is RecoveryPhase.RECOVERING
        assert doctor.omo_conflict is OmoPolicyConflict.CONFLICT_CRITICAL

    anyio.run(scenario)
