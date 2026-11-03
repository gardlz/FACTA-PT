"""Administration: accounts, roles and the platform settings.

Only an administrator reaches these routes (`gerir_utilizadores`, `gerir_plataforma`). Responses
never carry a password hash. Two invariants are enforced here, not only in the page: at least one
active administrator remains, and nobody can deactivate, demote or delete their own account.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from .acesso import exigir_permissao, verificar_origem
from .armazenamento import FalhaAoGravar
from .mensagens import lingua_do_pedido, texto
from .plataforma import PERMISSOES, PERMISSOES_EDITAVEIS, Definicoes
from .utilizadores import (
    PALAVRA_PASSE_MINIMA,
    UTILIZADOR_VALIDO,
    Utilizador,
    UserStore,
)

router = APIRouter(prefix="/api/admin", dependencies=[Depends(verificar_origem)])

Papel = Literal["jornalista", "administrador"]


def _lingua(request: Request) -> str:
    return lingua_do_pedido(request.headers.get("accept-language"))


def _store(request: Request) -> UserStore:
    return request.app.state.utilizadores


def _activos_admin(store: UserStore) -> list[Utilizador]:
    return [u for u in store.listar() if u.papel == "administrador" and u.activo]


class NovoUtilizador(BaseModel):
    utilizador: str = Field(min_length=1, max_length=40)
    nome: str = Field(default="", max_length=120)
    papel: Papel = "jornalista"
    palavra_passe: str = Field(min_length=1, max_length=512)
    activo: bool = True

    @field_validator("utilizador")
    @classmethod
    def _nome_valido(cls, v: str) -> str:
        v = v.strip().lower()
        if not UTILIZADOR_VALIDO.match(v):
            raise ValueError("utilizador inválido")
        return v


class AlterarUtilizador(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=120)
    papel: Optional[Papel] = None
    activo: Optional[bool] = None
    palavra_passe: Optional[str] = Field(default=None, max_length=512)


class AlterarPlataforma(BaseModel):
    permissoes: Optional[dict[str, list[str]]] = None
    definicoes: Optional[dict[str, Any]] = None


@router.get("/utilizadores")
async def utilizadores(
    request: Request, _: Utilizador = Depends(exigir_permissao("gerir_utilizadores"))
) -> JSONResponse:
    return JSONResponse({"utilizadores": [u.publico() for u in _store(request).listar()]},
                        headers={"Cache-Control": "no-store"})


@router.post("/utilizadores", status_code=201)
async def criar_utilizador(
    corpo: NovoUtilizador,
    request: Request,
    _: Utilizador = Depends(exigir_permissao("gerir_utilizadores")),
) -> JSONResponse:
    lingua = _lingua(request)
    store = _store(request)
    if len(corpo.palavra_passe) < PALAVRA_PASSE_MINIMA:
        raise HTTPException(status_code=422, detail=texto(
            "palavra_passe_curta", lingua, n=PALAVRA_PASSE_MINIMA))
    if store.por_nome(corpo.utilizador) is not None:
        raise HTTPException(status_code=409, detail=texto("utilizador_repetido", lingua))
    try:
        novo = store.criar(corpo.utilizador, corpo.palavra_passe, corpo.papel, corpo.nome,
                           activo=corpo.activo)
    except FalhaAoGravar:
        raise HTTPException(status_code=503, detail=texto("falha_guardar", lingua))
    return JSONResponse(novo.publico(), status_code=201, headers={"Cache-Control": "no-store"})


@router.patch("/utilizadores/{utilizador_id}")
async def alterar_utilizador(
    utilizador_id: str,
    corpo: AlterarUtilizador,
    request: Request,
    actual: Utilizador = Depends(exigir_permissao("gerir_utilizadores")),
) -> JSONResponse:
    lingua = _lingua(request)
    store = _store(request)
    alvo = store.por_id(utilizador_id)
    if alvo is None:
        raise HTTPException(status_code=404, detail=texto("utilizador_ausente", lingua))
    if corpo.palavra_passe is not None and len(corpo.palavra_passe) < PALAVRA_PASSE_MINIMA:
        raise HTTPException(status_code=422, detail=texto(
            "palavra_passe_curta", lingua, n=PALAVRA_PASSE_MINIMA))
    desactiva = corpo.activo is False
    despromove = corpo.papel is not None and corpo.papel != "administrador"
    if alvo.id == actual.id and (desactiva or despromove):
        raise HTTPException(status_code=409, detail=texto("conta_propria", lingua))
    if alvo.papel == "administrador" and alvo.activo and (desactiva or despromove):
        if len(_activos_admin(store)) <= 1:
            raise HTTPException(status_code=409, detail=texto("ultimo_admin", lingua))
    campos = {
        "nome": corpo.nome,
        "papel": corpo.papel,
        "activo": corpo.activo,
        "palavra_passe": corpo.palavra_passe,
    }
    try:
        mudado = store.actualizar(utilizador_id, **campos)
    except KeyError:
        raise HTTPException(status_code=404, detail=texto("utilizador_ausente", lingua))
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro))
    except FalhaAoGravar:
        raise HTTPException(status_code=503, detail=texto("falha_guardar", lingua))
    return JSONResponse(mudado.publico(), headers={"Cache-Control": "no-store"})


@router.delete("/utilizadores/{utilizador_id}", status_code=204)
async def apagar_utilizador(
    utilizador_id: str,
    request: Request,
    actual: Utilizador = Depends(exigir_permissao("gerir_utilizadores")),
) -> Response:
    lingua = _lingua(request)
    store = _store(request)
    alvo = store.por_id(utilizador_id)
    if alvo is None:
        raise HTTPException(status_code=404, detail=texto("utilizador_ausente", lingua))
    if alvo.id == actual.id:
        raise HTTPException(status_code=409, detail=texto("conta_propria_apagar", lingua))
    if alvo.papel == "administrador" and alvo.activo and len(_activos_admin(store)) <= 1:
        raise HTTPException(status_code=409, detail=texto("ultimo_admin", lingua))
    try:
        store.apagar(utilizador_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=texto("utilizador_ausente", lingua))
    except FalhaAoGravar:
        raise HTTPException(status_code=503, detail=texto("falha_guardar", lingua))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/plataforma")
async def plataforma(
    request: Request, _: Utilizador = Depends(exigir_permissao("gerir_plataforma"))
) -> JSONResponse:
    return JSONResponse(request.app.state.plataforma.estado(),
                        headers={"Cache-Control": "no-store"})


@router.patch("/plataforma")
async def alterar_plataforma(
    corpo: AlterarPlataforma,
    request: Request,
    actual: Utilizador = Depends(exigir_permissao("gerir_plataforma")),
) -> JSONResponse:
    lingua = _lingua(request)
    if corpo.permissoes is not None:
        desconhecidas = set(corpo.permissoes) - {"jornalista"}
        invalidas = {p for valores in corpo.permissoes.values() for p in valores} - set(PERMISSOES)
        if desconhecidas or invalidas:
            raise HTTPException(status_code=422, detail=texto("plataforma_invalida", lingua))
        # The administration permissions are never a journalist's to have.
        if set(corpo.permissoes.get("jornalista", [])) - set(PERMISSOES_EDITAVEIS):
            raise HTTPException(status_code=422, detail=texto("plataforma_invalida", lingua))
    if corpo.definicoes is not None:
        try:
            Definicoes.model_validate({**request.app.state.plataforma.definicoes().model_dump(),
                                       **corpo.definicoes})
        except ValueError:
            raise HTTPException(status_code=422, detail=texto("plataforma_invalida", lingua))
    try:
        estado = request.app.state.plataforma.actualizar(
            corpo.permissoes.get("jornalista") if corpo.permissoes is not None else None,
            corpo.definicoes,
            autor=actual.id,
        )
    except FalhaAoGravar:
        raise HTTPException(status_code=503, detail=texto("falha_guardar", lingua))
    return JSONResponse(estado, headers={"Cache-Control": "no-store"})
