"""System prompt and analysis logic for the guessing game agent.

=== EDIT THIS FILE ===

This is where you define your agent's strategy:
- What system prompt to use
- How to analyze each frame
- When to submit a guess vs. gather more context
"""

from __future__ import annotations

import io
import json

from pydantic_ai import Agent, BinaryContent

from core import Frame

# ---------------------------------------------------------------------------
# System prompt — tweak this to improve your agent's guessing ability.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are playing charades. A person is acting out a word/phrase WITHOUT speaking.

Reply with ONLY a JSON object:
{"guess": "your guess", "reasoning": "what you see", "confidence": "high/medium/low"}

Rules:
- ALWAYS guess. Never skip.
- NEVER repeat a wrong guess. If told a guess was wrong, try something COMPLETELY different.
- Think broadly: animals, actions, movies, sports, objects, emotions, professions
- Be specific: "swimming" not "moving arms"
"""

agent = Agent(
    'openrouter:google/gemini-3-flash-preview',
    system_prompt=SYSTEM_PROMPT,
)


async def analyze(frame: Frame) -> str | None:
    result = await _analyze_with_usage(frame)
    return result[0]


async def _analyze_with_usage(
    frame: Frame,
    wrong_guesses: list[str] | None = None,
) -> tuple[str | None, dict, dict]:
    """Analyze a frame and return (guess, usage_dict, detail_dict)."""
    # Resize image to save tokens — max 512px wide
    img = frame.image
    if img.width > 512:
        ratio = 512 / img.width
        img = img.resize((512, int(img.height * ratio)))

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=60)
    image_bytes = buf.getvalue()

    # Build user prompt with wrong guesses
    user_prompt = "What is this person acting out in charades?"
    if wrong_guesses:
        wrong_list = ", ".join(wrong_guesses)
        user_prompt += (
            f"\n\nWRONG guesses (DO NOT repeat any of these): {wrong_list}"
            f"\nYou MUST guess something different from all of the above."
        )

    result = await agent.run(
        [
            user_prompt,
            BinaryContent(data=image_bytes, media_type='image/jpeg'),
        ]
    )

    raw_output = result.output.strip()

    # Parse structured response
    guess = None
    detail = {"reasoning": "", "confidence": "", "raw": raw_output}

    try:
        parsed = json.loads(raw_output)
        guess = parsed.get("guess", "").strip()
        detail["reasoning"] = parsed.get("reasoning", "")
        detail["confidence"] = parsed.get("confidence", "")
        if not guess or guess.upper() == "SKIP":
            guess = None
    except json.JSONDecodeError:
        guess = raw_output if raw_output.upper() != "SKIP" else None

    usage = result.usage()
    usage_dict = {
        "request_tokens": usage.request_tokens or 0,
        "response_tokens": usage.response_tokens or 0,
        "total_tokens": usage.total_tokens or 0,
    }

    return guess, usage_dict, detail
