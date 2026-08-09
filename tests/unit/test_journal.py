from octower.recovery.journal import RecoveryJournal, RecoveryPhase


def test_journal_persists_schema_and_replays_active_transactions(tmp_path) -> None:
    journal = RecoveryJournal(tmp_path / "recovery.jsonl")
    intent = journal.start(
        session_id="ses-child",
        root_session_id="ses-root",
        parent_id="ses-parent",
        reason="confirmed_silent_stall_15m",
        attempt=1,
        created_at=10.0,
        last_activity_before=0.0,
        adapter="fake",
    )
    aborted = journal.advance(intent, RecoveryPhase.ABORT_REQUESTED, 11.0)

    records = journal.read()

    assert [record.phase for record in records] == [RecoveryPhase.INTENT, RecoveryPhase.ABORT_REQUESTED]
    assert records[0].session_id == "ses-child"
    assert records[0].root_session_id == "ses-root"
    assert records[0].parent_id == "ses-parent"
    assert journal.active() == (aborted,)


def test_journal_excludes_terminal_recoveries_and_tracks_parent_wakes(tmp_path) -> None:
    journal = RecoveryJournal(tmp_path / "recovery.jsonl")
    intent = journal.start(
        session_id="ses-parent",
        root_session_id="ses-root",
        parent_id=None,
        reason="all_relevant_children_terminal",
        attempt=0,
        created_at=5.0,
        last_activity_before=0.0,
        adapter="fake",
    )
    journal.advance(intent, RecoveryPhase.PARENT_WAKE_REQUESTED, 6.0)

    assert journal.active("ses-parent") == ()
    assert journal.has_parent_wake("ses-parent") is True
