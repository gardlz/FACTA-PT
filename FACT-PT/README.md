# FACT-PT

Fact-checking of claims in European Portuguese: verification questions, evidence from the LUSA
archive, relevance and claim–evidence classification, and an article citing its sources.

- `web/` — the website (FastAPI + React), port 8000.
- `worker` — takes the runs that use the models from a queue (Redis + RQ) one at a time, and runs
  them; same image as the website. The page shows how many runs are ahead, and a run goes on when
  the browser drops its connection: the page reconnects. More runs at once:
  `docker compose up -d --scale worker=2`.
- `redis` — the queue and each run's events.
- `web/inference/` — the inference service with the models (see [MODELS.md](MODELS.md)), port 8100,
  reached only by the website and the worker.

## Running

1. Copy `.env.example` to `.env` and fill it in: the LUSA account (the API only answers over the
   VPN), the Modal gateway of the AMALIA models (`MODAL_API_URL`, `MODAL_API_KEY`), the OpenRouter
   key for the Gemma writer (`ARTICLE_API_KEY`) and the first administrator (`python -m
   app.acesso` in `web/`, or copy `.env` from another machine).
2. Start it:
   - NVIDIA GPU: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build`
   - no GPU: `docker compose up -d --build`
3. The first start downloads the classifiers (about 3 GB, [MODELS.md](MODELS.md)). The website answers
   at once, with the worked examples; new claims once the models are loaded:
   `docker compose exec inference python -c "import urllib.request as u; print(u.urlopen('http://localhost:8100/health').read().decode())"`
   says which are.
4. Open http://localhost:8000 and sign in with the first administrator (`admin`, unless
   `ADMIN_USERNAME` says otherwise, and the password whose hash is in `.env`). Over plain HTTP set
   `COOKIE_SECURE=false` in `.env`, or the login does not stick. To serve it to others over HTTPS,
   see [SERVER-GUIDE.md](SERVER-GUIDE.md).

## Accounts and roles

Everyone signs in with their own account; there is no shared password. An administrator makes the
others in **Administração**, which also holds what each role may do and the platform's defaults.

- **Jornalista** — verifies, reads and edits results, and takes part in the editorial review. The
  administrator may take any of those away. A journalist's verification also runs in the background
  (`segundo_plano`): it has its address from the start, goes on when its page is left or closed,
  and is listed on its own page, *Verificações*, under the account, for a day, to be opened again
  from any session. A run that stopped without a verification (cancelled, failed or lost) can be
  restarted from there.
- **Administrador** — everything, including the accounts and the platform settings. At least one
  active administrator always remains.

Permissions are read on every request, so a change of role applies at once. Deactivating or deleting
an account, or changing its password, ends that person's sessions; nobody can deactivate, demote or
delete themselves. Deleting cannot be undone, but the revisions the account signed keep its name.

## Editorial review

A saved verification is a **draft** an editor can change where it is shown: which news items count,
what each passage says (or a stretch of a news item highlighted as supporting, refuting or
undecided), the verdict, from the verdict band, and the article's text. One undo and one redo
(Ctrl+Z, Ctrl+Shift+Z) cover every kind of edit, and nothing is kept until the editor saves
(`Guardar versão`, Ctrl+S): each save is one version, with its author, time and the fields it
changed. A draft not yet saved survives a reload in the same browser.

The automated result is never changed: it is version 0. The history opens any version on the page
to be read as it was, and saving it brings it back as a new version. The article can also be
written again from the saved evidence, with the run's writer or another; the rewrite is a version
of its own.

## On a server

Behind HTTPS, with a reverse proxy, the port kept off the network and the proxy's address trusted:
see [SERVER-GUIDE.md](SERVER-GUIDE.md). With no domain of your own, Tailscale Funnel serves the same
site over HTTPS at a `*.ts.net` address:
[Without a domain: Tailscale Funnel](SERVER-GUIDE.md#without-a-domain-tailscale-funnel).

## The 8 GB GPU desktop

The RTX 4060 Ti desktop (32 GB, Windows + WSL): see [GPU-GUIDE.md](GPU-GUIDE.md).
