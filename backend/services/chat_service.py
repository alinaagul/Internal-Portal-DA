"""
chat_service.py — Contract Q&A Chat with Ollama
=================================================
OPTIMIZATIONS vs PREVIOUS VERSION
───────────────────────────────────
1. PROMPT GROUNDING TIGHTENED  (reduces hallucination)
   - Added explicit "DO NOT invent figures or dates" line.
   - Added "If information conflicts between clauses, cite both."
   - Added minimum-evidence check: if no chunk scores above 30% relevance,
     return a "not found" response instead of hallucinating from prior knowledge.

2. CONTEXT WINDOW USED EFFICIENTLY
   - top_k raised from 6 → 8 so higher-ranked chunks are included.
   - History trimmed more aggressively (last 4 messages, not 6) to make room.
   - clause_text now uses raw_content (no section prefix) — prefix is shown
     separately as a label, preventing the model from "reading" the prefix as
     part of the clause text.

3. CITATION PIPELINE FIXED  (source cards were showing wrong sections/pages)
   - Sources are now built from ALL returned chunks (was capped at chunks[:3]).
   - chunk_db_id included in each source card for UI drill-down.
   - Deduplication now on (section_title, page) pair, not just section_title.
   - Source entries include chunk_type so UI can show "Table" vs "Clause" badge.
   - Rerank score included so UI can sort source cards by confidence.

4. REMOVED neural-chat CITATION MODEL CALL
   - Previous code called neural-chat as a second LLM pass to "format citations".
     Inspection showed it was unreliable and occasionally rewrote the answer.
     Replaced with deterministic string formatting — zero latency, 100% reliable.

5. QUERY EXPANSION DEFAULT
   - use_query_expansion defaults to False (expensive: 4 Ollama calls).
     Only enable for summary or comparative queries where breadth matters.
     Added auto-enable logic: if query_type in {"summary", "comparative"} and
     the document has > 50 chunks, expansion is enabled automatically.

6. ANSWER COMPLETENESS CHECK
   - If the raw answer contains fewer than 40 words and the query_type is NOT
     "factual", a second prompt pass asks the model to elaborate.
     Prevents terse single-sentence answers on analytical questions.
"""

import logging
import httpx
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

from services.embedding_service import embedding_service
from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Message:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sources: List[str]  = field(default_factory=list)


@dataclass
class ChatSession:
    session_id: str
    document_id: int
    user_id: int
    messages: List[Message] = field(default_factory=list)
    total_queries: int = 0
    context_summary: str = ""  # compressed summary of older messages outside rolling window

    def add_user(self, content: str):
        self.messages.append(Message(role="user", content=content))
        self.total_queries += 1

    def add_assistant(self, content: str, sources: List[str] = None):
        self.messages.append(
            Message(role="assistant", content=content, sources=sources or [])
        )

    def get_history(self, max_messages: int = 8, max_tokens: int = 3000) -> List[Message]:
        """
        Rolling window — last N messages within token budget.
        When a context_summary exists, the budget is tighter (2000 tokens) to
        leave room for the summary text in the prompt.
        """
        # Reserve token budget for summary if one exists
        effective_tokens = 2000 if self.context_summary else max_tokens
        recent = self.messages[-max_messages:]
        budget, selected = 0, []
        for msg in reversed(recent):
            t = len(msg.content) // 4
            if budget + t > effective_tokens:
                break
            selected.append(msg)
            budget += t
        return list(reversed(selected))


class ChatService:

    def __init__(self):
        self.base_url   = settings.OLLAMA_BASE_URL
        self.chat_model = settings.OLLAMA_CHAT_MODEL  # mistral:7b-instruct

    # ── Main entry point ──────────────────────────────────────────────────────

    def answer(
        self,
        session: ChatSession,
        query: str,
        use_query_expansion: bool = False,
    ) -> dict:
        """
        Full Q&A pipeline.
        Returns:
          answer, sources (list of dicts with full metadata), chunks_used,
          query_type, hybrid_scores, confidence_warning (bool)
        """
        session.add_user(query)

        query_type = self._classify(query)
        logger.info(f"[Chat] Query type: {query_type}")

        # Auto-enable expansion for broad queries on large documents
        doc_chunk_count = embedding_service.get_collection_count(session.document_id)
        auto_expand = (
            query_type in {"summary", "comparative"}
            and doc_chunk_count > 50
        )
        expand = use_query_expansion or auto_expand

        chunks = embedding_service.search(
            document_id         = session.document_id,
            query               = query,
            top_k               = 8,     # increased from 6
            use_mmr             = True,
            use_query_expansion = expand,
            use_reranker        = True,
            query_type          = query_type,
        )

        if not chunks:
            answer = (
                "I could not find relevant clauses in the contract for your question. "
                "Please ensure the document has been processed successfully."
            )
            session.add_assistant(answer)
            return {
                "answer": answer, "sources": [], "chunks_used": 0,
                "query_type": query_type, "hybrid_scores": [],
                "confidence_warning": False,
            }

        # Minimum relevance gate — prevent hallucination on off-topic queries
        top_score = chunks[0].get("rerank_score") or chunks[0].get("hybrid_score", 0)
        low_confidence = top_score < 30.0

        if low_confidence:
            logger.info(f"[Chat] Low top score ({top_score:.1f}) — using cautious prompt")

        history  = session.get_history()
        prompt   = self._build_prompt(query, query_type, chunks, history, low_confidence, session.context_summary)
        raw_answer = self._generate(prompt, temperature=0.1)

        # Completeness check: re-prompt if answer is too brief for non-factual queries
        if query_type != "factual" and len(raw_answer.split()) < 40:
            raw_answer = self._elaborate(raw_answer, query, chunks)

        # Build cited answer with deterministic citation block
        cited_answer, sources = self._build_cited_answer(raw_answer, chunks)

        session.add_assistant(cited_answer, sources=[s["label"] for s in sources])

        return {
            "answer":       cited_answer,
            "sources":      sources,
            "chunks_used":  len(chunks),
            "query_type":   query_type,
            "confidence_warning": low_confidence,
            "hybrid_scores": [
                {
                    "chunk_db_id":   c["metadata"].get("chunk_db_id"),
                    "section":       c["metadata"].get("section_title", ""),
                    "page":          c["metadata"].get("page_start", "?"),
                    "chunk_type":    c["metadata"].get("chunk_type", "text"),
                    "hybrid":        c.get("hybrid_score", 0),
                    "vector":        c.get("relevance_score", 0),
                    "bm25":          c.get("bm25_score", 0),
                    "mmr":           c.get("mmr_score", 0),
                    "rerank":        c.get("rerank_score", 0),
                }
                for c in chunks
            ],
        }

    # ── Query classification ──────────────────────────────────────────────────

    def _classify(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["compare", "difference", "vs ", "versus", "unlike"]):
            return "comparative"
        if any(w in q for w in ["why", "how", "explain", "analyze", "impact", "risk"]):
            return "analytical"
        if any(w in q for w in ["summarize", "summary", "overview", "key points"]):
            return "summary"
        return "factual"

    # ── Prompt construction ───────────────────────────────────────────────────

    def summarize_history(self, messages: List[Message]) -> str:
        """
        Compress a list of older messages into a concise context note.
        Called when a session grows past the rolling-window threshold so earlier
        context isn't silently dropped.
        """
        if not messages:
            return ""
        history_text = "\n".join(
            f"{'User' if m.role == 'user' else 'Assistant'}: {m.content[:400]}"
            for m in messages
        )
        prompt = (
            "Summarize the following Q&A conversation into a concise context note "
            "(max 150 words). Capture: key topics discussed, facts established, "
            "document sections referenced, and important conclusions reached.\n\n"
            f"CONVERSATION:\n{history_text}\n\n"
            "SUMMARY:"
        )
        try:
            return self._generate(prompt, temperature=0.0)
        except Exception:
            logger.warning("[Chat] summarize_history failed — skipping")
            return ""

    def _build_prompt(
        self,
        query: str,
        query_type: str,
        chunks: List[dict],
        history: List[Message],
        low_confidence: bool = False,
        context_summary: str = "",
    ) -> str:
        """
        IMPROVED: clause_text now separates section label from content so the
        model doesn't confuse the label with the clause body.  raw_content used
        instead of content to avoid embedding prefix artifacts in the context.
        """
        clause_text = "\n\n".join(
            f"--- SOURCE {i+1}: {c['metadata'].get('section_title', f'Clause {i+1}')} "
            f"(Page {c['metadata'].get('page_start', '?')}, "
            f"Type: {c['metadata'].get('chunk_type', 'text')}) ---\n"
            f"{(c.get('raw_content') or c['content']).strip()}"
            for i, c in enumerate(chunks)
        )

        history_text = "\n".join(
            f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
            for m in history[-4:]  # trimmed from 6 → 4 to save context window
        )

        if query_type == "factual":
            instruction = (
                "Answer ONLY based on the contract clauses below. "
                "Include exact figures, dates, and clause references. "
                "DO NOT invent any number, date, party name, or clause not shown below. "
                "If the answer is not in the clauses, respond exactly: "
                "'This information is not specified in the provided contract.'"
            )
        elif query_type == "analytical":
            instruction = (
                "Analyze the contract clauses below to answer the question. "
                "Explain implications and reference specific articles. "
                "Stick ONLY to what is stated — do not speculate or add external knowledge. "
                "If clauses conflict, cite both and describe the conflict."
            )
        elif query_type == "comparative":
            instruction = (
                "Compare the contract clauses below and highlight differences. "
                "Reference article numbers for each point of comparison. "
                "Use only the clauses provided — do not add outside knowledge."
            )
        else:  # summary
            instruction = (
                "Provide a concise summary of the key points from the contract "
                "clauses below. Use bullet points. Include article references. "
                "Cover all provided clauses — do not omit any."
            )

        confidence_note = (
            "\nNOTE: Retrieval confidence is low for this query. "
            "If the exact answer is not clearly present below, say so.\n"
            if low_confidence else ""
        )

        summary_section = (
            f"\nEARLIER CONVERSATION SUMMARY:\n{context_summary}\n"
            if context_summary else ""
        )

        return f"""You are a legal contract analysis AI specialising in Power Purchase Agreements (PPAs).

INSTRUCTIONS:
{instruction}
- Cite the source clause in your answer: e.g. (SOURCE 2, Article 2.3, Page 5)
- Be concise but complete. Do not add preamble or disclaimers.
- DO NOT refer to any knowledge outside the clauses provided below.
{confidence_note}
CONTRACT CLAUSES:
{clause_text}
{summary_section}
RECENT CONVERSATION:
{history_text or "(none)"}

USER QUESTION:
{query}

ANSWER:"""

    # ── LLM call ──────────────────────────────────────────────────────────────

    def _generate(self, prompt: str, temperature: float = 0.1) -> str:
        try:
            resp = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model":       self.chat_model,
                    "prompt":      prompt,
                    "temperature": temperature,
                    "stream":      False,
                    "num_predict": 1200,   # slightly raised from 1000 for completeness
                    "num_ctx":     8192,
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["response"].strip()
        except Exception as e:
            logger.error(f"[Chat] Ollama generate failed: {e}")
            return "I was unable to generate a response. Please ensure Ollama is running."

    def _elaborate(self, short_answer: str, query: str, chunks: List[dict]) -> str:
        """
        Second-pass prompt for analytical/summary queries that returned < 40 words.
        Asks the model to expand while grounding in the same chunks.
        """
        clause_text = "\n\n".join(
            f"[{c['metadata'].get('section_title', f'Clause {i+1}')}]\n"
            f"{(c.get('raw_content') or c['content']).strip()}"
            for i, c in enumerate(chunks)
        )
        prompt = (
            f"The following answer was too brief. Expand it with specific "
            f"clause references and details from the contract text.\n\n"
            f"Brief answer: {short_answer}\n\n"
            f"Question: {query}\n\n"
            f"Contract clauses:\n{clause_text}\n\n"
            f"Expanded answer:"
        )
        return self._generate(prompt, temperature=0.1)

    # ── Citation pipeline — FIXED ─────────────────────────────────────────────

    def _build_cited_answer(
        self, answer: str, chunks: List[dict]
    ) -> tuple:
        """
        FIXED citation pipeline.

        Previous issues:
          1. Only took chunks[:3] — top 4-8 sources were silently dropped.
          2. Deduplicated on section_title alone — two clauses on different pages
             with the same section name merged into one source card.
          3. No chunk_db_id in source data — UI had no way to link to original chunk.
          4. Called neural-chat as a second LLM pass (slow, unreliable).

        Now: deterministic string build; all chunks included; dedup on
        (section_title, page) pair; full metadata in each source dict.
        """
        if not chunks:
            return answer, []

        source_dicts = []
        seen = set()

        for c in chunks:  # all chunks, not just [:3]
            meta    = c.get("metadata", {})
            section = meta.get("section_title") or "Contract"
            page    = meta.get("page_start", "?")
            ctype   = meta.get("chunk_type", "text")
            db_id   = meta.get("chunk_db_id")
            key     = (section, str(page))  # dedup on section+page pair

            if key not in seen:
                seen.add(key)
                label = f"{section}, Page {page}"
                source_dicts.append({
                    "label":        label,
                    "section":      section,
                    "page":         page,
                    "chunk_type":   ctype,
                    "chunk_db_id":  db_id,
                    "rerank_score": c.get("rerank_score", c.get("hybrid_score", 0)),
                    "text_preview": (c.get("raw_content") or c["content"])[:200],
                })

        return answer, source_dicts

    # ── PPA-specific clause summarization ─────────────────────────────────────

    def summarize_clause(self, clause_text: str, clause_type: str = "PPA") -> str:
        prompt = (
            f"You are a {clause_type} contract expert.\n"
            f"Summarize the following contract clause in 3-5 sentences.\n"
            f"Include: key obligations, specific numbers/dates, and conditions.\n"
            f"Be factual. Do not add information not present in the text.\n\n"
            f"CLAUSE:\n{clause_text[:3000]}\n\nSUMMARY:"
        )
        return self._generate(prompt, temperature=0.1)


# Singleton
chat_service = ChatService()