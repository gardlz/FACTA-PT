"""A stored example as a run: the events the page receives, rebuilt from what the example holds.

Every stage comes back done, with what the page shows of it: the questions, how many news items
were retrieved and how many of them were relevant, the relevant ones and what each does to the
claim, and the articles written from the same evidence, each citation pointing at its passage in
the text of its news item. The article first in the list is the one the run's chosen model wrote; the
others are the recorded articles of the remaining models.
"""

from __future__ import annotations

import re

from ..schemas import (
    REDATORES,
    STAGE_LABELS,
    STAGE_ORDER,
    Article,
    ArticleBlock,
    Citation,
    CitedExcerpt,
    ClaimInput,
    EvidenceDocument,
    Excerpt,
    ExcerptStance,
    Question,
    RunResult,
    StageReport,
)

# A citation in the example's text is its number, `[1]`; the page marks it `[[C:1:<id>]]`.
CITACAO = re.compile(r"\s*\[(\d+)\]")
# The model each writer's articles in the examples were recorded with, where it is not the one the
# writer runs now: the Gemma articles were written by Gemma 4 E4B, before it moved to an API.
GRAVADOS_COM = {"gemma": "Gemma 4 E4B"}
# What a news item does to the claim: the relations of its deciding passages.
DECIDE = {"supported": ("supported",), "refuted": ("refuted",),
          "ambos": ("supported", "refuted"), "nei": ()}


def _passagens(noticia: dict) -> list[tuple[Excerpt, str]]:
    """The passages the example keeps for a news item, each with its relation, found in its text
    in order (a passage it does not find is left out)."""
    passagens, desde = [], 0
    for i, passagem in enumerate(noticia.get("excertos", []), 1):
        inicio = noticia["texto"].find(passagem["texto"], desde)
        if inicio < 0:
            inicio = noticia["texto"].find(passagem["texto"])
        if inicio < 0:
            continue
        fim = inicio + len(passagem["texto"])
        passagens.append((Excerpt(id=f"{noticia['lusa_id']}-p{i}", doc_id=noticia["lusa_id"],
                                  begin=inicio, end=fim, text=passagem["texto"]),
                          passagem["relacao"]))
        desde = inicio + 1
    return passagens


def _documento(noticia: dict) -> EvidenceDocument:
    return EvidenceDocument(
        doc_id=noticia["lusa_id"],
        headline=noticia["titulo"],
        published_at=noticia["data"],
        relevant=True,
        genre=noticia["genero"],
        byline=noticia["autor"],
        word_count=noticia["palavras"],
        content=noticia["texto"],
        excerpts=[excerto for excerto, _ in _passagens(noticia)],
    )


def _decisivos(noticias: list[dict]) -> tuple[list[ExcerptStance], list[str]]:
    """Each passage the example keeps, with its relation, and one deciding entry per relation each
    news item has: what the timeline and the balance count. The deciding entry is the news item's
    first passage of that relation, or, when it keeps none, an entry of its own whose id starts
    with the news item's, as the passages' do."""
    estados, decisivos = [], []
    for noticia in noticias:
        passagens = _passagens(noticia)
        estados.extend(ExcerptStance(excerpt_id=excerto.id, label=rotulo)
                       for excerto, rotulo in passagens)
        for rotulo in DECIDE[noticia["relacao"]]:
            identificador = next((excerto.id for excerto, r in passagens if r == rotulo), None)
            if identificador is None:
                identificador = f"{noticia['lusa_id']}-{rotulo}"
                estados.append(ExcerptStance(excerpt_id=identificador, label=rotulo))
            decisivos.append(identificador)
    return estados, decisivos


def _janelas(citacao: dict, texto: str, inicio: int, fim: int) -> list[CitedExcerpt]:
    """The classified windows the example keeps for a citation, each found in the news item's
    text inside the cited passage, in order. An example recorded before they were kept has none."""
    janelas, desde = [], inicio
    for i, janela in enumerate(citacao.get("excertos", []), 1):
        comeco = texto.find(janela["texto"], desde)
        if comeco < 0 or comeco + len(janela["texto"]) > fim:
            continue
        janelas.append(CitedExcerpt(excerpt_id=f"c{citacao['n']}-{i}", label=janela["relacao"],
                                    begin=comeco, end=comeco + len(janela["texto"]),
                                    text=janela["texto"]))
        desde = comeco + 1
    return janelas


def _artigo(artigo: dict, noticias: list[dict]) -> Article:
    """An article with its citations resolved: each one's news item, found by its headline and
    date, and where its passage stands in the text, the passage's first occurrence there."""

    def marcar(texto: str) -> str:
        return CITACAO.sub(lambda encontro: f"[[C:{encontro.group(1)}:c{encontro.group(1)}]]",
                           texto).strip()

    blocos = []
    for seccao in artigo["seccoes"]:
        blocos.append(ArticleBlock(type="heading", text=marcar(seccao["titulo"])))
        blocos.extend(ArticleBlock(type="paragraph", text=marcar(p)) for p in seccao["paragrafos"])
    citacoes = []
    for citacao in artigo["citacoes"]:
        noticia = next(n for n in noticias
                       if (n["titulo"], n["data"]) == (citacao["noticia"], citacao["data"]))
        inicio = noticia["texto"].find(citacao["excerto"])
        fim = inicio + len(citacao["excerto"])
        citacoes.append(Citation(
            marker=str(citacao["n"]),
            excerpt_id=f"c{citacao['n']}",
            doc_id=noticia["lusa_id"],
            headline=noticia["titulo"],
            published_at=noticia["data"],
            label=citacao["relacao"],
            excerpt_text=citacao["excerto"],
            begin=inicio,
            end=fim,
            excerpts=_janelas(citacao, noticia["texto"], inicio, fim),
        ))
    return Article(model=artigo["modelo"], title=artigo["titulo"], lead=marcar(artigo["lead"]),
                   blocks=blocos, citations=citacoes)


def eventos(exemplo: dict, run_id: str, data: ClaimInput) -> list[dict]:
    """The run of a stored example, from start to done, with the articles recorded for it, the
    chosen model's first; while none is written yet, the article stage is skipped."""
    perguntas = [Question(id=f"q{i}", index=i, text=texto)
                 for i, texto in enumerate(exemplo["perguntas"], 1)]
    documentos = [_documento(noticia) for noticia in exemplo["noticias"]]
    estados, decisivos = _decisivos(exemplo["noticias"])
    # Every article recorded, the chosen model's first: the page shows that one and lets the
    # reader switch to the others, which were written from the same evidence.
    artigos = sorted(
        (_artigo(artigo, exemplo["noticias"]) for artigo in exemplo["artigos"]
         if artigo["titulo"] is not None),
        key=lambda artigo: artigo.model not in (REDATORES[data.redator],
                                                GRAVADOS_COM.get(data.redator)))
    recuperadas, relevantes = exemplo["noticias_recuperadas"], exemplo["noticias_relevantes"]

    por_etapa = {
        "questions": ({"perguntas": len(perguntas)},
                      {"questions": [p.model_dump() for p in perguntas]}),
        "retrieval": ({"perguntas": len(perguntas), "por_pergunta": data.top_k}, {}),
        # The news items retrieved reach the timeline here, not yet judged relevant, as on the
        # model path. The example keeps only the relevant ones, so those are all it can show.
        "dedup": ({"distintos": recuperadas},
                  {"documents": [{**d.resumo(), "relevant": None} for d in documentos]}),
        "relevance": ({"notícias": recuperadas, "relevantes": relevantes,
                       "irrelevantes": recuperadas - relevantes,
                       "percentagem": exemplo["percentagem_relevantes"]},
                      {"documents": [d.resumo() for d in documentos]}),
        "excerpts": ({"documentos": len(documentos)}, {}),
        "stance": ({"decisivos": len(decisivos)},
                   {"stances": [e.model_dump() for e in estados], "decisive": decisivos}),
        "article": ({"artigos": len(artigos)},
                    {"articles": [a.model_dump() for a in artigos]}),
    }
    relatorios = {nome: StageReport(name=nome, label=STAGE_LABELS[nome], status="pending")
                  for nome in STAGE_ORDER}
    saida = [{"type": "start", "run_id": run_id,
              "stages": [r.model_dump() for r in relatorios.values()]}]
    for nome in STAGE_ORDER:
        estatisticas, dados = por_etapa[nome]
        relatorio = relatorios[nome]
        if nome == "article" and not artigos:
            relatorio.status, relatorio.detail = "skipped", "artigo por gerar para esta claim"
            saida.append({"type": "stage", "stage": relatorio.model_dump()})
            continue
        relatorio.status, relatorio.provenance, relatorio.stats = "done", "exemplo", estatisticas
        saida.append({"type": "stage", "stage": relatorio.model_dump(), **dados})

    resultado = RunResult(run_id=run_id, input=data, stages=list(relatorios.values()),
                          questions=perguntas, documents=documentos, stances=estados,
                          decisive_excerpt_ids=decisivos, articles=artigos)
    saida.append({"type": "done", "result": resultado.model_dump(mode="json")})
    return saida
