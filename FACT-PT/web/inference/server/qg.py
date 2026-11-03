"""Question generation: AMALIA with its QLoRA adapter, served behind an OpenAI-compatible API
(`QG_API_URL`, or Modal's gateway: `MODAL_API_URL`), with the API's key when it asks for one.

The prompt is built here and fitted to the model window (the adapter's `max_seq_length`, less the
answer's room), as in training and evaluation, with the base model's tokenizer, then sent as it is
to the API's completions endpoint, which reads it as the evaluation's tokenizer did, the
beginning-of-sequence token added.
Generation parameters, prompt version and window come from the adapter's `checkpoint_info.json`,
which is part of the checkpoint: of the base and the adapter only those files are read, never the
weights. Decoding is greedy, as evaluated; what the server's arithmetic does with the weights is its
own (the evaluated run read the base in 4-bit NF4).

On Modal the GPU is off while nobody asks it anything, and the next request waits for it to start;
one still running after 150 s is answered with a redirect to its result, which is followed.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

import httpx

from . import api_externa, checkpoint
from .gpu import ModeloMovel
from .prompts import PROMPT_VERSION, build_question_input
from .settings import Settings
from .textutils import claim_context, localizar, parse_questions

logger = logging.getLogger(__name__)


def base_do_adaptador(settings: Settings) -> tuple[str, str, dict]:
    """(base model, its revision, the adapter's checkpoint_info.json): the revision the adapter was
    trained on, unless another is asked for. Also the AMALIA writer's tokenizer."""
    if not settings.qg_adapter_path:
        raise FileNotFoundError("QG_ADAPTER_PATH por definir")
    ficha = json.loads(checkpoint.ficheiro(settings.qg_adapter_path, "checkpoint_info.json",
                                           settings.qg_adapter_revision).read_text(encoding="utf-8"))
    caminho = settings.qg_model_path or ficha.get("base_model") or ""
    revisao = settings.qg_model_revision
    if not revisao and caminho == ficha.get("base_model"):
        revisao = ficha.get("base_model_revision") or ""
    return caminho, revisao, ficha


@lru_cache
def tokenizador(caminho: str, revisao: str):
    """The checkpoint's tokenizer alone - its few files, not the weights - read once."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(caminho, revision=revisao or None, use_fast=True)


class QuestionGenerator(ModeloMovel):
    descricao = "o gerador de perguntas"
    #: Runs outside this process: it takes no GPU and no memory here, and has a queue of its own
    #: (`main._fila`).
    externa = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tokenizer = None
        self._max_novos = 192
        self._penalizacao = 1.0
        self._max_entrada = 1024
        self._pronto = False
        self._motivo = ""

    @property
    def loaded(self) -> bool:
        return self._pronto

    @property
    def motivo(self) -> str:
        """Why the model is not available, when it is not."""
        return self._motivo

    def _recusar(self, motivo: str) -> None:
        self._pronto = False
        self._motivo = motivo
        logger.error("modelo de geração de perguntas não disponível: %s", motivo)

    def load(self) -> None:
        url, modelo = self._settings.qg_api_url, self._settings.qg_api_model
        if not url:
            return self._recusar(api_externa.indisponivel("QG_API_URL por definir"))
        # The writer's model answers without the adapter: the questions would be another model's.
        if (modelo == self._settings.amalia_api_model
                and api_externa.mesmo_servidor(url, self._settings.amalia_api_url)):
            return self._recusar(api_externa.indisponivel(
                "QG_API_MODEL é o modelo do redator, sem o adaptador de perguntas"))
        _, falta = api_externa.servido(url, modelo, self._settings.qg_api_key)
        if falta:
            return self._recusar(falta)

        try:
            caminho, revisao, ficha = base_do_adaptador(self._settings)
        except Exception as erro:  # noqa: BLE001 - no card, no prompt: refused with the reason
            return self._recusar(f"sem o checkpoint_info.json do adaptador: {erro}")
        if ficha.get("prompt_version") != PROMPT_VERSION:
            return self._recusar(
                f"o adaptador foi treinado com a prompt {ficha.get('prompt_version')!r}, "
                f"e este serviço constrói a {PROMPT_VERSION!r}"
            )
        geracao = ficha.get("generation_config") or {}
        # Only greedy decoding is asked of the API, and the evaluation decoded no other way.
        if (geracao.get("do_sample") or geracao.get("num_beams", 1) != 1
                or geracao.get("no_repeat_ngram_size")):
            return self._recusar(f"a geração do adaptador não se pede pela API: {geracao}")
        if not caminho:
            return self._recusar("QG_MODEL_PATH por definir")

        try:
            self._tokenizer = tokenizador(caminho, revisao)
        except Exception as erro:  # noqa: BLE001 - no tokenizer, no prompt: refused with the reason
            return self._recusar(f"sem o tokenizador de {caminho}: {erro}")
        self._max_novos = int(geracao.get("max_new_tokens", 192))
        self._penalizacao = float(geracao.get("repetition_penalty", 1.0))
        # A decoder's prompt was fitted to max_seq_length in training and evaluation.
        self._max_entrada = int(ficha["max_seq_length"])
        self._pronto = True
        self._motivo = ""
        logger.info("modelo de geração de perguntas disponível: %s na API (tokenizador %s, "
                    "%d tokens novos)", modelo, caminho, self._max_novos)

    def _n_tokens(self, texto: str) -> int:
        return len(self._tokenizer(texto, add_special_tokens=True)["input_ids"])

    def _entrada(self, claim_span: str, publication_time: str, context: str) -> str:
        """The prompt with the ±1 sentence window, fitted to the model window minus the room
        the answer needs. A window that does not fit is cut by characters around the claim."""
        janela = claim_context(context, claim_span)
        entrada = build_question_input(claim_span, publication_time, janela)
        orcamento = max(32, self._max_entrada - self._max_novos)
        if not janela or self._n_tokens(entrada) <= orcamento:
            return entrada

        alvo = localizar(janela, claim_span)
        if alvo is None:
            contexto = janela
            while contexto:
                contexto = contexto[: max(0, int(len(contexto) * 0.85))]
                candidata = build_question_input(claim_span, publication_time, contexto)
                if self._n_tokens(candidata) <= orcamento:
                    return candidata
            return build_question_input(claim_span, publication_time, "")

        inicio, fim = alvo
        baixo, alto, melhor = 0, len(janela), None
        while baixo <= alto:
            meio = (baixo + alto) // 2
            pedaco = janela[max(0, inicio - meio) : min(len(janela), fim + meio)].strip()
            candidata = build_question_input(claim_span, publication_time, pedaco)
            if self._n_tokens(candidata) <= orcamento:
                melhor, baixo = candidata, meio + 1
            else:
                alto = meio - 1
        if melhor is None:
            logger.warning("a prompt não cabe na janela do modelo nem sem contexto")
            return build_question_input(claim_span, publication_time, "")
        return melhor

    def generate(self, claim_span: str, publication_time: str, context: str) -> tuple[list[str], str]:
        if not self.loaded:
            raise RuntimeError("modelo de geração de perguntas não disponível")

        url = self._settings.qg_api_url
        corpo = {
            "model": self._settings.qg_api_model,
            "prompt": self._entrada(claim_span, publication_time, context),
            "max_tokens": self._max_novos,
            "temperature": 0,
        }
        # A penalty other than none goes as vLLM's own parameter; the evaluated one is none.
        if self._penalizacao != 1.0:
            corpo["repetition_penalty"] = self._penalizacao
        try:
            with api_externa.pedido(url, self._settings.modal_gpu_idle_s):
                resposta = httpx.post(
                    api_externa.endereco(url, "completions"), json=corpo,
                    headers=api_externa.cabecalhos(self._settings.qg_api_key),
                    timeout=httpx.Timeout(self._settings.api_timeout_s, connect=15.0),
                    follow_redirects=True,
                )
        except httpx.HTTPError as erro:
            # Gone since it was found: the next request asks the server again.
            self._recusar(api_externa.indisponivel(
                f"perguntas: a API não responde ({erro.__class__.__name__})"))
            raise RuntimeError(self._motivo) from erro
        if resposta.status_code != 200:
            motivo = api_externa.indisponivel(f"perguntas: {api_externa.resposta_falhada(resposta)}")
            if resposta.status_code in (401, 403, 404):
                self._recusar(motivo)
            raise RuntimeError(motivo)
        bruto = (resposta.json()["choices"][0].get("text") or "").strip()
        return parse_questions(bruto), bruto
