"""
embedding_service.py — Hybrid Retrieval: Vector (HNSW) + BM25 + MMR + Query Expansion
========================================================================================
PURPOSE:
  Third step in the pipeline. Converts chunks into vector embeddings via Ollama
  and stores them in ChromaDB with HNSW index. Also builds a BM25 in-memory
  keyword index per document. At query time combines both with MMR diversity
  re-ranking and optional query expansion.

WHY THIS FILE EXISTS:
  Pure vector search misses exact keyword matches ("PPA", "NEPRA", specific
  clause numbers). Pure BM25 misses semantic variants ("terminate" vs "end").
  Hybrid = best of both worlds for contract clause retrieval.

  MMR (Maximum Marginal Relevance) prevents returning 6 chunks from the same
  paragraph — forces diversity across contract sections.

  Query Expansion uses Ollama/Mistral to rephrase the user's query with legal
  synonyms, then aggregates results by vote count (most-agreed chunk wins).

OLLAMA MODELS USED:
  Embedding : mxbai-embed-large  (1024 dims, best for legal text)
              Pull: ollama pull mxbai-embed-large
              Alt : nomic-embed-text (768 dims, lighter)
              Pull: ollama pull nomic-embed-text

  Query expansion LLM: mistral:7b-instruct  (temp=0.1)
              Pull: ollama pull mistral:7b-instruct
              WHY Mistral over LLaMA-2: Mistral follows instructions more
              precisely. LLaMA-2 at 7B tends to ramble. For expansion we
              need clean synonym lines, not essays.

VECTOR INDEX:
  ChromaDB with hnsw:space=cosine
  HNSW is used (not IVFFlat) because:
    - Lower query latency (~3ms vs ~15ms at 10K vectors)
    - No training step needed (IVFFlat requires nlist centroids training)
    - ChromaDB uses HNSW natively

BM25:
  rank_bm25 library — indexes raw_content (no section-title noise)
  Install: pip install rank-bm25

RETRIEVAL FLOW for a query:
  1. Embed query → vector search (top_k * 3 candidates)
  2. BM25 score same candidates
  3. Hybrid score = 0.6 * vector_score + 0.4 * bm25_score
  4. MMR re-rank for diversity (lambda=0.5)
  5. Optional: query expansion → merge + vote → final top_k
"""

import logging
import math
import httpx
import chromadb
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from core.config import settings

logger = logging.getLogger(__name__)

CHROMA_PATH = Path("chroma_db")

# ── Hybrid weights ─────────────────────────────────────────────────────────────
VECTOR_WEIGHT = 0.6   # weight for cosine similarity score
BM25_WEIGHT   = 0.4   # weight for BM25 score
MMR_LAMBDA    = 0.5   # 0=pure relevance, 1=pure diversity; 0.5 is balanced


class EmbeddingService:
    """
    Manages embeddings + hybrid retrieval for all uploaded documents.
    One ChromaDB collection per document_id.
    One BM25 index per document_id (in-memory, rebuilt on demand).
    """

    def __init__(self):
        CHROMA_PATH.mkdir(exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        # BM25 cache: { document_id: (BM25Okapi instance, [chunk_ids], [raw_texts]) }
        self._bm25_cache: Dict[int, tuple] = {}

    # ── Collection name helper ─────────────────────────────────────────────────

    def _col(self, document_id: int) -> str:
        return f"doc_{document_id}"

    # ── Embedding via Ollama ───────────────────────────────────────────────────

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Call Ollama embeddings API.
        Model: settings.OLLAMA_EMBED_MODEL (default mxbai-embed-large)
        Returns None on failure — caller must handle gracefully.
        """
        try:
            resp = httpx.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text},
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception as e:
            logger.error(f"[Embed] Ollama embedding failed: {e}")
            return None

    # ── Embed + store all chunks for a document ────────────────────────────────

    def embed_chunks(
        self,
        document_id: int,
        chunks: List[dict],   # {id, chunk_index, content, raw_content, section_title, page_start, chunk_type}
        batch_size: int = 10,
    ) -> Tuple[int, int]:
        """
        Generate embeddings for all chunks and store in ChromaDB (HNSW cosine).
        Also builds the BM25 index for this document.
        Returns (success_count, fail_count).
        """
        collection = self._client.get_or_create_collection(
            name=self._col(document_id),
            metadata={"hnsw:space": "cosine"},   # HNSW with cosine distance
        )

        success, failed = 0, 0
        all_raw_texts: List[str] = []
        all_chunk_ids: List[str] = []

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i: i + batch_size]
            logger.info(
                f"[Embed] Batch {i // batch_size + 1}/{math.ceil(len(chunks)/batch_size)} "
                f"({len(batch)} chunks)…"
            )

            ids, embeddings, documents, metadatas = [], [], [], []

            for chunk in batch:
                emb = self.get_embedding(chunk["content"])   # enriched content
                if emb is None:
                    failed += 1
                    continue

                cid = f"doc{document_id}_chunk{chunk['chunk_index']}"
                ids.append(cid)
                embeddings.append(emb)
                documents.append(chunk["content"])
                metadatas.append({
                    "document_id":   document_id,
                    "chunk_index":   chunk["chunk_index"],
                    "chunk_db_id":   chunk["id"],
                    "section_title": chunk.get("section_title") or "",
                    "page_start":    chunk.get("page_start") or 1,
                    "chunk_type":    chunk.get("chunk_type") or "text",
                    "raw_content":   chunk.get("raw_content") or chunk["content"],
                })
                all_raw_texts.append(chunk.get("raw_content") or chunk["content"])
                all_chunk_ids.append(cid)
                success += 1

            if ids:
                collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                )

        # Build BM25 index for this document
        self._build_bm25(document_id, all_chunk_ids, all_raw_texts)

        logger.info(f"[Embed] Done — {success} embedded, {failed} failed")
        return success, failed

    # ── BM25 index builder ─────────────────────────────────────────────────────

    def _build_bm25(
        self, document_id: int, chunk_ids: List[str], raw_texts: List[str]
    ):
        """Build in-memory BM25 index from raw_content (no section-prefix noise)."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("[BM25] rank-bm25 not installed — pip install rank-bm25")
            return

        tokenized = [text.lower().split() for text in raw_texts]
        bm25 = BM25Okapi(tokenized)
        self._bm25_cache[document_id] = (bm25, chunk_ids, raw_texts)
        logger.info(f"[BM25] Index built for doc {document_id} ({len(raw_texts)} chunks)")

    def _get_bm25_scores(
        self, document_id: int, query: str, chunk_ids: List[str]
    ) -> Dict[str, float]:
        """
        Return BM25 scores for specified chunk_ids.
        Scores are normalised to [0, 1].
        """
        if document_id not in self._bm25_cache:
            # Rebuild BM25 from ChromaDB metadata if cache was cleared
            self._reload_bm25_from_chroma(document_id)

        entry = self._bm25_cache.get(document_id)
        if not entry:
            return {cid: 0.0 for cid in chunk_ids}

        bm25, all_ids, _ = entry
        tokenized_query = query.lower().split()
        scores = bm25.get_scores(tokenized_query)   # scores for ALL chunks

        id_to_score: Dict[str, float] = {}
        for i, cid in enumerate(all_ids):
            id_to_score[cid] = float(scores[i])

        # Normalise
        max_s = max(id_to_score.values()) if id_to_score else 1.0
        if max_s > 0:
            id_to_score = {k: v / max_s for k, v in id_to_score.items()}

        return {cid: id_to_score.get(cid, 0.0) for cid in chunk_ids}

    def _reload_bm25_from_chroma(self, document_id: int):
        """Rebuild BM25 cache from ChromaDB when cache is missing (restart)."""
        try:
            col = self._client.get_collection(self._col(document_id))
            result = col.get(include=["metadatas", "documents"])
            ids = result["ids"]
            raw_texts = [
                m.get("raw_content") or d
                for m, d in zip(result["metadatas"], result["documents"])
            ]
            self._build_bm25(document_id, ids, raw_texts)
        except Exception as e:
            logger.warning(f"[BM25] Reload failed for doc {document_id}: {e}")

    # ── Main retrieval: Hybrid Vector + BM25 → MMR ────────────────────────────

    def search(
        self,
        document_id: int,
        query: str,
        top_k: int = 6,
        use_mmr: bool = True,
        use_query_expansion: bool = False,
        filter_section: Optional[str] = None,
    ) -> List[dict]:
        """
        Full hybrid retrieval pipeline.
        1. Vector search (top_k * 3 candidates)
        2. BM25 score each candidate
        3. Hybrid score = VECTOR_WEIGHT * vec + BM25_WEIGHT * bm25
        4. MMR re-rank for diversity
        5. Optionally expand query → aggregate by vote

        Returns list of dicts:
          content, raw_content, metadata, distance,
          relevance_score, bm25_score, hybrid_score
        """
        if use_query_expansion:
            return self._search_with_expansion(
                document_id, query, top_k, filter_section
            )

        candidates = self._hybrid_candidates(document_id, query, top_k, filter_section)

        if use_mmr and len(candidates) > top_k:
            candidates = self._apply_mmr(candidates, query, top_k)
        else:
            candidates = candidates[:top_k]

        return candidates

    def _hybrid_candidates(
        self,
        document_id: int,
        query: str,
        top_k: int,
        filter_section: Optional[str],
    ) -> List[dict]:
        """
        Vector search → fetch top_k*3 candidates → merge BM25 scores.
        """
        try:
            col = self._client.get_collection(self._col(document_id))
        except Exception:
            logger.warning(f"[Embed] No collection for doc {document_id}")
            return []

        q_emb = self.get_embedding(query)
        if q_emb is None:
            return []

        where = {"document_id": document_id}
        if filter_section:
            where["section_title"] = {"$contains": filter_section}

        n_candidates = min(top_k * 3, col.count())
        if n_candidates == 0:
            return []

        results = col.query(
            query_embeddings=[q_emb],
            n_results=n_candidates,
            where=where,
            include=["documents", "metadatas", "distances", "embeddings"],
        )

        if not results or not results["documents"]:
            return []

        docs      = results["documents"][0]
        metas     = results["metadatas"][0]
        dists     = results["distances"][0]
        embs      = results["embeddings"][0] if results.get("embeddings") else [None] * len(docs)
        chunk_ids = [m.get("chunk_db_id") or f"doc{document_id}_chunk{i}"
                     for i, m in enumerate(metas)]

        # Collect ChromaDB chunk IDs for BM25 lookup
        chroma_ids = [
            f"doc{document_id}_chunk{m.get('chunk_index', i)}"
            for i, m in enumerate(metas)
        ]
        bm25_scores = self._get_bm25_scores(document_id, query, chroma_ids)

        candidates = []
        for i, (doc, meta, dist, emb) in enumerate(zip(docs, metas, dists, embs)):
            vec_score  = round(1.0 - float(dist), 4)   # cosine similarity
            bm25_score = bm25_scores.get(chroma_ids[i], 0.0)
            hybrid     = round(VECTOR_WEIGHT * vec_score + BM25_WEIGHT * bm25_score, 4)

            candidates.append({
                "content":         doc,
                "raw_content":     meta.get("raw_content", doc),
                "metadata":        meta,
                "chroma_id":       chroma_ids[i],
                "distance":        float(dist),
                "relevance_score": round(vec_score * 100, 1),
                "bm25_score":      round(bm25_score * 100, 1),
                "hybrid_score":    round(hybrid * 100, 1),
                "_embedding":      emb,   # kept for MMR cosine calc; stripped on return
            })

        # Sort by hybrid score (descending)
        candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return candidates

    # ── MMR Re-Ranking ─────────────────────────────────────────────────────────

    def _apply_mmr(
        self, candidates: List[dict], query: str, top_k: int
    ) -> List[dict]:
        """
        Maximum Marginal Relevance:
          mmr_score = (1 - λ) * hybrid_score - λ * max_sim_to_selected

        λ = MMR_LAMBDA = 0.5
        → 50% relevance, 50% diversity
        → Prevents returning 6 chunks from the same clause
        """
        selected: List[dict] = []
        remaining = list(candidates)

        while remaining and len(selected) < top_k:
            best_idx, best_score = 0, -float("inf")

            for i, cand in enumerate(remaining):
                rel_score = cand["hybrid_score"] / 100.0

                # Penalty: similarity to already-selected chunks
                if selected:
                    sims = [
                        self._cosine(cand["_embedding"], s["_embedding"])
                        for s in selected
                        if cand["_embedding"] and s["_embedding"]
                    ]
                    max_sim = max(sims) if sims else 0.0
                else:
                    max_sim = 0.0

                mmr = (1 - MMR_LAMBDA) * rel_score - MMR_LAMBDA * max_sim

                if mmr > best_score:
                    best_score = mmr
                    best_idx = i

            chosen = remaining.pop(best_idx)
            chosen["mmr_score"] = round(best_score * 100, 1)
            selected.append(chosen)

        # Strip internal embedding from output
        for item in selected:
            item.pop("_embedding", None)

        return selected

    @staticmethod
    def _cosine(a: Optional[List[float]], b: Optional[List[float]]) -> float:
        if not a or not b:
            return 0.0
        dot   = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(y * y for y in b))
        return dot / (mag_a * mag_b) if mag_a * mag_b > 0 else 0.0

    # ── Query Expansion via Ollama Mistral ─────────────────────────────────────

    def _search_with_expansion(
        self,
        document_id: int,
        query: str,
        top_k: int,
        filter_section: Optional[str],
    ) -> List[dict]:
        """
        1. Ask Mistral to generate 3 legal-synonym rephrases of query
        2. Search each variant (top_k=3 per variant)
        3. Aggregate by vote count (chunk appearing in most searches wins)
        4. Apply MMR on final pool

        WHY Mistral for expansion (not neural-chat):
          Mistral follows the "Return ONLY 3 lines" instruction precisely.
          Neural-chat tends to add explanations before/after the list.
          For expansion we need clean output, not conversational.
        """
        expansions = self._expand_query(query)
        all_queries = [query] + expansions[:3]

        vote_map: Dict[str, dict] = {}   # chroma_id → {chunk_data, votes}

        for q in all_queries:
            results = self._hybrid_candidates(document_id, q, top_k=3, filter_section=filter_section)
            for r in results:
                cid = r["chroma_id"]
                if cid not in vote_map:
                    vote_map[cid] = {"data": r, "votes": 0}
                vote_map[cid]["votes"] += 1

        # Sort by votes DESC then hybrid_score DESC
        pool = sorted(
            vote_map.values(),
            key=lambda x: (x["votes"], x["data"]["hybrid_score"]),
            reverse=True,
        )
        candidates = [v["data"] for v in pool]

        return self._apply_mmr(candidates, query, top_k)

    def _expand_query(self, query: str) -> List[str]:
        """
        Use Mistral 7B (temp=0.1) to rephrase the query with legal synonyms.
        Returns list of alternative query strings.
        """
        try:
            prompt = (
                "You are a legal contract expert. "
                "Rephrase the following query into 3 alternative legal wordings "
                "that would match equivalent contract clauses. "
                "Return ONLY 3 lines of text. No numbering. No explanation.\n\n"
                f"Query: {query}\n\nAlternatives:"
            )
            resp = httpx.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model":       settings.OLLAMA_CHAT_MODEL,   # mistral:7b-instruct
                    "prompt":      prompt,
                    "temperature": 0.1,
                    "stream":      False,
                    "num_predict": 150,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            lines = resp.json()["response"].strip().split("\n")
            # Filter blank/noise lines
            return [ln.strip() for ln in lines if ln.strip()][:3]
        except Exception as e:
            logger.warning(f"[QueryExpand] Failed: {e} — using original query only")
            return []

    # ── Housekeeping ───────────────────────────────────────────────────────────

    def delete_document(self, document_id: int):
        try:
            self._client.delete_collection(self._col(document_id))
            self._bm25_cache.pop(document_id, None)
            logger.info(f"[Embed] Deleted collection + BM25 cache for doc {document_id}")
        except Exception as e:
            logger.warning(f"[Embed] Delete failed: {e}")

    def is_ollama_available(self) -> bool:
        try:
            r = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    def get_collection_count(self, document_id: int) -> int:
        """Return number of vectors stored for a document."""
        try:
            return self._client.get_collection(self._col(document_id)).count()
        except Exception:
            return 0


# Singleton
embedding_service = EmbeddingService()