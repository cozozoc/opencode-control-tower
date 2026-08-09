"""Durable write-ahead recovery records and replay queries (§13.1-§13.2)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from uuid import uuid4


class RecoveryPhase(str, Enum):
    """Ordered hard-recovery phases plus terminal transaction outcomes (§13.2)."""

    INTENT = "INTENT"
    ABORT_REQUESTED = "ABORT_REQUESTED"
    ABORT_CONFIRMED = "ABORT_CONFIRMED"
    SESSION_REVALIDATED = "SESSION_REVALIDATED"
    RESUME_REQUESTED = "RESUME_REQUESTED"
    RECOVERING = "RECOVERING"
    ACTIVITY_CONFIRMED = "ACTIVITY_CONFIRMED"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"
    PARENT_WAKE_REQUESTED = "PARENT_WAKE_REQUESTED"


@dataclass(frozen=True, slots=True)
class RecoveryRecord:
    """One append-only audit record for a same-session recovery (§13.1)."""

    recovery_id: str
    session_id: str
    root_session_id: str
    parent_id: str | None
    reason: str
    phase: RecoveryPhase
    attempt: int
    created_at: float
    last_activity_before: float | None
    adapter: str


class RecoveryJournal:
    """JSONL source of truth for recovery replay and idempotency (INV-008)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def start(
        self,
        *,
        session_id: str,
        root_session_id: str,
        parent_id: str | None,
        reason: str,
        attempt: int,
        created_at: float,
        last_activity_before: float | None,
        adapter: str,
    ) -> RecoveryRecord:
        """Write transaction intent before any abort or continuation action (§13.1)."""
        record = RecoveryRecord(
            recovery_id=str(uuid4()),
            session_id=session_id,
            root_session_id=root_session_id,
            parent_id=parent_id,
            reason=reason,
            phase=RecoveryPhase.INTENT,
            attempt=attempt,
            created_at=created_at,
            last_activity_before=last_activity_before,
            adapter=adapter,
        )
        return self.append(record)

    def advance(self, record: RecoveryRecord, phase: RecoveryPhase, created_at: float) -> RecoveryRecord:
        """Append the next durable phase without changing recovery identity (§13.2)."""
        return self.append(
            RecoveryRecord(
                recovery_id=record.recovery_id,
                session_id=record.session_id,
                root_session_id=record.root_session_id,
                parent_id=record.parent_id,
                reason=record.reason,
                phase=phase,
                attempt=record.attempt,
                created_at=created_at,
                last_activity_before=record.last_activity_before,
                adapter=record.adapter,
            )
        )

    def append(self, record: RecoveryRecord) -> RecoveryRecord:
        """Atomically append and flush one JSONL record before returning (§13.1)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(record)
        payload["phase"] = record.phase.value
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record

    def read(self) -> tuple[RecoveryRecord, ...]:
        """Read ordered recovery records; malformed journal entries fail loudly."""
        if not self.path.exists():
            return ()
        records: list[RecoveryRecord] = []
        with self.path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    payload["phase"] = RecoveryPhase(payload["phase"])
                    records.append(RecoveryRecord(**payload))
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(f"invalid recovery journal entry at line {line_number}") from error
        return tuple(records)

    def records_for(self, session_id: str) -> tuple[RecoveryRecord, ...]:
        """Return every journal record for one session in append order."""
        return tuple(record for record in self.read() if record.session_id == session_id)

    def latest_by_recovery(self, session_id: str | None = None) -> dict[str, RecoveryRecord]:
        """Return the final known phase for each transaction, optionally by session."""
        latest: dict[str, RecoveryRecord] = {}
        for record in self.read():
            if session_id is None or record.session_id == session_id:
                latest[record.recovery_id] = record
        return latest

    def active(self, session_id: str | None = None) -> tuple[RecoveryRecord, ...]:
        """Return unfinished recovery transactions that must be replayed after restart."""
        terminal = {RecoveryPhase.RECOVERED, RecoveryPhase.FAILED, RecoveryPhase.PARENT_WAKE_REQUESTED}
        return tuple(record for record in self.latest_by_recovery(session_id).values() if record.phase not in terminal)

    def has_parent_wake(self, session_id: str) -> bool:
        """Identify a write-ahead parent wake record for idempotent R10 handling."""
        return any(
            record.session_id == session_id and record.phase is RecoveryPhase.PARENT_WAKE_REQUESTED
            for record in self.read()
        )
