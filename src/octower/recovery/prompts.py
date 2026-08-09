"""Configurable same-session continuation prompts (R9, R10, §14)."""

DEFAULT_RECOVERY_PROMPT = """[Guardian Recovery]

This existing session was recovered after a confirmed prolonged stall.

Continue the ORIGINAL delegated task from the point where execution stopped.

Rules:
- Preserve and use the existing conversation/session context.
- Inspect existing tool results and unfinished TODO/task state before acting.
- Do not redo completed work unless verification proves it is necessary.
- Continue the interrupted step.
- Finish remaining deliverables and required validation.
- Ask the user only when a genuine human decision is required.
- Mark task/TODO state accurately when finished.
"""

DEFAULT_PARENT_WAKE_PROMPT = """[Guardian Parent Continuation]

Background child work has reached a terminal state.
Reconcile the completed child session results with the ORIGINAL orchestration.

- Read the existing parent and child context.
- Do not recreate completed child work.
- Collect required results.
- Continue remaining parent TODO/task steps.
- Finish the original user request.
"""
