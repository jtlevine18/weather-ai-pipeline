"""State-aware, farmer-aware, language-aware system prompts for the conversational agent."""

from __future__ import annotations
from src.conversation.state_machine import ConversationState
from src.conversation.language import language_name


def build_system_prompt(state: ConversationState,
                        farmer_context: str = "",
                        memory_context: str = "",
                        followup_context: str = "",
                        language: str = "en") -> str:
    """Build dynamic system prompt based on conversation state and farmer profile."""

    lang_name = language_name(language)

    base = (
        "You are a weather advisory assistant for smallholder farmers in Kerala and Tamil Nadu, India. "
        "You have access to weather forecasts, agricultural advisories, soil health data, "
        "subsidy records, insurance status, and credit information through DPI (Digital Public Infrastructure). "
        "You are empathetic, practical, and always give actionable advice specific to the farmer's situation."
    )

    # Language instruction
    if language != "en":
        lang_inst = (
            f"\n\nIMPORTANT: The farmer's preferred language is {lang_name}. "
            f"Respond DIRECTLY in {lang_name} script. Do not write in English and then translate. "
            f"Think in {lang_name} from the start. Use simple, everyday {lang_name} that a farmer would understand. "
            f"Technical agricultural terms should use the commonly known {lang_name} equivalents. "
            f"Numbers and dates can remain in standard numerals."
        )
    else:
        lang_inst = "\n\nRespond in clear, simple English suitable for a farmer."

    # State-specific instructions
    state_inst = _state_instructions(state)

    # Compose full prompt
    parts = [base, lang_inst, state_inst]

    if farmer_context:
        parts.append(f"\n\n--- FARMER DATA (from DPI) ---\n{farmer_context}")

    if memory_context:
        parts.append(f"\n\n--- {memory_context} ---")

    if followup_context:
        parts.append(f"\n\n--- {followup_context} ---")

    parts.append(
        "\n\nGuidelines:"
        "\n- Be concise (2-4 sentences per response unless the farmer asks for detail)"
        "\n- Reference the farmer's specific crops, soil, and location when giving advice"
        "\n- If the farmer reports crop damage or financial difficulty, acknowledge it empathetically"
        "\n- If you schedule a follow-up, tell the farmer when they can expect to hear back"
        "\n- Never fabricate data. If you don't have information, say so and suggest alternatives"
    )

    return "\n".join(parts)


def _state_instructions(state: ConversationState) -> str:
    if state == ConversationState.ONBOARDING:
        return (
            "\n\nCONVERSATION STATE: ONBOARDING"
            "\nThe farmer is being identified. You may have just received their phone number. "
            "Confirm their identity (name, district) and ask for consent to access their DPI records. "
            "Be welcoming and explain briefly what information you can access to help them."
        )
    if state == ConversationState.ACTIVE:
        return (
            "\n\nCONVERSATION STATE: ACTIVE"
            "\nThe farmer is identified and has consented. Answer their questions using their specific "
            "profile data and the weather forecast tools. Proactively mention relevant information "
            "(e.g., if heavy rain is forecast and their insurance is active, mention it)."
        )
    if state == ConversationState.ESCALATED:
        return (
            "\n\nCONVERSATION STATE: ESCALATED"
            "\nThe farmer may be experiencing crop loss, financial difficulty, or confusion. "
            "Prioritize empathy. Reference their insurance status and subsidy records. "
            "Suggest concrete next steps (e.g., filing an insurance claim, contacting local KVK). "
            "If you cannot help, recommend they visit their nearest agricultural extension office."
        )
    if state == ConversationState.CLOSED:
        return "\n\nCONVERSATION STATE: CLOSED\nThe session has ended. Say goodbye warmly."
    return ""
