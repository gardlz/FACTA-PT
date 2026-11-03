"""Web application: serves the interface and exposes the fact-checking pipeline API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers

from . import acesso
from .admin import router as admin_router
from .api import router
from .fila import Fila
from .mensagens import lingua_do_pedido, texto
from .plataforma import PlatformStore
from .revisao import ReviewStore
from .runstore import RunStore
from .services.inference import InferenceClient
from .services.lusa import LusaClient
from .settings import get_settings
from .utilizadores import UserStore

# The interface's build (`web/frontend`, `npm run build`): `index.html` plus hashed files under
# `assets/`. The Docker image builds it in its own stage.
ESTATICOS = Path(__file__).parent / "static"

# The largest request body taken, in bytes: a claim with the longest context allowed
# (`ClaimInput`), every character escaped, is a fraction of it.
CORPO_MAXIMO = 1 << 20


class EstaticosImutaveis(StaticFiles):
    """Serve the bundle's files as cacheable forever.

    Their names carry a hash of their content, so a fix ships under a new name that the
    (always revalidated) `index.html` points to; a cached copy is never stale.
    """

    def file_response(self, *args, **kwargs):
        resposta = super().file_response(*args, **kwargs)
        resposta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resposta


class CabecalhosDeSeguranca:
    """Headers on every response. Plain ASGI rather than `BaseHTTPMiddleware`, which would
    buffer the run's event stream and mishandle a page that goes away mid-run."""

    def __init__(self, app, hsts: bool) -> None:
        self.app = app
        self.cabecalhos = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"same-origin"),
            (b"cross-origin-opener-policy", b"same-origin"),
        ]
        if hsts:
            self.cabecalhos.append((b"strict-transport-security", b"max-age=31536000"))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def enviar(mensagem):
            if mensagem["type"] == "http.response.start":
                mensagem["headers"] = [*mensagem.get("headers", []), *self.cabecalhos]
            await send(mensagem)

        return await self.app(scope, receive, enviar)


class SoJson:
    """Refuses, before anything reads it, a request body that is not JSON (415), that does not
    say how long it is (411) or that is longer than `maximo` (413).

    Every body the API takes is JSON, and nothing in the site parses XML or forms: this keeps it
    so, whatever a route does later. An XML document - external entities, entity expansion - is
    turned away at the door, and so is a `text/plain` POST, the one cross-site requests can send
    without asking first."""

    METODOS_COM_CORPO = frozenset({"POST", "PUT", "PATCH"})

    def __init__(self, app, maximo: int) -> None:
        self.app = app
        self.maximo = maximo

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in self.METODOS_COM_CORPO:
            return await self.app(scope, receive, send)
        cabecalhos = Headers(scope=scope)
        tipo = cabecalhos.get("content-type", "").split(";")[0].strip().lower()
        comprimento = cabecalhos.get("content-length", "")
        if tipo != "application/json":
            estado, chave = 415, "corpo_nao_json"
        elif not comprimento.isdigit():
            # A chunked body says its length only at the end: the limit could not be checked.
            estado, chave = 411, "corpo_sem_tamanho"
        elif int(comprimento) > self.maximo:
            estado, chave = 413, "corpo_grande"
        else:
            return await self.app(scope, receive, send)
        lingua = lingua_do_pedido(cabecalhos.get("accept-language"))
        resposta = JSONResponse({"detail": texto(chave, lingua)}, status_code=estado,
                                headers={"Cache-Control": "no-store"})
        await resposta(scope, receive, send)


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    definicoes = get_settings()
    utilizadores = UserStore(definicoes.utilizadores_path)
    acesso.validar_configuracao(definicoes, utilizadores)
    if not definicoes.access_gate_disabled:
        utilizadores.garantir_admin(definicoes)
    app.state.utilizadores = utilizadores
    app.state.plataforma = PlatformStore(definicoes.plataforma_path)
    app.state.revisoes = ReviewStore(definicoes.revisoes_dir)
    app.state.lusa = LusaClient(definicoes)
    app.state.inference = InferenceClient(definicoes)
    app.state.runs = RunStore(definicoes.run_retention, definicoes.run_store_dir,
                              definicoes.saved_retention)
    app.state.fila = Fila(definicoes)
    try:
        yield
    finally:
        await app.state.lusa.aclose()
        await app.state.inference.aclose()
        await app.state.fila.aclose()


def create_app() -> FastAPI:
    definicoes = get_settings()
    app = FastAPI(
        title=definicoes.app_name,
        description="Pipeline de verificação factual: perguntas, evidência, classificação e artigo.",
        version="1.0.0",
        lifespan=lifespan,
        # No public API documentation: it would describe the routes to someone not signed in.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Added first, so it runs inside the headers below: its refusals carry them too.
    app.add_middleware(SoJson, maximo=CORPO_MAXIMO)
    app.add_middleware(CabecalhosDeSeguranca, hsts=definicoes.cookie_secure)
    if definicoes.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=definicoes.allowed_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["*"],
        )
    app.include_router(acesso.router)
    app.include_router(admin_router)
    app.include_router(router)
    # `check_dir=False`: the API still starts when the interface has not been built.
    app.mount("/assets", EstaticosImutaveis(directory=ESTATICOS / "assets", check_dir=False), name="assets")

    # The interface's own routes (React Router) load the same page, so their addresses can be
    # reloaded and shared.
    @app.get("/", include_in_schema=False)
    @app.get("/verificacao", include_in_schema=False)
    @app.get("/sobre", include_in_schema=False)
    @app.get("/administracao", include_in_schema=False)
    @app.get("/verificacao/{exemplo_id}", include_in_schema=False)
    async def index(exemplo_id: str | None = None) -> FileResponse:
        return FileResponse(ESTATICOS / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(ESTATICOS / "favicon.svg")

    return app


app = create_app()
