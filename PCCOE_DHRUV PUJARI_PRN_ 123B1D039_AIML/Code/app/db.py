"""SQLite for documents, extracted entities, findings, review decisions and the audit log."""
import json
import sqlite3
import time
from contextlib import contextmanager
from .config import path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT, name TEXT, version TEXT,
  pages INTEGER, chunks INTEGER, eda TEXT, inventory TEXT, created TEXT,
  UNIQUE(project, name, version));
CREATE TABLE IF NOT EXISTS findings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, rule TEXT, severity TEXT,
  entity TEXT, message TEXT, page INTEGER, status TEXT DEFAULT 'pending', note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS qa_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT, question TEXT, answer TEXT,
  confidence TEXT, sources TEXT, status TEXT DEFAULT 'pending', note TEXT DEFAULT '', ts TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, action TEXT, detail TEXT);
"""


@contextmanager
def conn():
    p = path("sqlite")
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def audit(user, action, detail=""):
    with conn() as c:
        c.execute("INSERT INTO audit(ts,user,action,detail) VALUES(?,?,?,?)", (now(), user, action, detail))


def save_document(project, name, version, pages, chunks, eda):
    with conn() as c:
        c.execute("DELETE FROM documents WHERE project=? AND name=? AND version=?", (project, name, version))
        cur = c.execute("INSERT INTO documents(project,name,version,pages,chunks,eda,created) VALUES(?,?,?,?,?,?,?)",
                        (project, name, version, pages, chunks, json.dumps(eda), now()))
        return cur.lastrowid


def list_documents(project=None):
    with conn() as c:
        q = "SELECT id,project,name,version,pages,chunks,created, inventory IS NOT NULL AS has_inventory FROM documents"
        rows = c.execute(q + (" WHERE project=?" if project else ""), (project,) if project else ()).fetchall()
        return [dict(r) for r in rows]


def get_document(doc_id):
    with conn() as c:
        r = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(r) if r else None


def save_inventory(doc_id, inv, findings):
    with conn() as c:
        c.execute("UPDATE documents SET inventory=? WHERE id=?", (json.dumps(inv), doc_id))
        c.execute("DELETE FROM findings WHERE doc_id=?", (doc_id,))
        for f in findings:
            c.execute("INSERT INTO findings(doc_id,rule,severity,entity,message,page) VALUES(?,?,?,?,?,?)",
                      (doc_id, f["rule"], f["severity"], f["entity"], f["message"], f.get("page")))


def get_findings(doc_id):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM findings WHERE doc_id=?", (doc_id,)).fetchall()]


def log_answer(project, question, ans):
    with conn() as c:
        cur = c.execute("INSERT INTO qa_log(project,question,answer,confidence,sources,ts) VALUES(?,?,?,?,?,?)",
                        (project, question, ans["answer"], ans["confidence"],
                         json.dumps([{k: s.get(k) for k in ("doc", "version", "page", "section")} for s in ans["sources"]]),
                         now()))
        return cur.lastrowid


def review(table, row_id, status, note=""):
    assert table in ("findings", "qa_log")
    assert status in ("accepted", "edited", "rejected", "pending")
    with conn() as c:
        c.execute(f"UPDATE {table} SET status=?, note=? WHERE id=?", (status, note, row_id))


def pending(table):
    assert table in ("findings", "qa_log")
    with conn() as c:
        return [dict(r) for r in c.execute(f"SELECT * FROM {table} WHERE status='pending' ORDER BY id DESC LIMIT 200")]
