"""Web application: serves the interface and exposes the fact-checking pipeline API."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .runstore import RunStore
from .services.inference import InferenceClient
from .services.lusa import LusaClient
from .settings import get_settings

ESTATICOS = Path(__file__).parent / "static"


class EstaticosRevalidados(StaticFiles):
    """Static files sent with `no-cache`, so the browser revalidates them instead of reusing a
    stale copy."""

    def file_response(self, *args, **kwargs):
        resposta = super().file_response(*args, **kwargs)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    definicoes = get_settings()
    app.state.lusa = LusaClient(definicoes)
    app.state.inference = InferenceClient(definicoes)
    app.state.runs = RunStore(definicoes.run_retention, definicoes.run_store_dir)
    app.state.limitador = asyncio.Semaphore(max(1, definicoes.max_concurrent_runs))
    try:
        yield
    finally:
        await app.state.lusa.aclose()
        await app.state.inference.aclose()


def create_app() -> FastAPI:
    definicoes = get_settings()
    app = FastAPI(
        title=definicoes.app_name,
        description="Pipeline de verificação factual: perguntas, evidência, classificação e artigo.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    if definicoes.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=definicoes.allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )
    app.include_router(router)
    app.mount("/assets", EstaticosRevalidados(directory=ESTATICOS), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(ESTATICOS / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(ESTATICOS / "favicon.svg")

    return app


app = create_app()
