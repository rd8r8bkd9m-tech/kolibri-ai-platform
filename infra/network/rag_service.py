"""RAG Service — ChromaDB-powered Retrieval Augmented Generation engine.

Endpoints:
  POST   /rag/documents       — upload documents (text/markdown/PDF extraction)
  POST   /rag/search          — semantic search over knowledge base
  POST   /rag/query           — full RAG pipeline (search + context building)
  GET    /rag/collections     — list ChromaDB collections
  DELETE /rag/documents/{id}  — remove document
  GET    /rag/health          — health check
"""

import hashlib
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

# ── Config ─────────────────────────────────────────────────────────

CHROMADB_PATH = os.getenv("CHROMADB_PATH", "/opt/kolibri-ai/data/chromadb")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
DEFAULT_COLLECTION = os.getenv("RAG_DEFAULT_COLLECTION", "kolibri_knowledge")
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "64"))
MAX_DOCUMENT_SIZE = int(os.getenv("RAG_MAX_DOC_SIZE", str(10 * 1024 * 1024)))

# ── App ────────────────────────────────────────────────────────────

app = FastAPI(title="Kolibri RAG Service", version="1.0.0")

# ── Global state (initialized on startup) ──────────────────────────

embedding_model: SentenceTransformer = None  # type: ignore[assignment]
chroma_client: chromadb.PersistentClient = None  # type: ignore[assignment]


@app.on_event("startup")
def startup():
    global embedding_model, chroma_client
    os.makedirs(CHROMADB_PATH, exist_ok=True)
    embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    chroma_client = chromadb.PersistentClient(
        path=CHROMADB_PATH,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


# ── Models ─────────────────────────────────────────────────────────

class DocumentUpload(BaseModel):
    content: str
    source: Optional[str] = None
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    collection: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    collection: Optional[str] = None
    filter_metadata: Optional[Dict[str, Any]] = None


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    collection: Optional[str] = None
    filter_metadata: Optional[Dict[str, Any]] = None


class SearchResult(BaseModel):
    id: str
    content: str
    metadata: Dict[str, Any]
    distance: Optional[float] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]
    query: str
    latency_ms: int


class QueryResponse(BaseModel):
    results: List[SearchResult]
    context: str
    query: str
    latency_ms: int


class DocumentResponse(BaseModel):
    id: str
    chunks_count: int
    collection: str


class DeleteResponse(BaseModel):
    deleted: bool
    id: str


# ── Helpers ────────────────────────────────────────────────────────

def get_collection(name: Optional[str] = None):
    col_name = name or DEFAULT_COLLECTION
    return chroma_client.get_or_create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine"},
    )


def chunk_text(text: str, size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks by character count, breaking on sentence boundaries."""
    if len(text) <= size:
        return [text]

    sentences = re.split(r'(?<=[.!?;\n])\s+', text)
    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 > size and current:
            chunks.append(current.strip())
            words = current.split()
            overlap_words: List[str] = []
            char_count = 0
            for w in reversed(words):
                if char_count + len(w) + 1 > overlap:
                    break
                overlap_words.insert(0, w)
                char_count += len(w) + 1
            current = " ".join(overlap_words) + " " + sentence
        else:
            current = current + " " + sentence if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


def make_doc_id(source: Optional[str], content: str) -> str:
    if source:
        return hashlib.sha256(source.encode()).hexdigest()[:16]
    return hashlib.sha256(content[:512].encode()).hexdigest()[:16]


def embed_texts(texts: List[str]) -> List[List[float]]:
    return embedding_model.encode(texts, show_progress_bar=False).tolist()


# ── Endpoints ──────────────────────────────────────────────────────

@app.get("/rag/health")
async def health():
    try:
        collections = chroma_client.list_collections()
        return {
            "status": "ok",
            "service": "rag",
            "model": EMBEDDING_MODEL,
            "collections_count": len(collections),
            "chromadb_path": CHROMADB_PATH,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"status": "error", "service": "rag", "error": str(e)}


@app.post("/rag/documents", response_model=DocumentResponse)
async def upload_document(doc: DocumentUpload):
    collection = get_collection(doc.collection)
    chunk_size = doc.chunk_size or CHUNK_SIZE
    chunk_overlap = doc.chunk_overlap or CHUNK_OVERLAP

    if len(doc.content) > MAX_DOCUMENT_SIZE:
        raise HTTPException(status_code=413, detail="Document too large")

    doc_id = make_doc_id(doc.source, doc.content)
    chunks = chunk_text(doc.content, chunk_size, chunk_overlap)
    embeddings = embed_texts(chunks)

    base_metadata = {
        "source": doc.source or "direct_upload",
        "title": doc.title or "",
        "tags": ",".join(doc.tags) if doc.tags else "",
        "doc_id": doc_id,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    if doc.metadata:
        for k, v in doc.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                base_metadata[k] = v

    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [{**base_metadata, "chunk_index": i, "total_chunks": len(chunks)} for i in range(len(chunks))]

    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    return DocumentResponse(id=doc_id, chunks_count=len(chunks), collection=collection.name)


@app.post("/rag/documents/file")
async def upload_file(
    file: UploadFile = File(...),
    source: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    collection: Optional[str] = Form(None),
):
    content_bytes = await file.read()
    if len(content_bytes) > MAX_DOCUMENT_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 text (text, markdown, or pre-extracted PDF)")

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    doc = DocumentUpload(
        content=text,
        source=source or file.filename,
        title=title or file.filename,
        tags=tag_list,
        collection=collection,
    )
    return await upload_document(doc)


@app.post("/rag/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    start = time.time()
    collection = get_collection(req.collection)
    query_embedding = embed_texts([req.query])[0]

    kwargs: Dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": req.top_k,
    }
    if req.filter_metadata:
        kwargs["where"] = req.filter_metadata

    results = collection.query(**kwargs)

    search_results: List[SearchResult] = []
    if results and results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            search_results.append(SearchResult(
                id=results["ids"][0][i],
                content=results["documents"][0][i] if results["documents"] else "",
                metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                distance=results["distances"][0][i] if results.get("distances") else None,
            ))

    latency = int((time.time() - start) * 1000)
    return SearchResponse(results=search_results, query=req.query, latency_ms=latency)


@app.post("/rag/query", response_model=QueryResponse)
async def query_rag(req: QueryRequest):
    start = time.time()
    collection = get_collection(req.collection)
    query_embedding = embed_texts([req.query])[0]

    kwargs: Dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": req.top_k,
    }
    if req.filter_metadata:
        kwargs["where"] = req.filter_metadata

    results = collection.query(**kwargs)

    search_results: List[SearchResult] = []
    context_parts: List[str] = []
    if results and results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            content = results["documents"][0][i] if results["documents"] else ""
            search_results.append(SearchResult(
                id=results["ids"][0][i],
                content=content,
                metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                distance=results["distances"][0][i] if results.get("distances") else None,
            ))
            context_parts.append(content)

    context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant documents found."
    latency = int((time.time() - start) * 1000)
    return QueryResponse(results=search_results, context=context, query=req.query, latency_ms=latency)


@app.get("/rag/collections")
async def list_collections():
    collections = chroma_client.list_collections()
    result = []
    for col in collections:
        c = chroma_client.get_collection(col)
        result.append({
            "name": col,
            "count": c.count(),
        })
    return {"collections": result}


@app.delete("/rag/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str, collection: Optional[str] = None):
    col = get_collection(collection)
    try:
        results = col.get(where={"doc_id": doc_id})
        if results and results["ids"]:
            col.delete(ids=results["ids"])
            return DeleteResponse(deleted=True, id=doc_id)
        return DeleteResponse(deleted=False, id=doc_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Entrypoint ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
