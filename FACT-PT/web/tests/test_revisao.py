"""Editorial review: the automated result is kept apart, every save is one version of the draft
(relevance, passages, verdict and article), and only an editor may change anything."""

from datetime import date

import pytest

from app import trabalhador
from app.revisao import Autor, RevisaoEstado, passagens_revistas
from app.runstore import RunStore
from app.schemas import (
    Article,
    ArticleBlock,
    Citation,
    ClaimInput,
    EvidenceDocument,
    Excerpt,
    ExcerptStance,
    RunResult,
)
from conftest import criar_utilizador, entrar, sair

RUN_ID = "abc123def456"
CONTEUDO_1 = "O Governo anunciou hoje a medida."
CONTEUDO_2 = "A oposição discorda da medida."


def execucao(run_id: str = RUN_ID) -> RunResult:
    return RunResult(
        run_id=run_id,
        input=ClaimInput(claim="Uma claim suficientemente longa", claim_date=date(2025, 1, 2)),
        stages=[],
        documents=[
            EvidenceDocument(
                doc_id="d1", headline="Governo anuncia", published_at="2025-01-01", relevant=True,
                content=CONTEUDO_1,
                excerpts=[Excerpt(id="d1-0", doc_id="d1", begin=0, end=len(CONTEUDO_1),
                                  text=CONTEUDO_1)],
            ),
            EvidenceDocument(
                doc_id="d2", headline="Oposição discorda", published_at="2025-01-02", relevant=True,
                content=CONTEUDO_2,
                excerpts=[Excerpt(id="d2-0", doc_id="d2", begin=0, end=len(CONTEUDO_2),
                                  text=CONTEUDO_2)],
            ),
        ],
        stances=[ExcerptStance(excerpt_id="d1-0", label="supported"),
                 ExcerptStance(excerpt_id="d2-0", label="refuted")],
        decisive_excerpt_ids=["d1-0", "d2-0"],
        articles=[Article(
            model="gemma", title="A medida", lead="A medida foi anunciada. [[C:1:d1-0]] "
                                                 "A oposição discorda. [[C:2:d2-0]]",
            blocks=[ArticleBlock(type="paragraph", text="A medida foi anunciada.")],
            citations=[
                Citation(marker="1", excerpt_id="d1-0", doc_id="d1", headline="Governo anuncia",
                         published_at="2025-01-01", label="supported",
                         excerpt_text=CONTEUDO_1, begin=0, end=len(CONTEUDO_1)),
                Citation(marker="2", excerpt_id="d2-0", doc_id="d2", headline="Oposição discorda",
                         published_at="2025-01-02", label="refuted",
                         excerpt_text=CONTEUDO_2, begin=0, end=len(CONTEUDO_2)),
            ],
        )],
    )


class FilaFalsa:
    """Stands in for Redis: records the rewrites asked for."""

    def __init__(self):
        self.pedidos = []

    async def enfileirar_artigo(self, run_id, versao, autor, redator, quem):
        self.pedidos.append((run_id, versao, autor, redator, quem))
        return "job-1"

    async def aclose(self):
        pass


@pytest.fixture
def verificacao(jornalista, dados):
    store = RunStore(8, dados / "execucoes")
    assert store.guardar(execucao())
    jornalista.app.state.runs = store
    jornalista.app.state.fila = FilaFalsa()
    return jornalista


def revisao(cliente):
    resposta = cliente.get(f"/api/verificacoes/{RUN_ID}/revisao")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def guardar(cliente, estado, versao, restaurada_de=None):
    corpo = {"versao": versao, "estado": estado}
    if restaurada_de is not None:
        corpo["restaurada_de"] = restaurada_de
    return cliente.patch(f"/api/verificacoes/{RUN_ID}/revisao", json=corpo)


def versao_guardada(cliente, versao):
    resposta = cliente.get(f"/api/verificacoes/{RUN_ID}/revisao/versoes/{versao}")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["estado"]


def com_excerto(estado, excerto_id, **campos):
    """The state with one passage changed, as the page sends it."""
    return {
        **estado,
        "excertos": [
            {**excerto, **campos} if excerto["id"] == excerto_id else excerto
            for excerto in estado["excertos"]
        ],
    }


def com_documento(estado, doc_id, relevante):
    return {
        **estado,
        "documentos": [
            {**documento, "relevante": relevante} if documento["doc_id"] == doc_id else documento
            for documento in estado["documentos"]
        ],
    }


def test_the_automated_evidence_is_the_first_version(verificacao):
    corpo = revisao(verificacao)
    assert corpo["versao"] == 0 and corpo["historico"] == []
    assert corpo["original"] == corpo["actual"]
    original = corpo["original"]
    assert [(d["doc_id"], d["relevante"]) for d in original["documentos"]] == [
        ("d1", True), ("d2", True)]
    assert [(e["id"], e["rotulo"], e["origem"]) for e in original["excertos"]] == [
        ("d1-0", "supported", "automatico"), ("d2-0", "refuted", "automatico")]
    # The automated passages carry the text of the news item, not a copy of their own.
    assert original["excertos"][0]["texto"] == CONTEUDO_1
    assert original["veredito"] == "nei"  # evidence on both sides
    assert original["explicacao"] == "A medida foi anunciada. A oposição discorda."
    assert corpo["pode_editar"] is True
    # The run's own article is part of the state, and nobody has touched it.
    assert original["artigo"]["title"] == "A medida"
    assert corpo["artigo_origem"] is None and corpo["pedido"] is None


def test_a_passage_changes_side_and_the_verdict_follows(verificacao):
    corpo = revisao(verificacao)
    estado = com_excerto(corpo["actual"], "d2-0", rotulo="nei")
    resposta = guardar(verificacao, estado, 0)
    assert resposta.status_code == 200, resposta.text
    novo = resposta.json()
    assert novo["versao"] == 1
    assert novo["actual"]["veredito"] == "supported"
    assert novo["historico"][0]["autor"]["utilizador"] == "ana"
    assert "excertos" in novo["historico"][0]["alteracoes"]
    # The automated state is untouched, in the review and in the run.
    assert novo["original"]["veredito"] == "nei"


def test_a_news_item_ruled_out_leaves_the_evidence(verificacao):
    corpo = revisao(verificacao)
    estado = com_documento(corpo["actual"], "d2", False)
    novo = guardar(verificacao, estado, 0).json()
    assert novo["actual"]["veredito"] == "supported"
    assert "relevancia" in novo["historico"][0]["alteracoes"]
    # The passage stays in the review, readable, but no longer counts.
    assert [e["id"] for e in novo["actual"]["excertos"]] == ["d1-0", "d2-0"]


def test_a_passage_can_be_left_out_and_brought_back(verificacao):
    corpo = revisao(verificacao)
    estado = com_excerto(corpo["actual"], "d1-0", rotulo=None)
    novo = guardar(verificacao, estado, 0).json()
    assert novo["actual"]["veredito"] == "refuted"
    assert novo["actual"]["excertos"][0]["rotulo"] is None
    # The passage is still there, and the automated one can be restored.
    restaurado = guardar(verificacao, versao_guardada(verificacao, 0), 1, restaurada_de=0).json()
    assert restaurado["actual"] == restaurado["original"]


def test_a_highlight_on_a_news_item_ruled_out_brings_it_back(verificacao):
    corpo = revisao(verificacao)
    estado = com_documento(corpo["actual"], "d2", False)
    primeiro = guardar(verificacao, estado, 0).json()
    assert primeiro["actual"]["veredito"] == "supported"

    destaque = {
        "id": "local-1", "doc_id": "d2", "begin": 2, "end": 12,
        "texto": CONTEUDO_2[2:12], "rotulo": "supported", "origem": "humano", "nota": "",
    }
    segundo = com_documento(primeiro["actual"], "d2", True)
    segundo = {**segundo, "excertos": [*segundo["excertos"], destaque]}
    resposta = guardar(verificacao, segundo, 1)
    assert resposta.status_code == 200, resposta.text
    novo = resposta.json()
    adicionado = novo["actual"]["excertos"][-1]
    assert adicionado["id"] == "local-1" and adicionado["texto"] == CONTEUDO_2[2:12]
    assert adicionado["criado_por"] and adicionado["criado_em"]
    # Two supporting passages now; the refuted one still counts on the other side.
    assert novo["actual"]["veredito"] == "nei"


def test_a_highlight_is_checked_against_the_source(verificacao):
    corpo = revisao(verificacao)
    destaque = {
        "id": "local-1", "doc_id": "d1", "begin": 2, "end": 10,
        "texto": CONTEUDO_1[2:10], "rotulo": "supported", "origem": "humano", "nota": "",
    }
    mentira = {**destaque, "texto": "outra coisa"}
    resposta = guardar(verificacao, {**corpo["actual"], "excertos": [mentira]}, 0)
    assert resposta.status_code == 422

    curto = {**destaque, "end": destaque["begin"] + 1, "texto": CONTEUDO_1[2:3]}
    assert guardar(verificacao, {**corpo["actual"], "excertos": [curto]}, 0).status_code == 422

    sem_rotulo = {**destaque, "rotulo": None}
    assert guardar(verificacao, {**corpo["actual"], "excertos": [sem_rotulo]}, 0).status_code == 422


def test_a_manual_verdict_wins_over_the_evidence(verificacao):
    corpo = revisao(verificacao)
    estado = {**corpo["actual"], "veredito_manual": "supported"}
    novo = guardar(verificacao, estado, 0).json()
    assert novo["actual"]["veredito"] == "supported"
    assert novo["actual"]["veredito_manual"] == "supported"
    assert novo["historico"][0]["accao"] == "edicao"
    assert novo["historico"][0]["alteracoes"] == ["veredito"]

    # The evidence moving on does not override a person's verdict.
    segundo = guardar(verificacao, com_excerto(novo["actual"], "d1-0", rotulo="refuted"), 1).json()
    assert segundo["actual"]["veredito"] == "supported"

    # Dropping it hands the verdict back to the evidence.
    terceiro = guardar(
        verificacao, {**segundo["actual"], "veredito_manual": None}, 2).json()
    assert terceiro["actual"]["veredito"] == "refuted"


def test_the_explanation_is_edited_on_its_own(verificacao):
    corpo = revisao(verificacao)
    novo = guardar(verificacao, {**corpo["actual"], "explicacao": "Outra."}, 0).json()
    assert novo["actual"]["explicacao"] == "Outra."
    assert novo["historico"][0]["alteracoes"] == ["explicacao"]


def test_a_stale_version_is_a_conflict(verificacao):
    corpo = revisao(verificacao)
    assert guardar(verificacao, {**corpo["actual"], "explicacao": "Primeira."}, 0).status_code == 200
    resposta = guardar(verificacao, {**corpo["actual"], "explicacao": "Segunda."}, 0)
    assert resposta.status_code == 409
    assert resposta.json()["revisao"]["versao"] == 1
    assert resposta.json()["revisao"]["actual"]["explicacao"] == "Primeira."


def test_saving_the_same_state_adds_nothing(verificacao):
    corpo = revisao(verificacao)
    assert guardar(verificacao, corpo["actual"], 0).json()["versao"] == 0


def test_many_edits_saved_at_once_are_one_version(verificacao):
    corpo = revisao(verificacao)
    estado = com_documento(corpo["actual"], "d2", False)
    estado = {**com_excerto(estado, "d1-0", rotulo="nei"), "veredito_manual": "refuted"}
    estado["artigo"] = {**estado["artigo"], "title": "Outro título"}
    novo = guardar(verificacao, estado, 0).json()
    assert novo["versao"] == 1 and len(novo["historico"]) == 1
    assert novo["historico"][0]["accao"] == "edicao"
    assert novo["historico"][0]["alteracoes"] == ["relevancia", "excertos", "veredito", "artigo"]


def test_an_older_review_reads_as_versions(verificacao, dados):
    """Before the draft, every undo, redo and kind of edit was a revision of its own, and a
    rewritten article sat beside its revision: it reads as edits, and the article moves into the
    states from then on."""
    import json
    corpo = revisao(verificacao)
    autor = {"id": "x", "utilizador": "ana", "nome": "Ana", "papel": "jornalista"}
    artigo = {**corpo["original"]["artigo"], "title": "Reescrito"}
    estado = {k: v for k, v in corpo["original"].items() if k != "artigo"}
    antiga = {
        "run_id": RUN_ID, "original": estado, "versao_atual": 2,
        "historico": [
            {"versao": 1, "accao": "artigo", "autor": autor, "em": "2026-01-01T00:00:00+00:00",
             "alteracoes": ["artigo"], "estado": estado, "artigo": artigo, "redator": "gemma"},
            {"versao": 2, "accao": "veredito", "autor": autor, "em": "2026-01-01T00:01:00+00:00",
             "alteracoes": ["veredito"], "estado": {**estado, "veredito_manual": "supported"}},
        ],
    }
    pasta = dados / "execucoes" / "revisoes"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{RUN_ID}.json").write_text(json.dumps(antiga), encoding="utf-8")
    lida = revisao(verificacao)
    assert [v["accao"] for v in lida["historico"]] == ["artigo", "edicao"]
    assert lida["actual"]["artigo"]["title"] == "Reescrito"
    assert lida["artigo_origem"]["versao"] == 1 and lida["artigo_origem"]["redator"] == "gemma"


def test_the_article_is_edited_and_its_citations_checked(verificacao):
    corpo = revisao(verificacao)
    artigo = corpo["actual"]["artigo"]
    # The second citation's marker is taken out of the text: the citation goes with it.
    editado = {**artigo, "title": "Título revisto",
               "lead": "A medida foi anunciada, e bem. [[C:1:d1-0]]"}
    novo = guardar(verificacao, {**corpo["actual"], "artigo": editado}, 0).json()
    assert novo["historico"][0]["alteracoes"] == ["artigo"]
    assert novo["actual"]["artigo"]["title"] == "Título revisto"
    assert [c["marker"] for c in novo["actual"]["artigo"]["citations"]] == ["1"]
    assert novo["artigo_origem"]["versao"] == 1
    assert novo["artigo_origem"]["autor"]["utilizador"] == "ana"
    # The automated article is still version 0.
    assert novo["original"]["artigo"]["title"] == "A medida"

    # A citation the page made up is refused.
    falsa = {**artigo["citations"][0], "begin": 3}
    resposta = guardar(
        verificacao, {**novo["actual"], "artigo": {**editado, "citations": [falsa]}}, 1)
    assert resposta.status_code == 422


def test_a_reopened_version_is_saved_as_a_restore(verificacao):
    corpo = revisao(verificacao)
    guardar(verificacao, com_excerto(corpo["actual"], "d2-0", rotulo="nei"), 0)
    # Reopening a version changes nothing: it is only saved when a person saves it.
    reaberta = versao_guardada(verificacao, 0)
    assert reaberta == corpo["original"]
    assert revisao(verificacao)["versao"] == 1
    resposta = guardar(verificacao, reaberta, 1, restaurada_de=0)
    assert resposta.status_code == 200, resposta.text
    novo = resposta.json()
    assert novo["versao"] == 2
    assert novo["actual"] == novo["original"]
    assert novo["historico"][-1]["accao"] == "restauracao"
    assert novo["historico"][-1]["restaurada_de"] == 0


def test_the_history_is_metadata_only(verificacao):
    corpo = revisao(verificacao)
    guardar(verificacao, {**corpo["actual"], "explicacao": "Outra."}, 0)
    versao = revisao(verificacao)["historico"][0]
    assert set(versao) == {
        "versao", "accao", "autor", "em", "alteracoes", "restaurada_de", "redator"}


def test_a_version_that_does_not_exist_is_not_found(verificacao):
    resposta = verificacao.get(f"/api/verificacoes/{RUN_ID}/revisao/versoes/3")
    assert resposta.status_code == 404


def test_the_previous_review_is_kept_as_bak(verificacao, dados):
    corpo = revisao(verificacao)
    guardar(verificacao, {**corpo["actual"], "explicacao": "Primeira."}, 0)
    guardar(verificacao, {**corpo["actual"], "explicacao": "Segunda."}, 1)
    anterior = (dados / "execucoes" / "revisoes" / f"{RUN_ID}.bak.json").read_text(encoding="utf-8")
    assert "Primeira." in anterior


def test_the_rewrite_is_queued_with_the_runs_writer(verificacao):
    corpo = revisao(verificacao)
    resposta = verificacao.post(f"/api/verificacoes/{RUN_ID}/revisao/artigo",
                                json={"versao": 0})
    assert resposta.status_code == 200, resposta.text
    novo = resposta.json()
    assert novo["pedido"]["estado"] == "na-fila"
    assert novo["pedido"]["por"]["utilizador"] == "ana"
    assert novo["versao"] == 0  # asking is not a revision
    (run_id, versao, autor, redator, quem), = verificacao.app.state.fila.pedidos
    assert (run_id, versao, redator) == (RUN_ID, 0, "gemma")
    assert autor["utilizador"] == "ana" and quem
    assert novo["pedido"]["redator"] == "gemma"

    # A second request while it waits is refused, and does not queue another job.
    outra = verificacao.post(f"/api/verificacoes/{RUN_ID}/revisao/artigo", json={"versao": 0})
    assert outra.status_code == 409
    assert len(verificacao.app.state.fila.pedidos) == 1


def test_the_rewrite_may_use_another_writer(verificacao):
    redatores = verificacao.app.state.fila
    resposta = verificacao.post(f"/api/verificacoes/{RUN_ID}/revisao/artigo",
                                json={"versao": 0, "redator": "amalia"})
    assert resposta.status_code == 200, resposta.text
    assert redatores.pedidos[0][3] == "amalia"
    # One the deployment does not offer is refused.
    outra = verificacao.post(f"/api/verificacoes/{RUN_ID}/revisao/artigo",
                             json={"versao": 0, "redator": "nenhum"})
    assert outra.status_code == 422


def test_a_stale_rewrite_is_a_conflict(verificacao):
    corpo = revisao(verificacao)
    guardar(verificacao, {**corpo["actual"], "explicacao": "Outra."}, 0)
    resposta = verificacao.post(f"/api/verificacoes/{RUN_ID}/revisao/artigo",
                                json={"versao": 0})
    assert resposta.status_code == 409
    assert resposta.json()["revisao"]["versao"] == 1
    assert verificacao.app.state.fila.pedidos == []


def test_the_article_is_rewritten_from_the_reviewed_evidence(verificacao, dados, monkeypatch):
    corpo = revisao(verificacao)
    estado = com_documento(corpo["actual"], "d2", False)
    guardar(verificacao, estado, 0)
    pedido = verificacao.post(f"/api/verificacoes/{RUN_ID}/revisao/artigo", json={"versao": 1})
    assert pedido.status_code == 200, pedido.text

    vistas = {}

    class InferenciaFalsa:
        def __init__(self, definicoes):
            pass

        async def write_article(self, claim, claim_date, context, evidence, redator):
            vistas["passagens"] = evidence
            vistas["redator"] = redator
            return {
                "article": {"title": "Outra vez", "lead": "A medida foi anunciada. [E1]",
                            "blocks": []},
                "evidence": [{"ref": "E1", "id": evidence[0]["id"],
                              "doc_id": evidence[0]["doc_id"], "begin": evidence[0]["begin"],
                              "end": evidence[0]["end"], "label": evidence[0]["label"]}],
                "metadata": {},
            }

        async def aclose(self):
            pass

    monkeypatch.setattr(trabalhador, "InferenceClient", InferenciaFalsa)
    autor = pedido.json()["pedido"]["por"]
    trabalhador.reescrever(RUN_ID, 1, autor, "gemma")

    # Only the evidence the review keeps reaches the writer.
    assert [p["doc_id"] for p in vistas["passagens"]] == ["d1"]
    assert vistas["passagens"][0]["label"] == "supported"
    assert vistas["redator"] == "gemma"

    depois = revisao(verificacao)
    assert depois["versao"] == 2
    assert depois["pedido"]["estado"] == "feito"
    assert depois["actual"]["artigo"]["title"] == "Outra vez"
    assert depois["artigo_origem"] == {
        "versao": 2, "accao": "artigo", "autor": depois["historico"][-1]["autor"],
        "redator": "gemma"}
    assert depois["historico"][-1]["accao"] == "artigo"
    assert depois["historico"][-1]["alteracoes"] == ["artigo"]
    # The evidence is as it was: the rewrite is a revision of the article only.
    assert [(d["doc_id"], d["relevante"]) for d in depois["actual"]["documentos"]] == [
        ("d1", True), ("d2", False)]


def escrever_com(verificacao, redator, titulo, versao):
    """Files an article by `redator` as the worker does, from the evidence as it stands."""
    resultado = verificacao.app.state.runs.guardada(RUN_ID)
    atual = revisao(verificacao)["actual"]["artigo"]
    artigo = Article.model_validate({**atual, "model": redator, "title": titulo})
    autor = Autor(id="u1", utilizador="ana")
    verificacao.app.state.revisoes.registar_artigo(resultado, artigo, autor, redator, versao)


def test_the_articles_of_the_same_evidence_are_there_to_compare(verificacao):
    corpo = revisao(verificacao)
    assert [(a["versao"], a["redator"], a["artigo"]["title"]) for a in corpo["artigos"]] == [
        (0, "gemma", "A medida")]
    assert corpo["artigos"][0]["autor"] is None and corpo["artigos_anteriores"] == 0

    escrever_com(verificacao, "amalia", "Outra voz", 0)
    corpo = revisao(verificacao)
    assert [(a["versao"], a["redator"], a["artigo"]["title"]) for a in corpo["artigos"]] == [
        (0, "gemma", "A medida"), (1, "amalia", "Outra voz")]
    assert corpo["artigos"][1]["autor"]["utilizador"] == "ana"

    # A person's edit of the text, or the pick of one of them, is not a candidate of its own.
    editado = {**corpo["actual"]["artigo"], "title": "Editado"}
    corpo = guardar(verificacao, {**corpo["actual"], "artigo": editado}, 1).json()
    assert [a["versao"] for a in corpo["artigos"]] == [0, 1]

    # Once the evidence changes, the earlier articles were written from something else.
    corpo = guardar(verificacao, com_documento(corpo["actual"], "d2", False), 2).json()
    assert corpo["artigos"] == [] and corpo["artigos_anteriores"] == 2
    escrever_com(verificacao, "gemma", "Sem a oposição", 3)
    corpo = revisao(verificacao)
    assert [a["artigo"]["title"] for a in corpo["artigos"]] == ["Sem a oposição"]
    assert corpo["artigos_anteriores"] == 2

    # Bringing the evidence back brings the articles written from it back.
    corpo = guardar(verificacao, com_documento(corpo["actual"], "d2", True), 4).json()
    assert [a["versao"] for a in corpo["artigos"]] == [0, 1]
    assert corpo["artigos_anteriores"] == 1


def test_the_rewrite_fails_when_the_evidence_moved_on(verificacao, monkeypatch):
    corpo = revisao(verificacao)
    verificacao.post(f"/api/verificacoes/{RUN_ID}/revisao/artigo", json={"versao": 0})
    guardar(verificacao, {**corpo["actual"], "explicacao": "Outra."}, 0)

    class InferenciaFalsa:
        def __init__(self, definicoes):
            pass

        async def aclose(self):
            pass

    monkeypatch.setattr(trabalhador, "InferenceClient", InferenciaFalsa)
    autor = {"id": "x", "utilizador": "ana", "nome": "Ana", "papel": "jornalista"}
    trabalhador.reescrever(RUN_ID, 0, autor, "gemma")

    depois = revisao(verificacao)
    assert depois["pedido"]["estado"] == "erro"
    assert depois["pedido"]["erro"] == "revisao_artigo_desatualizado"
    assert depois["artigo_origem"] is None


def test_a_writer_the_service_lacks_says_so(verificacao, monkeypatch):
    """What gave the 503: the run's writer is not served by the inference service."""
    from app.services.inference import InferenceUnavailable

    verificacao.post(f"/api/verificacoes/{RUN_ID}/revisao/artigo", json={"versao": 0})

    class InferenciaFalsa:
        def __init__(self, definicoes):
            pass

        async def write_article(self, *argumentos):
            raise InferenceUnavailable("este serviço não tem o modelo de redação «gemma»")

        async def aclose(self):
            pass

    monkeypatch.setattr(trabalhador, "InferenceClient", InferenciaFalsa)
    autor = {"id": "x", "utilizador": "ana", "nome": "Ana", "papel": "jornalista"}
    trabalhador.reescrever(RUN_ID, 0, autor, "gemma")

    pedido = revisao(verificacao)["pedido"]
    assert pedido["estado"] == "erro" and pedido["erro"] == "revisao_artigo_indisponivel"
    assert "gemma" in pedido["detalhe"] and pedido["redator"] == "gemma"


def test_a_journalist_who_may_not_edit_reads_but_cannot_edit(admin, dados):
    store = RunStore(8, dados / "execucoes")
    store.guardar(execucao())
    admin.app.state.runs = store
    admin.app.state.fila = FilaFalsa()
    admin.app.state.plataforma.actualizar(["verificar", "ver_resultados", "ver_historico"])
    criar_utilizador(admin, "ana", "jornalista")
    sair(admin)
    assert entrar(admin, "ana").status_code == 204

    corpo = revisao(admin)
    assert corpo["pode_editar"] is False
    assert guardar(admin, {**corpo["actual"], "explicacao": "Não pode."}, 0).status_code == 403
    assert versao_guardada(admin, 0) == corpo["original"]
    assert admin.post(f"/api/verificacoes/{RUN_ID}/revisao/artigo",
                      json={"versao": 0}).status_code == 403


def test_a_verification_that_was_not_kept_has_no_review(verificacao):
    assert verificacao.get("/api/verificacoes/ffffffffffff/revisao").status_code == 404
    assert verificacao.get("/api/verificacoes/nao-um-id/revisao").status_code == 404


def test_the_reviewed_passages_are_what_the_writer_reads(verificacao):
    resultado = execucao()
    corpo = revisao(verificacao)
    estado = corpo["actual"]
    passagens = passagens_revistas(RevisaoEstado.model_validate(estado), resultado)
    assert [p["id"] for p in passagens] == ["d1-0", "d2-0"]
    assert [p["text"] for p in passagens] == [CONTEUDO_1, CONTEUDO_2]
    assert [p["label"] for p in passagens] == ["supported", "refuted"]
