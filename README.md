# arxiv lens

A semantic search and RAG chat interface over ~288k AI/ML papers from arxiv. Ask research questions in natural language, get grounded answers with inline citations that link directly to the source papers.

![arxiv lens demo](https://i.imgur.com/placeholder.png)

## Features

- **Semantic search** over 288k AI, ML, and computer vision papers via Qdrant + OpenAI embeddings
- **Streaming RAG chat** powered by Claude Sonnet — answers arrive token by token
- **Inline citations** — paper titles cited as clickable chips (`[1]`, `[2]`) that highlight the corresponding card in the right panel
- **Hover cross-linking** — hovering a citation scrolls the paper panel to that card; hovering a card highlights all its citations in chat
- **Category + result count filters** in the sidebar
- **Find similar papers** — triggers a new semantic search from any retrieved paper
- Fully dockerized — one command to run everything

## Stack

| Layer | Technology |
|---|---|
| LLM | Claude Sonnet (`claude-sonnet-4-20250514`) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| Vector DB | Qdrant |
| Backend | FastAPI + Server-Sent Events |
| Frontend | Vanilla JS + marked.js |
| Containerization | Docker Compose |

## Project Structure

```
arxiv-rag/
├── api.py                  # FastAPI app — chat, search, recommend, stats endpoints
├── run.py                  # Uvicorn entrypoint
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── frontend/
│   ├── index.html
│   ├── main.js             # Streaming, citation injection, hover linking
│   └── styles.css
├── rag/
│   ├── chains.py           # RAG chain — retrieval + Claude call
│   ├── retriever.py        # Qdrant search, recommendations, stats
│   └── prompts.py          # System prompt
└── scripts/
    ├── ingest.py           # Embed and load papers into Qdrant
    └── deduplicate.py      # Deduplicate .jsonl files by paper ID
```

## Quickstart

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- An [Anthropic API key](https://console.anthropic.com/)
- An [OpenAI API key](https://platform.openai.com/) (for embeddings)

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/arxiv-rag.git
cd arxiv-rag
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env`:
```
ANTHROPIC_API_KEY=your_anthropic_key_here
OPENAI_API_KEY=your_openai_key_here
QDRANT_URL=http://qdrant:6333
```

### 3. Restore the Qdrant snapshot

Download the pre-built snapshot (~2.4 GB) with 288k indexed papers:

**[Download snapshot from Google Drive](https://drive.google.com/file/d/1xOWx7w-dIEhv3JQedXij4MFSsfaHicKr/view?usp=sharing)**

Start Qdrant and restore:
```bash
# Start Qdrant
docker compose up qdrant -d

# Wait a few seconds, then restore the snapshot
curl -X POST "http://localhost:6333/collections/papers/snapshots/upload?collection_name=papers" \
  -H "Content-Type: multipart/form-data" \
  -F "snapshot=@papers-3973220066948834-2026-03-24-00-01-01.snapshot"
```

On Windows (PowerShell):
```powershell
curl.exe -X POST "http://localhost:6333/collections/papers/snapshots/upload?collection_name=papers" `
  -H "Content-Type: multipart/form-data" `
  -F "snapshot=@papers-3973220066948834-2026-03-24-00-01-01.snapshot"
```

### 4. Run the app

```bash
docker compose up --build
```

Open **http://localhost:8000** in your browser.

---

## Building the index from scratch

If you prefer to index your own papers instead of using the snapshot:

### 1. Fetch papers from arxiv

Collect papers in `.jsonl` format with the following fields per line:
```json
{
  "id": "2212.04285v3",
  "title": "...",
  "abstract": "...",
  "authors": ["Author One", "Author Two"],
  "categories": ["cs.LG", "cs.AI"],
  "primary_category": "cs.LG",
  "published": "2022-12-08T00:00:00Z",
  "abs_url": "https://arxiv.org/abs/2212.04285",
  "pdf_url": "https://arxiv.org/pdf/2212.04285"
}
```

Place `.jsonl` files in the `data/` directory.

### 2. Deduplicate (optional)

```bash
python scripts/deduplicate.py --data-dir data/ --output data/papers_deduped.jsonl
```

### 3. Ingest into Qdrant

```bash
# Make sure Qdrant is running first
docker compose up qdrant -d

python scripts/ingest.py --data-dir data/ --reset
```

This embeds all papers using `text-embedding-3-small` in batches of 256 and upserts them into Qdrant. Ingestion is resumable — if interrupted, re-run without `--reset` to continue where it left off.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves the frontend |
| `POST` | `/chat` | Streaming RAG chat (SSE) |
| `POST` | `/search` | Pure vector search, returns papers |
| `POST` | `/recommend` | Find similar papers by ID |
| `GET` | `/stats` | Collection stats |

### Chat request body
```json
{
  "message": "What are recent approaches to making LLMs more efficient?",
  "history": [],
  "category": "cs.LG",
  "k": 8
}
```

### SSE event types
```
data: {"type": "papers", "papers": [...]}
data: {"type": "token", "text": "Based on..."}
data: {"type": "done"}
```


<<<<<<< HEAD
## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key | required |
| `OPENAI_API_KEY` | OpenAI API key (embeddings) | required |
| `QDRANT_URL` | Qdrant connection URL | `http://localhost:6333` |
| `DEBUG` | Enable uvicorn reload | `false` |

---

## Docker

```bash
# Build and start everything
docker compose up --build

# Run in background
docker compose up --build -d

# View logs
docker compose logs -f app

# Stop (data is preserved)
docker compose down
```
=======
>>>>>>> 87b1dcaf3ab18a32e72e7c3fbf601005ac75d5fe
