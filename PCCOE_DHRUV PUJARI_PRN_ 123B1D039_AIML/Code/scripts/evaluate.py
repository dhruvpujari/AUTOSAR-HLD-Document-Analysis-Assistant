"""
Evaluation runner. Uses the files made by make_synthetic_hld.py.

    python scripts/evaluate.py --ingest                 # ingest the PDFs, then run the Q&A test set
    python scripts/evaluate.py --extract                # also run entity extraction + rule checks (slow, one LLM call per chunk)
    python scripts/evaluate.py --tag chunk300           # label the run (shows up in the results folder and MLflow)

Everything is written to ../Evaluation_Results/run_<tag>_<time>/ . Failures are kept in the CSV on purpose.
"""
import argparse
import csv
import json
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import rag, rules, ingest                                   # noqa: E402
from app.config import CFG, PROMPTS, path                            # noqa: E402

DATA = path("input_data")


def covers(h, doc, page):
    return h["doc"] == doc and h["page"] <= page <= h["page_end"]


def eval_qa(project, questions):
    rows = []
    for q in questions:
        ans = rag.ask(project, q["question"])
        retrieved = ans.get("retrieved") or ans.get("sources") or []
        if q["type"] == "not_found":
            ok = not ans["found"]
            hit = cite = None
            correct = ok
        else:
            hit = any(covers(h, q["doc"], q["page"]) for h in retrieved)
            cite = any(covers(s, q["doc"], q["page"]) for s in ans["sources"]) if ans["found"] else False
            text = ans["answer"].lower()
            correct = ans["found"] and all(k.lower() in text for k in q["keywords"])
        rows.append({"id": q["id"], "type": q["type"], "question": q["question"], "expected_doc": q["doc"],
                     "expected_page": q["page"], "keywords": ";".join(q["keywords"]), "found": ans["found"],
                     "retrieval_hit": hit, "citation_ok": cite, "answer_correct": correct,
                     "confidence": ans["confidence"], "latency_s": ans["latency_s"],
                     "answer": ans["answer"].replace("\n", " ")[:400]})
        print(f"{q['id']:>3} {q['type']:<9} hit={hit} cite={cite} correct={correct}  {q['question'][:60]}")
    return rows


def summarise_qa(rows):
    ans_rows = [r for r in rows if r["type"] != "not_found"]
    nf = [r for r in rows if r["type"] == "not_found"]
    pct = lambda xs: round(100 * sum(bool(x) for x in xs) / len(xs), 1) if xs else None
    s = {
        "questions": len(rows),
        "retrieval_hit_at_k_pct": pct([r["retrieval_hit"] for r in ans_rows]),
        "citation_accuracy_pct": pct([r["citation_ok"] for r in ans_rows]),
        "answer_correct_pct": pct([r["answer_correct"] for r in ans_rows]),
        "not_found_correct_pct": pct([r["answer_correct"] for r in nf]),
        "latency_median_s": round(st.median(r["latency_s"] for r in rows), 2),
        "latency_max_s": max(r["latency_s"] for r in rows),
    }
    for t in sorted({r["type"] for r in ans_rows}):
        s[f"answer_correct_pct_{t}"] = pct([r["answer_correct"] for r in ans_rows if r["type"] == t])
    return s


def prf(pred, gold):
    pred, gold = set(pred), set(gold)
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def entity_sets(inv):
    return {
        "components": set(inv["components"]),
        "interfaces": set(inv["interfaces"]),
        "signals": set(inv["signals"]),
        "port_links": {(c, p["name"], p.get("interface", "")) for c, v in inv["components"].items() for p in v.get("ports", [])},
    }


def eval_extraction(gold, defects, expected_diff):
    from app import extract
    out, invs = [], {}
    for doc, g in gold.items():
        pages = ingest.clean_pages(ingest.read_pdf(str(DATA / "hld_pdfs" / doc)))
        inv, stats = extract.build_inventory(ingest.chunk_document(pages))
        invs[doc] = inv
        pe, ge = entity_sets(inv), entity_sets(g)
        row = {"doc": doc, **{f"llm_{k}": v for k, v in stats.items()}}
        for k in ge:
            p, r, f = prf(pe[k], ge[k])
            row.update({f"{k}_precision": p, f"{k}_recall": r, f"{k}_f1": f})
        found = {(x["rule"], x["entity"]) for x in rules.check_inventory(inv)}
        want = {(x["rule"], x["entity"]) for x in defects[doc]}
        row["defect_recall"] = round(len(found & want) / len(want), 3) if want else None
        row["defect_false_alarms"] = len(found - want)
        out.append(row)
        print(doc, {k: v for k, v in row.items() if k.endswith("_f1") or k.startswith("defect")})
    diff_row = None
    a, b = "HLD_DoorLock_v1.0.pdf", "HLD_DoorLock_v1.1.pdf"
    if a in invs and b in invs:
        got = {(d["change"], d["kind"], d["name"]) for d in rules.compare_inventories(invs[a], invs[b])}
        exp = {(d["change"], d["kind"], d["name"]) for d in expected_diff}
        p, r, f = prf(got, exp)
        diff_row = {"precision": p, "recall": r, "f1": f}
    return out, diff_row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="eval")
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--tag", default="baseline")
    a = ap.parse_args()

    run_dir = path("results_dir") / f"run_{a.tag}_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    if a.ingest:
        from app import pipeline
        for pdf in sorted((DATA / "hld_pdfs").glob("*.pdf")):
            ver = pdf.stem.split("_v")[-1]
            _, eda, _ = pipeline.ingest_file(a.project, pdf, ver, user="eval")
            print("ingested", pdf.name, eda)

    questions = json.loads((DATA / "test_questions.json").read_text(encoding="utf-8"))
    rows = eval_qa(a.project, questions)
    summary = {"tag": a.tag, "llm": CFG["llm"]["model"], "embedding": CFG["embedding"]["model"],
               "chunk_tokens": CFG["chunking"]["max_tokens"], "top_k": CFG["retrieval"]["top_k"],
               "min_score": CFG["retrieval"]["min_score"], "prompt_version": PROMPTS["version"],
               "qa": summarise_qa(rows)}

    with open(run_dir / "qa_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    if a.extract:
        gold = json.loads((DATA / "gold_inventory.json").read_text(encoding="utf-8"))
        defects = json.loads((DATA / "seeded_defects.json").read_text(encoding="utf-8"))
        diff = json.loads((DATA / "expected_revision_diff.json").read_text(encoding="utf-8"))
        ex_rows, diff_row = eval_extraction(gold, defects, diff)
        summary["extraction"] = ex_rows
        summary["revision_diff"] = diff_row
        with open(run_dir / "extraction_results.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(ex_rows[0]))
            w.writeheader()
            w.writerows(ex_rows)

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n", json.dumps(summary["qa"], indent=2), "\nSaved to", run_dir)

    try:                                         # optional experiment tracking
        import mlflow
        mlflow.set_tracking_uri(f"file:{path('results_dir') / 'mlruns'}")
        mlflow.set_experiment("autosar-hld-rag")
        with mlflow.start_run(run_name=a.tag):
            mlflow.log_params({k: summary[k] for k in ("llm", "embedding", "chunk_tokens", "top_k", "min_score", "prompt_version")})
            mlflow.log_metrics({k: v for k, v in summary["qa"].items() if isinstance(v, (int, float))})
            mlflow.log_artifacts(str(run_dir))
    except ImportError:
        pass


if __name__ == "__main__":
    main()
