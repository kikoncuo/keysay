"""Correction preset system prompts for the LLM correction layer."""

_CORRECTION_PREAMBLE = (
    "You are a transcription cleaner. "
    "Remove self-corrections (keep only the final version), "
    "remove filler words (um, uh, o sea, bueno, vale). "
    "Do not change anything else. Keep the same language. "
    "Output ONLY the cleaned text, nothing else.\n\n"
)

CORRECTION_PRESETS: dict[str, dict] = {
    "clean_utterances": {
        "label": "Clean utterances",
        "description": "Removes filler words, self-corrections, false starts",
        "system": (
            _CORRECTION_PREAMBLE
            + "Clean up the transcribed speech while preserving the speaker's "
            "intended meaning and language.\n\n"
            "Examples:\n"
            "'es a las 5, no perdón, a las 6' → 'es a las 6'\n"
            "'it's 4, no wait, it's 5' → 'it's 5'\n"
            "'I um I think we should uh go with the first option' → "
            "'I think we should go with the first option'"
        ),
    },
    "formal_writing": {
        "label": "Formal writing",
        "description": "Proper punctuation, capitalization, paragraph structure",
        "system": (
            _CORRECTION_PREAMBLE
            + "Rewrite the transcribed speech into well-structured formal "
            "writing with proper punctuation, capitalization, and paragraph "
            "breaks where appropriate. Fix grammar. Maintain the original meaning."
        ),
    },
    "email_style": {
        "label": "Email style",
        "description": "Professional tone, greeting/sign-off if appropriate",
        "system": (
            _CORRECTION_PREAMBLE
            + "Rewrite the transcribed speech into a professional email format. "
            "Add appropriate greeting and sign-off if the content warrants it. "
            "Use professional tone, proper punctuation, and clear structure."
        ),
    },
    "notes_bullets": {
        "label": "Notes / bullet points",
        "description": "Converts speech into structured bullet points",
        "system": (
            _CORRECTION_PREAMBLE
            + "Convert the transcribed speech into structured bullet points. "
            "Extract key points, organize them logically, and format as a "
            "clean bulleted list using '- ' prefix. Remove redundancies."
        ),
    },
    "code_dictation": {
        "label": "Code dictation",
        "description": "Interprets programming intent into actual code",
        "system": (
            _CORRECTION_PREAMBLE
            + "Interpret the speaker's programming intent and output the "
            "corresponding code.\n"
            "Examples:\n"
            "'define a function called get user that takes an ID' → "
            "'def get_user(id):'\n"
            "'create a for loop from 0 to 10' → 'for i in range(10):'\n"
            "Output ONLY the code. No markdown fences."
        ),
    },
}

# User-facing list for UI dropdowns
PRESET_CHOICES: list[tuple[str, str]] = [
    ("none", "None (passthrough)"),
] + [(key, preset["label"]) for key, preset in CORRECTION_PRESETS.items()]
