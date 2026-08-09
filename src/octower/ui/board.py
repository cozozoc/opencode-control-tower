"""Virtualized kanban board and persistent selection for handoff §26."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, HorizontalScroll, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static

from octower.models import AgentState
from octower.ui.data_source import AgentSnapshot, BoardSnapshot


LANE_STATES = tuple(state for state in AgentState if state is not AgentState.DONE)


class StateLane(Vertical):
    """One state lane backed by DataTable viewport virtualization."""

    def __init__(self, state: AgentState) -> None:
        super().__init__(classes=f"state-lane state-{state.value}", id=f"lane-{state.value}")
        self.state = state

    def compose(self) -> ComposeResult:
        yield Static(self.state.value.replace("_", " ").upper(), classes="lane-title")
        yield DataTable(
            id=f"table-{self.state.value}",
            cursor_type="row",
            show_header=False,
            zebra_stripes=True,
        )

    def on_mount(self) -> None:
        self.query_one(DataTable).add_column("Agent", key="agent", width=33)


class BoardScreen(Screen[None]):
    """Incrementally updated control-room board with a fixed detail rail."""

    BINDINGS = [("enter", "focus_agent", "Focus")]

    def __init__(self) -> None:
        super().__init__(id="board-screen")
        self._snapshot = BoardSnapshot(())
        self._visible: tuple[str, ...] = ()
        self._rows_by_lane = {state: set[str]() for state in LANE_STATES}
        self._rendered: dict[str, AgentSnapshot] = {}

    @property
    def visible_session_ids(self) -> tuple[str, ...]:
        return self._visible

    @property
    def selected_session_id(self) -> str | None:
        return self.app.selected_session_id

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="board-shell"):
            with Horizontal(id="board-toolbar"):
                yield Static("AGENT CONTROL ROOM", id="board-title")
                yield Input(
                    placeholder="/  session:  state:  parent:  text",
                    id="filter-input",
                )
                yield Static("DONE 0", id="done-count")
            with Horizontal(id="board-body"):
                with HorizontalScroll(id="lanes-scroll"):
                    for state in LANE_STATES:
                        yield StateLane(state)
                with Vertical(id="detail-rail"):
                    yield Static("SELECTED AGENT", classes="section-title")
                    yield Static("No agent selected", id="detail-heading")
                    yield Static("", id="detail-state")
                    yield Static("", id="detail-output")
        yield Footer()

    def apply_snapshot(self, snapshot: BoardSnapshot) -> None:
        self._snapshot = snapshot
        self.query_one("#done-count", Static).update(f"DONE {snapshot.done_count}")
        self._apply_filter(self.query_one("#filter-input", Input).value)

    def select_session(self, session_id: str) -> None:
        agent = next(
            (item for item in self._snapshot.agents if item.session_id == session_id),
            None,
        )
        if agent is None:
            return
        self.app.selected_session_id = session_id
        self._show_detail(agent)
        self._restore_cursor(session_id, focus=True)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._apply_filter(event.value)

    def on_resize(self, event: events.Resize) -> None:
        detail_rail = self.query_one("#detail-rail")
        detail_rail.display = event.size.width >= 100

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.has_focus and event.row_key.value is not None:
            self.select_session(str(event.row_key.value))

    def action_focus_agent(self) -> None:
        self.app.action_focus_agent()

    def _apply_filter(self, query: str) -> None:
        visible_agents = tuple(
            agent
            for agent in self._snapshot.agents
            if agent.state is not AgentState.DONE and _matches(agent, query)
        )
        desired = {
            state: {agent.session_id for agent in visible_agents if agent.state is state}
            for state in LANE_STATES
        }
        agents_by_id = {agent.session_id: agent for agent in visible_agents}
        for state in LANE_STATES:
            table = self.query_one(f"#table-{state.value}", DataTable)
            for session_id in self._rows_by_lane[state] - desired[state]:
                table.remove_row(session_id)
            for agent in visible_agents:
                if agent.state is not state:
                    continue
                prior = self._rendered.get(agent.session_id)
                if agent.session_id not in self._rows_by_lane[state]:
                    table.add_row(_card(agent), key=agent.session_id, height=4)
                elif prior != agent:
                    table.update_cell(agent.session_id, "agent", _card(agent))
            self._rows_by_lane[state] = desired[state]
        self._rendered = agents_by_id
        self._visible = tuple(agent.session_id for agent in visible_agents)
        selected = self.app.selected_session_id
        if selected is not None:
            selected_agent = agents_by_id.get(selected)
            if selected_agent is not None:
                self._show_detail(selected_agent)
                self._restore_cursor(selected)
        elif visible_agents:
            self.select_session(visible_agents[0].session_id)

    def _show_detail(self, agent: AgentSnapshot) -> None:
        self.query_one("#detail-heading", Static).update(agent.title)
        self.query_one("#detail-state", Static).update(
            f"{agent.state.value.upper()}  ·  {agent.session_id}"
        )
        history = agent.output_history or (agent.output_preview,)
        self.query_one("#detail-output", Static).update("\n".join(history[-12:]))

    def _restore_cursor(self, session_id: str, *, focus: bool = False) -> None:
        agent = self._rendered.get(session_id)
        if agent is None:
            return
        table = self.query_one(f"#table-{agent.state.value}", DataTable)
        row_index = next(
            (
                index
                for index, row_key in enumerate(table.rows)
                if row_key.value == session_id
            ),
            None,
        )
        if row_index is not None:
            table.move_cursor(row=row_index)
            if focus:
                table.focus()


def _matches(agent: AgentSnapshot, query: str) -> bool:
    fields = {
        "session": agent.session_id.lower(),
        "state": agent.state.value.lower(),
        "parent": (agent.parent_id or "").lower(),
    }
    text = " ".join(
        (agent.session_id, agent.title, agent.parent_id or "", agent.output_preview)
    ).lower()
    for token in query.lower().split():
        key, separator, value = token.partition(":")
        if separator and key in fields:
            if value not in fields[key]:
                return False
        elif token not in text:
            return False
    return True


def _card(agent: AgentSnapshot) -> Text:
    parent = agent.parent_id or "root"
    return Text.assemble(
        (agent.title, "bold"),
        f"\n{agent.session_id}  ·  {agent.state.value.upper()}",
        f"\nparent {parent}",
        f"\n{agent.output_preview}",
        overflow="ellipsis",
        no_wrap=True,
    )
