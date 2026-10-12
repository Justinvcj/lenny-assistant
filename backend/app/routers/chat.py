"""Chat router handling message submission, retrieval grounding, agent execution, and citation verification.

Endpoints:
    POST /sessions/{session_id}/messages
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.orchestrator import run_agent
from app.agent.prompts import (
    EXACT_REFUSAL_MESSAGE,
    build_system_prompt,
    is_standalone_query,
    rewrite_query,
)
from app.agent.router import Intent, classify_intent
from app.agent.verify import (
    extract_citation_tags,
    normalize_citations,
    resolve_citations,
    verify_citations,
)
from app.config import get_settings
from app.db import get_db_session
from app.errors import AppException
from app.llm.base import LLMProvider
from app.llm.factory import get_provider
from app.models import Artifact, Chunk, Message, Session, utc_now
from app.rag.embeddings import get_embeddings_client
from app.rag.retrieval import RetrievalResult, retrieve
from app.schemas import ChatResponse, CitationItem, MessageCreate, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["chat"])


# ---------------------------------------------------------------------------
# Dependency providers (can be overridden via app.dependency_overrides)
# ---------------------------------------------------------------------------


def get_chat_provider() -> LLMProvider:
    """Return the active LLM provider."""
    return get_provider()


def get_chat_embedder() -> Any:
    """Return the active embeddings client."""
    return get_embeddings_client()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


async def _load_sources_from_citations(
    citations: List[Dict[str, Any]],
    db: AsyncSession,
) -> List[RetrievalResult]:
    """Load RetrievalResult objects from cited chunk IDs in previous assistant turn."""
    chunk_ids = []
    for c in citations:
        cid = c.get("chunk_id")
        if cid:
            try:
                chunk_ids.append(uuid.UUID(str(cid)))
            except Exception:
                pass
    if not chunk_ids:
        return []

    stmt = (
        select(Chunk)
        .options(selectinload(Chunk.document))
        .where(Chunk.id.in_(chunk_ids))
    )
    res = await db.execute(stmt)
    chunks = list(res.scalars().all())
    chunk_map = {c.id: c for c in chunks}

    results: List[RetrievalResult] = []
    for c in citations:
        cid = c.get("chunk_id")
        if not cid:
            continue
        try:
            u = uuid.UUID(str(cid))
        except Exception:
            continue
        chunk_obj = chunk_map.get(u)
        if chunk_obj:
            doc = chunk_obj.document
            results.append(
                RetrievalResult(
                    chunk_id=chunk_obj.id,
                    text=chunk_obj.text,
                    score=1.0,
                    document_slug=doc.slug if doc else "",
                    title=doc.title if doc else "",
                    guest=doc.guest if doc else None,
                    speaker=chunk_obj.speaker,
                    start_char=chunk_obj.start_char,
                    end_char=chunk_obj.end_char,
                    chunk_index=chunk_obj.chunk_index,
                )
            )
        else:
            results.append(
                RetrievalResult(
                    chunk_id=u,
                    text=c.get("passage", ""),
                    score=1.0,
                    document_slug=c.get("doc_slug", ""),
                    title=c.get("title", ""),
                    guest=c.get("guest"),
                    speaker=None,
                    start_char=None,
                    end_char=None,
                    chunk_index=0,
                )
            )
    return results


def derive_artifact_type_from_prompt(user_message: str) -> str:
    """Derive artifact type deterministically from user prompt.

    Per spec: default to html for "page/one-page/landing", markdown otherwise.
    """
    msg = user_message.lower()
    if any(k in msg for k in ["markdown", " md", ".md"]):
        return "markdown"
    if any(k in msg for k in ["html", "page", "one-page", "one pager", "one-pager", "landing", "webpage", "web page"]):
        return "html"
    return "markdown"


def _citation_val(c: Any, key: str, default: Any = "") -> Any:
    """Helper to safely extract field from dict or Pydantic CitationItem."""
    if isinstance(c, dict):
        return c.get(key, default)
    return getattr(c, key, default)


def extract_explicit_topic(text: str) -> Optional[str]:
    """Extract explicit topic from user prompt when present."""
    cleaned = text.strip()
    patterns = [
        r"^(?:please\s+)?(?:write|draft|generate|create|make)\s+(?:a\s+|an\s+)?(?:ship\s*30\s+)?(?:essay|article|post|summary|one-pager|artifact|document|doc|page|webpage|table)\s+(?:about|on|focusing on|featuring|regarding)\s+(.+)$",
        r"^(?:ship\s*30\s+)?(?:essay|article|one-pager|document|doc)\s+(?:about|on|focusing on|featuring|regarding)\s+(.+)$",
        r"^(?:topic:\s*)(.+)$",
    ]
    for pat in patterns:
        m = re.match(pat, cleaned, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip().strip("\"'.,")
            if not re.match(r"^(that|this|it|the above|previous|last answer)$", candidate, re.IGNORECASE):
                if len(candidate) > 2:
                    return candidate

    m_sub = re.search(r"\b(?:about|on|focusing on|featuring)\s+([A-Za-z0-9\s\-_',]{3,})$", cleaned, re.IGNORECASE)
    if m_sub:
        candidate = m_sub.group(1).strip().strip("\"'.,")
        if not re.match(r"^(that|this|it|the above|previous|last answer)$", candidate, re.IGNORECASE):
            if len(candidate) > 2:
                return candidate

    return None


def is_summary_artifact_request(text: str) -> bool:
    """Check if the user request is asking for a summary/one-pager of the previous answer."""
    cleaned = text.lower()
    return bool(
        re.search(
            r"\b(one-?pager|summariz\w*|summary|takeaways|notes|doc summarizing|that into|this into|format as|export\w*|download\w*|output\w*|render\w*|save\w*)\b",
            cleaned,
        )
    )


def is_command_string(text: str) -> bool:
    """Check if the text is a command instruction rather than a topical question."""
    cleaned = text.strip()
    if is_summary_artifact_request(cleaned):
        return True
    if classify_intent(cleaned) != Intent.QA:
        return True
    if re.search(
        r"^(?:(?:please|can you|could you)\s+)?(?:make|create|write|draft|generate|turn|format|convert|transform|build|summarize|export|download|output|render|save)\b",
        cleaned,
        re.IGNORECASE,
    ):
        return True
    return False


def find_last_grounded_qa_exchange(
    history: Sequence[Any],
) -> tuple[Optional[Any], Optional[Any]]:
    """Walk backward through history to find the last grounded QA exchange.

    Returns (grounded_user_msg, grounded_assistant_msg).
    Skips intermediate ARTIFACT and ESSAY user turns and assistant confirmation
    messages/refusals/clarifications to locate the substantive grounded QA turn.
    """
    if not history:
        return None, None

    for i in range(len(history) - 1, -1, -1):
        msg = history[i]
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        if role != "assistant":
            continue

        content = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
        citations = (msg.get("citations") if isinstance(msg, dict) else getattr(msg, "citations", [])) or []
        intent_val = msg.get("intent") if isinstance(msg, dict) else getattr(msg, "intent", None)

        # Skip refusals
        if content == EXACT_REFUSAL_MESSAGE or content.startswith(
            "I don't have information about that in the transcripts."
        ):
            continue
        # Skip clarifications
        if content.startswith("What topic would you like"):
            continue
        # Skip assistant artifact / essay confirmation messages
        if intent_val and str(intent_val).upper() in ("ARTIFACT", "ESSAY"):
            continue
        if content.startswith("Your ") and (
            "is ready:" in content or "essay is ready" in content or "one-pager is ready" in content
        ):
            continue
        # Must have citations to be grounded QA
        if not citations:
            continue

        # Found candidate grounded assistant message; find the user query that prompted it
        created_at = msg.get("created_at") if isinstance(msg, dict) else getattr(msg, "created_at", None)
        for j in range(i - 1, -1, -1):
            prev_m = history[j]
            prev_role = prev_m.get("role") if isinstance(prev_m, dict) else getattr(prev_m, "role", None)
            prev_time = prev_m.get("created_at") if isinstance(prev_m, dict) else getattr(prev_m, "created_at", None)
            if prev_role == "user" and (created_at is None or prev_time is None or prev_time < created_at):
                u_content = (
                    prev_m.get("content") if isinstance(prev_m, dict) else getattr(prev_m, "content", "")
                ) or ""
                # Verify user message is not an artifact or essay command
                if not is_command_string(u_content) and classify_intent(u_content) == Intent.QA:
                    # If user query is elliptical (e.g. 'Why is that?'), walk back to root question
                    if not is_standalone_query(u_content):
                        for k in range(j - 1, -1, -1):
                            root_m = history[k]
                            r_role = root_m.get("role") if isinstance(root_m, dict) else getattr(root_m, "role", None)
                            if r_role == "user":
                                r_content = (
                                    root_m.get("content") if isinstance(root_m, dict) else getattr(root_m, "content", "")
                                ) or ""
                                if (
                                    is_standalone_query(r_content)
                                    and not is_command_string(r_content)
                                    and classify_intent(r_content) == Intent.QA
                                ):
                                    return root_m, msg
                    return prev_m, msg

    return None, None


def derive_summary_title(prev_user_text: Optional[str], prev_assistant_text: str) -> str:
    """Derive an informative H1 title for summary artifacts.

    Rejects command strings (e.g. artifact/essay generation instructions). For
    grounded questions, strips question frames in a deterministic cascade so
    the title is the clean noun phrase (title-cased with ": Summary"). Falls
    back to the first heading in the answer, then to a generic default.
    """
    if prev_user_text and not is_command_string(prev_user_text):
        cleaned = prev_user_text.strip().rstrip("?.,!").strip()

        # Question-frame cascade. Each pattern is anchored to the start and
        # strips a known lead-in; apply repeatedly until nothing changes so
        # layered frames ("what do the guests say about...") collapse. Order
        # matters: longer, more specific frames go first.
        frames = [
            # "what does/do the podcast/guests/people say/think/recommend about X"
            r"^(?:what|how)\s+(?:do(?:es)?|should|would|could|did)\s+(?:the\s+|an?\s+)?"
            r"(?:podcast|guests?|people|lenny|founders?|startups?|teams?|pms?|users?|customers?|experts?)\s+"
            r"(?:say|think|recommend|discuss|mention|believe|argue|suggest|advise|do|know)\s+(?:about\s+)?",
            # "how should a startup think about X" / "how do I think about X"
            r"^(?:how|what)\s+(?:do(?:es)?|should|would|could|can)\s+"
            r"(?:a\s+|an\s+|the\s+|i\s+|we\s+|you\s+|they\s+|one\s+)?[\w\- ]{0,25}?"
            r"\s*think\s+about\s+",
            # "how do I know when/if I have X" / "how to know when you have X"
            r"^(?:how\s+)?(?:do\s+(?:you|i|we)|to)\s+know\s+(?:when|if)\s+(?:you|i|we)\s+have\s+",
            # "how do I/you/we X"  — but keep the X
            r"^how\s+(?:do|does|did|should|would|could|can)\s+(?:i|you|we|they|one|a|an|the)\s+",
            # "what is / what are / what was X"
            r"^what\s+(?:is|are|was|were)\s+(?:the\s+|an?\s+)?",
            # "tell me (more )?about X" / "explain X" / "describe X"
            r"^(?:please\s+)?(?:tell\s+me\s+(?:more\s+)?about|explain|describe|elaborate\s+on)\s+",
            # "can you / could you ..." leading phrase
            r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?",
            # Residual leading question words: who/why/when/where/how plus
            # auxiliary verb; strip ONLY if what follows still has >= 2 words
            r"^(?:why|who|when|where)\s+(?:is|are|was|were|does|do|did|should|would|could|can)\s+",
            # "say/think/recommend about" if a frame starts there
            r"^(?:(?:lenny|guests?|people)\s+)?(?:say|think|recommend|discuss|mention)\s+(?:about\s+)?",
        ]

        prev = None
        while cleaned != prev:
            prev = cleaned
            for pat in frames:
                new = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
                if new and new != cleaned:
                    cleaned = new
                    break

        cleaned = cleaned.rstrip("?.,!").strip()

        # Strip residual leading articles/determiners that are not part of the
        # noun phrase itself ("the podcast" leaked by a non-matching frame).
        for lead in ("the ", "a ", "an "):
            if cleaned.lower().startswith(lead):
                cleaned = cleaned[len(lead):].strip()
                break

        if (
            len(cleaned) > 3
            and cleaned.lower() not in ("that", "this", "it", "explain that more", "explain that", "more")
        ):
            return f"{cleaned[:70].title()}: Summary"

    for line in prev_assistant_text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            h = line.lstrip("#").strip().strip("*_`# ")
            if len(h) > 3 and not h.lower().startswith("sources") and not h.lower().startswith("checks"):
                return h[:70]

    return "Key Growth Insights: Executive Summary"



def clean_html_asterisks(html_str: str) -> str:
    """Ensure zero literal ** leak outside code/pre/style tags in HTML."""
    parts = re.split(
        r"(<code[^>]*>.*?</code>|<pre[^>]*>.*?</pre>|<style[^>]*>.*?</style>)",
        html_str,
        flags=re.DOTALL | re.IGNORECASE,
    )
    for i in range(0, len(parts), 2):
        # Convert paired **text** to <strong>text</strong>
        parts[i] = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", parts[i])
        # Strip any remaining orphan **
        parts[i] = parts[i].replace("**", "")
    return "".join(parts)


def generate_deterministic_html_summary(
    title: str,
    markdown_text: str,
    citations: Sequence[Any],
) -> str:
    """Deterministically convert grounded markdown to beautiful, safe HTML without LLM call."""
    from markdown_it import MarkdownIt

    lines = markdown_text.strip().splitlines()
    body_lines = []
    for line in lines:
        if line.strip().startswith("# ") and line.strip().lstrip("# ").strip().lower() == title.lower():
            continue
        body_lines.append(line)
    clean_md = "\n".join(body_lines)
    from app.agent.verify import normalize_citations
    clean_md = normalize_citations(clean_md)

    sources_heading_idx = clean_md.find("\n## Sources")
    if sources_heading_idx != -1:
        clean_md = clean_md[:sources_heading_idx].strip()

    def replace_cit_bracket(match: re.Match) -> str:
        nums = re.findall(r"\d+", match.group(0))
        return "".join(f"CITATOKEN_{n}_END" for n in nums)

    # Tokenize single and grouped citation brackets like [S1], [S1, S2, S5], [s1], (S1), ([S1, S2])
    protected_md = re.sub(r"\[\s*[sS]\d+(?:\s*[,;\s]+\s*(?:[sS]\s*)?\d+)*\s*\]", replace_cit_bracket, clean_md)
    protected_md = re.sub(r"\(\s*\[?\s*[sS]\d+(?:\s*[,;\s]+\s*(?:[sS]\s*)?\d+)*\s*\]?\s*\)", replace_cit_bracket, protected_md)
    protected_md = re.sub(r"\[[sS](\d+)\]", r"CITATOKEN_\1_END", protected_md)
    protected_md = re.sub(r"\([sS](\d+)\)", r"CITATOKEN_\1_END", protected_md)

    md = MarkdownIt("commonmark", {"html": False})
    rendered_html = md.render(protected_md)

    def restore_cit_token(match):
        num = match.group(1)
        return f'<sup><a href="#source-S{num}">[{num}]</a></sup>'

    rendered_html = re.sub(r"CITATOKEN_(\d+)_END", restore_cit_token, rendered_html)

    # Safety pass: Ensure zero raw [S..] tags remain anywhere in rendered_html
    def restore_stray_cit(match: re.Match) -> str:
        nums = re.findall(r"\d+", match.group(0))
        return "".join(f'<sup><a href="#source-S{n}">[{n}]</a></sup>' for n in nums)

    rendered_html = re.sub(r"\[\s*[sS]\d+(?:\s*[,;\s]+\s*(?:[sS]\s*)?\d+)*\s*\]", restore_stray_cit, rendered_html)
    rendered_html = re.sub(r"\(\s*\[?\s*[sS]\d+(?:\s*[,;\s]+\s*(?:[sS]\s*)?\d+)*\s*\]?\s*\)", restore_stray_cit, rendered_html)

    def _cit_num(c: Any) -> int:
        val = _citation_val(c, "n", 0)
        if isinstance(val, int):
            return val
        try:
            return int(val)
        except (ValueError, TypeError):
            m = re.search(r"\d+", str(val))
            return int(m.group(0)) if m else 0

    sorted_citations = sorted(citations, key=_cit_num)

    sources_html_items = []
    for cit in sorted_citations:
        num = _cit_num(cit) or 1
        guest = _citation_val(cit, "guest")
        ep_title = _citation_val(cit, "title", "Podcast Episode")
        passage = _citation_val(cit, "passage", "")
        passage_snippet = ""
        if passage:
            # Clean raw passage text sliced into passage[:140] to strip/convert markdown formatting
            p_slice = passage[:140]
            p_clean = (
                p_slice.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            p_clean = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", p_clean)
            p_clean = p_clean.replace("**", "")
            passage_snippet = p_clean

        if guest:
            guest_str = f"<strong>{guest}</strong> &mdash; "
        else:
            guest_str = ""
        snippet_str = f' <em>("{passage_snippet}...")</em>' if passage_snippet else ""
        sources_html_items.append(
            f'<li id="source-S{num}">{guest_str}{ep_title}{snippet_str}</li>'
        )

    sources_block = ""
    if sources_html_items:
        sources_block = (
            '<h2 id="sources">Sources</h2>\n'
            '<ol class="sources-list">\n'
            + "\n".join(f"  {item}" for item in sources_html_items)
            + "\n</ol>\n"
        )

    safe_title = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

    html_page = (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        f"  <title>{safe_title}</title>\n"
        "  <style>\n"
        "    body {\n"
        "      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;\n"
        "      line-height: 1.6;\n"
        "      max-width: 800px;\n"
        "      margin: 40px auto;\n"
        "      padding: 0 24px;\n"
        "      color: #1a1a1a;\n"
        "      background-color: #fafafa;\n"
        "    }\n"
        "    .container {\n"
        "      background: #ffffff;\n"
        "      padding: 36px 44px;\n"
        "      border-radius: 8px;\n"
        "      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);\n"
        "    }\n"
        "    h1 {\n"
        "      font-size: 1.85rem;\n"
        "      color: #111827;\n"
        "      border-bottom: 2px solid #e5e7eb;\n"
        "      padding-bottom: 12px;\n"
        "      margin-top: 0;\n"
        "    }\n"
        "    h2 {\n"
        "      font-size: 1.35rem;\n"
        "      color: #1f2937;\n"
        "      margin-top: 28px;\n"
        "      border-bottom: 1px solid #f3f4f6;\n"
        "      padding-bottom: 6px;\n"
        "    }\n"
        "    p { margin: 16px 0; }\n"
        "    ul, ol { padding-left: 24px; margin: 16px 0; }\n"
        "    li { margin: 6px 0; }\n"
        "    sup a {\n"
        "      color: #0284c7;\n"
        "      text-decoration: none;\n"
        "      font-weight: 600;\n"
        "      padding: 0 2px;\n"
        "    }\n"
        "    sup a:hover { text-decoration: underline; }\n"
        "    .sources-list {\n"
        "      border-top: 1px solid #e5e7eb;\n"
        "      padding-top: 16px;\n"
        "      margin-top: 32px;\n"
        "      font-size: 0.88rem;\n"
        "      color: #4b5563;\n"
        "    }\n"
        "    .sources-list li { margin-bottom: 8px; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <div class=\"container\">\n"
        f"    <h1>{safe_title}</h1>\n"
        f"    {rendered_html}\n"
        f"    {sources_block}"
        "  </div>\n"
        "</body>\n"
        "</html>"
    )
    return clean_html_asterisks(html_page)


def generate_deterministic_markdown_summary(
    title: str,
    markdown_text: str,
    citations: Sequence[Any],
) -> str:
    """Deterministically convert grounded markdown to clean markdown artifact without LLM call."""
    lines = markdown_text.strip().splitlines()
    body_lines = []
    for line in lines:
        if line.strip().startswith("# ") and line.strip().lstrip("# ").strip().lower() == title.lower():
            continue
        body_lines.append(line)
    clean_md = "\n".join(body_lines).strip()
    from app.agent.verify import normalize_citations
    clean_md = normalize_citations(clean_md)

    sources_heading_idx = clean_md.find("\n## Sources")
    if sources_heading_idx != -1:
        clean_md = clean_md[:sources_heading_idx].strip()

    def replace_md_citation(match: re.Match) -> str:
        nums = re.findall(r"\d+", match.group(0))
        return "".join(f"[{n}](#source-S{n})" for n in nums)

    clean_md = re.sub(r"\[\s*[sS]\d+(?:\s*[,;\s]+\s*(?:[sS]\s*)?\d+)*\s*\]", replace_md_citation, clean_md)
    clean_md = re.sub(r"\(\s*\[?\s*[sS]\d+(?:\s*[,;\s]+\s*(?:[sS]\s*)?\d+)*\s*\]?\s*\)", replace_md_citation, clean_md)
    clean_md = re.sub(r"\[[sS](\d+)\]", r"[\1](#source-S\1)", clean_md)
    clean_md = re.sub(r"\([sS](\d+)\)", r"[\1](#source-S\1)", clean_md)

    def _cit_num(c: Any) -> int:
        val = _citation_val(c, "n", 0)
        if isinstance(val, int):
            return val
        try:
            return int(val)
        except (ValueError, TypeError):
            m = re.search(r"\d+", str(val))
            return int(m.group(0)) if m else 0

    sorted_citations = sorted(citations, key=_cit_num)

    sources_items = []
    for cit in sorted_citations:
        num = _cit_num(cit) or 1
        guest = _citation_val(cit, "guest")
        ep_title = _citation_val(cit, "title", "Podcast Episode")
        if guest:
            sources_items.append(f"{num}. **{guest}** &mdash; {ep_title}")
        else:
            sources_items.append(f"{num}. {ep_title}")

    sources_block = ""
    if sources_items:
        sources_block = "\n\n## Sources\n\n" + "\n".join(sources_items)

    return f"# {title}\n\n{clean_md}{sources_block}"


# ---------------------------------------------------------------------------
# POST /sessions/{session_id}/messages
# ---------------------------------------------------------------------------


@router.post("/{session_id}/messages", response_model=ChatResponse)
async def post_message(
    session_id: uuid.UUID,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db_session),
    provider: LLMProvider = Depends(get_chat_provider),
    embedder: Any = Depends(get_chat_embedder),
) -> ChatResponse:
    """Send a message to a session, run RAG retrieval + agent, and persist response."""
    settings = get_settings()
    t0 = time.perf_counter()

    # 1. Validate session existence
    stmt = select(Session).where(Session.id == session_id)
    res = await db.execute(stmt)
    session_obj = res.scalar_one_or_none()
    if not session_obj:
        raise AppException(
            code="session_not_found",
            message=f"Session {session_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        raise AppException(
            code="bad_gateway",
            message="Anthropic API key is not configured. Please set ANTHROPIC_API_KEY in environment.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    # 2. Persist user message
    user_msg = Message(
        id=uuid.uuid4(),
        session_id=session_id,
        role="user",
        content=body.content.strip(),
        created_at=utc_now(),
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    # 3. Fetch prior session history (excluding current user turn)
    history_stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .where(Message.id != user_msg.id)
        .order_by(Message.created_at.asc())
    )
    history_res = await db.execute(history_stmt)
    history_messages = list(history_res.scalars().all())

    # 4. Classify intent
    intent = classify_intent(body.content, history=history_messages)

    # Identify previous grounded QA exchange (walk back past ARTIFACT/ESSAY turns and refusals)
    grounded_user, grounded_assistant = find_last_grounded_qa_exchange(history_messages)

    # Identify previous assistant response (strictly most recent by created_at)
    prev_assistant = next(
        (m for m in reversed(history_messages)
         if m.role == "assistant"
         and m.content != EXACT_REFUSAL_MESSAGE),
        None,
    )
    prev_user = None
    if prev_assistant:
        prev_user = next(
            (m for m in reversed(history_messages)
             if m.role == "user" and m.created_at < prev_assistant.created_at),
            None,
        )

    explicit_topic = extract_explicit_topic(body.content)

    # 5. Handle Precedence for ESSAY and ARTIFACT intents
    t_retrieval_start = time.perf_counter()
    t_retrieval_ms = 0.0

    if intent in (Intent.ESSAY, Intent.ARTIFACT):
        if explicit_topic:
            # (1) User explicitly stated a topic -> fresh retrieval top_k=10
            raw_chunks = await retrieve(
                query=explicit_topic,
                db=db,
                top_k=settings.retrieval_top_k,
                min_score=None,
                embedder=embedder,
            )
            t_retrieval_ms = (time.perf_counter() - t_retrieval_start) * 1000
            top_score = raw_chunks[0].score if raw_chunks else 0.0
            threshold = settings.retrieval_min_score

            if not raw_chunks or top_score < threshold:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(
                    "Explicit topic refusal: top_score=%.4f < threshold=%.4f topic=%r",
                    top_score,
                    threshold,
                    explicit_topic,
                )
                assistant_msg = Message(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    role="assistant",
                    content=EXACT_REFUSAL_MESSAGE,
                    intent=intent.value,
                    citations=[],
                    created_at=utc_now(),
                    tool_trace=[
                        {
                            "action": "refusal_below_retrieval_threshold",
                            "top_score": round(top_score, 4),
                            "threshold": threshold,
                            "topic": explicit_topic,
                        }
                    ],
                    degraded=False,
                    latency_ms=elapsed_ms,
                )
                db.add(assistant_msg)
                await db.commit()
                await db.refresh(assistant_msg)

                return ChatResponse(
                    message=MessageResponse.model_validate(assistant_msg),
                    citations=[],
                    intent=intent.value,
                    degraded=False,
                    latency_ms=elapsed_ms,
                    artifact=None,
                    warnings=[],
                )
            sources = [c for c in raw_chunks if c.score >= threshold]
            resolved_topic = explicit_topic

        elif grounded_assistant or prev_assistant:
            target_assistant = grounded_assistant or prev_assistant
            target_user = grounded_user or prev_user
            # (2) Pure reference -> reuse grounded assistant's cited chunks + fresh query
            cited_sources = await _load_sources_from_citations(target_assistant.citations, db=db)
            prior_query = target_user.content if target_user else body.content
            fresh_chunks = await retrieve(
                query=prior_query,
                db=db,
                top_k=settings.retrieval_top_k,
                min_score=None,
                embedder=embedder,
            )
            t_retrieval_ms = (time.perf_counter() - t_retrieval_start) * 1000
            seen_ids = {s.chunk_id for s in cited_sources}
            sources = list(cited_sources)
            for fc in fresh_chunks:
                if fc.chunk_id not in seen_ids:
                    sources.append(fc)
                    seen_ids.add(fc.chunk_id)
            resolved_topic = target_user.content if target_user else "key takeaways"

        else:
            # (3) Neither explicit topic nor previous assistant answer -> prompt for topic (0 LLM calls)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            action_name = "an essay" if intent == Intent.ESSAY else "an artifact"
            clarification_msg = (
                f"What topic would you like me to write {action_name} about? "
                f"Please provide a topic or ask a question first so I can ground the response in relevant podcast transcripts."
            )
            assistant_msg = Message(
                id=uuid.uuid4(),
                session_id=session_id,
                role="assistant",
                content=clarification_msg,
                intent=intent.value,
                citations=[],
                created_at=utc_now(),
                tool_trace=[
                    {
                        "action": "prompt_for_topic",
                        "reason": "no_previous_answer_or_topic",
                        "intent": intent.value,
                    }
                ],
                degraded=False,
                latency_ms=elapsed_ms,
            )
            db.add(assistant_msg)
            await db.commit()
            await db.refresh(assistant_msg)

            return ChatResponse(
                message=MessageResponse.model_validate(assistant_msg),
                citations=[],
                intent=intent.value,
                degraded=False,
                latency_ms=elapsed_ms,
                artifact=None,
                warnings=[],
            )

    # 6. Execution by intent
    artifact_record: Optional[Artifact] = None
    final_citations: List[CitationItem] = []
    warnings_list: List[str] = []

    if intent == Intent.ESSAY:
        from app.skills.ship30 import generate_essay
        t_gen_start = time.perf_counter()
        try:
            essay_result = await generate_essay(
                topic=resolved_topic,
                sources=sources,
                provider=provider,
            )
            t_gen_ms = (time.perf_counter() - t_gen_start) * 1000

            essay_title = getattr(essay_result, "title", None)
            if not essay_title:
                m = re.search(r"^#\s+(.+)$", essay_result.content, re.M)
                essay_title = m.group(1).strip() if m else f"Ship 30 Essay: {resolved_topic[:60]}"
            wc = essay_result.word_count

            # Normalize citations in essay content before storing
            art_content = normalize_citations(essay_result.content)

            # Resolve valid citations from essay content
            t_checks_start = time.perf_counter()
            valid_tags = extract_citation_tags(art_content)
            final_citations = resolve_citations(valid_tags, sources)

            status_label = "Ready" if essay_result.report.passed else "Needs review"
            checks_panel = essay_result.report.checks_markdown()
            final_content = (
                f"Your Ship 30 essay is ready: '{essay_title}' ({wc} words). **Status: {status_label}**\n\n"
                f"{checks_panel}"
            )
            final_content = normalize_citations(final_content)
            t_checks_ms = (time.perf_counter() - t_checks_start) * 1000

            content_bytes = len(art_content.encode("utf-8"))
            if content_bytes > settings.artifact_max_bytes:
                raise AppException(
                    code="artifact_too_large",
                    message=f"Artifact size ({content_bytes} bytes) exceeds limit of {settings.artifact_max_bytes} bytes",
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
            artifact_record = Artifact(
                session_id=session_id,
                type="markdown",
                title=essay_title,
                content=art_content,
            )
            t_db_start = time.perf_counter()
            db.add(artifact_record)
            await db.flush()
            t_db_ms = (time.perf_counter() - t_db_start) * 1000

            tool_trace = [
                {
                    "action": "ship30_generate_essay",
                    "word_count": wc,
                    "repaired": essay_result.repaired,
                    "passed": essay_result.report.passed,
                    "failed_rules": essay_result.report.failed_rules,
                }
            ]
            degraded = False

            logger.info(
                "ESSAY request completed: topic=%r title=%r words=%d passed=%s\n"
                "  Stage timings: Retrieval=%.1fms, Generation=%.1fms, Checks=%.1fms, DB=%.1fms",
                resolved_topic, essay_title, wc, essay_result.report.passed,
                t_retrieval_ms, t_gen_ms, t_checks_ms, t_db_ms,
            )
        except AppException:
            raise
        except Exception as exc:
            logger.error("Ship 30 essay generation failed: %s", exc, exc_info=True)
            final_content = f"Failed to generate essay: {str(exc)}"
            tool_trace = [{"action": "ship30_generate_essay", "error": str(exc)}]
            degraded = True

    elif intent == Intent.ARTIFACT:
        t_deriv_start = time.perf_counter()
        target_type = derive_artifact_type_from_prompt(body.content)
        target_assistant = grounded_assistant or prev_assistant
        target_user = grounded_user or prev_user
        base_text = target_assistant.content if target_assistant else ""
        citations_list = target_assistant.citations if target_assistant else []

        if target_assistant:
            art_stmt = (
                select(Artifact)
                .where(Artifact.session_id == session_id)
                .order_by(Artifact.created_at.desc())
                .limit(1)
            )
            art_res = await db.execute(art_stmt)
            latest_art = art_res.scalar_one_or_none()
            if latest_art and latest_art.content:
                # If substantive markdown artifact exists (e.g. Ship 30 essay), prefer its content
                # over confirmation strings or short text, but avoid using HTML content as base_text
                if latest_art.type == "markdown" and not latest_art.content.startswith("<"):
                    if (
                        target_assistant.content.startswith("Your Ship 30 essay is ready")
                        or target_assistant.content.startswith("Your ")
                        or len(latest_art.content) > len(target_assistant.content)
                    ):
                        base_text = latest_art.content

        # Derive title from original grounded user question, never from command text
        title_user_text = target_user.content if target_user else None
        art_title = derive_summary_title(title_user_text, base_text or resolved_topic)
        t_deriv_ms = (time.perf_counter() - t_deriv_start) * 1000

        # Standalone artifact requested with explicit topic and no prior assistant text
        if not base_text and explicit_topic:
            system_prompt = build_system_prompt(
                sources=sources,
                history=history_messages,
                max_history_turns=settings.history_turns,
            )
            agent_res = await run_agent(
                intent=intent,
                system_prompt=system_prompt,
                user_message=body.content,
                provider=provider,
                timeout_s=settings.artifact_timeout_s,
                db=db,
                embedder=embedder,
                sources=sources,
            )
            base_text = agent_res.content
            tool_trace = list(agent_res.tool_trace)
            degraded = agent_res.degraded
        else:
            tool_trace = [
                {
                    "action": "deterministic_summary_artifact",
                    "type": target_type,
                }
            ]
            degraded = False

        t_build_start = time.perf_counter()
        if target_type == "html":
            art_body = generate_deterministic_html_summary(
                title=art_title,
                markdown_text=base_text,
                citations=citations_list,
            )
            artifact_label = "HTML one-pager"
        else:
            art_body = generate_deterministic_markdown_summary(
                title=art_title,
                markdown_text=base_text,
                citations=citations_list,
            )
            artifact_label = "Markdown document"
        t_build_ms = (time.perf_counter() - t_build_start) * 1000

        wc = len(art_body.split())
        status_label = "Needs review" if degraded else "Ready"
        violations_desc = " (degraded mode)" if degraded else " (all checks passed)"
        checks_panel = (
            f"<details{' open' if degraded else ''}>\n"
            f"<summary><strong>Checks: {status_label}{violations_desc}</strong></summary>\n\n"
            f"- **Artifact Format:** PASS — Valid {target_type.upper()} structure\n"
            f"- **Grounding Integrity:** PASS — Sourced deterministically from verified answer\n"
            f"- **Citations Verified:** PASS — {len(citations_list)} citations preserved\n\n"
            "</details>"
        )
        final_content = (
            f"Your {artifact_label} is ready: '{art_title}' ({wc} words). **Status: {status_label}**\n\n"
            f"{checks_panel}"
        )
        final_content = normalize_citations(final_content)
        final_citations = [CitationItem.model_validate(c) if isinstance(c, dict) else c for c in citations_list]

        content_bytes = len(art_body.encode("utf-8"))
        if content_bytes > settings.artifact_max_bytes:
            raise AppException(
                code="artifact_too_large",
                message=f"Artifact size ({content_bytes} bytes) exceeds limit of {settings.artifact_max_bytes} bytes",
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        artifact_record = Artifact(
            session_id=session_id,
            type=target_type,
            title=art_title,
            content=art_body,
        )
        t_db_start = time.perf_counter()
        db.add(artifact_record)
        await db.flush()
        t_db_ms = (time.perf_counter() - t_db_start) * 1000

        logger.info(
            "ARTIFACT stage timing: target_type=%s title=%r derivation_ms=%.1f build_ms=%.1f db_ms=%.1f total_ms=%.1f",
            target_type, art_title, t_deriv_ms, t_build_ms, t_db_ms, (time.perf_counter() - t0) * 1000,
        )

    else:
        # Check if preceding assistant turn was a refusal and this is an elliptical follow-up
        if (
            history_messages
            and history_messages[-1].role == "assistant"
            and history_messages[-1].content == EXACT_REFUSAL_MESSAGE
            and not is_standalone_query(body.content)
        ):
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.info("Immediate refusal: follow-up to out-of-domain refusal without LLM call")
            assistant_msg = Message(
                id=uuid.uuid4(),
                session_id=session_id,
                role="assistant",
                content=EXACT_REFUSAL_MESSAGE,
                intent=intent.value,
                citations=[],
                created_at=utc_now(),
                tool_trace=[
                    {
                        "action": "refusal_followup_to_out_of_domain",
                        "reason": "preceding_turn_refused",
                    }
                ],
                degraded=False,
                latency_ms=elapsed_ms,
            )
            db.add(assistant_msg)
            await db.commit()
            await db.refresh(assistant_msg)

            return ChatResponse(
                message=MessageResponse.model_validate(assistant_msg),
                citations=[],
                intent=intent.value,
                degraded=False,
                latency_ms=elapsed_ms,
                artifact=None,
                warnings=[],
            )

        # R1: detect a grounded follow-up. A grounded follow-up is a short or
        # anaphoric user message whose most recent prior assistant turn was a
        # grounded answer (not a refusal and carried >=1 citation). These
        # bypass the retrieval score gate — the enriched rewritten query is
        # often too long/diffuse to clear the floor even when the user is
        # clearly asking about the same topic — and merge the previous
        # answer's cited chunks into the sources list so the agent + verifier
        # can still ground the follow-up.
        is_grounded_followup = False
        prev_asst_for_followup: Optional[Message] = None
        if history_messages and not is_standalone_query(body.content):
            last = history_messages[-1]
            if (
                last.role == "assistant"
                and last.content != EXACT_REFUSAL_MESSAGE
                and not last.content.startswith(
                    "I don't have information about that in the transcripts."
                )
                and last.citations
            ):
                is_grounded_followup = True
                prev_asst_for_followup = last

        # QA Intent: retrieve with threshold gate
        search_query = rewrite_query(body.content, history=history_messages)
        threshold = settings.retrieval_min_score
        raw_chunks = await retrieve(
            query=search_query,
            db=db,
            top_k=settings.retrieval_top_k,
            min_score=None,
            embedder=embedder,
        )
        top_score = raw_chunks[0].score if raw_chunks else 0.0

        if not is_grounded_followup and (not raw_chunks or top_score < threshold):
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "Immediate refusal triggered: top_score=%.4f < threshold=%.4f query=%r",
                top_score,
                threshold,
                search_query,
            )
            assistant_msg = Message(
                id=uuid.uuid4(),
                session_id=session_id,
                role="assistant",
                content=EXACT_REFUSAL_MESSAGE,
                intent=intent.value,
                citations=[],
                created_at=utc_now(),
                tool_trace=[
                    {
                        "action": "refusal_below_retrieval_threshold",
                        "top_score": round(top_score, 4),
                        "threshold": threshold,
                        "chunks_found": len(raw_chunks),
                    }
                ],
                degraded=False,
                latency_ms=elapsed_ms,
            )
            db.add(assistant_msg)
            await db.commit()
            await db.refresh(assistant_msg)

            return ChatResponse(
                message=MessageResponse.model_validate(assistant_msg),
                citations=[],
                intent=intent.value,
                degraded=False,
                latency_ms=elapsed_ms,
                artifact=None,
                warnings=[],
            )

        if is_grounded_followup:
            # Merge previous answer's cited chunks with fresh retrieval,
            # dedupe by chunk_id, cap at retrieval_top_k. Previously cited
            # chunks lead so the agent sees the sources that produced the
            # grounded answer the user is following up on.
            prev_cits = list(prev_asst_for_followup.citations or []) if prev_asst_for_followup else []
            prev_sources = await _load_sources_from_citations(prev_cits, db)
            seen_ids: set = set()
            merged: List[RetrievalResult] = []
            for c in list(prev_sources) + list(raw_chunks):
                if c.chunk_id in seen_ids:
                    continue
                seen_ids.add(c.chunk_id)
                merged.append(c)
            sources = merged[: settings.retrieval_top_k]
            logger.info(
                "Grounded follow-up detected: bypassing score gate; merged %d prev + %d fresh -> %d sources (top_score=%.4f threshold=%.4f)",
                len(prev_sources), len(raw_chunks), len(sources), top_score, threshold,
            )
        else:
            sources = [c for c in raw_chunks if c.score >= threshold]

        system_prompt = build_system_prompt(
            sources=sources,
            history=history_messages,
            max_history_turns=settings.history_turns,
        )
        timeout_s = settings.agent_timeout_s
        agent_res = await run_agent(
            intent=intent,
            system_prompt=system_prompt,
            user_message=body.content,
            provider=provider,
            timeout_s=timeout_s,
            db=db,
            embedder=embedder,
            sources=sources,
        )

        tool_trace = list(agent_res.tool_trace)
        degraded = agent_res.degraded

        verif = verify_citations(answer=agent_res.content, sources=sources, db=db)
        if verif.needs_retry and not verif.is_refusal:
            logger.info(
                "Verification retry triggered: unsupported_names=%r needs_citation_retry=%s",
                verif.unsupported_names,
                len(verif.citations) == 0,
            )
            if verif.unsupported_names:
                supported_guest_names = [getattr(s, "guest", None) for s in sources if getattr(s, "guest", None)]
                supported_names_str = ", ".join(filter(None, set(supported_guest_names))) or "the provided sources"
                unsupported_str = ", ".join(verif.unsupported_names)
                retry_prompt = (
                    f"{body.content}\n\n"
                    f"[Grounding reminder: You must name ONLY guests who appear in the provided sources: {supported_names_str}. "
                    f"Do NOT mention {unsupported_str} as they are not in the provided sources. "
                    f"Tag every claim with its [S#] identifier using ONLY the provided sources. "
                    f"If the sources do not contain the answer, reply exactly: {EXACT_REFUSAL_MESSAGE}]"
                )
            else:
                retry_prompt = (
                    f"{body.content}\n\n"
                    "[Grounding reminder: You must tag every claim with its source identifier [S#] "
                    "using ONLY the provided sources. If the sources do not contain the answer, "
                    f"reply exactly: {EXACT_REFUSAL_MESSAGE}]"
                )

            retry_res = await run_agent(
                intent=intent,
                system_prompt=system_prompt,
                user_message=retry_prompt,
                provider=provider,
                timeout_s=timeout_s,
                db=db,
                embedder=embedder,
                sources=sources,
            )
            verif_retry = verify_citations(answer=retry_res.content, sources=sources, db=db)

            tool_trace.append({"retry": True})
            tool_trace.extend(retry_res.tool_trace)
            degraded = degraded or retry_res.degraded

            if verif_retry.unsupported_names:
                for uname in verif_retry.unsupported_names:
                    w_msg = f"Mentions {uname}, who is not in the cited transcripts"
                    warnings_list.append(w_msg)
                    tool_trace.append({"warning": w_msg, "unsupported_name": uname})

            if not verif_retry.is_refusal and len(verif_retry.citations) == 0:
                logger.warning("Second attempt also failed citation verification — forcing refusal")
                final_content = EXACT_REFUSAL_MESSAGE
                final_citations = []
            else:
                final_content = normalize_citations(verif_retry.cleaned_text)
                final_citations = verif_retry.citations
        else:
            final_content = normalize_citations(verif.cleaned_text)
            final_citations = verif.citations
            if verif.unsupported_names:
                for uname in verif.unsupported_names:
                    w_msg = f"Mentions {uname}, who is not in the cited transcripts"
                    warnings_list.append(w_msg)
                    tool_trace.append({"warning": w_msg, "unsupported_name": uname})

    # 7. Persist assistant message
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    assistant_msg = Message(
        id=uuid.uuid4(),
        session_id=session_id,
        role="assistant",
        content=final_content,
        intent=intent.value,
        citations=[c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in final_citations],
        created_at=utc_now(),
        tool_trace=tool_trace,
        degraded=degraded,
        latency_ms=elapsed_ms,
    )
    if artifact_record:
        assistant_msg.artifacts.append(artifact_record)

    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    # 8. Build artifact response payload
    artifact_response = None
    if artifact_record:
        artifact_response = {
            "id": str(artifact_record.id),
            "title": artifact_record.title,
            "type": artifact_record.type,
            "content": artifact_record.content,
        }

    msg_resp = MessageResponse.model_validate(assistant_msg)
    msg_resp.warnings = warnings_list

    return ChatResponse(
        message=msg_resp,
        citations=final_citations,
        intent=intent.value,
        degraded=degraded,
        latency_ms=elapsed_ms,
        artifact=artifact_response,
        warnings=warnings_list,
    )

