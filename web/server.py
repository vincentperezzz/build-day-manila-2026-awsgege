"""Simple web UI for the Casper charades agent.

Usage:
    uv run python web/server.py
    uv run python web/server.py --camera 1

Then open http://localhost:8000 in your browser.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
from datetime import datetime, timezone

from PIL import Image
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from core import Frame

# Lazy import to avoid loading the model at module level
_analyze_fn = None


async def _get_analyze():
    global _analyze_fn
    if _analyze_fn is None:
        from agent.prompt import _analyze_with_usage
        _analyze_fn = _analyze_with_usage
    return _analyze_fn


async def homepage(request: Request) -> HTMLResponse:
    with open("web/static/index.html") as f:
        return HTMLResponse(f.read())


async def analyze_frame(request: Request) -> JSONResponse:
    """Receive a base64 JPEG frame, run the agent, return the guess."""
    try:
        body = await request.json()
        image_data = body.get("image", "")
        wrong_guesses = body.get("wrong_guesses", [])

        # Strip data URL prefix if present
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        frame = Frame(
            image=image,
            timestamp=datetime.now(timezone.utc),
        )

        analyze = await _get_analyze()
        guess, usage, detail = await analyze(frame, wrong_guesses=wrong_guesses)

        print(f"[analyze] Frame {image.size[0]}x{image.size[1]} -> "
              f"guess: {guess!r} | confidence: {detail.get('confidence', '?')} | "
              f"reasoning: {detail.get('reasoning', '?')} | tokens: {usage}")

        return JSONResponse({
            "guess": guess,
            "timestamp": frame.timestamp.isoformat(),
            "usage": usage,
            "reasoning": detail.get("reasoning", ""),
            "confidence": detail.get("confidence", ""),
            "raw": detail.get("raw", ""),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def reset_agent(request: Request) -> JSONResponse:
    """Reset the agent's internal wrong-guess tracking."""
    from agent.prompt import reset
    reset()
    return JSONResponse({"ok": True})


routes = [
    Route("/", homepage),
    Route("/api/analyze", analyze_frame, methods=["POST"]),
    Route("/api/reset", reset_agent, methods=["POST"]),
    Mount("/static", StaticFiles(directory="web/static"), name="static"),
]

app = Starlette(routes=routes)


if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Casper Agent Web UI")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
