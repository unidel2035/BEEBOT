FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Limit thread memory (critical for 2 GB VPS)
ENV OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false

# Python dependencies (no torch — using fastembed/ONNX Runtime instead)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download embedding model at build time (fastembed caches ONNX model)
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# Copy application code
COPY src/ src/
COPY data/processed/ data/processed/
COPY data/texts/ data/texts/

# Copy PDF files (moved to data/pdfs/)
COPY data/pdfs/ data/pdfs/

# Copy curated text files for knowledge base
COPY data/texts/ data/texts/

CMD ["python", "-m", "src.bot"]
