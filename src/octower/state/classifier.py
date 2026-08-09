"""Pure 5/10/15 agent state machine with DONE-first ordering (§11, INV-001)."""

from __future__ import annotations

from octower.models import (
    AgentState,
    Classification,
    Clock,
    CompletionEvidence,
    ConfirmationProgress,
    SessionEvidence,
    ThresholdConfig,
)
from octower.state.completion import classify_completion
from octower.state.invariants import stall_guards


class AgentStateClassifier:
    """Classify supplied evidence only; Phase 2 performs neither nudges nor aborts (§27)."""

    def __init__(self, clock: Clock, config: ThresholdConfig | None = None) -> None:
        self._clock = clock
        self._config = config or ThresholdConfig()

    def classify(
        self, evidence: SessionEvidence, prior_state: AgentState = AgentState.DISCOVERED
    ) -> Classification:
        """Apply §10 completion before all §11 silence/stall decisions (INV-001)."""
        completion = classify_completion(evidence)
        if completion.terminal:
            return Classification(AgentState.DONE, completion, self._silence(evidence), completion.reasons)

        if evidence.paused:
            return Classification(AgentState.PAUSED, completion, self._silence(evidence), ("monitoring is paused",))
        if not evidence.backend_available:
            return Classification(AgentState.BACKEND_DOWN, completion, self._silence(evidence), ("backend is unavailable",))
        if not self._data_healthy(evidence):
            return Classification(AgentState.DEGRADED, completion, self._silence(evidence), ("semantic API data is degraded",))
        if evidence.status is None:
            return Classification(AgentState.WAITING, completion, self._silence(evidence), ("session status is unavailable",))
        if evidence.recovery_attempts >= self._config.max_recovery_attempts:
            return Classification(AgentState.FAILED_RECOVERY, completion, self._silence(evidence), ("maximum recovery attempts reached",))
        if evidence.recovery_in_progress:
            return Classification(AgentState.RECOVERING, completion, self._silence(evidence), ("recovery is in progress",))

        protection = self._protection_state(evidence, completion)
        if protection is not None:
            return Classification(AgentState.WAITING, completion, self._silence(evidence), (protection,))

        silence = self._silence(evidence)
        if silence is None:
            return Classification(AgentState.DEGRADED, completion, None, ("last semantic activity is unavailable",))
        if prior_state is AgentState.RECOVERING:
            if (
                evidence.recovery_started_at is not None
                and evidence.last_semantic_activity is not None
                and evidence.last_semantic_activity > evidence.recovery_started_at
            ):
                return Classification(AgentState.RUNNING, completion, silence, ("activity observed after recovery",))
            return Classification(AgentState.RECOVERING, completion, silence, ("awaiting activity after recovery",))
        if silence >= self._config.stall_seconds:
            return Classification(AgentState.STALL_CONFIRMING, completion, silence, ("stall confirmation required",))
        if silence >= self._config.suspect_seconds:
            return Classification(AgentState.SUSPECT, completion, silence, ("semantic silence exceeds suspect threshold",))
        if silence >= self._config.slow_seconds:
            return Classification(AgentState.SLOW, completion, silence, ("semantic silence exceeds slow threshold",))
        return Classification(AgentState.RUNNING, completion, silence, ("recent semantic activity",))

    def confirm_candidate(
        self, evidence: SessionEvidence, progress: ConfirmationProgress | None
    ) -> Classification:
        """Recheck every protection for each §12 confirmation sample without recovery I/O."""
        initial = self.classify(evidence, AgentState.STALL_CONFIRMING)
        if initial.state is not AgentState.STALL_CONFIRMING:
            return initial

        now = self._clock.now()
        if evidence.last_semantic_activity is not None and progress is not None:
            if evidence.last_semantic_activity > progress.started_at:
                return Classification(AgentState.RUNNING, initial.completion, initial.silence_seconds, ("new semantic activity cancelled confirmation",))
        if progress is None or now - progress.started_at > self._config.stall_confirm_seconds:
            next_progress = ConfirmationProgress(now, 1)
        else:
            next_progress = ConfirmationProgress(progress.started_at, progress.samples + 1)

        elapsed = now - next_progress.started_at
        confirmed = (
            next_progress.samples >= self._config.stall_confirm_samples
            and elapsed >= self._config.stall_confirm_seconds
        )
        if confirmed:
            return Classification(AgentState.RECOVERING, initial.completion, initial.silence_seconds, ("silent stall confirmation completed",), next_progress)
        return Classification(AgentState.STALL_CONFIRMING, initial.completion, initial.silence_seconds, ("stall confirmation sample recorded",), next_progress)

    def _silence(self, evidence: SessionEvidence) -> float | None:
        if evidence.last_semantic_activity is None:
            return None
        return max(0.0, self._clock.now() - evidence.last_semantic_activity)

    @staticmethod
    def _data_healthy(evidence: SessionEvidence) -> bool:
        return evidence.api_healthy and evidence.semantic_data_complete and evidence.data_consistent

    def _protection_state(
        self, evidence: SessionEvidence, completion: CompletionEvidence
    ) -> str | None:
        guards = stall_guards(evidence, completion, self._config.max_recovery_attempts)
        failed = next((guard for guard in guards if not guard.passed), None)
        return failed.reason if failed is not None else None
