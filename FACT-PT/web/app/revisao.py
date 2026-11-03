"""Editorial review of a verification: the evidence a person stands behind, kept apart from the
automated result.

The run's own `RunResult` is never touched. A review is a file of its own,
`<RUN_STORE_DIR>/revisoes/<run_id>.json`, holding:

- `original`: the automated evidence, expanded: every news item with its relevance, and every
  classified passage with its relation. It is version 0.
- `historico`: one full state per saved version, oldest first, each with its author, time, action
  and the fields it changed. Version 0 is the automated state, and is not in the list.
- `pedido`: the state of the last article rewrite (waiting, writing, done, failed).

A state is the draft as the page shows it: each news item is relevant or not, each passage is
supported, refuted, undecided, or excluded (`rotulo` null), and the article. The verdict follows
from those passages, unless a person set it by hand (`veredito_manual`). `artigo` null is the run's
own article; a person's edit or a rewrite from the reviewed evidence is kept in full.

The page edits a draft of its own, with its own undo and redo, and a version exists only when a
person saves it (`edicao`), saves an earlier version they reopened (`restauracao`, pointing at
it), or the worker files a rewritten article (`artigo`). Nothing is overwritten, and
`armazenamento` keeps the previous file as `.bak` on every write.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .armazenamento import FalhaAoGravar, bloqueio, gravar_json, ler_json
from .pipeline.evidencia import margem, prioridade
from .runstore import RUN_ID_VALIDO
from .schemas import Article, Excerpt, RunResult, StanceLabel

logger = logging.getLogger(__name__)

Veredito = Literal["supported", "refuted", "nei", "nei_sem_evidencia"]
Accao = Literal[
    "edicao", "restauracao", "artigo",
    # Older reviews saved every undo, redo and kind of edit as a revision of its own.
    "desfazer", "refazer", "destaque", "relevancia", "veredito",
]
ACCOES_ANTIGAS = {"desfazer", "refazer", "destaque", "relevancia", "veredito"}

MAX_EXPLICACAO = 20_000
MAX_EXCERTOS = 1_000
# A highlight shorter than this is almost always a stray click, not a passage.
MIN_DESTAQUE = 2
MAX_TITULO = 500
MAX_TEXTO = 20_000
MAX_BLOCOS = 200

_MARCADOR = re.compile(r"\[\[C:\d+:[^\]]+\]\]")
_CITACAO = re.compile(r"\[\[C:(\d+):([^\]]+)\]\]")
_PONTUACAO = re.compile(r"[ \t]+")


class ErroRevisao(ValueError):
    """A review that cannot be accepted. `chave` names the message to show (`mensagens.py`)."""

    def __init__(self, chave: str, **valores: object) -> None:
        super().__init__(chave)
        self.chave = chave
        self.valores = valores


class DocumentoRevisto(BaseModel):
    """A news item in the review: relevant, or ruled out (and still readable)."""

    doc_id: str
    relevante: bool


class ExcertoRevisto(BaseModel):
    """A passage of a news item: one the pipeline classified (`automatico`), or a stretch a person
    highlighted (`humano`). `rotulo` null means it is not counted as evidence, though it stays in
    the review (and can be brought back)."""

    id: str
    doc_id: str
    begin: int
    end: int
    rotulo: Optional[StanceLabel] = None
    origem: Literal["automatico", "humano"] = "automatico"
    # Filled for a person's highlight; the automated ones are read from the news item.
    texto: str = ""
    nota: str = Field(default="", max_length=2000)
    criado_por: Optional[str] = None
    criado_em: Optional[str] = None

    @field_validator("nota")
    @classmethod
    def _limpar(cls, v: str) -> str:
        # `texto` is not trimmed: a highlight must match the source exactly, spaces included.
        return v.strip() if isinstance(v, str) else v


class RevisaoEstado(BaseModel):
    documentos: list[DocumentoRevisto] = Field(default_factory=list)
    excertos: list[ExcertoRevisto] = Field(default_factory=list)
    veredito: Veredito
    veredito_manual: Optional[Veredito] = None
    explicacao: str = Field(default="", max_length=MAX_EXPLICACAO)
    artigo: Optional[Article] = None


class Autor(BaseModel):
    id: str
    utilizador: str
    nome: str = ""
    papel: str = ""


class PedidoArtigo(BaseModel):
    """The last article rewrite asked for, and where it got to. Not a revision: the page polls it
    while the worker writes."""

    estado: Literal["na-fila", "em-curso", "feito", "erro"]
    por: Autor
    em: str
    erro: str = ""
    # What the inference service said when it refused (a writer it does not have), and the writer.
    detalhe: str = ""
    redator: str = ""
    job_id: str = ""


class RevisaoVersao(BaseModel):
    versao: int
    accao: Accao
    autor: Autor
    em: str
    alteracoes: list[str] = Field(default_factory=list)
    restaurada_de: Optional[int] = None
    estado: RevisaoEstado
    # Older reviews kept a rewritten article here, beside the state; it now lives in the state.
    artigo: Optional[Article] = None
    # The writer, when this version is a rewrite.
    redator: str = ""


class Revisao(BaseModel):
    run_id: str
    original: RevisaoEstado
    versao_atual: int = 0
    historico: list[RevisaoVersao] = Field(default_factory=list)
    pedido: Optional[PedidoArtigo] = None

    @model_validator(mode="after")
    def _migrar(self) -> "Revisao":
        """An older review kept each rewritten article beside its revision, and the latest one was
        the article shown: it moves into the states, from its revision on."""
        ultimo: Article | None = None
        historico = []
        for versao in self.historico:
            if versao.artigo is not None:
                ultimo = versao.artigo
            if ultimo is not None and versao.estado.artigo is None:
                versao = versao.model_copy(
                    update={"estado": versao.estado.model_copy(update={"artigo": ultimo})}
                )
            historico.append(versao.model_copy(update={"artigo": None}))
        self.historico = historico
        return self

    def estado_actual(self) -> RevisaoEstado:
        return self.historico[-1].estado if self.historico else self.original

    def estado_de(self, versao: int) -> RevisaoEstado:
        if versao < 0 or versao > self.versao_atual:
            raise ErroRevisao("revisao_versao", versao=versao)
        return self.original if versao == 0 else self.historico[versao - 1].estado

    def origem_do_artigo(self) -> RevisaoVersao | None:
        """The version that put the current article in place: a rewrite, a person's edit or a
        restore. None while it is the run's own."""
        actual = self.estado_actual().artigo
        if actual is None:
            return None
        origem = None
        for versao in reversed(self.historico):
            if versao.estado.artigo != actual:
                break
            origem = versao
        return origem


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---- The articles written from the same evidence -----------------------------------------------


def _evidencia(estado: RevisaoEstado) -> tuple:
    """What an article is written from: which news items count and which passages, with their
    relation. Notes, the verdict and the article itself are not part of it."""
    return (
        frozenset((d.doc_id, d.relevante) for d in estado.documentos),
        frozenset((e.id, e.doc_id, e.begin, e.end, e.rotulo, e.origem) for e in estado.excertos),
    )


def artigos_da_evidencia(
    revisao: Revisao, resultado: RunResult
) -> tuple[list[dict], int]:
    """The articles written from the evidence as it stands now, oldest first, to compare and pick
    from: the run's own, when nobody changed the evidence since, and each rewrite filed on it. A
    person's edit of the text is not a candidate of its own (it is a version in the history).
    Also how many articles were written from an earlier state of the evidence, which only the
    history reaches."""
    actual = _evidencia(revisao.estado_actual())
    candidatos: list[dict] = []
    anteriores = 0
    automatico = artigo_automatico(resultado)
    if automatico is not None:
        if _evidencia(revisao.original) == actual:
            candidatos.append({"versao": 0, "accao": "automatica", "autor": None, "em": None,
                               "redator": resultado.input.redator, "artigo": automatico})
        else:
            anteriores += 1
    for versao in revisao.historico:
        if versao.accao != "artigo" or versao.estado.artigo is None:
            continue
        if _evidencia(versao.estado) != actual:
            anteriores += 1
            continue
        candidatos.append({"versao": versao.versao, "accao": versao.accao, "autor": versao.autor,
                           "em": versao.em, "redator": versao.redator,
                           "artigo": versao.estado.artigo})
    return candidatos, anteriores


# ---- The evidence -----------------------------------------------------------------------------


def _relevantes(estado: RevisaoEstado) -> set[str]:
    return {documento.doc_id for documento in estado.documentos if documento.relevante}


def contagem(estado: RevisaoEstado) -> dict[str, int]:
    """Passages supporting, refuting or deciding nothing, in the news items kept as relevant. A
    news item with four supporting passages and one refuting counts 4 and 1."""
    relevantes = _relevantes(estado)
    conta = {"supported": 0, "refuted": 0, "nei": 0}
    for excerto in estado.excertos:
        if excerto.doc_id in relevantes and excerto.rotulo in conta:
            conta[excerto.rotulo] += 1
    return conta


def veredito_da_evidencia(estado: RevisaoEstado) -> Veredito:
    conta = contagem(estado)
    if conta["supported"] and conta["refuted"]:
        return "nei"
    if conta["supported"]:
        return "supported"
    if conta["refuted"]:
        return "refuted"
    return "nei" if conta["nei"] else "nei_sem_evidencia"


def _explicacao_automatica(resultado: RunResult) -> str:
    """The article's lead, without the citation markers the page turns into buttons."""
    artigo = resultado.articles[0] if resultado.articles else None
    if artigo is None:
        return ""
    texto = _MARCADOR.sub("", artigo.lead or "")
    return _PONTUACAO.sub(" ", texto).strip()


def _rotulos(resultado: RunResult) -> dict[str, StanceLabel]:
    return {estado.excerpt_id: estado.label for estado in resultado.stances}


def _excertos_automaticos(resultado: RunResult) -> list[ExcertoRevisto]:
    """The passages the automated result showed: every supporting or refuting one, and, for a
    news item with none, the passage closest to deciding (`evidencia.consolidar`). The other
    passages the classifier read are not evidence on the page, and a person can highlight them
    from the source if they want them."""
    rotulos = _rotulos(resultado)
    stances = {estado.excerpt_id: estado for estado in resultado.stances}
    escolhidos: list[tuple[str, Excerpt]] = []
    for documento in resultado.documents:
        classificados = [e for e in documento.excerpts if e.id in rotulos]
        decisivos = [e for e in classificados if rotulos[e.id] in ("supported", "refuted")]
        if decisivos:
            escolhidos.extend((documento.doc_id, e) for e in decisivos)
        elif classificados:
            escolhidos.append((
                documento.doc_id,
                min(classificados, key=lambda e: margem(stances[e.id])),
            ))
    return [
        ExcertoRevisto(
            id=excerto.id,
            doc_id=doc_id,
            begin=excerto.begin,
            end=excerto.end,
            rotulo=rotulos.get(excerto.id),
        )
        for doc_id, excerto in escolhidos
    ]


def estado_automatico(resultado: RunResult) -> RevisaoEstado:
    """What the pipeline produced, as the review's version 0: every news item, relevant or not,
    and every passage it classified."""
    estado = RevisaoEstado(
        documentos=[
            DocumentoRevisto(doc_id=documento.doc_id, relevante=documento.relevant is not False)
            for documento in resultado.documents
        ],
        excertos=_excertos_automaticos(resultado),
        veredito="nei_sem_evidencia",
        explicacao=_explicacao_automatica(resultado),
    )
    return estado.model_copy(update={"veredito": veredito_da_evidencia(estado)})


def artigo_automatico(resultado: RunResult) -> Article | None:
    return resultado.articles[0] if resultado.articles else None


def expandir(estado: RevisaoEstado, resultado: RunResult) -> RevisaoEstado:
    """The state as the page reads it: the automated passages carry the text of the news item (the
    review stores only their offsets), every news item of the run is present, and the article is
    there in full, the run's own when the review has none of its own."""
    documentos = {documento.doc_id: documento for documento in resultado.documents}
    existentes = {documento.doc_id: documento for documento in estado.documentos}
    docs = [
        existentes.get(documento.doc_id)
        or DocumentoRevisto(doc_id=documento.doc_id, relevante=documento.relevant is not False)
        for documento in resultado.documents
    ]
    excertos = []
    for excerto in estado.excertos:
        documento = documentos.get(excerto.doc_id)
        if documento is None:
            continue
        if excerto.origem == "automatico":
            excerto = excerto.model_copy(
                update={"texto": documento.content[excerto.begin:excerto.end]}
            )
        excertos.append(excerto)
    return estado.model_copy(update={
        "documentos": docs,
        "excertos": excertos,
        "artigo": estado.artigo or artigo_automatico(resultado),
    })


# ---- Validation ------------------------------------------------------------------------------


def _chave_citacao(citacao) -> tuple:
    return (citacao.marker, citacao.excerpt_id, citacao.doc_id, citacao.begin, citacao.end)


def normalizar_artigo(
    artigo: Article | None, resultado: RunResult, conhecidas: list[Article]
) -> Article | None:
    """A person's article, checked: its text within bounds, and its citations ones an article of
    this verification already made (`conhecidas`), never new ones from the page. A citation whose
    marker the text no longer carries is dropped. The run's own article, unchanged, is null."""
    if artigo is None:
        return None
    automatico = artigo_automatico(resultado)
    if automatico is not None and artigo == automatico:
        return None
    if len(artigo.title) > MAX_TITULO or len(artigo.lead) > MAX_TEXTO \
            or len(artigo.blocks) > MAX_BLOCOS \
            or any(len(bloco.text) > MAX_TEXTO for bloco in artigo.blocks):
        raise ErroRevisao("revisao_artigo_longo")
    validas = {_chave_citacao(c): c for conhecida in conhecidas for c in conhecida.citations}
    textos = [artigo.title, artigo.lead, *(bloco.text for bloco in artigo.blocks)]
    usadas = {
        (encontro.group(1), encontro.group(2))
        for texto in textos for encontro in _CITACAO.finditer(texto)
    }
    citacoes = []
    for citacao in artigo.citations:
        chave = _chave_citacao(citacao)
        if chave not in validas:
            raise ErroRevisao("revisao_citacao", marcador=citacao.marker)
        if (citacao.marker, citacao.excerpt_id) in usadas:
            citacoes.append(validas[chave])
    return artigo.model_copy(update={
        "title": artigo.title.strip(),
        "lead": artigo.lead.strip(),
        "blocks": [bloco for bloco in artigo.blocks if bloco.text.strip()],
        "citations": citacoes,
    })


def normalizar(
    estado: RevisaoEstado, resultado: RunResult, conhecidas: list[Article] | None = None
) -> RevisaoEstado:
    """Checks the state against the run and takes the passages' text and offsets from the source,
    never from the page. An automated passage the page does not send stays as it was; to leave it
    out of the evidence it must be sent with `rotulo` null. `conhecidas` are the articles whose
    citations an edited article may keep (`normalizar_artigo`)."""
    if len(estado.excertos) > MAX_EXCERTOS:
        raise ErroRevisao("revisao_demasiados", n=MAX_EXCERTOS)

    documentos = {documento.doc_id: documento for documento in resultado.documents}
    relevancia: dict[str, bool] = {}
    for documento in estado.documentos:
        if documento.doc_id not in documentos:
            raise ErroRevisao("revisao_documento", id=documento.doc_id)
        relevancia[documento.doc_id] = documento.relevante

    submetidos: dict[str, ExcertoRevisto] = {}
    for excerto in estado.excertos:
        if excerto.id in submetidos:
            raise ErroRevisao("revisao_excerto_repetido", id=excerto.id)
        submetidos[excerto.id] = excerto

    rotulos = {e.id: e.rotulo for e in _excertos_automaticos(resultado)}
    excertos: list[ExcertoRevisto] = []
    for documento in resultado.documents:
        for excerto in documento.excerpts:
            if excerto.id not in rotulos:
                continue
            enviado = submetidos.pop(excerto.id, None)
            excertos.append(
                ExcertoRevisto(
                    id=excerto.id,
                    doc_id=documento.doc_id,
                    begin=excerto.begin,
                    end=excerto.end,
                    rotulo=rotulos[excerto.id] if enviado is None else enviado.rotulo,
                    origem="automatico",
                    nota="" if enviado is None else enviado.nota,
                )
            )

    # Whatever is left is a person's highlight: it must be exactly a stretch of the news item.
    for excerto in submetidos.values():
        if excerto.origem != "humano":
            raise ErroRevisao("revisao_excerto", id=excerto.id)
        documento = documentos.get(excerto.doc_id)
        if documento is None:
            raise ErroRevisao("revisao_documento", id=excerto.doc_id)
        if not (0 <= excerto.begin < excerto.end <= len(documento.content)):
            raise ErroRevisao("revisao_destaque")
        if documento.content[excerto.begin:excerto.end] != excerto.texto:
            raise ErroRevisao("revisao_destaque")
        if excerto.end - excerto.begin < MIN_DESTAQUE or excerto.rotulo is None:
            raise ErroRevisao("revisao_destaque")
        excertos.append(excerto.model_copy(update={"doc_id": documento.doc_id}))

    normalizado = estado.model_copy(
        update={
            "documentos": [
                DocumentoRevisto(
                    doc_id=documento.doc_id,
                    relevante=relevancia.get(
                        documento.doc_id, documento.relevant is not False
                    ),
                )
                for documento in resultado.documents
            ],
            "excertos": excertos,
            "artigo": normalizar_artigo(
                estado.artigo, resultado, [*resultado.articles, *(conhecidas or [])]
            ),
        }
    )
    return normalizado.model_copy(
        update={
            "veredito": normalizado.veredito_manual or veredito_da_evidencia(normalizado),
        }
    )


def _com_autoria(anterior: RevisaoEstado, novo: RevisaoEstado, autor: Autor) -> RevisaoEstado:
    """Stamps the highlights that are new in this revision with their author and time; those
    carried over keep the author they had."""
    antigos = {excerto.id: excerto for excerto in anterior.excertos}
    quando = agora()
    excertos = []
    for excerto in novo.excertos:
        if excerto.origem != "humano":
            excertos.append(excerto)
            continue
        antes = antigos.get(excerto.id)
        if antes is not None:
            excerto = excerto.model_copy(
                update={"criado_por": antes.criado_por, "criado_em": antes.criado_em}
            )
        else:
            excerto = excerto.model_copy(update={"criado_por": autor.id, "criado_em": quando})
        excertos.append(excerto)
    return novo.model_copy(update={"excertos": excertos})


def alteracoes(anterior: RevisaoEstado, novo: RevisaoEstado) -> list[str]:
    campos = []
    if [(d.doc_id, d.relevante) for d in anterior.documentos] != [
        (d.doc_id, d.relevante) for d in novo.documentos
    ]:
        campos.append("relevancia")
    if [(e.id, e.rotulo) for e in anterior.excertos] != [
        (e.id, e.rotulo) for e in novo.excertos
    ]:
        campos.append("excertos")
    if anterior.veredito_manual != novo.veredito_manual or anterior.veredito != novo.veredito:
        campos.append("veredito")
    if anterior.explicacao != novo.explicacao:
        campos.append("explicacao")
    if anterior.artigo != novo.artigo:
        campos.append("artigo")
    return campos


# ---- Storage ---------------------------------------------------------------------------------


class Conflito(Exception):
    """Someone else saved a revision first: the page must reload before it can save."""

    def __init__(self, revisao: Revisao) -> None:
        super().__init__("conflito")
        self.revisao = revisao


class ReviewStore:
    def __init__(self, pasta: str | Path) -> None:
        self._pasta = Path(pasta)

    @property
    def pasta(self) -> Path:
        return self._pasta

    def caminho(self, run_id: str) -> Path:
        if not RUN_ID_VALIDO.match(run_id):
            raise ErroRevisao("revisao_ausente")
        return self._pasta / f"{run_id}.json"

    def ler(self, run_id: str) -> Revisao | None:
        dados = ler_json(self.caminho(run_id))
        if dados is None:
            return None
        try:
            return Revisao.model_validate(dados)
        except ValueError as erro:
            logger.error("revisão %s ilegível: %s", run_id, erro)
            return None

    def _obter(self, resultado: RunResult) -> Revisao:
        return self.ler(resultado.run_id) or Revisao(
            run_id=resultado.run_id, original=estado_automatico(resultado)
        )

    def obter(self, resultado: RunResult) -> Revisao:
        """The review of a saved verification, or a fresh one holding only the automated state."""
        return self._obter(resultado)

    def aplicar(
        self,
        resultado: RunResult,
        estado: RevisaoEstado,
        autor: Autor,
        versao_esperada: int,
        restaurada_de: int | None = None,
    ) -> Revisao:
        """Appends a version, if it changes anything, and returns the review: a person's save, or
        (`restaurada_de`) an earlier version they reopened and saved again, edited or not. Raises
        `Conflito` when the review moved on since `versao_esperada`."""
        caminho = self.caminho(resultado.run_id)
        with bloqueio(caminho):
            revisao = self._obter(resultado)
            if revisao.versao_atual != versao_esperada:
                raise Conflito(revisao)
            if restaurada_de is not None:
                revisao.estado_de(restaurada_de)
            anterior = revisao.estado_actual()
            conhecidas = [v.estado.artigo for v in revisao.historico if v.estado.artigo]
            novo = _com_autoria(anterior, normalizar(estado, resultado, conhecidas), autor)
            mudancas = alteracoes(anterior, novo)
            if not mudancas:
                return revisao
            versao = RevisaoVersao(
                versao=revisao.versao_atual + 1,
                accao="edicao" if restaurada_de is None else "restauracao",
                autor=autor,
                em=agora(),
                alteracoes=mudancas,
                restaurada_de=restaurada_de,
                estado=novo,
            )
            revisao = revisao.model_copy(
                update={
                    "versao_atual": versao.versao,
                    "historico": [*revisao.historico, versao],
                }
            )
            if not gravar_json(caminho, revisao.model_dump(mode="json")):
                raise FalhaAoGravar(str(caminho))
            return revisao

    def marcar_pedido(self, resultado: RunResult, pedido: PedidoArtigo) -> Revisao:
        """Records the state of an article rewrite, without making a revision."""
        caminho = self.caminho(resultado.run_id)
        with bloqueio(caminho):
            revisao = self._obter(resultado)
            revisao = revisao.model_copy(update={"pedido": pedido})
            if not gravar_json(caminho, revisao.model_dump(mode="json")):
                raise FalhaAoGravar(str(caminho))
            return revisao

    def registar_artigo(
        self,
        resultado: RunResult,
        artigo: Article,
        autor: Autor,
        redator: str,
        versao_esperada: int,
    ) -> Revisao:
        """Appends the article the worker wrote from the current state, as a version of its own: the
        evidence as it was, with the new article. Raises `Conflito` when the review moved on while
        it was being written."""
        caminho = self.caminho(resultado.run_id)
        with bloqueio(caminho):
            revisao = self._obter(resultado)
            if revisao.versao_atual != versao_esperada:
                raise Conflito(revisao)
            versao = RevisaoVersao(
                versao=revisao.versao_atual + 1,
                accao="artigo",
                autor=autor,
                em=agora(),
                alteracoes=["artigo"],
                estado=revisao.estado_actual().model_copy(update={"artigo": artigo}),
                redator=redator,
            )
            revisao = revisao.model_copy(
                update={
                    "versao_atual": versao.versao,
                    "historico": [*revisao.historico, versao],
                }
            )
            if not gravar_json(caminho, revisao.model_dump(mode="json")):
                raise FalhaAoGravar(str(caminho))
            return revisao


def passagens_revistas(estado: RevisaoEstado, resultado: RunResult) -> list[dict]:
    """The evidence the article writer reads: the passages the review keeps, in document order,
    with the relation a person gave each one. A person's highlight is not dropped for being short
    or for not fitting the classifier's plan; it is what they asked to be written from."""
    documentos = {documento.doc_id: documento for documento in resultado.documents}
    relevantes = _relevantes(estado)
    stances = {estado.excerpt_id: estado for estado in resultado.stances}
    por_doc: dict[str, list[ExcertoRevisto]] = {}
    for excerto in estado.excertos:
        if excerto.rotulo is None or excerto.doc_id not in relevantes:
            continue
        por_doc.setdefault(excerto.doc_id, []).append(excerto)

    passagens = []
    for documento in resultado.documents:
        if documento.doc_id not in relevantes:
            continue
        excertos = sorted(por_doc.get(documento.doc_id, []), key=lambda e: e.begin)
        posicoes = {excerto.id: posicao for posicao, excerto in enumerate(documento.excerpts, 1)}
        for excerto in excertos:
            stance = stances.get(excerto.id)
            passagens.append(
                {
                    "id": excerto.id,
                    "doc_id": documento.doc_id,
                    "label": excerto.rotulo,
                    "text": documento.content[excerto.begin:excerto.end],
                    "begin": excerto.begin,
                    "end": excerto.end,
                    "headline": documento.headline,
                    "published_at": documento.published_at,
                    "index": posicoes.get(excerto.id, 1),
                    "priority": 1.0 if excerto.origem == "humano"
                    else (prioridade(stance) if stance is not None else 0.0),
                }
            )
    return passagens
