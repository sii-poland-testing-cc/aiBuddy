"""
LLM + embedding model factories
================================
Returns LlamaIndex-compatible instances based on ``settings.LLM_PROVIDER``.

  LLM_PROVIDER=bedrock    (default) – Amazon Bedrock via BedrockConverse
  LLM_PROVIDER=anthropic            – Anthropic API directly

Embed model (get_embed_model):
  bedrock  → Bedrock Titan (BEDROCK_EMBED_MODEL_ID)
  other    → HuggingFace BAAI/bge-m3 (multilingual, ~560 MB on first download,
             no API key needed). Override model name with EMBED_MODEL_NAME env var.

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
            max_tokens=16000,
        )
    except ImportError:
        logger.warning("llama-index-llms-anthropic not installed; LLM disabled")
        return None


# ── Embedding model ───────────────────────────────────────────────────────────

_embed_model_singleton = None


def get_embed_model():
    """
    Return the embedding model for the configured LLM_PROVIDER.
    Cached as a module-level singleton (loaded once per process).

      bedrock  → Bedrock Titan (BEDROCK_EMBED_MODEL_ID)
      other    → HuggingFace BAAI/bge-m3 by default;
                 override with EMBED_MODEL_NAME env var.
    """
    global _embed_model_singleton
    if _embed_model_singleton is not None:
        return _embed_model_singleton

    if settings.LLM_PROVIDER.lower() == "bedrock":
        from llama_index.embeddings.bedrock import BedrockEmbedding
        _embed_model_singleton = BedrockEmbedding(
            model_name=settings.BEDROCK_EMBED_MODEL_ID,
            region_name=settings.AWS_REGION,
        )
    else:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        logger.info(
            "Loading HuggingFace embedding model '%s' (first load only)…",
            settings.EMBED_MODEL_NAME,
        )
        _embed_model_singleton = HuggingFaceEmbedding(model_name=settings.EMBED_MODEL_NAME)
        logger.info("Embedding model loaded and cached.")

    return _embed_model_singleton
