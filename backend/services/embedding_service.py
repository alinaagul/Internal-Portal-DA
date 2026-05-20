import logging
import httpx
import chromadb
from pathlib import Path
from typing import List, Optional, Tuple
from core.config import settings

logger = logging.getLogger(__name__)

# ChromaDB persists locally in ./chroma_db folder
CHROMA_PATH = Path("chroma_db")


class EmbeddingService:
    """
    Embedding + vector storage service.
    - Generates embeddings via Ollama (mxbai-embed-large)
    - Stores vectors in ChromaDB (local, persistent)
    - One ChromaDB collection per document
    """

    def __init__(self):
        CHROMA_PATH.mkdir(exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    def _collection_name(self, document_id: int) -> str:
        return f"doc_{document_id}"

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding vector from Ollama."""
        try:
            response = httpx.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text},
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception as e:
            logger.error(f"[Embed] Ollama embedding failed: {e}")
            return None

    def embed_chunks(
        self,
        document_id: int,
        chunks: List[dict],  # list of {id, content, section_title, page_start, chunk_type}
        batch_size: int = 10,
    ) -> Tuple[int, int]:
        """
        Embed all chunks for a document and store in ChromaDB.
        Returns (success_count, fail_count)
        """
        collection = self._client.get_or_create_collection(
            name=self._collection_name(document_id),
            metadata={"hnsw:space": "cosine"},
        )

        success = 0
        failed = 0

        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i: i + batch_size]
            logger.info(f"[Embed] Embedding batch {i//batch_size + 1} ({len(batch)} chunks)...")

            ids, embeddings, documents, metadatas = [], [], [], []

            for chunk in batch:
                embedding = self.get_embedding(chunk["content"])
                if embedding is None:
                    failed += 1
                    continue

                chunk_id = f"doc{document_id}_chunk{chunk['chunk_index']}"
                ids.append(chunk_id)
                embeddings.append(embedding)
                documents.append(chunk["content"])
                metadatas.append({
                    "document_id": document_id,
                    "chunk_index": chunk["chunk_index"],
                    "chunk_db_id": chunk["id"],
                    "section_title": chunk.get("section_title") or "",
                    "page_start": chunk.get("page_start") or 1,
                    "chunk_type": chunk.get("chunk_type") or "text",
                })
                success += 1

            if ids:
                collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

        logger.info(f"[Embed] Done — {success} embedded, {failed} failed")
        return success, failed

    def search(
        self,
        document_id: int,
        query: str,
        top_k: int = 5,
        filter_section: Optional[str] = None,
    ) -> List[dict]:
        """
        Semantic search in a document's vector store.
        Returns list of {content, metadata, distance}
        """
        try:
            collection = self._client.get_collection(self._collection_name(document_id))
        except Exception:
            logger.warning(f"[Embed] No collection for document {document_id}")
            return []

        query_embedding = self.get_embedding(query)
        if query_embedding is None:
            return []

        where = {"document_id": document_id}
        if filter_section:
            where["section_title"] = {"$contains": filter_section}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        output = []
        if results and results["documents"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                output.append({
                    "content": doc,
                    "metadata": meta,
                    "distance": dist,
                    "relevance_score": round((1 - dist) * 100, 1),
                })

        return output

    def delete_document(self, document_id: int):
        """Remove all embeddings for a document."""
        try:
            self._client.delete_collection(self._collection_name(document_id))
            logger.info(f"[Embed] Deleted collection for document {document_id}")
        except Exception as e:
            logger.warning(f"[Embed] Could not delete collection: {e}")

    def is_ollama_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            r = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False



# Singleton
embedding_service = EmbeddingService()