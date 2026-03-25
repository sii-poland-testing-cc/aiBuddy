"""Shared SSE formatting helpers."""

import json

# Terminal SSE frame — sent by every streaming endpoint after result/error.
SSE_DONE = "data: [DONE]\n\n"


def sse_event(payload: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
