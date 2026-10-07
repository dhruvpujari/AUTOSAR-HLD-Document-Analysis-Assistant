"""FastAPI service. Run:  uvicorn app.api:app --port 8000"""
import csv
import io
import json
import os
import shutil
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import db, rag, rules, extract, pipeline, ingest
from .config import path

app = FastAPI(title="AUTOSAR HLD Assistant")
TOKEN = os.environ.get("APP_TOKEN")             # optional shared token, set it in docker-compose


def check(token, user):
    if TOKEN and token != TOKEN:
        raise HTTPException(401, "bad token")
    return user or "engineer"


class Query(BaseModel):
    project: str
    question: str
    version: Optional[str] = None
    doc: Optional[str] = None


class Review(BaseModel):
    table: str
    id: int
    status: str
    note: str = ""


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/documents")
def documents(project: Optional[str] = None, x_token: str = Header(None), x_user: str = Header(None)):
    check(x_token, x_user)
    return db.list_documents(project)


@app.post("/ingest")
def do_ingest(project: str = Form(...), version: str = Form(...), file: UploadFile = File(...),
              x_token: str = Header(None), x_user: str = Header(None)):
    user = check(x_token, x_user)
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "only PDF files are accepted")
    up = path("upload_dir") / project
    up.mkdir(parents=True, exist_ok=True)
    dest = up / os.path.basename(file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    doc_id, eda, _ = pipeline.ingest_file(project, dest, version, user)
    return {"doc_id": doc_id, "eda": eda}


@app.post("/extract/{doc_id}")
def do_extract(doc_id: int, x_token: str = Header(None), x_user: str = Header(None)):
    """Slow: one LLM call per chunk. Builds the inventory and runs the rule checks."""
    user = check(x_token, x_user)
    d = db.get_document(doc_id)
    if not d:
        raise HTTPException(404, "document not found")
    pdf = path("upload_dir") / d["project"] / d["name"]
    pages = ingest.clean_pages(ingest.read_pdf(str(pdf)))
    chunks = ingest.chunk_document(pages)
    inv, stats = extract.build_inventory(chunks)
    findings = rules.check_inventory(inv)
    db.save_inventory(doc_id, inv, findings)
    db.audit(user, "extract", f"doc {doc_id} {stats} findings={len(findings)}")
    return {"stats": stats, "findings": len(findings)}


@app.post("/query")
def query(q: Query, x_token: str = Header(None), x_user: str = Header(None)):
    user = check(x_token, x_user)
    ans = rag.ask(q.project, q.question, q.version, q.doc)
    ans["log_id"] = db.log_answer(q.project, q.question, ans)
    ans.pop("retrieved", None)
    db.audit(user, "query", f"{q.project}: {q.question[:120]} -> {ans['confidence']}")
    return ans


@app.get("/entities/{doc_id}")
def entities(doc_id: int, x_token: str = Header(None), x_user: str = Header(None)):
    check(x_token, x_user)
    d = db.get_document(doc_id)
    if not d or not d["inventory"]:
        raise HTTPException(404, "no inventory yet, call /extract first")
    return json.loads(d["inventory"])


@app.get("/findings/{doc_id}")
def findings(doc_id: int, x_token: str = Header(None), x_user: str = Header(None)):
    check(x_token, x_user)
    return db.get_findings(doc_id)


@app.post("/compare")
def compare(old_id: int, new_id: int, x_token: str = Header(None), x_user: str = Header(None)):
    check(x_token, x_user)
    a, b = db.get_document(old_id), db.get_document(new_id)
    if not a or not b or not a["inventory"] or not b["inventory"]:
        raise HTTPException(400, "both documents need an inventory (run /extract)")
    return rules.compare_inventories(json.loads(a["inventory"]), json.loads(b["inventory"]))


@app.get("/export/{doc_id}")
def export(doc_id: int, fmt: str = "json", x_token: str = Header(None), x_user: str = Header(None)):
    user = check(x_token, x_user)
    d = db.get_document(doc_id)
    if not d or not d["inventory"]:
        raise HTTPException(404, "no inventory yet")
    inv = json.loads(d["inventory"])
    db.audit(user, "export", f"doc {doc_id} {fmt}")
    if fmt == "json":
        return Response(json.dumps(inv, indent=2), media_type="application/json")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["kind", "name", "port", "direction", "interface", "depends_on_or_producer", "consumers", "page"])
    for n, c in inv["components"].items():
        for p in c.get("ports") or [{}]:
            w.writerow(["component", n, p.get("name", ""), p.get("direction", ""), p.get("interface", ""),
                        ";".join(c.get("depends_on", [])), "", c.get("page", "")])
    for n, i in inv["interfaces"].items():
        w.writerow(["interface", n, "", "", ";".join(i.get("elements", [])), "", "", i.get("page", "")])
    for n, s in inv["signals"].items():
        w.writerow(["signal", n, "", "", "", s.get("producer", ""), ";".join(s.get("consumers", [])), s.get("page", "")])
    return Response(buf.getvalue(), media_type="text/csv")


@app.post("/review")
def do_review(r: Review, x_token: str = Header(None), x_user: str = Header(None)):
    user = check(x_token, x_user)
    db.review(r.table, r.id, r.status, r.note)
    db.audit(user, "review", f"{r.table}#{r.id} -> {r.status}")
    return {"ok": True}


@app.get("/review/pending")
def pending(x_token: str = Header(None), x_user: str = Header(None)):
    check(x_token, x_user)
    return {"findings": db.pending("findings"), "answers": db.pending("qa_log")}
