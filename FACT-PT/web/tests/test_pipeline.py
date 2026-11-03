"""The pipeline's own logic, without the models: passages, deduplication, evidence consolidation,
the relevance counts and the messages the page shows."""

from app.fila import sem_conteudo
from app.mensagens import Texto, lingua_do_pedido, traduzir
from app.pipeline.evidencia import consolidar
from app.pipeline.excerpts import build_excerpts, split_sentences
from app.pipeline.orchestrator import StageFailure, _contagem_de_relevancia
from app.pipeline.retrieval import deduplicate
from app.schemas import EvidenceDocument, ExcerptStance, FoundBy

TEXTO = "Primeira frase aqui. Segunda frase ali! Terceira frase? Quarta frase acolá."


def documento(doc_id, conteudo=TEXTO, origens=(), relevant=True):
    return EvidenceDocument(doc_id=doc_id, headline=f"Título {doc_id}",
                            published_at="2025-01-01T10:00:00", content=conteudo,
                            relevant=relevant,
                            found_by=[FoundBy(question_id=q, rank=r) for q, r in origens])


def logits(supported, refuted, nei):
    return {"supported": supported, "refuted": refuted, "nei": nei}


# ---- Passages ------------------------------------------------------------------------------

def test_sentences_are_split_with_offsets_into_the_text():
    frases = split_sentences(TEXTO)
    assert [TEXTO[a:b] for a, b in frases] == [
        "Primeira frase aqui.", "Segunda frase ali!", "Terceira frase?", "Quarta frase acolá."]


def test_passages_are_three_sentence_windows_one_sentence_apart():
    excertos = build_excerpts("d1", TEXTO)
    assert [e.id for e in excertos] == ["d1-e1", "d1-e2"]
    for excerto in excertos:
        assert TEXTO[excerto.begin:excerto.end] == excerto.text
    assert excertos[0].text == "Primeira frase aqui. Segunda frase ali! Terceira frase?"
    assert excertos[1].text == "Segunda frase ali! Terceira frase? Quarta frase acolá."


def test_a_short_news_item_is_one_passage_and_an_empty_one_none():
    assert [e.text for e in build_excerpts("d1", "Só uma frase.")] == ["Só uma frase."]
    assert build_excerpts("d1", "   ") == []


# ---- Deduplication -------------------------------------------------------------------------

def test_the_same_document_found_by_two_questions_is_one_with_both_origins():
    documentos = [
        documento("a", "Notícia sobre o orçamento do Estado aprovado ontem.", [("q2", 1)]),
        documento("a", "Notícia sobre o orçamento do Estado aprovado ontem.", [("q1", 3)]),
        documento("b", "Outra notícia, sobre futebol e o campeonato nacional.", [("q1", 1)]),
    ]
    finais, contagem = deduplicate(documentos)
    assert [d.doc_id for d in finais] == ["a", "b"]
    assert [(f.question_id, f.rank) for f in finais[0].found_by] == [("q1", 3), ("q2", 1)]
    assert contagem["repetidos"] == 1 and contagem["distintos"] == 2


def test_the_cut_keeps_an_item_among_the_first_top_k_of_some_question():
    documentos = [
        documento("a", "Primeiro texto, sobre a economia portuguesa.", [("q1", 1)]),
        documento("b", "Segundo texto, sobre o clima em Lisboa.", [("q1", 2)]),
        documento("c", "Terceiro texto, sobre eleições autárquicas.", [("q2", 1), ("q1", 3)]),
    ]
    finais, contagem = deduplicate(documentos, top_k=1)
    assert sorted(d.doc_id for d in finais) == ["a", "c"]
    assert contagem["fora_do_corte"] == 1


# ---- Evidence consolidation ----------------------------------------------------------------

def test_a_news_item_that_decides_forwards_no_context_and_joins_its_touching_passages():
    noticia = documento("d1")
    noticia.excerpts = build_excerpts("d1", TEXTO)
    estados = [ExcerptStance(excerpt_id="d1-e1", label="supported", logits=logits(3, 0, 1)),
               ExcerptStance(excerpt_id="d1-e2", label="supported", logits=logits(2, 0, 1))]
    resultado = consolidar([noticia], estados)

    assert resultado.decisivos == ["d1-e1", "d1-e2"]
    # The two windows overlap: the writer reads them once, as one passage.
    [passagem] = resultado.evidencia
    assert passagem.id == "d1-e1..d1-e2" and passagem.excerpt_ids == ["d1-e1", "d1-e2"]
    assert (passagem.begin, passagem.end) == (0, len(TEXTO))
    assert passagem.priority == 2.0
    assert resultado.contagem["juntos"] == 1 and resultado.contagem["nei"] == 0


def test_a_news_item_of_context_only_forwards_the_passage_closest_to_deciding():
    noticia = documento("d1")
    noticia.excerpts = build_excerpts("d1", TEXTO)
    estados = [ExcerptStance(excerpt_id="d1-e1", label="nei", logits=logits(0, 0, 5)),
               ExcerptStance(excerpt_id="d1-e2", label="nei", logits=logits(1, 0, 2))]
    resultado = consolidar([noticia], estados)

    assert resultado.decisivos == []
    assert [(p.id, p.label) for p in resultado.evidencia] == [("d1-e2", "nei")]
    assert resultado.contagem["nei_descartados"] == 1


# ---- Counts and messages -------------------------------------------------------------------

def test_the_relevance_percentage_is_rounded_half_up_from_the_counts():
    def percentagem(relevantes, total):
        return _contagem_de_relevancia(
            [documento(str(i), relevant=i < relevantes) for i in range(total)])["percentagem"]

    assert percentagem(1, 3) == 33 and percentagem(2, 3) == 67 and percentagem(1, 8) == 13
    assert _contagem_de_relevancia([]) == {"notícias": 0, "relevantes": 0, "irrelevantes": 0,
                                           "percentagem": 0}


def test_a_failure_is_shown_in_the_language_of_the_request_through_wrapping_errors():
    falha = StageFailure("questions", RuntimeError(Texto("sem_perguntas")))
    assert traduzir(falha, "en") == "the model returned no usable questions"
    assert traduzir(falha, "pt") == "o modelo não devolveu perguntas utilizáveis"
    assert traduzir(ValueError("texto livre"), "en") == "texto livre"


def test_the_language_is_the_first_one_the_browser_names():
    assert lingua_do_pedido("en-GB,en;q=0.9,pt;q=0.8") == "en"
    assert lingua_do_pedido("pt-PT,en;q=0.5") == "pt"
    assert lingua_do_pedido(None) == "pt"


def test_the_final_event_carries_no_news_text_but_keeps_the_offsets():
    resultado = {"run_id": "x", "documents": [{
        "doc_id": "d1", "headline": "H", "content": "Texto inteiro.",
        "excerpts": [{"id": "d1-e1", "doc_id": "d1", "begin": 0, "end": 5, "text": "Texto"}],
    }]}
    [aligeirado] = sem_conteudo(resultado)["documents"]
    assert "content" not in aligeirado
    assert aligeirado["excerpts"] == [{"id": "d1-e1", "doc_id": "d1", "begin": 0, "end": 5}]
    # The full run, kept in the store, is left as it was.
    assert resultado["documents"][0]["content"] == "Texto inteiro."
