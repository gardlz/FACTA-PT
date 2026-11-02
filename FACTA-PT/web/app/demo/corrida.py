"""A stored example as a run: the events the page receives, rebuilt from what the example holds.

Every stage comes back done, with what the page shows of it: the questions, how many news items
were retrieved and how many of them were relevant, the relevant ones and what each does to the
claim, and the article of the run's chosen model, each citation pointing at its passage in the
text of its news item.
"""

from __future__ import annotations

import re

from ..schemas import (
    REDATORES,
    STAGE_ORDER,
    Article,
    ArticleBlock,
    Citation,
    CitedExcerpt,
    ClaimInput,
    EvidenceDocument,
    ExcerptStance,
    Question,
    RunResult,
    StageReport,
)

# A citation in the example's text is its number, `[1]`; the page marks it `[[C:1:<id>]]`.
CITACAO = re.compile(r"\s*\[(\d+)\]")
# What a news item does to the claim: the relations of its deciding passages.
DECIDE = {"supported": ("supported",), "refuted": ("refuted",),
          "ambos": ("supported", "refuted"), "nei": ()}


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
    )


def _decisivos(noticias: list[dict]) -> tuple[list[ExcerptStance], list[str]]:
    """One deciding entry per relation each news item has: what the timeline and the balance
    count. Its id starts with the news item's, as the passages' ids do."""
    estados, decisivos = [], []
    for noticia in noticias:
        for rotulo in DECIDE[noticia["relacao"]]:
            identificador = f"{noticia['lusa_id']}-{rotulo}"
            estados.append(ExcerptStance(excerpt_id=identificador, label=rotulo))
            decisivos.append(identificador)
    return estados, decisivos


def _janelas(citacao: dict, texto: str, inicio: int, fim: int) -> list[CitedExcerpt]:
    """The classified windows the example keeps for a citation, each found in the news item's
    text inside the cited passage, in order."""
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
    """The run of a stored example, from start to done, with the article of the chosen model;
    when the example holds none by that model, the article stage is skipped."""
    perguntas = [Question(id=f"q{i}", index=i, text=texto)
                 for i, texto in enumerate(exemplo["perguntas"], 1)]
    documentos = [_documento(noticia) for noticia in exemplo["noticias"]]
    estados, decisivos = _decisivos(exemplo["noticias"])
    artigos = [_artigo(artigo, exemplo["noticias"]) for artigo in exemplo["artigos"]
               if artigo["modelo"] == REDATORES[data.redator] and artigo["titulo"] is not None]

    # What each stage hands the page: its counts, and its share of the result.
    por_etapa = {
        "questions": ({}, {"questions": [p.model_dump() for p in perguntas]}),
        "relevance": ({"notícias": exemplo["noticias_recuperadas"],
                       "relevantes": exemplo["noticias_relevantes"],
                       "percentagem": exemplo["percentagem_relevantes"]},
                      {"documents": [d.resumo() for d in documentos]}),
        "stance": ({}, {"stances": [e.model_dump() for e in estados], "decisive": decisivos}),
        "article": ({}, {"articles": [a.model_dump() for a in artigos]}),
    }
    relatorios = {nome: StageReport(name=nome, status="pending") for nome in STAGE_ORDER}
    saida = [{"type": "start", "run_id": run_id,
              "stages": [r.model_dump() for r in relatorios.values()]}]
    for nome in STAGE_ORDER:
        estatisticas, dados = por_etapa.get(nome, ({}, {}))
        relatorio = relatorios[nome]
        if nome == "article" and not artigos:
            relatorio.status, relatorio.stats = "skipped", {"motivo": "por_gerar"}
            saida.append({"type": "stage", "stage": relatorio.model_dump()})
            continue
        relatorio.status, relatorio.stats = "done", estatisticas
        saida.append({"type": "stage", "stage": relatorio.model_dump(), **dados})

    resultado = RunResult(run_id=run_id, input=data, stages=list(relatorios.values()),
                          questions=perguntas, documents=documentos, stances=estados,
                          decisive_excerpt_ids=decisivos, articles=artigos)
    saida.append({"type": "done", "result": resultado.model_dump(mode="json")})
    return saida
