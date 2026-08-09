from conftest import evidence

from octower.recovery.journal import RecoveryJournal
from octower.recovery.parent_wake import ParentWakeCoordinator


class ParentActions:
    def __init__(self, parent) -> None:
        self.parent = parent
        self.prompts: list[tuple[str, str]] = []

    def get_evidence(self, session_id: str):
        assert session_id == self.parent.session_id
        return self.parent

    def prompt_async(self, session_id: str, text: str) -> bool:
        self.prompts.append((session_id, text))
        return True


def terminal_child(session_id: str):
    return evidence(session_id=session_id, final_assistant_completed=True)


def make_coordinator(tmp_path, clock, parent):
    actions = ParentActions(parent)
    journal = RecoveryJournal(tmp_path / "recovery.jsonl")
    return ParentWakeCoordinator(actions, journal, clock), actions


def test_parent_wakes_once_when_all_children_terminal_and_parent_idle(tmp_path, clock) -> None:
    coordinator, actions = make_coordinator(tmp_path, clock, evidence(session_id="ses-parent"))
    children = [terminal_child("ses-one"), terminal_child("ses-two")]

    first = coordinator.on_child_done("ses-parent", children)
    second = coordinator.on_child_done("ses-parent", children)

    assert first.woken is True
    assert second.woken is False
    assert [session_id for session_id, _ in actions.prompts] == ["ses-parent"]


def test_parent_wake_skips_busy_parent_partial_children_and_native_wake(tmp_path, clock) -> None:
    busy, busy_actions = make_coordinator(tmp_path, clock, evidence(session_id="ses-parent", status="busy"))
    partial, partial_actions = make_coordinator(tmp_path, clock, evidence(session_id="ses-parent"))
    native, native_actions = make_coordinator(tmp_path, clock, evidence(session_id="ses-parent"))

    assert busy.on_child_done("ses-parent", [terminal_child("ses-child")]).woken is False
    assert partial.on_child_done("ses-parent", [terminal_child("ses-one"), evidence(session_id="ses-two")]).woken is False
    assert native.on_child_done("ses-parent", [terminal_child("ses-child")], wake_already_dispatched=True).woken is False
    assert busy_actions.prompts == []
    assert partial_actions.prompts == []
    assert native_actions.prompts == []
