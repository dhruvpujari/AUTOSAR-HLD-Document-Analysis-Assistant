FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app/Code
COPY Code/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY Code/ /app/Code/
COPY Model_Prompts_Config/ /app/Model_Prompts_Config/
ENV AIML_CONFIG_DIR=/app/Model_Prompts_Config
