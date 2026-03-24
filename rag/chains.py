"""
rag/chains.py — Claude-powered RAG chain over retrieved papers
"""

import os
import anthropic

from .retriever import search
from .prompts import SYSTEM_PROMPT

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL  = "claude-sonnet-4-20250514"


def format_papers(papers: list[dict]) -> str:
    blocks = []
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.get("authors", [])[:4])
        if len(p.get("authors", [])) > 4:
            authors += " et al."
        blocks.append(
            f"[{i}] {p['title']}\n"
            f"    Authors: {authors}\n"
            f"    Published: {p.get('published', '')[:10]}  "
            f"| Category: {p.get('primary_category', '')}  "
            f"| Score: {p.get('score', 0):.3f}\n"
            f"    Abstract: {p.get('abstract', '')[:500]}...\n"
            f"    URL: {p.get('abs_url', '')}"
        )
    return "\n\n".join(blocks)


def chat(
    user_message: str,
    history: list[dict],
    category: str = None,
    after: str = None,
    k: int = 8,
) -> tuple[str, list[dict]]:
    """
    Run one RAG turn.

    Returns:
        reply       — Claude's response string
        papers      — list of retrieved paper dicts (for display in UI)
    """
    papers  = search(user_message, k=k, category=category, after=after)
    context = format_papers(papers)

    augmented = (
        f"{user_message}\n\n"
        f"---\nRetrieved papers:\n{context}"
    )

    messages = history + [{"role": "user", "content": augmented}]

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  
            }
        ],
        messages=messages,
    )

    reply = response.content[0].text
    return reply, papers
