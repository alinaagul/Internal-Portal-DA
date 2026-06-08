"""
embedding_service.py — Hybrid Retrieval: Vector (HNSW) + BM25 + MMR + Cross-Encoder Reranking
================================================================================================
PURPOSE:
  Third step in the pipeline. Converts chunks into vector embeddings via Ollama
  and stores them in ChromaDB with HNSW index. Also builds a BM25 in-memory
  keyword index per document. At query time combines both with MMR diversity
  re-ranking, optional query expansion, and a cross-encoder reranker as the
  final scoring pass.

WHY THIS FILE EXISTS:
  Pure vector search misses exact keyword matches ("PPA", "NEPRA", specific
  clause numbers). Pure BM25 misses semantic variants ("terminate" vs "end").
  Hybrid = best of both worlds for contract clause retrieval.

  MMR (Maximum Marginal Relevance) prevents returning 6 chunks from the same
  paragraph — forces diversity across contract sections.

  Cross-Encoder Reranking (biggest quality improvement):
    Vector/BM25 scores are "retrieval" scores — fast approximate matches.
    A cross-encoder sees (query, chunk) together and produces a true relevance
    score.  It scores far fewer candidates (top 20 not all) so it's still fast.
    For legal Q&A this typically improves precision@3 by 15–25% because it
    catches subtle clause dependencies that cosine similarity misses entirely.
    Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (6-layer, ~22ms per pair on CPU)
    Install: pip install sentence-transformers

  BM25 Tuning:
    Uses BM25Plus (not BM25Okapi) — Plus uses a floor on term-frequency so
    documents containing a term zero times don't get a negative contribution.
    This matters for contracts with rare clause-specific terms (e.g. "dispatch",
    "tariff") that appear in only a handful of chunks.
    k1=1.5 (term saturation), b=0.75 (length normalisation) — standard values
    but explicitly set so they can be tuned per-corpus.
    Legal stopwords ("shall", "herein", "thereof", "hereinafter") are removed
    before indexing because they appear everywhere and dilute BM25 scores.

  MMR Tuning:
    Lambda is now dynamic:
      "factual" query  → λ=0.3  (prefer relevance — clause lookup)
      "analytical"     → λ=0.5  (balance — synthesis needs breadth)
      "comparative"    → λ=0.7  (prefer diversity — need different sections)
      "summary"        → λ=0.6  (breadth — need full contract coverage)
    Default λ=0.5 when query_type is unknown.
    MMR pool is now top_k * 4 candidates (was * 3) to give reranker more
    material to work with.

  Query Expansion uses Ollama/Mistral to rephrase the user's query with legal
  synonyms, then aggregates results by vote count (most-agreed chunk wins).

RETRIEVAL FLOW for a query (updated):
  1. Embed query → vector search (top_k * 4 candidates)
  2. BM25Plus score same candidates
  3. Hybrid score = 0.6 * vector_score + 0.4 * bm25_score
  4. MMR re-rank for diversity (dynamic λ by query type)
  5. Cross-encoder rerank top MMR results → final top_k
  6. Optional: query expansion → merge + vote → steps 3-5
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

VECTOR_WEIGHT = 0.6   # weight for cosine similarity score
BM25_WEIGHT   = 0.4   # weight for BM25Plus score

# Dynamic MMR lambda per query type (0=pure relevance, 1=pure diversity)
MMR_LAMBDA_BY_TYPE = {
    "factual":     0.3,   # clause lookup — maximise precision
    "analytical":  0.5,   # synthesis — balance relevance + breadth
    "comparative": 0.7,   # needs chunks from different sections
    "summary":     0.6,   # needs broad contract coverage
    "default":     0.5,
}

# BM25Plus parameters
BM25_K1   = 1.5    # term-frequency saturation (higher → rewards repeated terms more)
BM25_B    = 0.75   # length normalisation (1.0 = full; 0.0 = none)
BM25_DELTA = 0.5   # BM25Plus floor to avoid negative contributions

# Legal stopwords — removed before BM25 indexing (they appear everywhere in contracts)
LEGAL_STOPWORDS = frozenset({
    "shall", "herein", "thereof", "hereinafter", "hereto", "hereby",
    "hereunder", "whereof", "thereto", "therein", "thereunder",
    "the", "a", "an", "of", "in", "to", "and", "or", "for", "with",
    "that", "this", "such", "any", "all", "each", "its", "be", "by",
    "as", "at", "on", "is", "are", "was", "were", "will", "may",
    "have", "has", "had", "not", "from", "upon", "which", "their",
})


class EmbeddingService:
    """
    Manages embeddings + hybrid retrieval for all uploaded documents.
    One ChromaDB collection per document_id.
    One BM25 index per document_id (in-memory, rebuilt on demand).
    """

    def __init__(self):
        CHROMA_PATH.mkdir(exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        # BM25 cache: { document_id: (BM25Plus instance, [chunk_ids], [raw_texts]) }
        self._bm25_cache: Dict[int, tuple] = {}
        # Cross-encoder reranker (lazy-loaded on first use)
        self._reranker = None
        self._reranker_available: Optional[bool] = None  # None = not yet checked

    # ── Collection name helper ─────────────────────────────────────────────────

    def _col(self, document_id: int) -> str:
        return f"doc_{document_id}"

    # ── Embedding via Ollama ───────────────────────────────────────────────────

    MAX_EMBED_CHARS = 400  

    def get_embedding(self, text: str) -> Optional[List[float]]:
        # Hard truncate to model context limit before sending
        if len(text) > self.MAX_EMBED_CHARS:
            logger.warning(
                f"[Embed] Truncating input from {len(text)} to {self.MAX_EMBED_CHARS} chars"
            )
            text = text[:self.MAX_EMBED_CHARS]

        try:
            logger.info(f"[Embed] Using model: {settings.OLLAMA_EMBED_MODEL}")
            resp = httpx.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={
                    "model": settings.OLLAMA_EMBED_MODEL,
                    "prompt": text          # ← was sending unbounded text
                },
                timeout=60.0,
            )
            logger.info(f"[Embed] Status Code: {resp.status_code}")
            resp.raise_for_status()
            return resp.json()["embedding"]

        except Exception as e:
            logger.error(f"[Embed] Ollama embedding failed: {e}")
            try:
                logger.error(f"[Embed] Response: {resp.text}")
            except:
                pass
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
        """
        Build in-memory BM25Plus index from raw_content.

        WHY BM25Plus over BM25Okapi:
          BM25Plus adds a delta floor so terms that don't appear in a document
          never subtract from the score. Contracts are full of rare but critical
          terms (e.g. "NEPRA", "tariff", "dispatch") that appear in only a few
          chunks — BM25Plus handles this better than Okapi.

        WHY remove legal stopwords before indexing:
          "shall", "herein", "thereof" etc. appear in nearly every chunk of a
          contract.  They carry zero discriminating signal but consume BM25's
          term-frequency budget, pushing rare meaningful terms down.
        """
        try:
            from rank_bm25 import BM25Plus
        except ImportError:
            logger.warning("[BM25] rank-bm25 not installed — pip install rank-bm25")
            return

        if not raw_texts:
            logger.warning(f"[BM25] No chunks to index for doc {document_id} — skipping BM25 build")
            return

        tokenized = [
            [w for w in text.lower().split() if w not in LEGAL_STOPWORDS]
            for text in raw_texts
        ]

        # After stopword removal some chunks may be empty token lists.
        # BM25Plus divides by corpus_size (number of non-empty docs) so we
        # must ensure at least one token survives per chunk.
        tokenized = [toks if toks else ["_empty_"] for toks in tokenized]

        try:
            bm25 = BM25Plus(tokenized, k1=BM25_K1, b=BM25_B, delta=BM25_DELTA)
        except ZeroDivisionError:
            logger.warning(f"[BM25] ZeroDivisionError building index for doc {document_id} — skipping")
            return

        self._bm25_cache[document_id] = (bm25, chunk_ids, raw_texts)
        logger.info(f"[BM25] BM25Plus index built for doc {document_id} ({len(raw_texts)} chunks)")

    def _get_bm25_scores(
        self, document_id: int, query: str, chunk_ids: List[str]
    ) -> Dict[str, float]:
        """
        Return BM25Plus scores for specified chunk_ids.
        Scores are normalised to [0, 1].
        Query tokens are filtered with the same legal stopwords used at index time
        so BM25 scoring is symmetric.
        """
        if document_id not in self._bm25_cache:
            self._reload_bm25_from_chroma(document_id)

        entry = self._bm25_cache.get(document_id)
        if not entry:
            return {cid: 0.0 for cid in chunk_ids}

        bm25, all_ids, _ = entry
        tokenized_query = [
            w for w in query.lower().split() if w not in LEGAL_STOPWORDS
        ]
        if not tokenized_query:
            return {cid: 0.0 for cid in chunk_ids}

        scores = bm25.get_scores(tokenized_query)   # scores for ALL chunks

        id_to_score: Dict[str, float] = {}
        for i, cid in enumerate(all_ids):
            id_to_score[cid] = float(scores[i])

        # Normalise to [0, 1]
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
        use_reranker: bool = True,
        query_type: str = "default",
        filter_section: Optional[str] = None,
    ) -> List[dict]:
        """
        Full hybrid retrieval pipeline.
        1. Vector search (top_k * 4 candidates)
        2. BM25Plus score each candidate
        3. Hybrid score = VECTOR_WEIGHT * vec + BM25_WEIGHT * bm25
        4. MMR re-rank for diversity (dynamic λ by query_type)
        5. Cross-encoder rerank → final top_k  (biggest quality jump)
        6. Optionally expand query → aggregate by vote

        Returns list of dicts:
          content, raw_content, metadata, distance,
          relevance_score, bm25_score, hybrid_score, rerank_score
        """
        if use_query_expansion:
            candidates = self._search_with_expansion(
                document_id, query, top_k, filter_section
            )
        else:
            candidates = self._hybrid_candidates(document_id, query, top_k, filter_section)

            if use_mmr and len(candidates) > top_k:
                candidates = self._apply_mmr(candidates, query, top_k, query_type)
            else:
                candidates = candidates[:top_k]

        # Cross-encoder reranking — applied last, always on the MMR output
        if use_reranker and candidates:
            candidates = self._apply_reranker(query, candidates)

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

        n_candidates = min(top_k * 4, col.count())   # larger pool for reranker
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
        self, candidates: List[dict], query: str, top_k: int,
        query_type: str = "default",
    ) -> List[dict]:
        """
        Maximum Marginal Relevance with dynamic lambda.

        Lambda is chosen by query_type:
          factual     → 0.3  (tight relevance; clause-lookup needs precision)
          analytical  → 0.5  (balance; synthesis needs related sections)
          comparative → 0.7  (diversity; must pull from different articles)
          summary     → 0.6  (breadth; need wide contract coverage)

        Formula: mmr_score = (1-λ) * hybrid_score − λ * max_sim_to_selected

        WHY we pass query_type from chat_service:
          The chat classifier already knows what kind of query this is.
          Reusing that label here avoids a second LLM call and keeps the
          retrieval strategy coherent with the generation strategy.
        """
        mmr_lambda = MMR_LAMBDA_BY_TYPE.get(query_type, MMR_LAMBDA_BY_TYPE["default"])
        logger.debug(f"[MMR] query_type={query_type} → λ={mmr_lambda}")

        selected: List[dict] = []
        remaining = list(candidates)

        while remaining and len(selected) < top_k:
            best_idx, best_score = 0, -float("inf")

            for i, cand in enumerate(remaining):
                rel_score = cand["hybrid_score"] / 100.0

                if selected:
                    sims = [
                        self._cosine(cand["_embedding"], s["_embedding"])
                        for s in selected
                        if cand["_embedding"] and s["_embedding"]
                    ]
                    max_sim = max(sims) if sims else 0.0
                else:
                    max_sim = 0.0

                mmr = (1 - mmr_lambda) * rel_score - mmr_lambda * max_sim

                if mmr > best_score:
                    best_score = mmr
                    best_idx   = i

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

    # ── Cross-Encoder Reranking ────────────────────────────────────────────────

    def _load_reranker(self) -> bool:
        """
        Lazy-load the cross-encoder model on first use.
        Model: cross-encoder/ms-marco-MiniLM-L-6-v2
          - 6-layer MiniLM, ~22MB, ~22ms per (query, passage) pair on CPU
          - Fine-tuned on MS-MARCO passage ranking (generalises well to legal)
          - Install: pip install sentence-transformers
        Returns True if loaded successfully, False otherwise.
        """
        if self._reranker_available is not None:
            return self._reranker_available

        try:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                max_length=512,
            )
            self._reranker_available = True
            logger.info("[Reranker] cross-encoder/ms-marco-MiniLM-L-6-v2 loaded ✓")
        except Exception as e:
            logger.warning(
                f"[Reranker] Could not load cross-encoder: {e}\n"
                "  → Install: pip install sentence-transformers\n"
                "  → Retrieval will still work but without reranking."
            )
            self._reranker_available = False

        return self._reranker_available

    def _apply_reranker(self, query: str, candidates: List[dict]) -> List[dict]:
        """
        Cross-encoder reranking — the biggest quality improvement in the pipeline.

        HOW IT WORKS:
          A bi-encoder (what we use for retrieval) embeds query and document
          *independently*, then scores by cosine distance.  Fast but approximate.
          A cross-encoder sees (query, document) *concatenated* and scores the
          pair jointly.  Much slower per pair but far more accurate because it
          can model token-level interactions between query and clause.

        WHY IT'S PLACED LAST:
          We run it only on the MMR output (top_k candidates, typically 6-10)
          not on all chunks.  This keeps latency low (~130ms for 6 pairs on CPU)
          while capturing the full precision advantage.

        SCORE NORMALISATION:
          Cross-encoder logits are unbounded.  We apply sigmoid to map them to
          [0, 1] and store as `rerank_score` (0–100 after * 100).

        CHUNK TYPE BOOSTING:
          Definition chunks get a +5 point boost when the query contains
          "mean", "define", "what is", "what does" — this is cheaper and more
          reliable than fine-tuning the model.
          Table chunks get a +3 point boost for numeric/tabular queries.
        """
        if not self._load_reranker():
            return candidates   # graceful degradation — return MMR order

        import math as _math

        def sigmoid(x: float) -> float:
            return 1.0 / (1.0 + _math.exp(-x))

        q_lower = query.lower()
        is_definition_query = any(
            w in q_lower for w in ["mean", "define", "what is", "what does", "definition of"]
        )
        is_numeric_query = any(
            w in q_lower for w in ["how much", "price", "rate", "amount", "percentage", "%", "mw", "kwh"]
        )

        # Build (query, passage) pairs — use raw_content for reranker
        # (no section prefix; the cross-encoder should score the actual clause text)
        pairs = [
            (query, c.get("raw_content", c["content"])[:512])
            for c in candidates
        ]

        try:
            logits = self._reranker.predict(pairs)
        except Exception as e:
            logger.warning(f"[Reranker] Inference failed: {e} — returning MMR order")
            return candidates

        for cand, logit in zip(candidates, logits):
            score = sigmoid(float(logit)) * 100.0

            # Chunk-type boosting
            chunk_type = cand.get("metadata", {}).get("chunk_type", "text")
            if is_definition_query and chunk_type == "definition":
                score = min(100.0, score + 5.0)
            elif is_numeric_query and chunk_type == "table":
                score = min(100.0, score + 3.0)

            cand["rerank_score"] = round(score, 1)

        # Sort by rerank_score descending
        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        logger.debug(
            f"[Reranker] Top scores: "
            + ", ".join(f"{c['rerank_score']:.1f}" for c in candidates[:3])
        )
        return candidates

    # ── Query Expansion via Ollama Mistral ─────────────────────────────────────

    def _search_with_expansion(
        self,
        document_id: int,
        query: str,
        top_k: int,
        filter_section: Optional[str],
        query_type: str = "default",
        use_reranker: bool = True,
    ) -> List[dict]:
        """
        1. Ask Mistral to generate 3 legal-synonym rephrases of query
        2. Search each variant (top_k=3 per variant)
        3. Aggregate by vote count (chunk appearing in most searches wins)
        4. Apply MMR on final pool (dynamic λ by query_type)
        5. Apply cross-encoder reranker

        WHY Mistral for expansion (not neural-chat):
          Mistral follows the "Return ONLY 3 lines" instruction precisely.
          Neural-chat tends to add explanations before/after the list.
          For expansion we need clean output, not conversational.
        """
        expansions  = self._expand_query(query)
        all_queries = [query] + expansions[:3]

        vote_map: Dict[str, dict] = {}

        for q in all_queries:
            results = self._hybrid_candidates(document_id, q, top_k=3, filter_section=filter_section)
            for r in results:
                cid = r["chroma_id"]
                if cid not in vote_map:
                    vote_map[cid] = {"data": r, "votes": 0}
                vote_map[cid]["votes"] += 1

        pool = sorted(
            vote_map.values(),
            key=lambda x: (x["votes"], x["data"]["hybrid_score"]),
            reverse=True,
        )
        candidates = [v["data"] for v in pool]
        candidates = self._apply_mmr(candidates, query, top_k, query_type)

        if use_reranker and candidates:
            candidates = self._apply_reranker(query, candidates)

        return candidates

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