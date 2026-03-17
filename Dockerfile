FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU-only FIRST (before requirements.txt pulls CUDA version)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Python dependencies (torch already installed — pip will skip it)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Limit thread memory (critical for 2 GB VPS)
ENV OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false

# Download embedding model at build time
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# Copy application code
COPY src/ src/
COPY data/processed/ data/processed/

# Copy PDF files (moved to data/pdfs/)
COPY data/pdfs/ data/pdfs/

CMD ["python", "-m", "src.bot"]
