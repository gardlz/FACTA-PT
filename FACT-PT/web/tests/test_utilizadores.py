"""Accounts: creation, password changes, session generations and the bootstrap administrator."""

import json

import pytest

from app.settings import Settings
from app.utilizadores import UserStore, gerar_hash

PALAVRA_PASSE = "uma frase longa e correta"


def test_create_and_read_back(tmp_path):
    store = UserStore(tmp_path / "utilizadores.json")
    novo = store.criar("Ana.Silva", PALAVRA_PASSE, "jornalista", "Ana Silva")
    assert novo.utilizador == "ana.silva" and novo.papel == "jornalista"
    assert "palavra_passe" not in novo.publico()
    assert UserStore(tmp_path / "utilizadores.json").por_nome("ANA.SILVA").id == novo.id


def test_a_repeated_name_is_refused(tmp_path):
    store = UserStore(tmp_path / "utilizadores.json")
    store.criar("ana", PALAVRA_PASSE)
    with pytest.raises(ValueError):
        store.criar("ana", PALAVRA_PASSE)


@pytest.mark.parametrize("nome", ["ab", "Ana Silva", "-ana", "a" * 41])
def test_an_invalid_name_is_refused(tmp_path, nome):
    with pytest.raises(ValueError):
        UserStore(tmp_path / "utilizadores.json").criar(nome, PALAVRA_PASSE)


def test_a_short_password_is_refused(tmp_path):
    with pytest.raises(ValueError):
        UserStore(tmp_path / "utilizadores.json").criar("ana", "curta")


def test_changing_a_password_bumps_the_session_generation(tmp_path):
    store = UserStore(tmp_path / "utilizadores.json")
    novo = store.criar("ana", PALAVRA_PASSE)
    mudado = store.actualizar(novo.id, palavra_passe="outra frase longa")
    assert mudado.versao_sessao == novo.versao_sessao + 1


def test_deactivating_bumps_the_session_generation_and_reactivating_does_not(tmp_path):
    store = UserStore(tmp_path / "utilizadores.json")
    novo = store.criar("ana", PALAVRA_PASSE)
    desactivado = store.actualizar(novo.id, activo=False)
    assert desactivado.activo is False and desactivado.versao_sessao == novo.versao_sessao + 1
    reactivado = store.actualizar(novo.id, activo=True)
    assert reactivado.activo is True and reactivado.versao_sessao == desactivado.versao_sessao


def test_deleting_removes_only_that_account_and_frees_its_name(tmp_path):
    store = UserStore(tmp_path / "utilizadores.json")
    ana = store.criar("ana", PALAVRA_PASSE)
    rui = store.criar("rui", PALAVRA_PASSE)
    store.apagar(ana.id)
    assert store.por_id(ana.id) is None and store.por_id(rui.id) is not None
    with pytest.raises(KeyError):
        store.apagar(ana.id)
    assert store.criar("ana", PALAVRA_PASSE).id != ana.id


def test_every_write_keeps_the_previous_file(tmp_path):
    caminho = tmp_path / "utilizadores.json"
    store = UserStore(caminho)
    novo = store.criar("ana", PALAVRA_PASSE)
    store.actualizar(novo.id, nome="Ana Silva")
    anterior = json.loads((tmp_path / "utilizadores.bak.json").read_text(encoding="utf-8"))
    assert anterior["utilizadores"][0]["nome"] == "ana"


def test_the_bootstrap_administrator_is_made_once(tmp_path):
    definicoes = Settings(ADMIN_USERNAME="chefe",
                          ADMIN_PASSWORD_HASH=gerar_hash(PALAVRA_PASSE))
    store = UserStore(tmp_path / "utilizadores.json")
    assert store.garantir_admin(definicoes).papel == "administrador"
    assert store.por_nome("chefe") is not None
    assert store.garantir_admin(definicoes) is None


def test_without_a_hash_no_administrator_is_made(tmp_path):
    from app.utilizadores import UtilizadoresMalConfigurados

    with pytest.raises(UtilizadoresMalConfigurados):
        UserStore(tmp_path / "utilizadores.json").garantir_admin(Settings())
