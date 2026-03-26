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
from app.core.llm import get_embed_model

logger = logging.getLogger("ai_buddy")


class ContextBuilder:
    """
    Manages per-project RAG indexes.

    Usage:
        builder = ContextBuilder()
        await builder.index_files(project_id="proj_1", file_paths=[...])
        text, sources = await builder.build_with_sources(project_id="proj_1", query="coverage gaps")
        # or, if sources are not needed:
        context = await builder.build(project_id="proj_1", query="coverage gaps")
    """

    def __init__(self):
        self._embed_model = get_embed_model()
        Settings.embed_model = self._embed_model
        Settings.node_parser = SentenceSplitter(
            chunk_size=cfg.RAG_CHUNK_SIZE,
            chunk_overlap=cfg.RAG_CHUNK_OVERLAP,
        )

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
        except Exception as exc:
            msg = str(exc)
            if "dimension" in msg.lower() or "InvalidArgumentError" in type(exc).__name__:
                logger.warning(
                    "Embedding dimension mismatch for project %s — index was built with a "
                    "different model. Rebuild context to fix. Error: %s",
                    project_id, msg,
                )
                return (
                    "(Context index is stale: it was built with a different embedding model. "
                    "Please rebuild the context via the Context Builder page.)",
                    [],
                )
            logger.warning("RAG retrieval failed for project %s: %s", project_id, msg)
            return "(No indexed context found for this project.)", []


    async def retrieve_nodes(
        self, project_id: str, query: str, top_k: int | None = None
    ) -> list:
        """Return raw LlamaIndex nodes (with full metadata) for a query."""
        k = top_k if top_k is not None else cfg.RAG_TOP_K
        try:
            collection = self._get_collection(project_id)
            if collection.count() == 0:
                return []
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
            index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_ctx)
            retriever = index.as_retriever(similarity_top_k=k)
            return await retriever.aretrieve(query)
        except Exception as exc:
            logger.warning("retrieve_nodes failed for project %s: %s", project_id, exc)
            return []

    def get_indexed_filenames(self, project_id: str) -> list[str]:
        """Return unique filenames of all indexed documents for this project."""
        try:
            collection = self._get_collection(project_id)
            results = collection.get(include=["metadatas"])
            filenames = {str(m.get("filename", "")) for m in (results.get("metadatas") or [])}
            return sorted(f for f in filenames if f)
        except Exception as exc:
            logger.warning("get_indexed_filenames failed for project %s: %s", project_id, exc)
            return []

    async def index_from_docs(
        self,
        project_id: str,
        docs: list[dict],
    ) -> int:
        """
        Index already-parsed documents (from DocumentParser) into Chroma.
        Called by M1 ContextBuilderWorkflow after the parse step.

        Enriches chunk metadata with:
          - first_heading: first document heading (aids breadcrumb generation)
          - has_tables: whether the source doc contains tables
          - is_table_row: True for table-derived documents (separate indexed items)

        Returns number of chunks indexed (approximate).
        """
        from llama_index.core.schema import Document as LlamaDocument

        llama_docs: list[LlamaDocument] = []

        for doc in docs:
            text = doc.get("text", "").strip()
            if not text:
                continue

            headings = doc.get("headings", [])
            tables = doc.get("tables", [])
            first_heading = headings[0]["text"] if headings else ""
            has_tables = bool(tables)

            base_meta = {
                "filename": doc["filename"],
                "source": doc.get("metadata", {}).get("source", "unknown"),
                "project_id": project_id,
                "first_heading": first_heading,
                "has_tables": has_tables,
                "is_table_row": False,
            }
            llama_docs.append(LlamaDocument(text=text, metadata=base_meta))  # type: ignore[call-arg]

            # Index each table row separately so structured data is retrievable
            for table in tables:
                for row in table:
                    row_text = " | ".join(str(c).strip() for c in row if str(c).strip())
                    if row_text:
                        llama_docs.append(LlamaDocument(  # type: ignore[call-arg]
                            text=row_text,
                            metadata={**base_meta, "is_table_row": True},
                        ))

        if not llama_docs:
            return 0

        collection = self._get_collection(project_id)

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
        try:
            self._chroma_client.delete_collection(self._collection_name(project_id))
        except Exception:
            pass  # collection may not exist yet

    # ── Private ───────────────────────────────────────────────────────────────

    def _collection_name(self, project_id: str) -> str:
        """Canonical Chroma collection name for a project."""
        return f"project_{project_id.replace('-', '_')}"

    def _get_collection(self, project_id: str):
        return self._chroma_client.get_or_create_collection(self._collection_name(project_id))
