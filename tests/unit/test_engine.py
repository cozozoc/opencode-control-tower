from dataclasses import replace

from conftest import evidence

from octower.models import AgentState
from octower.recovery.engine import RECOVERY_ACTIVITY_TIMEOUT, RecoveryEngine
from octower.recovery.journal import RecoveryJournal, RecoveryPhase


class RecordingActions:
    def __init__(self, current) -> None:
        self.current = current
        self.aborts: list[str] = []
        self.prompts: list[tuple[str, str]] = []
        self.validations: list[str] = []

    def abort_session(self, session_id: str) -> bool:
        self.aborts.append(session_id)
        self.current = replace(self.current, status="idle")
        return True

    def prompt_async(self, session_id: str, text: str) -> bool:
        self.prompts.append((session_id, text))
        return True

    def validate_session(self, session_id: str) -> bool:
        self.validations.append(session_id)
        return True

    def get_evidence(self, session_id: str):
        assert session_id == self.current.session_id
        return self.current


def make_engine(tmp_path, clock, current):
    actions = RecordingActions(current)
    journal = RecoveryJournal(tmp_path / "recovery.jsonl")
    return RecoveryEngine(actions, journal, clock), actions, journal


def test_case_d_idle_unfinished_soft_resumes_without_abort(tmp_path, clock) -> None:
    clock.advance_minutes(11)
    engine, actions, journal = make_engine(tmp_path, clock, evidence(status="idle"))

    result = engine.soft_resume("ses-child")

    assert result.state is AgentState.RECOVERING
    assert actions.aborts == []
    assert [session_id for session_id, _ in actions.prompts] == ["ses-child"]
    assert RecoveryPhase.RESUME_REQUESTED in [record.phase for record in journal.read()]


def test_case_e_hard_stall_aborts_and_recovers_same_session_after_activity(tmp_path, clock) -> None:
    engine, actions, journal = make_engine(tmp_path, clock, evidence(status="busy"))

    recovering = engine.hard_resume("ses-child", root_session_id="ses-root", parent_id="ses-parent")
    clock.advance(1)
    actions.current = replace(actions.current, last_semantic_activity=clock.now())
    recovered = engine.poll("ses-child")

    assert recovering.state is AgentState.RECOVERING
    assert recovered.state is AgentState.RUNNING
    assert actions.aborts == ["ses-child"]
    assert [session_id for session_id, _ in actions.prompts] == ["ses-child"]
    assert [record.phase for record in journal.read()] == [
        RecoveryPhase.INTENT,
        RecoveryPhase.ABORT_REQUESTED,
        RecoveryPhase.ABORT_CONFIRMED,
        RecoveryPhase.SESSION_REVALIDATED,
        RecoveryPhase.RESUME_REQUESTED,
        RecoveryPhase.RECOVERING,
        RecoveryPhase.ACTIVITY_CONFIRMED,
        RecoveryPhase.RECOVERED,
    ]


def test_case_f_replay_after_abort_resumes_once_without_second_abort(tmp_path, clock) -> None:
    engine, actions, journal = make_engine(tmp_path, clock, evidence(status="idle"))
    intent = journal.start(
        session_id="ses-child", root_session_id="ses-root", parent_id=None,
        reason="confirmed_silent_stall_15m", attempt=1, created_at=clock.now(),
        last_activity_before=0.0, adapter="fake",
    )
    requested = journal.advance(intent, RecoveryPhase.ABORT_REQUESTED, clock.now())
    journal.advance(requested, RecoveryPhase.ABORT_CONFIRMED, clock.now())

    results = engine.replay()

    assert results[0].state is AgentState.RECOVERING
    assert actions.aborts == []
    assert [session_id for session_id, _ in actions.prompts] == ["ses-child"]


def test_case_g_replay_after_prompt_does_not_duplicate_when_activity_exists(tmp_path, clock) -> None:
    engine, actions, journal = make_engine(tmp_path, clock, evidence(status="idle"))
    intent = journal.start(
        session_id="ses-child", root_session_id="ses-root", parent_id=None,
        reason="confirmed_silent_stall_15m", attempt=1, created_at=clock.now(),
        last_activity_before=0.0, adapter="fake",
    )
    validated = journal.advance(intent, RecoveryPhase.SESSION_REVALIDATED, clock.now())
    journal.advance(validated, RecoveryPhase.RESUME_REQUESTED, clock.now())
    clock.advance(1)
    actions.current = replace(actions.current, last_semantic_activity=clock.now())

    results = engine.replay()

    assert results[0].state is AgentState.RUNNING
    assert actions.aborts == []
    assert actions.prompts == []


def test_repeated_polls_do_not_duplicate_abort_or_prompt(tmp_path, clock) -> None:
    engine, actions, _ = make_engine(tmp_path, clock, evidence(status="busy"))

    engine.hard_resume("ses-child")
    engine.hard_resume("ses-child")
    engine.poll("ses-child")

    assert actions.aborts == ["ses-child"]
    assert len(actions.prompts) == 1


def test_timeout_retries_once_then_exhausts_attempt_budget(tmp_path, clock) -> None:
    engine, actions, _ = make_engine(tmp_path, clock, evidence(status="busy"))

    engine.hard_resume("ses-child")
    actions.current = replace(actions.current, status="busy")
    clock.advance(RECOVERY_ACTIVITY_TIMEOUT + 1)
    engine.poll("ses-child")
    actions.current = replace(actions.current, status="busy")
    clock.advance(RECOVERY_ACTIVITY_TIMEOUT + 1)
    exhausted = engine.poll("ses-child")
    third = engine.hard_resume("ses-child")

    assert actions.aborts == ["ses-child", "ses-child"]
    assert len(actions.prompts) == 2
    assert exhausted.state is AgentState.FAILED_RECOVERY
    assert third.state is AgentState.FAILED_RECOVERY
