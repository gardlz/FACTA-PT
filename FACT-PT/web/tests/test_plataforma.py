"""Platform settings: the role matrix and the defaults an administrator may change."""

import pytest

from app.plataforma import PERMISSOES, PlatformStore


def test_the_default_matrix(tmp_path):
    store = PlatformStore(tmp_path / "plataforma.json")
    assert "editar_resultados" in store.permissoes("jornalista")
    assert set(store.permissoes("administrador")) == set(PERMISSOES)


def test_the_journalist_row_is_editable(tmp_path):
    store = PlatformStore(tmp_path / "plataforma.json")
    estado = store.actualizar(["ver_resultados", "editar_resultados"], autor="x")
    assert estado["permissoes"]["jornalista"] == ["ver_resultados", "editar_resultados"]
    assert estado["actualizado_por"] == "x"


def test_the_administration_permissions_are_never_a_journalist_s(tmp_path):
    store = PlatformStore(tmp_path / "plataforma.json")
    estado = store.actualizar(["ver_resultados", "gerir_utilizadores", "inventada"])
    assert estado["permissoes"]["jornalista"] == ["ver_resultados"]
    assert set(estado["permissoes"]["administrador"]) == set(PERMISSOES)


def test_an_invalid_default_is_refused(tmp_path):
    store = PlatformStore(tmp_path / "plataforma.json")
    with pytest.raises(ValueError):
        store.actualizar(definicoes={"top_k_omissao": 7})
    with pytest.raises(ValueError):
        store.actualizar(definicoes={"redator_omissao": "outro"})


def test_the_defaults_are_read_back(tmp_path):
    store = PlatformStore(tmp_path / "plataforma.json")
    store.actualizar(definicoes={"top_k_omissao": 10})
    definicoes = PlatformStore(tmp_path / "plataforma.json").definicoes()
    assert definicoes.top_k_omissao == 10


def test_a_permission_is_checked_with_the_role(tmp_path):
    store = PlatformStore(tmp_path / "plataforma.json")

    class U:
        papel = "jornalista"
        activo = True

    assert store.pode(U(), "editar_resultados")
    assert not store.pode(U(), "gerir_plataforma")
    store.actualizar(["ver_resultados"])
    assert not store.pode(U(), "editar_resultados")
