"""
ContextBuilder
==============
Indexes project files into a vector store (Chroma by default)
and retrieves relevant chunks for the Audit/Optimize/Regenerate agents.

Swap VECTOR_STORE_TYPE to "pgvector" for production deployments.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

from app.core.config import settings as cfg

logger = logging.getLogger("ai_buddy")


def _build_embed_model():
    """Return embed model based on LLM_PROVIDER. Bedrock for AWS, local HuggingFace otherwise."""
    if cfg.LLM_PROVIDER.lower() == "bedrock":
        from llama_index.embeddings.bedrock import BedrockEmbedding
        return BedrockEmbedding(
            model_name=cfg.BEDROCK_EMBED_MODEL_ID,
            region_name=cfg.AWS_REGION,
        )
    # Anthropic (or any non-Bedrock provider) → local multilingual model, no API key needed
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    logger.warning(
        "Embedding model changed — rebuild M1 context for existing projects "
        "to re-embed with the new model."
    )
    return HuggingFaceEmbedding(model_name=cfg.EMBED_MODEL_NAME)


class ContextBuilder:
    """
    Manages per-project RAG indexes.

    Usage:
        builder = ContextBuilder()
        await builder.index_files(project_id="proj_1", file_paths=[...])
        context = await builder.build(project_id="proj_1", query="coverage gaps")
    """

    def __init__(self):
        self._embed_model = _build_embed_model()
        Settings.embed_model = self._embed_model
        Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=64)

        self._chroma_client = chromadb.PersistentClient(path=cfg.CHROMA_PERSIST_DIR)

    # ── Public API ────────────────────────────────────────────────────────────

    async def index_files(self, project_id: str, file_paths: list[str]) -> None:
        """Parse and index uploaded files for a given project."""
        documents = SimpleDirectoryReader(input_files=file_paths).load_data()
        collection = self._get_collection(project_id)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex.from_documents(documents, storage_context=storage_ctx)

    async def build(self, project_id: str, query: str, top_k: int = 5) -> str:
        """Retrieve relevant context chunks for a query."""
        text, _ = await self.build_with_sources(project_id, query, top_k)
        return text

    async def build_with_sources(
        self, project_id: str, query: str, top_k: int = 5
    ) -> tuple[str, list[dict]]:
        """Retrieve context chunks and their source metadata.

        Returns:
            (combined_text, sources)
            sources: list of {"filename": str, "excerpt": str}
        """
        try:
            collection = self._get_collection(project_id)
            if collection.count() == 0:
                return "(No indexed context found for this project.)", []

            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
            index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_ctx)
            retriever = index.as_retriever(similarity_top_k=top_k)
            nodes = await retriever.aretrieve(query)

            text = "\n\n---\n\n".join(n.get_content() for n in nodes)
            seen: set[str] = set()
            sources: list[dict] = []
            for n in nodes:
                fname = n.metadata.get("filename", "unknown")
                excerpt = n.get_content()[:200].strip()
                if fname not in seen and excerpt:
                    seen.add(fname)
                    sources.append({"filename": fname, "excerpt": excerpt})
            return text, sources
        except Exception:
            return "(No indexed context found for this project.)", []


    async def index_from_docs(
        self,
        project_id: str,
        docs: list[dict],
    ) -> int:
        """
        Index already-parsed documents (from DocumentParser) into Chroma.
        Called by M1 ContextBuilderWorkflow after the parse step.

        Returns number of chunks indexed (approximate).
        """
        from llama_index.core.schema import Document as LlamaDocument

        llama_docs = [
            LlamaDocument(
                text=doc["text"],
                metadata={
                    "filename": doc["filename"],
                    "source": doc.get("metadata", {}).get("source", "unknown"),
                    "project_id": project_id,
                },
            )
            for doc in docs
            if doc.get("text", "").strip()
        ]

        if not llama_docs:
            return 0

        collection = self._get_collection(project_id)

        from llama_index.vector_stores.chroma import ChromaVectorStore
        from llama_index.core import VectorStoreIndex, StorageContext

        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex.from_documents(llama_docs, storage_context=storage_ctx)

        try:
            return collection.count()
        except Exception:
            return len(llama_docs) * 4   # rough fallback estimate

    async def is_indexed(self, project_id: str) -> bool:
        """Returns True if this project already has vectors in Chroma."""
        try:
            return self._get_collection(project_id).count() > 0
        except Exception:
            return False

    def delete_collection(self, project_id: str) -> None:
        """Delete the Chroma collection for a project (used by rebuild mode)."""
        safe_id = project_id.replace("-", "_")
        try:
            self._chroma_client.delete_collection(f"project_{safe_id}")
        except Exception:
            pass  # collection may not exist yet

    # ── Private ───────────────────────────────────────────────────────────────

    def _get_collection(self, project_id: str):
        safe_id = project_id.replace("-", "_")
        return self._chroma_client.get_or_create_collection(f"project_{safe_id}")
