"""Conversation state machine — manages session lifecycle."""

from __future__ import annotations
from enum import Enum
from typing import Optional


class ConversationState(str, Enum):
    ONBOARDING = "onboarding"    # phone received, verifying identity
    ACTIVE     = "active"        # identified, normal conversation
    ESCALATED  = "escalated"     # crop loss, credit issues, repeated confusion
    CLOSED     = "closed"        # explicit end or timeout


# Valid transitions
_TRANSITIONS = {
    ConversationState.ONBOARDING: {ConversationState.ACTIVE, ConversationState.CLOSED},
    ConversationState.ACTIVE:     {ConversationState.ACTIVE, ConversationState.ESCALATED, ConversationState.CLOSED},
    ConversationState.ESCALATED:  {ConversationState.ACTIVE, ConversationState.CLOSED},
    ConversationState.CLOSED:     set(),
}

# Escalation trigger keywords
_ESCALATION_TRIGGERS = [
    "crop loss", "crop damage", "total loss", "crop failed",
    "cannot repay", "loan default", "debt",
    "insurance claim", "claim rejected",
    "don't understand", "confused", "help me",
]


def can_transition(from_state: ConversationState, to_state: ConversationState) -> bool:
    return to_state in _TRANSITIONS.get(from_state, set())


def transition(from_state: ConversationState, to_state: ConversationState) -> ConversationState:
    if not can_transition(from_state, to_state):
        raise ValueError(f"Invalid transition: {from_state} -> {to_state}")
    return to_state


def check_escalation(message: str) -> bool:
    lower = message.lower()
    return any(trigger in lower for trigger in _ESCALATION_TRIGGERS)


def next_state(current: ConversationState, message: str,
               identity_verified: bool = False) -> ConversationState:
    """Determine next state based on current state and message context."""
    if current == ConversationState.ONBOARDING:
        if identity_verified:
            return ConversationState.ACTIVE
        return ConversationState.ONBOARDING

    if current == ConversationState.ACTIVE:
        if check_escalation(message):
            return ConversationState.ESCALATED
        return ConversationState.ACTIVE

    if current == ConversationState.ESCALATED:
        if not check_escalation(message):
            return ConversationState.ACTIVE
        return ConversationState.ESCALATED

    return current
