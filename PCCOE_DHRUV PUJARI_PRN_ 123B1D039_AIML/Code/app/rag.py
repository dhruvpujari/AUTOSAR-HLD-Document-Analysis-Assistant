"""Retrieval + grounded answer + citation check."""
import re
import time
from . import vectorstore, llm
from .config import CFG, PROMPTS

NOT_FOUND = "Not found in the uploaded documents."


def _tag(i, h):
    pages = f"p.{h['page']}" if h["page"] == h["page_end"] else f"p.{h['page']}-{h['page_end']}"
    return f"[S{i}] ({h['doc']} v{h['version']} | {pages} | {h['section']})"


def build_context(hits):
    return "\n\n".join(f"{_tag(i, h)}\n{h['text']}" for i, h in enumerate(hits, start=1))


def confidence(top_score, n_cites, cites_valid):
    if n_cites == 0 or not cites_valid:
        return "low"
    return "high" if top_score >= CFG["retrieval"]["high_score"] else "medium"


def ask(project, question, version=None, doc=None):
    t0 = time.time()
    hits = vectorstore.search(project, question, CFG["retrieval"]["top_k"], version, doc)
    hits = [h for h in hits if h["score"] >= CFG["retrieval"]["min_score"]]

    if not hits:                                   # nothing relevant, do not call the LLM at all
        return {"answer": NOT_FOUND, "found": False, "confidence": "low", "sources": [],
                "latency_s": round(time.time() - t0, 2)}

    user = PROMPTS["qa_user"].format(context=build_context(hits), question=question)
    raw = llm.chat(PROMPTS["qa_system"], user)

    if raw.strip().upper().startswith("NOT_FOUND"):
        return {"answer": NOT_FOUND, "found": False, "confidence": "low", "sources": hits,
                "latency_s": round(time.time() - t0, 2)}

    cited = sorted({int(n) for n in re.findall(r"\[S(\d+)\]", raw)})
    valid = all(1 <= n <= len(hits) for n in cited)
    sources = [dict(hits[n - 1], tag=f"S{n}") for n in cited if 1 <= n <= len(hits)]
    return {
        "answer": raw,
        "found": True,
        "confidence": confidence(hits[0]["score"], len(cited), valid),
        "citations_valid": valid,
        "sources": sources,
        "retrieved": hits,
        "latency_s": round(time.time() - t0, 2),
    }
