from __future__ import annotations

from .contracts import CapturedResponse, CompletionDecision, ConversationState


class CompletionDetector:
    def __init__(self, *, marker: str = "LIDIYA_TASK_COMPLETE", min_stable_samples: int = 2) -> None:
        self.marker = marker
        self.min_stable_samples = min_stable_samples

    def decide(self, response: CapturedResponse, *, handoff_required: bool = False) -> CompletionDecision:
        if response.error_banner:
            return CompletionDecision(
                state=ConversationState.FAILED,
                reason=f"platform error: {response.error_banner}",
                should_continue=False,
            )
        if handoff_required:
            return CompletionDecision(
                state=ConversationState.HANDOFF_REQUIRED,
                reason="context or development threshold reached",
                should_continue=False,
                should_handoff=True,
            )
        if response.generation_active:
            return CompletionDecision(
                state=ConversationState.WAITING,
                reason="generation still active",
                should_continue=False,
            )
        if response.stable_samples < self.min_stable_samples:
            return CompletionDecision(
                state=ConversationState.CAPTURING,
                reason="response has not remained stable long enough",
                should_continue=False,
            )
        if self.marker in response.text.splitlines():
            return CompletionDecision(
                state=ConversationState.COMPLETE,
                reason="explicit completion marker detected",
                should_continue=False,
            )
        return CompletionDecision(
            state=ConversationState.NEEDS_CONTINUE,
            reason="stable response captured without completion marker",
            should_continue=True,
        )
