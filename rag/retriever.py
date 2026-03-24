"""
rag/retriever.py — semantic search and recommendations over Qdrant
"""

import os
import uuid

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, Range
from dotenv import load_dotenv
load_dotenv()
COLLECTION  = "papers"
EMBED_MODEL = "text-embedding-3-small"
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")

qdrant        = QdrantClient(url=QDRANT_URL)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _paper_uuid(paper_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, paper_id))


def _embed(text: str) -> list[float]:
    return openai_client.embeddings.create(
        input=[text], model=EMBED_MODEL
    ).data[0].embedding


def _build_filter(
    category: str | None,
    after: str | None,
    authors: list[str] | None,
) -> Filter | None:
    conditions = []

    if category:
        conditions.append(
            FieldCondition(key="primary_category", match=MatchValue(value=category))
        )
    if after:
        conditions.append(
            FieldCondition(key="published", range=Range(gte=after))
        )
    if authors:
        conditions.append(
            FieldCondition(key="authors", match=MatchAny(any=authors))
        )

    return Filter(must=conditions) if conditions else None


def search(
    query: str,
    k: int = 8,
    category: str = None,
    after: str = None,
    authors: list[str] = None,
) -> list[dict]:
    """Semantic search with optional payload filters."""
    results = qdrant.query_points(
        collection_name=COLLECTION,
        query=_embed(query),
        query_filter=_build_filter(category, after, authors),
        limit=k,
        with_payload=True,
    ).points

    return [{"score": round(r.score, 4), **r.payload} for r in results]


def recommend_similar(paper_id: str, k: int = 6) -> list[dict]:
    point_id = _paper_uuid(paper_id)

    results = qdrant.query_points(
        collection_name=COLLECTION,
        query=point_id,         
        using=None,
        limit=k + 1,
        with_payload=True,
    ).points

    return [
        {"score": round(r.score, 4), **r.payload}
        for r in results
        if r.payload.get("paper_id") != paper_id
    ][:k]


def collection_stats() -> dict:
    """Returns basic stats about the indexed collection."""
    info = qdrant.get_collection(COLLECTION)
    return {
        "total_papers": info.points_count,
        "status": info.status,
    }
