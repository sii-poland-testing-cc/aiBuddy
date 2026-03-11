"""
LLM factory
===========
Returns a LlamaIndex-compatible LLM instance based on ``settings.LLM_PROVIDER``.

  LLM_PROVIDER=bedrock    (default) – Amazon Bedrock via BedrockConverse
  LLM_PROVIDER=anthropic            – Anthropic API directly

Workflows receive the LLM via their ``__init__(llm=...)`` parameter and fall back
to heuristic / non-LLM code paths when this function returns None.
"""

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("ai_buddy")


def get_llm():
    provider = settings.LLM_PROVIDER.lower()
    if provider == "anthropic":
        return _anthropic_llm()
    if provider == "bedrock":
        return _bedrock_llm()
    logger.warning("Unknown LLM_PROVIDER=%r, falling back to bedrock", settings.LLM_PROVIDER)
    return _bedrock_llm()


def _bedrock_llm():
    try:
        from llama_index.llms.bedrock_converse import BedrockConverse
        return BedrockConverse(
            model=settings.BEDROCK_MODEL_ID,
            region_name=settings.AWS_REGION,
        )
    except ImportError:
        logger.warning("llama-index-llms-bedrock-converse not installed; LLM disabled")
        return None


def _anthropic_llm():
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY is not set; LLM disabled")
        return None
    try:
        from llama_index.llms.anthropic import Anthropic
        return Anthropic(
            model=settings.ANTHROPIC_MODEL_ID,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=4096,
        )
    except ImportError:
        logger.warning("llama-index-llms-anthropic not installed; LLM disabled")
        return None
