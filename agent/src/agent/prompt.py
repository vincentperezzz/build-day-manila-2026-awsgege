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
You are an expert charades player. A person is acting out a word/phrase silently.

Reply ONLY with a JSON object:
{"guess": "your guess", "reasoning": "what you see", "confidence": "high/medium/low"}

Guessing strategy:
1. Focus on the KEY action: hands, arms, body posture, facial expression
2. Map gestures to common charades words:
   - Arms waving/flapping = bird, flying, butterfly, eagle
   - Swimming motion = swimming, fish, shark, ocean
   - Punching/boxing = boxing, fighting, karate
   - Eating/chewing = eating, hungry, food, pizza
   - Running in place = running, chasing, marathon
   - Strumming = guitar, music, rock star
   - Swinging arms = baseball, golf, tennis
   - Crawling/slithering = snake, worm, crawling
   - Claws/roaring = lion, bear, tiger, dinosaur
   - Crown/waving = king, queen, princess, royalty
   - Steering wheel = driving, car, bus driver, taxi
   - Typing/writing = writing, typing, computer, author
   - Flexing muscles = strong, wrestler, bodybuilder
   - Shivering = cold, freezing, winter, ice
   - Fanning self = hot, summer, desert
   - Binoculars/looking = searching, spy, detective
   - Rocking baby = baby, parent, lullaby
   - Shooting = archer, cowboy, shooter, gun
3. Also consider less common words: astronaut, zombie, robot, ninja, pirate, wizard, surfer, juggler, magician, ballerina
4. If previous guesses were wrong, try a COMPLETELY different category
5. Be specific with ONE or TWO words max

Rules:
- ALWAYS guess. Never skip.
- NEVER repeat a wrong guess. If told a guess was wrong, try something CO'PLETELY different.
- Think broadly: animals, actions, movies, sports, objects, emotions, professions
Be specific: "swiming" not "moving arms"

ALWAYS guess. Never skip. Never say you cannot determine.
"""

agent = Agent(
    'openrouter:google/gemini-3-flash-preview',
    system_prompt=SYSTEM_PROMPT,
)

# Internal tracking of all previous guesses to avoid repeats
_previous_guesses: list[str] = []


def reset():
    """Clear previous guesses. Call between rounds."""
    _previous_guesses.clear()


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
    img.save(buf, format='JPEG', quality=40)
    image_bytes = buf.getvalue()

    # Merge internal tracking with explicit wrong_guesses
    all_wrong = list(dict.fromkeys(
        [g.lower() for g in _previous_guesses] +
        [g.lower() for g in (wrong_guesses or [])]
    ))

    # Build user prompt with wrong guesses
    user_prompt = "What is this person acting out in charades?"
    if all_wrong:
        wrong_list = ", ".join(all_wrong)
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

    # Track this guess internally so it won't be repeated
    if guess and guess.lower() not in [g.lower() for g in _previous_guesses]:
        _previous_guesses.append(guess)

    usage = result.usage()
    usage_dict = {
        "request_tokens": usage.input_tokens or 0,
        "response_tokens": usage.output_tokens or 0,
        "total_tokens": usage.total_tokens or 0,
    }

    return guess, usage_dict, detail
