"""RAG: chunking, embeddings (fastembed, free & local) and a vector store (Pinecone Starter, or
an in-memory store when no PINECONE_API_KEY is set). One namespace per chat session."""
import hashlib
import re
import numpy as np
from .config import settings


# ---------- chunking ----------
def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n{1,}", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 1 > size and cur:
            chunks.append(cur)
            cur = cur[-overlap:] + " " + p
        else:
            cur = f"{cur}\n{p}".strip()
    if cur:
        chunks.append(cur)
    return chunks


# ---------- embeddings ----------
_model = None


def embed(texts: list[str]) -> list[list[float]]:
    global _model
    if settings.EMBEDDING_BACKEND == "fastembed":
        try:
            if _model is None:
                from fastembed import TextEmbedding
                _model = TextEmbedding(settings.EMBEDDING_MODEL)
            return [v.tolist() for v in _model.embed(texts)]
        except Exception:  # model not downloadable / library missing -> deterministic fallback
            settings.EMBEDDING_BACKEND = "hash"
    return [_hash_embed(t) for t in texts]


def _hash_embed(text: str, dim: int = settings.EMBEDDING_DIM) -> list[float]:
    v = np.zeros(dim)
    for tok in re.findall(r"\w+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1 if (h >> 8) & 1 else -1
    n = np.linalg.norm(v)
    return (v / n if n else v).tolist()


# ---------- stores ----------
class MemoryStore:
    def __init__(self):
        self.data: dict[str, list] = {}

    def upsert(self, ns, items):
        self.data.setdefault(ns, []).extend(items)

    def query(self, ns, vec, k):
        rows = self.data.get(ns, [])
        scored = sorted(((float(np.dot(vec, r["values"])), r) for r in rows), key=lambda x: -x[0])
        return [{"score": s, **r["metadata"]} for s, r in scored[:k]]

    def delete_ns(self, ns):
        self.data.pop(ns, None)


class PineconeStore:
    def __init__(self):
        from pinecone import Pinecone, ServerlessSpec
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        if not pc.has_index(settings.PINECONE_INDEX):
            pc.create_index(name=settings.PINECONE_INDEX, dimension=settings.EMBEDDING_DIM, metric="cosine",
                            spec=ServerlessSpec(cloud=settings.PINECONE_CLOUD, region=settings.PINECONE_REGION))
        self.index = pc.Index(settings.PINECONE_INDEX)

    def upsert(self, ns, items):
        for i in range(0, len(items), 100):
            self.index.upsert(vectors=[{"id": r["id"], "values": r["values"], "metadata": r["metadata"]} for r in items[i:i + 100]], namespace=ns)

    def query(self, ns, vec, k):
        res = self.index.query(vector=vec, top_k=k, namespace=ns, include_metadata=True)
        return [{"score": m["score"], **m["metadata"]} for m in res["matches"]]

    def delete_ns(self, ns):
        try:
            self.index.delete(delete_all=True, namespace=ns)
        except Exception:
            pass


_store = None


def get_store():
    global _store
    if _store is None:
        _store = PineconeStore() if settings.PINECONE_API_KEY else MemoryStore()
    return _store


def ingest(session_id: str, artifact_id: str, name: str, text: str) -> int:
    chunks = chunk_text(text)
    if not chunks:
        return 0
    vecs = embed(chunks)
    items = [{"id": f"{artifact_id}-{i}", "values": v,
              "metadata": {"text": c[:1500], "file": name, "chunk": i, "artifact_id": artifact_id}} for i, (c, v) in enumerate(zip(chunks, vecs))]
    get_store().upsert(session_id, items)
    return len(items)


def retrieve(session_id: str, query: str, k: int = 4) -> list[dict]:
    try:
        return [h for h in get_store().query(session_id, embed([query])[0], k) if h.get("text")]
    except Exception:
        return []
