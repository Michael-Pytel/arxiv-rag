"""
ingest.py — embed and load all .jsonl paper files into Qdrant

Usage:
    python scripts/ingest.py --data-dir data/ --reset
    python scripts/ingest.py --data-dir data/           # resumes if interrupted

Expects each line in .jsonl files to have:
    id, title, abstract, authors (list), categories (list),
    primary_category, published, abs_url, pdf_url
"""

import argparse
import json
import uuid
import glob
import os
import sys
from pathlib import Path

from tqdm import tqdm
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    PayloadSchemaType,
)
from dotenv import load_dotenv
load_dotenv()

COLLECTION  = "papers"
EMBED_MODEL = "text-embedding-3-small"
VECTOR_DIM  = 1536
BATCH_SIZE  = 256
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
OPENAI_KEY  = os.getenv("OPENAI_API_KEY")

openai_client = OpenAI(api_key=OPENAI_KEY)
qdrant        = QdrantClient(url=QDRANT_URL)


# ── Helpers ───────────────────────────────────────────────────────────────────

def paper_uuid(paper_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, paper_id))


def make_text(p: dict) -> str:
    text = (
        f"Title: {p['title']}\n"
        f"Abstract: {p['abstract']}\n"
        f"Categories: {', '.join(p.get('categories', []))}\n"
        f"Authors: {', '.join(p.get('authors', []))}"
    )
    return text[:32000]


def make_payload(p: dict) -> dict:
    """Metadata stored in Qdrant for filtering and display."""
    return {
        "paper_id":         p["id"],
        "title":            p["title"],
        "abstract":         p["abstract"],
        "published":        p.get("published", ""),
        "primary_category": p.get("primary_category", ""),
        "categories":       p.get("categories", []),
        "authors":          p.get("authors", []),
        "abs_url":          p.get("abs_url", ""),
        "pdf_url":          p.get("pdf_url", ""),
    }


# ── Qdrant setup ──────────────────────────────────────────────────────────────

def setup_collection(reset: bool = False):
    existing = [c.name for c in qdrant.get_collections().collections]

    if reset and COLLECTION in existing:
        qdrant.delete_collection(COLLECTION)
        print(f"Deleted existing collection '{COLLECTION}'.")
        existing = []

    if COLLECTION not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        for field, schema in {
            "primary_category": PayloadSchemaType.KEYWORD,
            "categories":       PayloadSchemaType.KEYWORD,
            "published":        PayloadSchemaType.DATETIME,
            "authors":          PayloadSchemaType.KEYWORD,
        }.items():
            qdrant.create_payload_index(COLLECTION, field, schema)
        print(f"Created collection '{COLLECTION}' with payload indexes.")
    else:
        print(f"Collection '{COLLECTION}' exists — resuming ingestion.")


def get_existing_ids() -> set[str]:
    """Fetch all already-indexed point IDs for resume support."""
    print("Fetching existing IDs for resume support...")
    ids, offset = set(), None
    while True:
        result, offset = qdrant.scroll(
            COLLECTION,
            limit=1000,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        ids.update(str(p.id) for p in result)
        if offset is None:
            break
    print(f"  {len(ids):,} papers already indexed.")
    return ids


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_batch(texts: list[str]) -> list[list[float]]:
    response = openai_client.embeddings.create(input=texts, model=EMBED_MODEL)
    return [e.embedding for e in response.data]


# ── Loading ───────────────────────────────────────────────────────────────────

def load_papers_from_jsonl(paths: list[str]) -> list[dict]:
    """Read all .jsonl files, skip malformed lines."""
    papers = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    papers.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"  Warning: skipped malformed line {i} in {path}")
    return papers


# ── Ingestion ─────────────────────────────────────────────────────────────────

def ingest(data_dir: str, reset: bool = False):
    paths = sorted(glob.glob(os.path.join(data_dir, "*.jsonl")))
    if not paths:
        print(f"No .jsonl files found in '{data_dir}'. Exiting.")
        sys.exit(1)

    print(f"Found {len(paths)} .jsonl file(s): {[Path(p).name for p in paths]}")

    setup_collection(reset=reset)
    existing_ids = set() if reset else get_existing_ids()

    print("Loading papers from disk...")
    all_papers = load_papers_from_jsonl(paths)
    print(f"  {len(all_papers):,} total papers loaded.")

    # Filter out already-indexed papers
    papers = [p for p in all_papers if paper_uuid(p["id"]) not in existing_ids]
    print(f"  {len(papers):,} papers to index ({len(all_papers) - len(papers):,} skipped).")

    if not papers:
        print("Nothing to do. Index is up to date.")
        return

    failed = 0
    for i in tqdm(range(0, len(papers), BATCH_SIZE), desc="Ingesting"):
        batch = papers[i : i + BATCH_SIZE]
        texts = [make_text(p) for p in batch]

        try:
            vectors = embed_batch(texts)
        except Exception as e:
            print(f"\n  Batch {i//BATCH_SIZE} failed ({e}) — retrying one by one...")
            vectors = []
            for text in texts:
                try:
                    vectors.append(embed_batch([text[:32000]])[0])
                except Exception:
                    vectors.append(None)

        points = [
            PointStruct(id=paper_uuid(p["id"]), vector=vec, payload=make_payload(p))
            for p, vec in zip(batch, vectors) if vec is not None
        ]
        try:
            qdrant.upsert(collection_name=COLLECTION, points=points)
        except Exception as e:
            print(f"\n  Qdrant upsert error on batch {i//BATCH_SIZE}: {e} — skipping batch.")
            failed += len(batch)

    print(f"\nDone. {len(papers) - failed:,} papers indexed, {failed:,} failed.")
    info = qdrant.get_collection(COLLECTION)
    print(f"Total vectors in collection: {info.points_count:,}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest arxiv papers into Qdrant.")
    parser.add_argument("--data-dir", default="data/", help="Directory containing .jsonl files")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the collection")
    args = parser.parse_args()

    ingest(data_dir=args.data_dir, reset=args.reset)
