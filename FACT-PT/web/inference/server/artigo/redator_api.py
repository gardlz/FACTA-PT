"""The article writers, each a model behind an OpenAI-compatible API: AMALIA-9B-0626-DPO on Modal's
gateway (`MODAL_API_*`) or a vLLM server (`AMALIA_API_*`), and Gemma on OpenRouter
(`ARTICLE_API_*`). The plan and the prompt of the evaluated run go to the API's chat completions
endpoint; a request still running after 150 s, which Modal answers with a redirect to its result,
follows the redirect.

What it keeps from the evaluated configuration. The evaluated run rendered the two messages with the
checkpoint's chat template and fed that text to vLLM's offline `LLM.generate`, which added the
tokenizer's BOS on top of the one the template writes (`prompt_base.prompt_final`, `bos_duplo`).
To a vLLM server the same two messages go with `add_special_tokens`, vLLM's own parameter, for that
BOS: the server reads the token ids that run read. They are counted here with the model's
tokenizer, to fit the passages to `ARTICLE_MAX_PROMPT_TOKENS` and to the server's window.
Greedy decoding, the repetition penalty (1.05, and 1.15 on the second attempt), and the plan's JSON
Schema of the evaluated run (`esquema.esquema_do_plano`), its character class kept off U+D800-U+DFFF
(`_sem_substitutos`), which vLLM compiles with xgrammar - free whitespace disabled in the server's
configuration, as that run set it (MODELS.md), and asked for per request as vLLM 0.8 takes it. New
tokens are capped at 8192; the evaluated run allowed 4096, a ceiling that only stops the generation.
The plan and its data message are the evaluated ones (`plano.construir`, `render.mensagem`), and the
answer is read as that run read it: only complete JSON, mended at its last value when cut, never
rewritten (`resposta.interpretar`).

OpenRouter routes the request to a provider of its choosing. Of the parameters above it is asked
only those the model's entry in its /models lists (`supported_parameters`) - the schema only to a
model that lists `structured_outputs`, which the free Gemma variants do not, nor the penalty - and,
with `require_parameters`, only by a provider that honours them; when none does, by any provider. Thinking is turned off, as the evaluated chat template left it. The schema is then
the provider's to enforce, with a grammar engine of its own: the article is not the evaluated one.

A server that refuses the schema is asked again without it, and the article records
`formato="livre"`, as one written without it from the start. A request that fails - no answer, a
refusal - is an attempt that wrote nothing, and the article is completed from the plan, as when no
attempt finishes in time. What the server's arithmetic does with the weights is its own: greedy
decoding is not reproducible across engines, nor across two runs of the same one.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Callable

import httpx

from .. import api_externa, gpu
from ..qg import tokenizador
from ..settings import Settings
from ..textutils import claim_context
from . import admissao, plano as pv, prompt_base as pb, render, versao
from .completar import completar, paragrafos_por_seccao
from .esquema import esquema_do_plano
from .resposta import LIMIAR_CICLO, interpretar, pontos, precisa_retentar, repeticao

logger = logging.getLogger(__name__)

# The same ceiling and penalties for every writer: an article stopped by one of them and not by the
# other would not be a difference between the models.
MAX_NOVOS = 8192
PENALIZACAO = 1.05
PENALIZACAO_RETENTATIVA = 1.15
# A generation is stuck when it ends in this many blank characters, or when the same eight words
# come back as often as the cycle detector's threshold doubled.
BRANCOS = 64
LIMIAR_PRESO = 2 * LIMIAR_CICLO
# Characters per token, for a Portuguese text under the checkpoint's tokenizer: measured at about
# 3.4, and rounded down so that the estimate errs on the side of dropping a passage. Only used when
# the tokenizer cannot be read.
CHARS_POR_TOKEN = 3.0
# An attempt starts only with this long left before the caller's deadline, which is also the read
# timeout of its request: the article must be back, completed if it must be.
ESCRITA_MINIMA = 60.0
# A rate-limited request (429: a free model, shared by everyone) is sent again after a wait - the
# server's Retry-After, or these seconds, one per try - while the deadline leaves room to write.
ESPERAS_429 = (5.0, 15.0, 30.0, 60.0)
# vLLM's server refuses a pattern whose character class runs over U+D800-U+DFFF ("surrogates not
# allowed"). Those are not characters in UTF-8, so a class kept off them admits the same text.
_SUBSTITUTOS = ("\u201f-\uffff", "\u201f-\ud7ff\ue000-\uffff")


# Parameters that only a vLLM server takes: anywhere else they are left out.
SO_VLLM = ("add_special_tokens", "guided_whitespace_pattern")


class ArticleError(RuntimeError):
    """The article could not be written."""


class ArticleCancelled(ArticleError):
    """Whoever asked for the article is gone, and the generation stopped."""


class ApiWriter(gpu.ModeloMovel):
    """The article, written by a model behind an OpenAI-compatible API.

    It is not in this process, so it takes no GPU and no main memory here: `movel` stays false, and
    `externa` says so - the service gives it the article's queue rather than the GPU's
    (`main._fila`).
    """

    #: Runs outside this process. It never takes a turn with the models that run in it.
    externa = True

    def __init__(self, settings: Settings, nome: str, url: str, modelo: str, chave: str = "",
                 tokenizador_de: Callable[[], tuple[str, str]] | None = None,
                 vllm: bool = True) -> None:
        """`url` and `modelo`, the API and the model's name there; `chave`, its key, when it asks
        for one; `tokenizador_de`, the (checkpoint, revision) whose tokenizer counts the prompt;
        `vllm`, whether the server is vLLM, which takes parameters no other does."""
        self._settings = settings
        self.nome = nome
        self.descricao = f"o modelo de redação {nome}"
        self._url = url
        self._modelo = modelo
        self._chave = chave
        self._tokenizador_de = tokenizador_de
        self._vllm = vllm
        self.identificador = f"api:{modelo}"
        # The server's window, as /v1/models gives it.
        self.contexto = None
        # The parameters the model takes, as /v1/models lists them; None, every one (vLLM).
        self._parametros: set[str] | None = None
        self._tokenizer = None
        self._limite = settings.article_max_prompt_tokens
        self._pronto = False
        # Why the model is not available, when it is not.
        self.motivo = ""
        # A request OpenRouter could not charge for (402): only a run tries the writer again.
        self._sem_credito = False

    @property
    def loaded(self) -> bool:
        return self._pronto

    def _recusar(self, motivo: str) -> None:
        self._pronto = False
        self.motivo = motivo
        logger.error("modelo de redação %s não disponível: %s", self.nome, motivo)

    def load(self) -> None:
        """Whether the API answers and serves the model, and the window it serves it with. Asked
        again when a request finds the writer refused (`main._carregar_a_pedido`)."""
        self._sem_credito = False
        # OpenRouter lists its models to anyone, but writes only for a key.
        if not self._vllm and not self._chave:
            return self._recusar(api_externa.indisponivel(
                f"{self._modelo}: a chave da API está por definir (ARTICLE_API_KEY)"))
        entrada, falta = api_externa.servido(self._url, self._modelo, self._chave)
        if falta:
            return self._recusar(falta)
        # Whether it takes the key is asked of it apart, without writing anything.
        if not self._vllm:
            falta = api_externa.chave_openrouter(self._url, self._chave)
            if falta:
                return self._recusar(falta)
        # vLLM gives the window as `max_model_len`, OpenRouter as `context_length`.
        self.contexto = entrada.get("max_model_len") or entrada.get("context_length")
        parametros = entrada.get("supported_parameters")
        self._parametros = set(parametros) if parametros is not None else None
        self._limite = self._settings.article_max_prompt_tokens
        if self.contexto:
            self._limite = min(self._limite, int(self.contexto) - MAX_NOVOS)
            if self._limite <= 0:
                return self._recusar(api_externa.indisponivel(
                    f"a janela do modelo ({self.contexto} tokens) não deixa {MAX_NOVOS} para o "
                    f"artigo"))
        self._tokenizer = None
        try:
            if self._tokenizador_de is not None:
                self._tokenizer = tokenizador(*self._tokenizador_de())
        except Exception as erro:  # noqa: BLE001 - without it the passages are fitted by characters
            logger.warning("sem o tokenizador de %s (%s): as passagens cabem pela conta dos "
                           "caracteres", self.nome, erro)
        self._pronto = True
        self.motivo = ""
        logger.info("modelo de redação %s disponível na API (%s, prompt até %d tokens, %s)",
                    self.nome, self._modelo, self._limite,
                    "com o esquema" if self._aceita_esquema() else "sem o esquema")

    def verificar(self) -> None:
        """Asks OpenRouter again whether it takes the key, without writing anything
        (`api_externa.chave_openrouter`): the key's state changes outside this service. A writer
        that can no longer write is refused, and one refused that now can is loaded again - unless a
        request found no credits to pay for it, which the balance-blind check cannot tell has
        changed: that writer waits for a run to try it."""
        if self._vllm or not self._chave:
            return
        falta = api_externa.chave_openrouter(self._url, self._chave)
        if falta:
            self._recusar(falta)
        elif not self._pronto and not self._sem_credito:
            self.load()

    def _aceita(self, parametro: str) -> bool:
        """Whether the model takes `parametro`, as the API lists it."""
        if parametro in SO_VLLM:
            return self._vllm
        return self._parametros is None or parametro in self._parametros

    def _aceita_esquema(self) -> bool:
        """Whether the model takes the plan's JSON Schema. On OpenRouter a JSON Schema in
        `response_format` is `structured_outputs`: a provider that lists only `response_format`
        (JSON mode, as the free Gemma variants' does) refuses it."""
        if self._parametros is None:
            return True
        return "structured_outputs" in self._parametros

    # -- writing -----------------------------------------------------------------------------

    def esquema(self, plano: dict) -> dict:
        return _sem_substitutos(esquema_do_plano(plano))

    def _cabe(self, versao_do_plano: dict) -> bool:
        """Whether a version of the plan fits, in the token ids the server will read; by characters
        when the tokenizer could not be read."""
        if self._tokenizer is None:
            return versao_do_plano["caracteres"] <= self._limite * CHARS_POR_TOKEN
        if "tokens" not in versao_do_plano:
            _, ids = pb.prompt_final(self._tokenizer, versao_do_plano["mensagem"])
            versao_do_plano["tokens"] = len(ids)
        return versao_do_plano["tokens"] <= self._limite

    def _parar(self, cancelado: threading.Event) -> None:
        if cancelado.is_set():
            raise ArticleCancelled("o pedido foi abandonado e a geração pára")

    def _ha_tempo(self, prazo: float | None) -> bool:
        return prazo is None or prazo - time.monotonic() > ESCRITA_MINIMA

    def _pedir(self, versao_do_plano: dict, penalizacao: float,
               prazo: float | None, cancelado: threading.Event | None = None) -> dict:
        """One request to the API: the two messages and, when the model takes it, the plan's
        schema."""
        corpo = {
            "model": self._modelo,
            "messages": [
                {"role": "system", "content": pb.PROMPT_BASE},
                {"role": "user", "content": versao_do_plano["mensagem"]},
            ],
            "temperature": 0,
            "max_tokens": MAX_NOVOS,
        }
        if self._aceita("add_special_tokens"):
            corpo["add_special_tokens"] = True
        if self._aceita("repetition_penalty"):
            corpo["repetition_penalty"] = penalizacao
        if not self._vllm:
            # OpenRouter: a provider that honours every parameter asked, and no thinking, as the
            # evaluated chat template left it.
            corpo["provider"] = {"require_parameters": True}
            if self._aceita("reasoning"):
                corpo["reasoning"] = {"enabled": False}
        cabecalhos = {"X-Title": "FACTA-PT"}
        if self._chave:
            cabecalhos["Authorization"] = f"Bearer {self._chave}"
        # The answer has to be back by the caller's deadline, completed if it must be.
        espera = self._settings.api_timeout_s
        if prazo is not None:
            espera = min(espera, max(1.0, prazo - time.monotonic()))
        tempo = httpx.Timeout(espera, connect=15.0)

        def enviar(com_esquema: bool, exigir: bool = True) -> httpx.Response:
            pedido = dict(corpo)
            if not exigir:
                # Any provider, the parameters it does not take dropped by OpenRouter.
                pedido.pop("provider", None)
            if com_esquema:
                pedido["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "artigo", "schema": versao_do_plano["esquema"]},
                }
                # No whitespace between the JSON's tokens, as the evaluated run compiled it: a
                # server not configured so lets the model write blanks until the ceiling.
                if self._aceita("guided_whitespace_pattern"):
                    pedido["guided_whitespace_pattern"] = ""
            with (httpx.Client(timeout=tempo) as cliente,
                  api_externa.pedido(self._url, self._settings.modal_gpu_idle_s)):
                return cliente.post(api_externa.endereco(self._url, "chat/completions"),
                                    json=pedido, headers=cabecalhos, follow_redirects=True)

        inicio = time.perf_counter()
        com_esquema = self._aceita_esquema()
        resposta = enviar(com_esquema)
        for espera in ESPERAS_429:
            if resposta.status_code != 429:
                break
            pedida = _segundos(resposta.headers.get("Retry-After"))
            espera = min(pedida, 120.0) if pedida is not None else espera
            # Not past the point where the article could still be written in time.
            if prazo is not None and prazo - time.monotonic() - espera <= ESCRITA_MINIMA:
                break
            logger.warning("a API está limitada (429): novo pedido daqui a %.0f s", espera)
            if (cancelado or threading.Event()).wait(espera):
                break
            resposta = enviar(com_esquema)
        if com_esquema and (resposta.status_code == 400 or _sem_fornecedor(resposta)):
            logger.warning("a API recusou o esquema (%s %s): o artigo é pedido sem ele",
                           resposta.status_code, resposta.text[:200])
            com_esquema = False
            resposta = enviar(False)
        if not self._vllm and _sem_fornecedor(resposta):
            # No provider takes every parameter asked: any provider, without those it does not take.
            logger.warning("nenhum fornecedor aceita todos os parâmetros (%s): o artigo é pedido "
                           "a qualquer um", resposta.text[:200])
            resposta = enviar(False, exigir=False)
        if resposta.status_code != 200:
            motivo = api_externa.indisponivel(f"artigo: {api_externa.resposta_falhada(resposta)}")
            # Refused for good - no key, no such model, no credits to pay for it - and not for what
            # this request asked.
            if resposta.status_code in (401, 402, 403, 404) and not _sem_fornecedor(resposta):
                self._sem_credito = resposta.status_code == 402
                self._recusar(motivo)
            raise ArticleError(motivo)
        dados = resposta.json()
        # OpenRouter can answer 200 with the provider's error in the body.
        if dados.get("error") or not dados.get("choices"):
            erro = dados.get("error") or {}
            raise ArticleError(api_externa.indisponivel(
                f"artigo: a API respondeu sem artigo ({erro.get('code', '')} "
                f"{str(erro.get('message', ''))[:200]})"))
        escolha = dados["choices"][0]
        uso = dados.get("usage") or {}
        return {
            "texto": (escolha.get("message") or {}).get("content") or "",
            # "stop" when the answer ended by itself, "length" when the ceiling cut it.
            "parou": escolha.get("finish_reason") == "stop",
            "tokens_gerados": uso.get("completion_tokens"),
            "tokens_prompt": uso.get("prompt_tokens"),
            "segundos": round(time.perf_counter() - inicio, 1),
            "com_esquema": com_esquema,
            # Who wrote it, when the API chose (OpenRouter's provider).
            "provedor": dados.get("provider"),
        }

    def _tentar(self, versao_do_plano: dict, penalizacao: float,
                cancelado: threading.Event, prazo: float | None) -> dict:
        """One attempt at the article of a plan; a request that fails is an attempt that wrote
        nothing."""
        self._parar(cancelado)
        plano = versao_do_plano["plano"]
        validos = {e["ref"] for e in pv.todas_as_evidencias(plano)}
        try:
            dados = self._pedir(versao_do_plano, penalizacao, prazo, cancelado)
        except (httpx.HTTPError, ArticleError) as erro:
            if isinstance(erro, (httpx.ConnectError, httpx.ConnectTimeout)):
                # Gone since it was found: the next request asks the server again.
                self._recusar(api_externa.indisponivel(
                    f"artigo: a API não responde ({erro.__class__.__name__})"))
            logger.error("tentativa do artigo sem resposta da API: %s", erro)
            return {
                "estado": "sem_resposta", "reparado": False,
                "artigo": {"title": None, "lead": "", "blocks": []},
                "repeticao_max": 0, "ids_citados": [], "ids_invalidos": [],
                "penalizacao": penalizacao, "tokens_gerados": None, "tokens_prompt": None,
                "tokens_estimados": True, "truncado": False, "preso": False,
                "prazo": bool(prazo is not None and time.monotonic() >= prazo),
                "formato": "livre", "segundos_leitura": None, "segundos": None,
                "versao": versao_do_plano, "em_falta": _seccoes_em_falta(plano, []),
            }
        texto = dados["texto"]
        lido = interpretar(texto, validos)
        if not dados["parou"] and lido["estado"] not in ("ok", "reparado"):
            lido["estado"] = "truncado"
        lido.update(
            penalizacao=penalizacao,
            # A server that does not count sends nothing, and `tokens_estimados` records it.
            tokens_gerados=dados["tokens_gerados"],
            tokens_prompt=dados["tokens_prompt"],
            tokens_estimados=dados["tokens_prompt"] is None,
            truncado=not dados["parou"],
            preso=preso(texto),
            prazo=bool(prazo is not None and time.monotonic() >= prazo),
            formato="esquema" if dados["com_esquema"] else "livre",
            provedor=dados["provedor"],
            segundos_leitura=None,
            segundos=dados["segundos"],
        )
        lido["versao"] = versao_do_plano
        lido["em_falta"] = _seccoes_em_falta(plano, lido["artigo"]["blocks"])
        return lido

    def write(self, claim: str, claim_date: str, context: str, passagens: list[dict],
              cancelado: threading.Event | None = None, prazo: float | None = None) -> dict:
        """The article, always with every section of its plan.

        The sequence the evaluated writer followed: the passages that fit the cap go in, an attempt
        that does not come out clean is written again with the heavier penalty, a last attempt
        reads half the passages, and what none finishes is completed from the plan. `prazo` is a
        `time.monotonic()` instant by which the article must be back.

        Cancellation is best effort: the request is abandoned where it stands, which closes the
        connection, but nothing tells the server to stop by name.
        """
        if not self._pronto:
            raise ArticleError(f"modelo de redação {self.nome} não disponível: "
                               f"{self.motivo or 'por carregar'}")
        cancelado = cancelado or threading.Event()
        self._parar(cancelado)
        inicio = time.perf_counter()

        janela = claim_context(context, claim)
        versoes: dict[tuple[str, ...], dict] = {}

        def versao_de(escolhidas: list[dict]) -> dict:
            chave = tuple(p["id"] for p in escolhidas)
            if chave not in versoes:
                plano = pv.construir(claim, claim_date, janela, escolhidas)
                mensagem = render.mensagem(plano)
                versoes[chave] = {
                    "passagens": escolhidas,
                    "plano": plano,
                    "mensagem": mensagem,
                    "esquema": self.esquema(plano),
                    "caracteres": len(pb.PROMPT_BASE) + len(mensagem),
                }
            return versoes[chave]

        lidas, fora = admissao.admitir(
            passagens, lambda escolhidas: self._cabe(versao_de(escolhidas))
        )
        completa = versao_de(lidas)
        tentativas: list[dict] = []
        sem_tempo = 0
        melhor = None
        if self._ha_tempo(prazo):
            melhor = self._tentar(completa, PENALIZACAO, cancelado, prazo)
            tentativas.append(melhor)
            if precisa_retentar(melhor) and not cancelado.is_set():
                if self._ha_tempo(prazo):
                    tentativas.append(
                        self._tentar(completa, PENALIZACAO_RETENTATIVA, cancelado, prazo)
                    )
                    if pontos(tentativas[-1]) > pontos(melhor):
                        melhor = tentativas[-1]
                else:
                    sem_tempo += 1
        else:
            sem_tempo += 1
        if (melhor is None or melhor["em_falta"]) and not cancelado.is_set():
            reduzidas = admissao.metade(lidas)
            if len(reduzidas) < len(lidas):
                curta = versao_de(reduzidas)
                if self._ha_tempo(prazo):
                    tentativas.append(
                        self._tentar(curta, PENALIZACAO_RETENTATIVA, cancelado, prazo)
                    )
                    if not tentativas[-1]["em_falta"]:
                        melhor = tentativas[-1]
                else:
                    sem_tempo += 1
        self._parar(cancelado)

        completadas: list[str] = []
        cortado_em = None
        if melhor is not None and not melhor["em_falta"]:
            artigo, final, estado = melhor["artigo"], melhor["versao"], melhor["estado"]
        else:
            if tentativas:
                melhor = max(tentativas, key=lambda t: (-len(t["em_falta"]), pontos(t)))
                escritas = [s for s, ps
                            in paragrafos_por_seccao(melhor["artigo"]["blocks"]).items() if ps]
                cortado_em = escritas[-1] if escritas else None
                artigo, final = melhor["artigo"], melhor["versao"]
            else:
                artigo, final = {"title": None, "lead": "", "blocks": []}, completa
            artigo, completadas = completar(final["plano"], artigo)
            estado = "completado"
            logger.warning("artigo completado sem o modelo em %s (cortado em %s, %d tentativas)",
                           completadas, cortado_em, len(tentativas))

        plano = final["plano"]
        evidencias = pv.todas_as_evidencias(plano)
        # The attempt the article comes from: its numbers describe what was read and written.
        escolhida = melhor or {}

        return {
            "article": artigo,
            "evidence": [
                {"ref": e["ref"], "id": e["id"], "doc_id": e["doc_id"], "begin": e["begin"],
                 "end": e["end"], "label": e["relacao"]}
                for e in evidencias
            ],
            "metadata": {
                **versao.VERSOES,
                "modelo": self.identificador,
                "modelo_nome": self.nome,
                "modelo_revisao": "",
                "dispositivo": "api",
                "classificacao": plano["classificacao"],
                "motivo": plano["motivo"],
                "caso": plano["caso"],
                "data_limite": plano["data_limite"],
                "contexto_localizado": bool(janela),
                "prompt_sha256": _sha(pb.PROMPT_BASE + "\n\n" + final["mensagem"]),
                "prompt_final_sha256": _sha(final["mensagem"]),
                "esquema_sha256": _sha_esquema(final["esquema"]),
                # As the server counted them.
                "tokens_prompt": escolhida.get("tokens_prompt"),
                "tokens_estimados": escolhida.get("tokens_estimados", True),
                # The cap the passages were fitted to: the server's window can make it lower.
                "limite_tokens_prompt": self._limite,
                "max_novos": MAX_NOVOS,
                "contexto": self.contexto,
                "passagens_recebidas": len(passagens),
                "passagens_lidas": len(final["passagens"]),
                "fora_pelo_limite": len(fora),
                "estado": estado,
                # Attempts the deadline did not leave time for, and whether one was stopped by it.
                "sem_tempo": sem_tempo,
                "prazo_esgotado": bool(sem_tempo) or any(t["prazo"] for t in tentativas),
                "formato": escolhida.get("formato", "livre"),
                "completadas": completadas,
                "cortado_em": cortado_em,
                "tentativas": [
                    {"passagens": len(t["versao"]["passagens"]),
                     **{k: t.get(k) for k in ("penalizacao", "estado", "repeticao_max",
                                              "tokens_gerados", "truncado", "preso", "prazo",
                                              "provedor", "segundos_leitura", "segundos")}}
                    for t in tentativas
                ],
                "segundos": round(time.perf_counter() - inicio, 1),
            },
        }


def _segundos(valor: str | None) -> float | None:
    """A Retry-After header in seconds; None when absent or a date."""
    try:
        return max(0.0, float(valor)) if valor else None
    except ValueError:
        return None


def _sem_fornecedor(resposta: httpx.Response) -> bool:
    """OpenRouter's 404 when no provider of the model takes the parameters asked: the model is
    there, the request is what it refuses."""
    return resposta.status_code == 404 and "No endpoints found" in resposta.text


def _sem_substitutos(esquema):
    """The plan's schema with every pattern's character class kept off U+D800-U+DFFF."""
    if isinstance(esquema, dict):
        return {chave: (valor.replace(*_SUBSTITUTOS) if chave == "pattern" and isinstance(valor, str)
                        else _sem_substitutos(valor))
                for chave, valor in esquema.items()}
    if isinstance(esquema, list):
        return [_sem_substitutos(valor) for valor in esquema]
    return esquema


def preso(texto: str) -> bool:
    """Whether a generation is stuck: blanks to the ceiling, or a phrase come back too often."""
    cauda = texto[-BRANCOS:]
    return (len(cauda) == BRANCOS and cauda.isspace()) or repeticao(texto) >= LIMIAR_PRESO


def _seccoes_em_falta(plano: dict, blocos: list[dict]) -> list[str]:
    """The plan's sections the article does not bring whole: a heading with at least one
    paragraph, and the fixed texts verbatim."""
    paragrafos = paragrafos_por_seccao(blocos)
    em_falta = []
    for seccao in plano["seccoes"]:
        escritos = paragrafos.get(seccao["titulo"])
        if not escritos or ("texto_fixo" in seccao and escritos != [seccao["texto_fixo"]]):
            em_falta.append(seccao["titulo"])
    return em_falta


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _sha_esquema(esquema: dict) -> str:
    corpo = json.dumps(esquema, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()
