"""Runs in the background: an account with `segundo_plano` may leave its run and open it again,
from any session."""

import pytest

from conftest import entrar, sair

RUN_ID = "abc123def456"


class FilaFalsa:
    """Stands in for Redis: one run in the background, of the account `conta`."""

    def __init__(self, conta: str | None = None, estado: str = "em-curso") -> None:
        self.conta = conta
        self.estado = estado
        self.donos: dict[str, str] = {}
        self.pedidos: list[tuple] = []
        self.retiradas: list[str] = []
        self.recusa: str | None = None

    async def e_dono(self, run_id, quem, utilizador_id=None):
        return self.donos.get(run_id) == quem or (
            bool(utilizador_id) and utilizador_id == self.conta)

    async def execucao(self, run_id):
        if run_id != RUN_ID:
            return None
        return {"run_id": RUN_ID, "claim": "Uma claim", "claim_date": "2025-01-02",
                "context": "", "pedida_em": "2026-10-28T10:00:00+00:00",
                "top_k": 5, "redator": "gemma",
                "estado": self.estado, "frente": None}

    async def execucoes(self, utilizador_id):
        return [await self.execucao(RUN_ID)] if utilizador_id == self.conta else []

    async def existe(self, run_id):
        return run_id == RUN_ID

    async def ler(self, run_id, lingua, desde="0"):
        yield 'data: {"type": "fim"}\n\n'

    async def por_na_fila(self, payload, lingua, run_id, quem, endereco, limite_sessao=None,
                          conta=None):
        if self.recusa is None:
            self.pedidos.append((payload, run_id, conta))
        return self.recusa

    async def retirar_da_conta(self, run_id, utilizador_id):
        self.retiradas.append(run_id)

    async def aclose(self):
        pass


def _id(cliente, utilizador):
    return next(u["id"] for u in cliente.get("/api/admin/utilizadores").json()["utilizadores"]
                if u["utilizador"] == utilizador)


@pytest.fixture
def contas(admin):
    """Ana, a journalist whose run is under way."""
    from conftest import criar_utilizador

    criar_utilizador(admin, "ana", "jornalista")
    admin.app.state.fila = FilaFalsa(_id(admin, "ana"))
    sair(admin)
    return admin


def test_the_account_lists_and_opens_its_run_from_another_session(contas):
    assert entrar(contas, "ana").status_code == 204
    lista = contas.get("/api/execucoes").json()["execucoes"]
    assert [e["run_id"] for e in lista] == [RUN_ID]
    assert lista[0]["guardada"] is False
    # A new session, the same account: the run is still its own.
    assert contas.get(f"/api/execucoes/{RUN_ID}").json()["claim"] == "Uma claim"
    assert contas.get(f"/api/runs/{RUN_ID}/eventos").status_code == 200


def test_another_account_does_not_see_the_run(contas):
    assert entrar(contas, "admin").status_code == 204
    assert contas.get("/api/execucoes").json()["execucoes"] == []
    assert contas.get(f"/api/execucoes/{RUN_ID}").status_code == 404
    assert contas.get(f"/api/runs/{RUN_ID}/eventos").status_code == 404


@pytest.mark.parametrize("estado", ["terminada", "perdida"])
def test_a_stopped_run_is_asked_for_again_in_place_of_the_old_one(contas, estado):
    fila = contas.app.state.fila
    fila.estado = estado
    assert entrar(contas, "ana").status_code == 204
    resposta = contas.post(f"/api/execucoes/{RUN_ID}/reiniciar", json={})
    assert resposta.status_code == 200
    (payload, novo, conta), = fila.pedidos
    assert resposta.json()["run_id"] == novo != RUN_ID
    assert (payload.claim, str(payload.claim_date), payload.top_k) == ("Uma claim", "2025-01-02", 5)
    assert conta
    assert fila.retiradas == [RUN_ID]


@pytest.mark.parametrize("estado", ["na-fila", "em-curso"])
def test_a_run_still_going_is_not_restarted(contas, estado):
    fila = contas.app.state.fila
    fila.estado = estado
    assert entrar(contas, "ana").status_code == 204
    assert contas.post(f"/api/execucoes/{RUN_ID}/reiniciar", json={}).status_code == 409
    assert fila.pedidos == [] and fila.retiradas == []


def test_only_the_account_restarts_its_run(contas):
    contas.app.state.fila.estado = "perdida"
    assert entrar(contas, "admin").status_code == 204
    assert contas.post(f"/api/execucoes/{RUN_ID}/reiniciar", json={}).status_code == 404


def test_a_refused_restart_keeps_the_old_run(contas):
    fila = contas.app.state.fila
    fila.estado, fila.recusa = "perdida", "fila"
    assert entrar(contas, "ana").status_code == 204
    assert contas.post(f"/api/execucoes/{RUN_ID}/reiniciar", json={}).status_code == 503
    assert fila.retiradas == []
