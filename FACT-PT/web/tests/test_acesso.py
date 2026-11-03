"""Sign-in: accounts, sessions, roles, throttling, and that nothing is served without a session."""

import time

import pytest

from app import acesso
from app.settings import get_settings
from conftest import PALAVRA_PASSE, SEGREDO, criar_utilizador, entrar, sair


def test_api_is_closed_without_session(cliente):
    assert cliente.get("/api/exemplos").status_code == 401
    assert cliente.get("/api/health").status_code == 401
    assert cliente.post("/api/run", json={}).status_code == 401
    assert cliente.get("/api/runs/x/documents/y").status_code == 401
    assert cliente.get("/api/verificacoes/x/revisao").status_code == 401
    # No API documentation either.
    assert cliente.get("/api/docs").status_code == 404
    assert cliente.get("/api/openapi.json").status_code == 404


def test_state_is_public_and_not_cached(cliente):
    r = cliente.get("/api/sessao")
    assert r.status_code == 200
    assert r.json()["autenticada"] is False and r.json()["utilizador"] is None
    assert r.headers["cache-control"] == "no-store"


def test_wrong_password_is_refused(cliente):
    r = entrar(cliente, "admin", "errada")
    assert r.status_code == 401
    assert "set-cookie" not in r.headers


def test_an_unknown_account_is_refused_with_the_same_answer(cliente):
    assert entrar(cliente, "ninguem").status_code == 401
    assert entrar(cliente, "ninguem").json()["detail"] == \
        entrar(cliente, "admin", "errada").json()["detail"]


def test_the_old_shared_password_no_longer_signs_in(cliente):
    # The hash bootstrapped the admin, but it is not a password of its own any more.
    assert entrar(cliente, "admin", PALAVRA_PASSE).status_code == 204


def test_sign_in_opens_the_api_and_cookie_is_hardened(cliente):
    r = entrar(cliente)
    assert r.status_code == 204
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    estado = cliente.get("/api/sessao").json()
    assert estado["autenticada"] is True
    assert estado["utilizador"]["utilizador"] == "admin"
    assert estado["utilizador"]["papel"] == "administrador"
    assert "palavra_passe_hash" not in estado["utilizador"]
    assert set(estado["permissoes"]) >= {"editar_resultados", "gerir_utilizadores"}
    assert cliente.get("/api/exemplos").status_code == 200


def test_secure_cookie_uses_host_prefix(cliente, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    r = entrar(cliente)
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("__Host-facta_sessao=") and "Secure" in cookie


def test_sign_out_clears_session(cliente):
    entrar(cliente)
    sair(cliente)
    assert cliente.get("/api/exemplos").status_code == 401


def test_tampered_expired_and_foreign_tokens_are_refused(cliente):
    definicoes = get_settings()
    admin = cliente.app.state.utilizadores.por_nome("admin")
    token = acesso.criar_sessao(definicoes, admin)
    assert acesso.sessao_valida(token, definicoes)
    carga, _, assinatura = token.rpartition(".")
    assert not acesso.sessao_valida(carga + "." + "A" * len(assinatura), definicoes)
    assert not acesso.sessao_valida(token + "x", definicoes)
    assert not acesso.sessao_valida(token.replace("v2.", "v2.9", 1), definicoes)
    assert not acesso.sessao_valida("não-ascii.é.é.é", definicoes)
    assert not acesso.sessao_valida("", definicoes) and not acesso.sessao_valida(None, definicoes)
    futuro = definicoes.session_hours * 3600 + 5
    assert not acesso.sessao_valida(token, definicoes, agora=time.time() + futuro)
    cliente.cookies.set("facta_sessao", "v2.9999999999.abc.1.def.@@@")
    assert cliente.get("/api/exemplos").status_code == 401  # and no 500


def test_changing_the_secret_signs_everyone_out(cliente, monkeypatch):
    definicoes = get_settings()
    token = acesso.criar_sessao(definicoes, cliente.app.state.utilizadores.por_nome("admin"))
    monkeypatch.setenv("SESSION_SECRET", "t" * 48)
    get_settings.cache_clear()
    assert not acesso.sessao_valida(token, get_settings())
    monkeypatch.setenv("SESSION_SECRET", SEGREDO)
    get_settings.cache_clear()
    assert acesso.sessao_valida(token, get_settings())


def test_changing_a_password_ends_only_that_account_s_sessions(admin):
    criar_utilizador(admin, "ana")
    sair(admin)
    assert entrar(admin, "ana").status_code == 204
    token_ana = admin.cookies.get("facta_sessao")
    # Back as the administrator, reset the journalist's password.
    assert entrar(admin, "admin").status_code == 204
    ana = admin.app.state.utilizadores.por_nome("ana")
    assert admin.patch(f"/api/admin/utilizadores/{ana.id}",
                       json={"palavra_passe": "outra frase longa"}).status_code == 200
    # The administrator is still signed in; the journalist's old token is not.
    assert admin.get("/api/exemplos").status_code == 200
    admin.cookies.set("facta_sessao", token_ana)
    assert admin.get("/api/exemplos").status_code == 401


def test_a_deactivated_account_cannot_sign_in_and_loses_its_session(admin):
    utilizador = criar_utilizador(admin, "ana")
    sair(admin)
    assert entrar(admin, "ana").status_code == 204
    token = admin.cookies.get("facta_sessao")
    assert entrar(admin, "admin").status_code == 204
    assert admin.patch(f"/api/admin/utilizadores/{utilizador['id']}",
                       json={"activo": False}).status_code == 200
    admin.cookies.set("facta_sessao", token)
    assert admin.get("/api/exemplos").status_code == 401
    sair(admin)
    assert entrar(admin, "ana").status_code == 401


def test_a_deleted_account_cannot_sign_in_and_loses_its_session(admin):
    utilizador = criar_utilizador(admin, "ana")
    sair(admin)
    assert entrar(admin, "ana").status_code == 204
    token = admin.cookies.get("facta_sessao")
    assert entrar(admin, "admin").status_code == 204
    assert admin.delete(f"/api/admin/utilizadores/{utilizador['id']}").status_code == 204
    assert admin.delete(f"/api/admin/utilizadores/{utilizador['id']}").status_code == 404
    admin.cookies.set("facta_sessao", token)
    assert admin.get("/api/exemplos").status_code == 401
    sair(admin)
    assert entrar(admin, "ana").status_code == 401


def test_nobody_deletes_their_own_account(admin):
    proprio = admin.app.state.utilizadores.por_nome("admin")
    assert admin.delete(f"/api/admin/utilizadores/{proprio.id}").status_code == 409
    assert admin.app.state.utilizadores.por_id(proprio.id) is not None


def test_only_an_administrator_deletes_accounts(admin):
    criar_utilizador(admin, "ana", "jornalista")
    proprio = admin.app.state.utilizadores.por_nome("admin")
    sair(admin)
    entrar(admin, "ana")
    assert admin.delete(f"/api/admin/utilizadores/{proprio.id}").status_code == 403
    assert admin.app.state.utilizadores.por_id(proprio.id) is not None


def test_a_role_change_applies_on_the_next_request(admin):
    criar_utilizador(admin, "ana", "jornalista")
    ana = admin.app.state.utilizadores.por_nome("ana")
    sair(admin)
    entrar(admin, "ana")
    assert admin.get("/api/admin/utilizadores").status_code == 403
    sair(admin)
    entrar(admin, "admin")
    assert admin.patch(f"/api/admin/utilizadores/{ana.id}",
                       json={"papel": "administrador"}).status_code == 200
    sair(admin)
    entrar(admin, "ana")
    assert admin.get("/api/admin/utilizadores").status_code == 200


def test_failures_are_throttled(cliente):
    for _ in range(get_settings().login_max_failures):
        assert entrar(cliente, "admin", "errada").status_code == 401
    r = entrar(cliente)  # even the right one waits
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_window_expires():
    definicoes = get_settings()
    limitador = acesso.Limitador()
    for i in range(definicoes.login_max_failures):
        limitador.falhou("1.2.3.4", agora=100.0 + i)
    assert limitador.espera("1.2.3.4", definicoes, agora=110.0) > 0
    assert limitador.espera("1.2.3.4", definicoes, agora=100.0 + definicoes.login_window + 10) == 0
    assert limitador.espera("9.9.9.9", definicoes, agora=110.0) == 0


def test_cross_site_post_is_refused(cliente):
    entrar(cliente)
    r = cliente.post("/api/run", json={}, headers={"Origin": "https://mau.example"})
    assert r.status_code == 403
    r = entrar(cliente, Origin="https://mau.example")
    assert r.status_code == 403
    assert entrar(cliente, Origin="http://testserver").status_code == 204


def test_oversized_password_is_rejected_before_hashing(cliente):
    assert entrar(cliente, "admin", "x" * 10_000).status_code == 422


def test_security_headers(cliente):
    h = cliente.get("/api/sessao").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"


def test_refuses_to_start_unconfigured(dados, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "")
    monkeypatch.delenv("ACCESS_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "")
    monkeypatch.delenv("ACCESS_GATE_DISABLED", raising=False)
    get_settings.cache_clear()
    with pytest.raises(acesso.AcessoMalConfigurado):
        acesso.validar_configuracao(get_settings())
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "plaintext")
    monkeypatch.setenv("SESSION_SECRET", SEGREDO)
    get_settings.cache_clear()
    with pytest.raises(acesso.AcessoMalConfigurado):
        acesso.validar_configuracao(get_settings())
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", acesso.gerar_hash("x"))
    monkeypatch.setenv("SESSION_SECRET", "curto")
    get_settings.cache_clear()
    with pytest.raises(acesso.AcessoMalConfigurado):
        acesso.validar_configuracao(get_settings())


def test_the_old_shared_hash_bootstraps_the_first_admin(dados, monkeypatch):
    """A deployment that only has ACCESS_PASSWORD_HASH still starts: it signs in once as the
    administrator and makes the real accounts."""
    from app.utilizadores import UserStore

    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("ACCESS_PASSWORD_HASH", acesso.gerar_hash(PALAVRA_PASSE))
    monkeypatch.setenv("SESSION_SECRET", SEGREDO)
    get_settings.cache_clear()
    definicoes = get_settings()
    store = UserStore(definicoes.utilizadores_path)
    acesso.validar_configuracao(definicoes, store)
    assert store.garantir_admin(definicoes) is not None
    assert store.por_nome("admin").papel == "administrador"
    # A second start does not make another one.
    assert store.garantir_admin(definicoes) is None
