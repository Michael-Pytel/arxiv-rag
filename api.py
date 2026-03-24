"""
api.py — FastAPI backend for arxiv lens

Endpoints:
    GET  /              → serves index.html
    POST /chat          → RAG chat (streaming)
    POST /search        → pure vector search
    POST /recommend     → similar papers
    GET  /stats         → collection stats
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import json

from rag.retriever import search, recommend_similar, collection_stats, _embed
from rag.prompts import SYSTEM_PROMPT

app = FastAPI(title="arxiv lens")
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL  = "claude-sonnet-4-20250514"


# ── Request models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message:  str
    history:  list[dict] = []
    category: str | None = None
    after:    str | None = None
    k:        int        = 8

class SearchRequest(BaseModel):
    query:    str
    k:        int        = 8
    category: str | None = None
    after:    str | None = None

class RecommendRequest(BaseModel):
    paper_id: str
    k:        int = 6


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse("frontend/index.html")


@app.get("/stats")
async def stats():
    try:
        return collection_stats()
    except Exception as e:
        return {"error": str(e)}


@app.post("/search")
async def search_papers(req: SearchRequest):
    try:
        papers = search(req.query, k=req.k, category=req.category, after=req.after)
        return {"papers": papers}
    except Exception as e:
        return {"error": str(e), "papers": []}


@app.post("/recommend")
async def recommend(req: RecommendRequest):
    try:
        papers = recommend_similar(req.paper_id, k=req.k)
        return {"papers": papers}
    except Exception as e:
        return {"error": str(e), "papers": []}


@app.post("/chat")
async def chat(req: ChatRequest):
    """Streaming RAG chat endpoint."""

    papers = search(req.message, k=req.k, category=req.category, after=req.after)

    context = "\n\n".join(
        f"[{i+1}] {p['title']}\n"
        f"    Authors: {', '.join(p.get('authors',[])[:3])}\n"
        f"    Published: {p.get('published','')[:10]} | Category: {p.get('primary_category','')}\n"
        f"    Abstract: {p.get('abstract','')[:400]}...\n"
        f"    URL: {p.get('abs_url','')}"
        for i, p in enumerate(papers)
    )

    augmented = f"{req.message}\n\n---\nRetrieved papers:\n{context}"
    messages  = req.history + [{"role": "user", "content": augmented}]

    def generate():
        # First, stream the papers as a JSON header
        yield f"data: {json.dumps({'type': 'papers', 'papers': papers})}\n\n"

        # Then stream the LLM response token by token
        with client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
