FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN adduser --system --group --no-create-home aplicacao

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# NLTK's Punkt model for Portuguese (punkt_tab), the sentence split of the entailment classifier's
# training windows; `app/pipeline/excerpts.py` looks for it here first. Loading it once makes the
# build fail if the download did not succeed.
ENV NLTK_DATA=/srv/nltk_data
RUN python -m nltk.downloader -q -d /srv/nltk_data punkt_tab \
    && python -c "from nltk.tokenize.punkt import PunktTokenizer; PunktTokenizer('portuguese')"

COPY app ./app

RUN chown -R aplicacao:aplicacao /srv
USER aplicacao

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/exemplos', timeout=4).status==200 else 1)"

ENV WEB_WORKERS=2

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_WORKERS} --proxy-headers --forwarded-allow-ips '*'"]
