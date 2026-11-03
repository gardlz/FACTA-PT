"""A site of its own for each test: accounts and platform settings in a temporary folder, and an
administrator made at startup from `ADMIN_PASSWORD_HASH`."""

import pytest
from fastapi.testclient import TestClient

from app import acesso
from app.settings import get_settings

PALAVRA_PASSE = "uma frase longa e correta"
SEGREDO = "s" * 48


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_STORE_DIR", str(tmp_path / "execucoes"))
    monkeypatch.setenv("UTILIZADORES_FILE", str(tmp_path / "utilizadores.json"))
    monkeypatch.setenv("PLATAFORMA_FILE", str(tmp_path / "plataforma.json"))
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", acesso.gerar_hash(PALAVRA_PASSE))
    monkeypatch.delenv("ACCESS_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("SESSION_SECRET", SEGREDO)
    monkeypatch.setenv("COOKIE_SECURE", "false")  # TestClient talks plain HTTP
    get_settings.cache_clear()
    acesso._limitador = acesso.Limitador()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def cliente(dados):
    from app.main import create_app

    with TestClient(create_app(), base_url="http://testserver") as c:
        yield c


def entrar(cliente, utilizador="admin", palavra_passe=PALAVRA_PASSE, **cabecalhos):
    return cliente.post(
        "/api/sessao",
        json={"utilizador": utilizador, "palavra_passe": palavra_passe},
        headers=cabecalhos,
    )


def sair(cliente):
    assert cliente.delete("/api/sessao").status_code == 204
    cliente.cookies.clear()


@pytest.fixture
def admin(cliente):
    assert entrar(cliente).status_code == 204
    return cliente


def criar_utilizador(cliente, utilizador, papel="jornalista", palavra_passe=PALAVRA_PASSE):
    resposta = cliente.post(
        "/api/admin/utilizadores",
        json={"utilizador": utilizador, "papel": papel, "nome": utilizador.title(),
              "palavra_passe": palavra_passe},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@pytest.fixture
def jornalista(admin):
    criar_utilizador(admin, "ana", "jornalista")
    sair(admin)
    assert entrar(admin, "ana").status_code == 204
    return admin
