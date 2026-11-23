from __future__ import annotations
"""Errors shared by the stage table (orchestrator) and the change lane (change_desk)."""


class ConfirmationRequiredError(RuntimeError):
    """G2: a stage was started without the human record it depends on."""


class PipelineStateError(ValueError):
    """The request does not fit the current pipeline state (wrong stage, bad answer, ...)."""
