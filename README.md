# AUTOSAR HLD Document Analysis Assistant

A local AI-powered assistant for analysing AUTOSAR High-Level Design (HLD) documents using a Large Language Model (LLM) and Retrieval-Augmented Generation (RAG).

Developed as an academic capstone project for the **Tech Pulse FY-26 AI/ML Capstone Programme** at Pimpri Chinchwad College of Engineering (PCCOE), Pune.

## Overview

AUTOSAR HLD documents contain important information about software components, interfaces, signals, dependencies, and system design. Reviewing these documents manually can be time-consuming.

This project helps users search, analyse, and compare HLD documents using local AI models. It provides answers with source citations, extracts design information, identifies potential consistency issues, and displays evaluation results.

## Features

- **PDF Upload:** Upload HLD documents for analysis.
- **Question Answering:** Ask questions and receive answers grounded in retrieved document content.
- **Source Citations:** View supporting page and section references.
- **RAG-Based Retrieval:** Retrieve relevant document passages before generating answers.
- **Entity Extraction:** Extract software components, interfaces, signals, and related information.
- **Consistency Checks:** Identify potential design issues, including undefined interfaces and unknown dependencies.
- **Revision Comparison:** Compare document revisions and review detected changes.
- **Review Queue:** Review AI-generated findings before accepting or rejecting them.
- **Evaluation Dashboard:** View evaluation results and analyse system performance.
- **Local AI Processing:** Run the language model and embedding model locally.

## Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3.11 |
| Language Model | Llama 3.1 8B Instruct |
| Model Runtime | Ollama |
| Embedding Model | BAAI/bge-small-en-v1.5 |
| Vector Database | ChromaDB |
| Backend | FastAPI |
| Frontend | Streamlit |
| Database | SQLite |
| Data Validation | Pydantic |
| PDF Processing | PyMuPDF, pdfplumber |
| OCR Support | Tesseract OCR |

## System Workflow

1. Upload an AUTOSAR HLD PDF.
2. Extract text and tables from the document.
3. Split the content into searchable chunks and generate embeddings.
4. Store the embeddings in the local ChromaDB vector database.
5. Retrieve relevant content when a user asks a question.
6. Generate an answer using the local LLM and provide source citations.
7. Extract design entities and run consistency checks when requested.
8. Compare revisions and review potential issues.
9. Evaluate the system using test questions and expected results.

## Project Structure

```text
PCCOE_DHRUV_PUJARI_123B1D039_AIML/
├── Code/
│   ├── app/
│   ├── scripts/
│   └── ui/
├── Input_Data/
├── Model_Prompts_Config/
├── Evaluation_Results/
├── Documentation/
├── Synopsis.docx
├── Technical_Report.docx
└── README.md
```

*The displayed structure is illustrative. Actual filenames may differ in the repository.*

## Installation and Setup

### Prerequisites

- Python 3.11
- Git
- Ollama
- Required Python packages from the project's dependency files

### 1. Clone the Repository

```bash
git clone https://github.com/dhruvpujari/AUTOSAR-HLD-Document-Analysis-Assistant.git
cd AUTOSAR-HLD-Document-Analysis-Assistant
```

### 2. Download the Local Language Model

Install Ollama, then run:

```bash
ollama pull llama3.1:8b-instruct-q4_K_M
```

Keep Ollama running while using the application.

### 3. Install Python Dependencies

Create and activate a Python 3.11 virtual environment from the project root.

**Windows PowerShell:**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the dependencies using the project's available requirements file. For example, if `Code/requirements.txt` exists:

```powershell
python -m pip install -r .\Code\requirements.txt
```

If your dependency file is located elsewhere, use its actual path.

### 4. Start the Backend

Open a terminal in the `Code` directory and activate the virtual environment. Run:

```powershell
uvicorn app.api:app --port 8000
```

### 5. Start the Streamlit Interface

Open another terminal, activate the same virtual environment, and run from the repository root:

```powershell
python -m streamlit run ".\Code\ui\streamlit_app.py"
```

Open the local URL shown in the terminal.

**Note:** These commands assume the repository root directly contains the `Code` directory. Adjust the paths if your actual repository structure differs.

## Evaluation

The system was evaluated using synthetic AUTOSAR-style HLD documents, expected outputs, seeded defects, and 54 test questions.

| Evaluation Category | Number of Questions |
|---|---:|
| Direct facts | 16 |
| Table lookups | 12 |
| Multi-item questions | 20 |
| Unanswerable questions | 6 |
| **Total** | **54** |

### Baseline Results

The recorded baseline evaluation reported:

| Metric | Result |
|---|---:|
| Retrieval Hit@5 | 100% |
| Answer Correctness | 93.8% |
| Citation Accuracy | 85.4% |
| Not-Found Accuracy | 100% |

These results are from the synthetic test set and do not guarantee the same performance on real-world AUTOSAR documents.

Detailed results are available in `Evaluation_Results/`, including:

- `qa_results.csv` — question-answer evaluation
- `extraction_results.csv` — entity extraction evaluation
- `summary.json` — evaluation summary and metrics

## Limitations

- Entity extraction may return extra or incorrect entities.
- Some design defects may be missed.
- Some valid design elements may be incorrectly flagged.
- Citation accuracy is not 100%.
- Evaluation has been performed using synthetic documents; testing on diverse real-world documents is still required.
- AI-generated answers and findings require human verification.

## Privacy and Data

The project uses synthetic AUTOSAR-style documents and test data. The language model and embedding model run locally during application use.

No confidential company documents are required for the demonstration. External AI tools may have been used during development for coding and documentation assistance; these are separate from the local models used by the application.

## Future Improvements

- Improve entity extraction precision and relationship detection.
- Reduce false alarms in consistency checks.
- Improve revision comparison accuracy.
- Expand the evaluation dataset.
- Test with diverse real-world documents where authorised.
- Add stronger user access controls and security features.

## Academic Attribution

This project was developed as part of the **Tech Pulse FY-26 AI/ML Capstone Programme** at Pimpri Chinchwad College of Engineering (PCCOE), Pune.

It is an academic implementation and does not imply official endorsement by Tata Technologies.

## Author

**Dhruv Pujari**  
B.Tech Computer Engineering  
Pimpri Chinchwad College of Engineering (PCCOE), Pune

*This project is intended to support HLD document analysis and does not replace expert review of system design documents.*
