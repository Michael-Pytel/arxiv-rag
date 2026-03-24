# arxiv lens 📚

A semantic search and chat interface over 400k AI/ML/CV papers from arxiv. Ask natural language questions, get grounded answers with real citations, and discover related papers — all running locally.

**[▶ Demo video](https://youtube.com/your-link-here)**

---

## What it does

- **Semantic search** — finds conceptually related papers, not just keyword matches
- **LLM-powered explanations** — Claude explains *why* each paper is relevant to your query
- **Native recommendations** — pick any retrieved paper and find the most similar ones
- **Filters** — narrow by arXiv category and publication date
- **Grounded answers** — every claim is tied to a real paper with a real URL

---

## Architecture

```
User query
    │
    ▼
OpenAI text-embedding-3-small          (embed query, ~$0.00002)
    │
    ▼
Qdrant vector search + payload filter  (ANN over 400k papers)
    │
    ▼
Top-k papers (title, abstract, URL)
    │
    ▼
Claude Sonnet 4                        (grounded synthesis)
    │
    ▼
Streamlit chat UI
```

**Stack:**
| Layer | Technology |
|---|---|
| Vector DB | Qdrant (Docker) |
| Embeddings | OpenAI text-embedding-3-small |
| LLM | Claude claude-sonnet-4-20250514 |
| UI | Streamlit |
| Ingestion | Python + tqdm, batched, resumable |

---

## Quickstart

### Prerequisites
- Docker + Docker Compose
- OpenAI API key
- Anthropic API key

### 1. Clone and configure
```bash
git clone https://github.com/your-username/arxiv-lens
cd arxiv-lens
cp .env.example .env
# edit .env with your API keys
```

### 2. Start Qdrant
```bash
docker compose up qdrant -d
```

### 3. Deduplicate (recommended before full ingestion)

Papers cross-listed in multiple categories appear in more than one `.jsonl` file. Run a deduplication pass first to avoid redundant embeddings and duplicate search results.

```bash
# Dry run — see stats without writing anything
python scripts/deduplicate.py --data-dir data/

# Write a single clean output file
python scripts/deduplicate.py --data-dir data/ --output data/papers_deduped.jsonl
```

The script:
- Keeps the **latest version** of each paper (e.g. prefers `v3` over `v1`)
- **Merges category lists** so no cross-listing information is lost
- Reports duplicate rate, per-file counts, and category distribution

### 4. Ingest papers

```bash
pip install -r requirements.txt
python scripts/ingest.py --data-dir data/ --data-file papers_deduped.jsonl
```

Ingestion is **resumable** — if it crashes, rerun the same command and it skips already-indexed papers.

For the full 400k dataset (~45 min, ~$6 in embedding costs):
```bash
python scripts/ingest.py --data-dir data/full/
```

### 4. Run the app
```bash
streamlit run app/main.py
# or with Docker:
docker compose up app
```

Open [http://localhost:8501](http://localhost:8501)

---

## Dataset format

Each line in your `.jsonl` files should be:

```json
{
  "id": "2212.04285v3",
  "title": "Paper title",
  "abstract": "Abstract text...",
  "authors": ["Author One", "Author Two"],
  "categories": ["cs.LG", "cs.AI"],
  "primary_category": "cs.LG",
  "published": "2022-12-01T00:00:00Z",
  "abs_url": "https://arxiv.org/abs/2212.04285v3",
  "pdf_url": "https://arxiv.org/pdf/2212.04285v3"
}
```

---

## Cost estimate

| Operation | Cost |
|---|---|
| One-time ingestion (400k papers) | ~$6 |
| Per query (embedding + Claude Sonnet 4) | ~$0.02 |
| Personal use (~20 queries/day) | ~$12/month |

---

## Project structure

```
arxiv-lens/
├── app/
│   ├── main.py                  # Streamlit entrypoint
│   └── components/
│       ├── sidebar.py           # filters UI
│       └── results.py           # paper cards + recommendations
├── rag/
│   ├── retriever.py             # Qdrant search + recommendations
│   ├── chains.py                # Claude RAG chain
│   └── prompts.py               # system prompts
├── scripts/
│   └── ingest.py                # batched, resumable ingestion
├── data/
│   └── sample_papers.jsonl      # 1k papers for demo
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```


