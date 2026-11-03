"""Run documents: only the session that asked for the run may read them."""

from datetime import date

import pytest

from app.schemas import ClaimInput, EvidenceDocument, RunResult
from conftest import entrar


class FilaFalsa:
    """Stands in for Redis: the first session to ask for a run becomes its owner."""

    def __init__(self) -> None:
        self.donos: dict[str, str] = {}
        self.consultas: list[tuple[str, str]] = []

    async def e_dono(self, run_id: str, quem: str, utilizador_id: str | None = None) -> bool:
        self.consultas.append((run_id, quem))
        return self.donos.setdefault(run_id, quem) == quem

    async def aclose(self) -> None:
        pass


class StoreFalso:
    def __init__(self, resultado: RunResult) -> None:
        self.resultado = resultado

    def get(self, run_id: str) -> RunResult | None:
        return self.resultado if run_id == self.resultado.run_id else None

    def guardada(self, run_id: str) -> RunResult | None:
        return None


@pytest.fixture
def sessao(cliente):
    assert entrar(cliente).status_code == 204
    return cliente


@pytest.fixture
def resultado() -> RunResult:
    return RunResult(
        run_id="abc123def456",
        input=ClaimInput(claim="Uma claim suficientemente longa", claim_date=date(2025, 1, 2)),
        stages=[],
        documents=[
            EvidenceDocument(
                doc_id="doc-1",
                headline="Título da notícia",
                published_at="2025-01-02",
                content="O texto da notícia.",
            )
        ],
    )


def test_document_is_read_only_by_the_session_that_asked_for_the_run(sessao, resultado):
    fila = FilaFalsa()
    sessao.app.state.fila = fila
    sessao.app.state.runs = StoreFalso(resultado)
    url = f"/api/runs/{resultado.run_id}/documents/doc-1"

    # Another session owns it: the run does not exist for this one.
    fila.donos[resultado.run_id] = "outra-sessao"
    assert sessao.get(url).status_code == 404
    assert fila.consultas[-1][0] == resultado.run_id
    assert fila.consultas[-1][1] != "outra-sessao"

    # This session asks for a run it owns.
    del fila.donos[resultado.run_id]
    resposta = sessao.get(url)
    assert resposta.status_code == 200
    assert resposta.json()["doc_id"] == "doc-1"
    assert resposta.json()["content"] == "O texto da notícia."

    # A new sign-in is a new session: the same run no longer exists for it.
    assert entrar(sessao).status_code == 204
    assert sessao.get(url).status_code == 404


def test_owner_still_gets_404_for_a_document_outside_the_run(sessao, resultado):
    sessao.app.state.fila = FilaFalsa()
    sessao.app.state.runs = StoreFalso(resultado)

    resposta = sessao.get(f"/api/runs/{resultado.run_id}/documents/outro")
    assert resposta.status_code == 404


def test_invalid_run_id_is_refused_without_asking_the_owner(sessao, resultado):
    fila = FilaFalsa()
    sessao.app.state.fila = fila
    sessao.app.state.runs = StoreFalso(resultado)

    assert sessao.get("/api/runs/nao-um-id/documents/doc-1").status_code == 404
    assert fila.consultas == []
