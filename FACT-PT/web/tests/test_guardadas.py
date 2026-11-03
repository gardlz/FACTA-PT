"""Finished verifications: kept when a run ends, opened again from their address."""

import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.fila import correr
from app.guardadas import eventos
from app.runstore import RunStore
from app.schemas import (
    STAGE_LABELS,
    STAGE_ORDER,
    ClaimInput,
    EvidenceDocument,
    ExcerptStance,
    Question,
    RunResult,
    StageReport,
)
from app.settings import Settings
from conftest import entrar


def execucao(run_id: str = "abc123def456", **estados: str) -> RunResult:
    """A run whose stages all ended `done`, except those `estados` names."""
    etapas = [StageReport(name=n, label=STAGE_LABELS[n], status=estados.get(n, "done"),
                          provenance="model") for n in STAGE_ORDER]
    return RunResult(
        run_id=run_id,
        input=ClaimInput(claim="Uma claim suficientemente longa", claim_date=date(2025, 1, 2)),
        stages=etapas,
        questions=[Question(id="q1", index=1, text="Uma pergunta?")],
        documents=[EvidenceDocument(doc_id="d1", headline="Título", published_at="2025-01-01",
                                    relevant=True, content="Texto.")],
        stances=[ExcerptStance(excerpt_id="d1-supported", label="supported")],
        decisive_excerpt_ids=["d1-supported"],
    )


def test_the_events_rebuild_the_run_stage_by_stage():
    lista = eventos(execucao())
    assert lista[0]["type"] == "start" and lista[0]["run_id"] == "abc123def456"
    assert lista[-1] == {"type": "done"}
    etapas = [e["stage"]["name"] for e in lista if e["type"] == "stage"]
    assert etapas == list(STAGE_ORDER)
    por_etapa = {e["stage"]["name"]: e for e in lista if e["type"] == "stage"}
    assert por_etapa["questions"]["questions"][0]["text"] == "Uma pergunta?"
    # The timeline fills with everything retrieved before the relevance stage narrows it.
    assert por_etapa["dedup"]["documents"][0]["relevant"] is None
    assert por_etapa["relevance"]["documents"][0]["relevant"] is True
    assert "content" not in por_etapa["relevance"]["documents"][0]
    assert por_etapa["stance"]["decisive"] == ["d1-supported"]


def test_a_stage_that_did_not_finish_carries_no_data():
    lista = eventos(execucao(article="skipped", stance="error"))
    por_etapa = {e["stage"]["name"]: e for e in lista if e["type"] == "stage"}
    assert por_etapa["article"]["stage"]["status"] == "skipped"
    assert "articles" not in por_etapa["article"]
    assert "stances" not in por_etapa["stance"]


# ---- The run keeps its verification ---------------------------------------------------------

class RedisFalso:
    def __init__(self) -> None:
        self.chaves: dict[str, str] = {}

    async def set(self, chave, valor, nx=False, ex=None, get=False):
        if nx and chave in self.chaves:
            return None
        self.chaves[chave] = valor
        return True

    async def exists(self, chave):
        return int(chave in self.chaves)

    async def xadd(self, *_):
        pass

    async def expire(self, *_):
        pass


class CorredorFalso:
    def __init__(self, *lista: dict) -> None:
        self.lista = lista

    async def run(self, payload, run_id):
        for evento in self.lista:
            yield evento


def correr_com(tmp_path, *lista: dict) -> RunStore:
    redis = RedisFalso()
    redis.chaves["facta-pt:execucao:abc123def456:visto"] = "1"
    store = RunStore(8, tmp_path)
    entrada = ClaimInput(claim="Uma claim suficientemente longa", claim_date=date(2025, 1, 2))
    asyncio.run(correr(Settings(), redis, CorredorFalso(*lista), store, entrada, "pt",
                       "abc123def456"))
    return store


def test_a_run_that_finishes_is_kept(tmp_path):
    evento = {"type": "done", "result": execucao().model_dump(mode="json")}
    store = correr_com(tmp_path, evento)
    assert store.guardada("abc123def456") is not None
    assert evento["guardada"] is True


def test_a_run_that_fails_is_not_kept(tmp_path):
    resultado = execucao(article="error")
    resultado.error = "falhou"
    evento = {"type": "error", "message": "falhou", "result": resultado.model_dump(mode="json")}
    store = correr_com(tmp_path, evento)
    assert store.get("abc123def456") is not None
    assert store.guardada("abc123def456") is None
    assert "guardada" not in evento


def test_a_run_by_a_writer_no_longer_offered_still_opens():
    """Runs saved while the Ollama writer was offered keep loading after it was retired."""
    guardada = execucao().model_dump(mode="json")
    guardada["input"]["redator"] = "amalia_q4"
    assert RunResult.model_validate(guardada).input.redator == "amalia_q4"
    with pytest.raises(ValueError):
        ClaimInput(claim="Uma claim suficientemente longa", claim_date=date(2025, 1, 2),
                   redator="outro")


def test_a_retired_writer_left_in_the_env_is_dropped_not_refused():
    assert Settings(article_writers="gemma,amalia,amalia_q4").redatores == ["gemma", "amalia"]


def test_a_worked_example_is_not_kept(tmp_path):
    resultado = execucao()
    for etapa in resultado.stages:
        etapa.provenance = "exemplo"
    evento = {"type": "done", "result": resultado.model_dump(mode="json")}
    store = correr_com(tmp_path, evento)
    assert store.guardada("abc123def456") is None
    assert "guardada" not in evento


# ---- The routes -----------------------------------------------------------------------------

class FilaFalsa:
    def __init__(self) -> None:
        self.dono: str | None = "outra-sessao"
        self.consultas = 0

    async def e_dono(self, run_id: str, quem: str, utilizador_id: str | None = None) -> bool:
        self.consultas += 1
        return self.dono == quem

    async def aclose(self) -> None:
        pass


@pytest.fixture
def cliente(dados):
    from app.main import create_app

    with TestClient(create_app(), base_url="http://testserver") as c:
        assert entrar(c).status_code == 204
        c.app.state.runs = RunStore(8, dados)
        c.app.state.fila = FilaFalsa()
        yield c


def test_a_kept_verification_opens_for_any_signed_in_session(cliente):
    cliente.app.state.runs.guardar(execucao())
    resposta = cliente.get("/api/verificacoes/abc123def456")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["input"]["claim"] == "Uma claim suficientemente longa"
    assert corpo["guardada_em"]
    assert corpo["eventos"][0]["type"] == "start" and corpo["eventos"][-1]["type"] == "done"
    # Nobody's ownership was asked for: the address is what is shared.
    assert cliente.app.state.fila.consultas == 0


def test_a_run_not_kept_has_no_address(cliente):
    cliente.app.state.runs.put(execucao())
    assert cliente.get("/api/verificacoes/abc123def456").status_code == 404
    assert cliente.get("/api/verificacoes/ffffffffffff").status_code == 404
    assert cliente.get("/api/verificacoes/nao-um-id").status_code == 404


def test_a_citation_of_a_kept_verification_opens_for_whoever_has_its_address(cliente):
    cliente.app.state.runs.guardar(execucao())
    resposta = cliente.get("/api/runs/abc123def456/documents/d1")
    assert resposta.status_code == 200 and resposta.json()["content"] == "Texto."


def test_a_run_under_way_still_belongs_to_who_asked_for_it(cliente):
    cliente.app.state.runs.put(execucao())
    assert cliente.get("/api/runs/abc123def456/documents/d1").status_code == 404
    assert cliente.app.state.fila.consultas == 1
