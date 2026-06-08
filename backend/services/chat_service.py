"""
chat_service.py — Contract Q&A Chat with Ollama
=================================================
PURPOSE:
  The intelligence layer. Given a user question about a contract document,
  this service:
    1. Routes the query type (factual / analytical / comparative / clause-lookup)
    2. Retrieves relevant chunks via hybrid search (Vector + BM25 + MMR)
    3. Optionally expands the query with legal synonyms
    4. Generates a cited answer using an Ollama LLM
    5. Maintains rolling conversation memory (last 10 messages, 4K tokens)

WHY THIS FILE EXISTS:
  The documents endpoints only handle upload/storage. This service handles
  the intelligence: reasoning over retrieved contract clauses, generating
  summaries specific to each query, and formatting citations.

OLLAMA MODELS USED & WHY:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ Task               │ Model                │ Temp │ Why              │
  ├────────────────────┼──────────────────────┼──────┼──────────────────┤
  │ PPA clause Q&A     │ mistral:7b-instruct  │ 0.1  │ Best instruction │
  │                    │                      │      │ following at 7B; │
  │                    │                      │      │ precise for legal │
  │ Citation formatting│ neural-chat          │ 0.0  │ Clean structured  │
  │                    │ (or mistral fallback)│      │ output; good at  │
  │                    │                      │      │ [Source: ...] fmt │
  │ Clause summarization│ mistral:7b-instruct │ 0.1  │ Consistent facts; │
  │                    │                      │      │ low hallucination │
  │ Query expansion    │ mistral:7b-instruct  │ 0.1  │ Instruction-tuned │
  │                    │                      │      │ follows 3-line fmt│
  └─────────────────────────────────────────────────────────────────────┘

  LLAMA-2 vs MISTRAL for contracts:
    LLaMA-2 7B: Good recall, but tends to add disclaimers and preamble even
                when told not to. For contracts you need "Article 2.3 states..."
                not "I should mention I'm an AI and this isn't legal advice..."
    Mistral 7B: Follows "Answer ONLY based on contract text" instructions
                precisely. Recommended for PPA/contract Q&A.

  NEURAL-CHAT vs ORCA-MINI for citations:
    neural-chat: Produces clean "[Source: Article 2.3, Page 5]" format reliably.
    orca-mini  : Smaller (3B), faster, but citation formatting is inconsistent.
    Recommendation: Use neural-chat for citation formatting; orca-mini only
                    if you need sub-2-second latency on low-RAM machines.

  PULL COMMANDS:
    ollama pull mistral:7b-instruct
    ollama pull neural-chat          (for citation model)
    ollama pull mxbai-embed-large    (for embeddings)

TEMPERATURE RATIONALE:
  0.0 → deterministic, auditable (use for factual clause lookups)
  0.1 → slight variation for readability (use for summaries and analysis)
  0.3+ → NOT recommended for legal documents (hallucination risk increases)

CONTRACT-SPECIFIC NOTE (PPA clauses):
  For Power Purchase Agreement clause summarization, use mistral:7b-instruct
  at temp=0.1 with the factual_prompt template below. The model performs well
  on energy contract terminology (NEPRA, tariff, dispatch, capacity charges).
"""

import logging
import httpx
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

from services.embedding_service import embedding_service
from core.config import settings

logger = logging.getLogger(__name__)


# ─── Session state ────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str                  # "user" | "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sources: List[str] = field(default_factory=list)   # chunk section_titles used


@dataclass
class ChatSession:
    session_id: str
    document_id: int
    user_id: int
    messages: List[Message] = field(default_factory=list)
    total_queries: int = 0

    def add_user(self, content: str):
        self.messages.append(Message(role="user", content=content))
        self.total_queries += 1

    def add_assistant(self, content: str, sources: List[str] = None):
        self.messages.append(
            Message(role="assistant", content=content, sources=sources or [])
        )

    def get_history(self, max_messages: int = 10, max_tokens: int = 4000) -> List[Message]:
        """
        Rolling window — last N messages, trimmed to token budget.
        Prevents context window overflow (Mistral 7B = 8K context).
        4K for history leaves 4K for retrieved clauses + answer.
        """
        recent = self.messages[-max_messages:]
        budget, selected = 0, []
        for msg in reversed(recent):
            t = len(msg.content) // 4   # approx tokens
            if budget + t > max_tokens:
                break
            selected.append(msg)
            budget += t
        return list(reversed(selected))


# ─── Chat service ─────────────────────────────────────────────────────────────

class ChatService:
    """
    Main Q&A engine for contract documents.
    call: chat_service.answer(session, query) → str
    """

    def __init__(self):
        self.base_url     = settings.OLLAMA_BASE_URL
        self.chat_model   = settings.OLLAMA_CHAT_MODEL       # mistral:7b-instruct
        self.citation_model = settings.OLLAMA_CITATION_MODEL  # neural-chat

    # ── Main entry point ──────────────────────────────────────────────────────

    def answer(
        self,
        session: ChatSession,
        query: str,
        use_query_expansion: bool = False,
    ) -> dict:
        """
        Full Q&A pipeline.
        Returns: { "answer": str, "sources": list, "chunks_used": int,
                   "query_type": str, "hybrid_scores": list }
        """
        session.add_user(query)

        # ── Step 1: Classify query type ────────────────────────────────────
        query_type = self._classify(query)
        logger.info(f"[Chat] Query type: {query_type}")

        # ── Step 2: Hybrid retrieval (Vector + BM25Plus + MMR + Reranker) ──────
        chunks = embedding_service.search(
            document_id        = session.document_id,
            query              = query,
            top_k              = 6,
            use_mmr            = True,
            use_query_expansion= use_query_expansion,
            use_reranker       = True,
            query_type         = query_type,   # passed so MMR lambda is query-aware
        )

        if not chunks:
            answer = (
                "I could not find relevant clauses in the contract for your question. "
                "Please ensure the document has been processed successfully."
            )
            session.add_assistant(answer)
            return {"answer": answer, "sources": [], "chunks_used": 0, "query_type": query_type}

        # ── Step 3: Build prompt based on query type ───────────────────────
        history  = session.get_history()
        prompt   = self._build_prompt(query, query_type, chunks, history)

        # ── Step 4: Generate answer (Mistral 7B, temp=0.1) ────────────────
        raw_answer = self._generate(prompt, model=self.chat_model, temperature=0.1)

        # ── Step 5: Format citations (neural-chat or mistral fallback) ────
        cited_answer = self._add_citations(raw_answer, chunks)

        # ── Step 6: Store in session memory ───────────────────────────────
        sources = [
            f"{c['metadata'].get('section_title', 'Unknown')} — "
            f"Page {c['metadata'].get('page_start', '?')}"
            for c in chunks[:3]
        ]
        session.add_assistant(cited_answer, sources=sources)

        return {
            "answer":        cited_answer,
            "sources":       sources,
            "chunks_used":   len(chunks),
            "query_type":    query_type,
            "hybrid_scores": [
                {
                    "section":  c["metadata"].get("section_title", ""),
                    "hybrid":   c.get("hybrid_score", 0),
                    "vector":   c.get("relevance_score", 0),
                    "bm25":     c.get("bm25_score", 0),
                    "mmr":      c.get("mmr_score", 0),
                    "rerank":   c.get("rerank_score", 0),   # cross-encoder score
                }
                for c in chunks
            ],
        }

    # ── Query classification ──────────────────────────────────────────────────

    def _classify(self, query: str) -> str:
        """
        Keyword-based query routing — fast, no LLM needed.
        Returns: "factual" | "analytical" | "comparative" | "summary"
        """
        q = query.lower()
        if any(w in q for w in ["compare", "difference", "vs ", "versus", "unlike"]):
            return "comparative"
        if any(w in q for w in ["why", "how", "explain", "analyze", "impact", "risk"]):
            return "analytical"
        if any(w in q for w in ["summarize", "summary", "overview", "key points"]):
            return "summary"
        return "factual"   # default: what/when/who/which

    # ── Prompt construction ───────────────────────────────────────────────────

    def _build_prompt(
        self,
        query: str,
        query_type: str,
        chunks: List[dict],
        history: List[Message],
    ) -> str:
        """
        Constructs the Ollama prompt.
        section_title is prepended to each chunk for citation anchoring.
        """
        clause_text = "\n\n".join(
            f"[{c['metadata'].get('section_title', f'Clause {i+1}')}]"
            f" (Page {c['metadata'].get('page_start', '?')})\n"
            f"{c.get('raw_content', c['content'])}"
            for i, c in enumerate(chunks)
        )

        history_text = "\n".join(
            f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
            for m in history[-6:]   # last 6 messages only
        )

        # ── Template by query type ─────────────────────────────────────────

        if query_type == "factual":
            instruction = (
                "Answer ONLY based on the contract clauses below. "
                "Include exact figures, dates, and clause references. "
                "If the answer is not in the contract, respond: "
                "'This information is not specified in the provided contract.'"
            )
        elif query_type == "analytical":
            instruction = (
                "Analyze the contract clauses below to answer the question. "
                "Explain the implications and reference specific articles. "
                "Stick to what is stated in the contract; do not speculate."
            )
        elif query_type == "comparative":
            instruction = (
                "Compare the contract clauses below and highlight differences. "
                "Reference article numbers for each point of comparison."
            )
        else:  # summary
            instruction = (
                "Provide a concise summary of the key points from the contract "
                "clauses below. Use bullet points. Include article references."
            )

        return f"""You are a legal contract analysis AI specialising in Power Purchase Agreements (PPAs).

INSTRUCTIONS:
{instruction}
- Always cite the source clause: e.g. (Article 2.3, Page 5)
- Be concise but complete. Avoid unnecessary preamble.
- Temperature is 0.1 — stay factual and consistent.

CONTRACT CLAUSES:
{clause_text}

CONVERSATION HISTORY:
{history_text or "(none)"}

USER QUESTION:
{query}

ANSWER:"""

    # ── LLM call ──────────────────────────────────────────────────────────────

    def _generate(self, prompt: str, model: str, temperature: float) -> str:
        """
        Call Ollama generate endpoint.
        model: mistral:7b-instruct for Q&A (temp=0.1)
               neural-chat for citation formatting (temp=0.0)
        """
        try:
            resp = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model":       model,
                    "prompt":      prompt,
                    "temperature": temperature,
                    "stream":      False,
                    "num_predict": 1000,
                    "num_ctx":     8192,   # Mistral/NeuralChat context window
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["response"].strip()
        except Exception as e:
            logger.error(f"[Chat] Ollama generate failed ({model}): {e}")
            return "I was unable to generate a response. Please ensure Ollama is running."

    # ── Citation formatting ───────────────────────────────────────────────────

    def _add_citations(self, answer: str, chunks: List[dict]) -> str:
        """
        Append a sources section at the end of the answer.

        WHY neural-chat for this task:
          neural-chat produces clean, consistent "[Source: ...]" format.
          If neural-chat is unavailable we fall back to simple string append
          (no extra LLM call needed — just format from chunk metadata).
        """
        # Simple deterministic citation append (no extra LLM call needed)
        if not chunks:
            return answer

        source_lines = []
        seen = set()
        for c in chunks[:4]:   # top 4 sources
            section = c["metadata"].get("section_title") or "Contract"
            page    = c["metadata"].get("page_start", "?")
            label   = f"{section}, Page {page}"
            if label not in seen:
                source_lines.append(f"  • {label}")
                seen.add(label)

        citation_block = "\n\nSources:\n" + "\n".join(source_lines)
        return answer + citation_block

    # ── PPA-specific clause summarization ─────────────────────────────────────

    def summarize_clause(
        self, clause_text: str, clause_type: str = "PPA"
    ) -> str:
        """
        Standalone clause summarization for PPA documents.
        Uses mistral:7b-instruct at temp=0.1.
        
        clause_type hints: "PPA" | "termination" | "payment" | "force_majeure"
        """
        prompt = f"""You are a {clause_type} contract expert.
Summarize the following contract clause in 3-5 sentences.
Include: key obligations, specific numbers/dates, and any conditions.
Be factual. Do not add information not present in the text.

CLAUSE:
{clause_text[:3000]}

SUMMARY:"""

        return self._generate(prompt, model=self.chat_model, temperature=0.1)


# Singleton
chat_service = ChatService()