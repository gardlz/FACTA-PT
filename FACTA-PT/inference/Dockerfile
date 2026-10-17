FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/cache/huggingface

WORKDIR /srv

RUN adduser --system --group --no-create-home aplicacao \
 && mkdir -p /cache/huggingface && chown -R aplicacao:aplicacao /cache

# COM_GPU=true installs PyTorch's CUDA 12.8 build and bitsandbytes (4-bit quantisation, CUDA
# only). The torch version is read from requirements.txt, so both images use the same one.
ARG COM_GPU=false
COPY requirements.txt requirements-gpu.txt ./
RUN if [ "$COM_GPU" = "true" ]; then \
        pip install --no-cache-dir "$(grep '^torch==' requirements.txt)" \
            --index-url https://download.pytorch.org/whl/cu128 \
     && pip install --no-cache-dir -r requirements.txt -r requirements-gpu.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# Let the CUDA allocator grow segments in place, so a cache that grows one token at a time
# reuses the memory it holds. Some drivers lend system memory to a full GPU instead of failing,
# and memory held there is many times slower.
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

COPY server ./server

RUN chown -R aplicacao:aplicacao /srv
USER aplicacao

EXPOSE 8100

# The service answers as soon as it starts; the models load in the background and /health
# says when they are ready.
HEALTHCHECK --interval=60s --timeout=20s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=8).status==200 else 1)"

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]
