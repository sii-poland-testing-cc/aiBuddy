"""
JSON cleanup helpers for LLM responses.

LLMs produce several classes of malformed JSON output:
  1. Markdown fences     — ```json ... ``` or ``` ... ```
  2. Preamble/postamble  — reasoning text before or after the JSON block
  3. Truncation          — response cut off at max_tokens inside an array

Each helper targets a specific failure class:
  strip_fences            — removes fences, finds first { or [
  recover_truncated_array — salvages an array cut off mid-token
  parse_json_object       — finds the *last* valid {...} in a response (beats preamble)
  parse_json_array        — finds the *last* valid [...] in a response (beats preamble)
"""

import json
import re
from typing import Any, Dict, List


def strip_fences(text: str) -> str:
    """Remove markdown code fences and find the first valid JSON value."""
    text = re.sub(r"^```[a-z]*\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            return text[i:]
    return text


def recover_truncated_array(raw: str) -> List[Dict]:
    """
    Salvage a JSON array cut off mid-token (e.g. at max_tokens limit).
    Finds the last complete object `}` inside the array and closes it.
    Returns a list of successfully parsed items, or [] on failure.
    """
    last_brace = raw.rfind("}")
    if last_brace == -1:
        return []
    candidate = raw[: last_brace + 1] + "]"
    for i, ch in enumerate(candidate):
        if ch == "[":
            candidate = candidate[i:]
            break
    else:
        return []
    try:
        result = json.loads(candidate)
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    return []


def parse_json_object(text: str) -> Dict[str, Any]:
    """
    Extract the last valid JSON object {...} from an LLM response.

    Models sometimes emit reasoning text before the JSON, e.g.:
      'Let me analyse this... {"verdict": "DUPLICATE", "reason": "..."}'
    Scanning from the end for the last '{...}' block returns the real answer.
    """
    text = re.sub(r"```[a-z]*\s*", "", text).replace("```", "").strip()
    for match in reversed(list(re.finditer(r"\{.*?\}", text, re.DOTALL))):
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue
    return json.loads(text)  # last resort — may raise


def parse_json_array(text: str) -> List[Any]:
    """
    Extract the last valid JSON array [...] from an LLM response.

    Models sometimes emit reasoning text before or after the JSON, e.g.:
      '[]\\n\\nWait, let me re-read...\\n\\n["FR-001", "FR-002"]'
    Scanning from the end returns the real answer.
    """
    text = re.sub(r"```[a-z]*\s*", "", text).replace("```", "").strip()
    for match in reversed(list(re.finditer(r"\[.*?\]", text, re.DOTALL))):
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue
    return json.loads(text)  # last resort — may raise
