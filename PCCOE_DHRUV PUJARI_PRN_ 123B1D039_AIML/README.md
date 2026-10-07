# AUTOSAR HLD Document Analysis Assistant (CS1)

Local RAG assistant for AUTOSAR High-Level Design documents: cited Q&A, entity extraction,
rule-based consistency checks and revision comparison. Everything runs on the local machine.

## Folder layout
- `Code/`                 application, UI, scripts
- `Model_Prompts_Config/` config.yaml, prompts.yaml, Dockerfile, docker-compose.yml
- `Input_Data/`           synthetic HLD PDFs and ground-truth files (made by the generator)
- `Evaluation_Results/`   one folder per evaluation run

## Setup (without Docker)
```bash
cd Code
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# also install Tesseract OCR (only needed for scanned pages) and Ollama (https://ollama.com)
ollama pull llama3.1:8b-instruct-q4_K_M
```

## Run
```bash
python scripts/make_synthetic_hld.py                    # creates ../Input_Data (already included)
uvicorn app.api:app --port 8000                         # terminal 1
streamlit run ui/streamlit_app.py                       # terminal 2  ->  http://localhost:8501
```
In the UI: Upload a PDF, ask questions, then use "Inventory and checks" to extract entities.

## Evaluate
```bash
python scripts/evaluate.py --ingest --tag baseline      # Q&A metrics
python scripts/evaluate.py --extract --tag baseline     # + extraction, defect recall, revision diff (slow)
```
To compare settings, change one value in `Model_Prompts_Config/config.yaml` (chunk size, embedding model, top_k,
min_score) and run again with a new `--tag`. Results land in `Evaluation_Results/`.

`min_score` and `high_score` depend on the embedding model. Look at the scores of correct and
"not found" questions in `qa_results.csv` and adjust them.

## Docker
```bash
docker compose -f Model_Prompts_Config/docker-compose.yml up --build
docker compose -f Model_Prompts_Config/docker-compose.yml exec ollama ollama pull llama3.1:8b-instruct-q4_K_M
```

## Notes
- Only synthetic or approved documents should be uploaded. Nothing is sent outside the machine.
- Answers and findings are drafts. Use the Review tab to accept, edit or reject them; decisions go to the audit log.
- Known limits: diagrams inside PDFs are not read, the naming rules (Swc_, If_, Sig_) in `extract.py` fit the synthetic documents and
  must be changed for other naming conventions.
