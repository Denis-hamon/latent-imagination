# latent-gate public build — CPU only, no GPU required.
# Les artefacts (pool + model.json) sont copiés DANS l'image au build :
# distribution interne hashée, jamais via le repo git.
# NOTE build : l'image de base n'est intentionnellement PAS digest-pinnée ici —
# pinner au moment de la release (docker buildx imagetools inspect python:3.12-slim).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir \
    "numpy>=2.2" \
    "torch>=2.5" --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir \
    "transformers>=4.49,<5" "tokenizers" "safetensors" \
    "fastapi>=0.115" "uvicorn>=0.30" "pydantic>=2.7"

# cache HF embarqué (encodeur gelé) — build offline-friendly ensuite
ENV HF_HOME=/app/hf_cache
RUN python -c "from transformers import AutoModel, AutoTokenizer; \
AutoTokenizer.from_pretrained('microsoft/unixcoder-base'); \
AutoModel.from_pretrained('microsoft/unixcoder-base')"

COPY src/ /app/src/
COPY public/artifacts/latent-pool-v6.json public/artifacts/latent-pool-v6.npz \
     public/artifacts/model.json /app/artifacts/
COPY public/README.md /app/README.md

ENV PYTHONPATH=/app/src LI_POOL_DIR=/app/artifacts LI_MODEL_JSON=/app/artifacts/model.json \
    LI_OUTCOME_DIR=/data/outcomes
VOLUME /data/outcomes

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=5)"

# MCP stdio reste dispo : docker run -i … python -m latent_gate.mcp_stdio
CMD ["python", "-m", "uvicorn", "latent_gate.http_app:app", "--host", "0.0.0.0", "--port", "8080"]
