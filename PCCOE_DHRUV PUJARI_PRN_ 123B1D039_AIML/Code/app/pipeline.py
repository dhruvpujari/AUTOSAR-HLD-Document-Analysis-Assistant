"""ingest -> chunk -> embed -> store, used by the API and by the evaluation script."""
from pathlib import Path
from . import ingest, vectorstore, db


def ingest_file(project, pdf_path, version, user="engineer"):
    pdf_path = Path(pdf_path)
    pages = ingest.clean_pages(ingest.read_pdf(str(pdf_path)))
    chunks = ingest.chunk_document(pages)
    vectorstore.add_chunks(project, pdf_path.name, version, chunks)
    eda = ingest.eda_summary(pages, chunks)
    doc_id = db.save_document(project, pdf_path.name, version, len(pages), len(chunks), eda)
    db.audit(user, "ingest", f"{project}/{pdf_path.name} v{version} {eda}")
    return doc_id, eda, chunks
