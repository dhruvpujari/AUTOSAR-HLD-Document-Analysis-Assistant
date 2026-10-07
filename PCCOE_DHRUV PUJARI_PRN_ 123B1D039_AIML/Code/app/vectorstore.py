"""BGE embeddings + ChromaDB (one collection per project)."""
import chromadb
from sentence_transformers import SentenceTransformer
from .config import CFG, path

_model = None
_client = None


def _embedder():
    global _model
    if _model is None:
        _model = SentenceTransformer(CFG["embedding"]["model"])
    return _model


def _chroma():
    global _client
    if _client is None:
        p = path("chroma_dir")
        p.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(p))
    return _client


def embed_docs(texts):
    return _embedder().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


def embed_query(q):
    return _embedder().encode(CFG["embedding"]["query_prefix"] + q, normalize_embeddings=True).tolist()


def collection(project):
    return _chroma().get_or_create_collection(f"proj_{project}", metadata={"hnsw:space": "cosine"})


def add_chunks(project, doc_name, version, chunks):
    col = collection(project)
    ids = [f"{doc_name}:{version}:{i}" for i in range(len(chunks))]
    metas = [{"doc": doc_name, "version": version, "page": c.page, "page_end": c.page_end,
              "section": c.section, "ctype": c.ctype} for c in chunks]
    col.upsert(ids=ids, documents=[c.text for c in chunks],
               embeddings=embed_docs([c.text for c in chunks]), metadatas=metas)
    return len(ids)


def delete_doc(project, doc_name, version):
    collection(project).delete(where={"$and": [{"doc": doc_name}, {"version": version}]})


def search(project, question, k, version=None, doc=None):
    where = None
    conds = []
    if version:
        conds.append({"version": version})
    if doc:
        conds.append({"doc": doc})
    if len(conds) == 1:
        where = conds[0]
    elif len(conds) > 1:
        where = {"$and": conds}
    res = collection(project).query(query_embeddings=[embed_query(question)], n_results=k, where=where)
    hits = []
    for text, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"text": text, "score": round(1 - dist, 4), **meta})
    return hits
