FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SENTINEL_DATA=/data \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XDG_CACHE_HOME=/data/model-cache \
    HF_HOME=/data/model-cache/huggingface
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 sentinel && useradd --uid 10001 --gid sentinel --create-home sentinel
WORKDIR /app
COPY requirements.txt requirements.lock requirements-ocr.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
ARG INSTALL_OCR=0
RUN if [ "$INSTALL_OCR" = "1" ]; then pip install --no-cache-dir -r requirements-ocr.txt; fi
COPY app ./app
COPY examples ./examples
RUN mkdir -p /data && chown -R sentinel:sentinel /data /app
USER sentinel
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
