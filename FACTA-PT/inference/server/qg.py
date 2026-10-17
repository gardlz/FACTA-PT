"""Question generation: the decoder and its QLoRA adapter, loaded and run as in evaluation.

Generation parameters, prompt version, quantisation and the model window come from the
adapter's `checkpoint_info.json`, which is part of the checkpoint.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import torch

from .dispositivo import MARGEM_RAM, escolher, memoria_disponivel
from .gpu import ModeloMovel, alocada
from .prompts import PROMPT_VERSION, build_question_input
from .settings import Settings
from .textutils import claim_context, localizar, parse_questions

logger = logging.getLogger(__name__)

DTYPES = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}


def tamanho_dos_pesos(caminho: str) -> int:
    """Size in bytes of the weight files of a local checkpoint. Zero if not a path."""
    pasta = Path(caminho)
    if not pasta.is_dir():
        return 0
    return sum(
        f.stat().st_size
        for padrao in ("*.safetensors", "*.bin")
        for f in pasta.glob(padrao)
    )


def parametros_de_geracao(config: dict) -> dict:
    """The evaluation's `generate()` arguments for a generation config."""
    parametros = {
        "max_new_tokens": config.get("max_new_tokens", 192),
        "do_sample": bool(config.get("do_sample", False)),
        "num_beams": config.get("num_beams", 1),
        "repetition_penalty": config.get("repetition_penalty", 1.0),
        "use_cache": True,
    }
    if config.get("no_repeat_ngram_size"):
        parametros["no_repeat_ngram_size"] = config["no_repeat_ngram_size"]
    for chave in ("eos_token_id", "pad_token_id"):
        if config.get(chave) is not None:
            parametros[chave] = config[chave]
    return parametros


class QuestionGenerator(ModeloMovel):
    # GPU memory a call needs beyond the weights: the attention cache of up to 2048 tokens
    # (prompt and answer) and the 4-bit layers unpacked one at a time.
    folga = int(0.5e9)
    descricao = "o gerador de perguntas"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._tokenizer = None
        self._geracao: dict = {}
        self._max_entrada = 0
        self._motivo = ""

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def motivo(self) -> str:
        """Why the model is not loaded, when it is not."""
        return self._motivo

    def _recusar(self, motivo: str) -> None:
        self._motivo = motivo
        logger.error("modelo de geração de perguntas não carregado: %s", motivo)

    def load(self) -> None:
        caminho = self._settings.qg_model_path
        adaptador = self._settings.qg_adapter_path
        if not caminho:
            return self._recusar("QG_MODEL_PATH por definir")
        # Without the adapter the base model would answer, and answer something else.
        ficha_caminho = Path(adaptador) / "checkpoint_info.json" if adaptador else None
        if ficha_caminho is None or not ficha_caminho.exists():
            return self._recusar(f"adaptador em falta ou sem checkpoint_info.json: {adaptador!r}")
        ficha = json.loads(ficha_caminho.read_text(encoding="utf-8"))
        if ficha.get("prompt_version") != PROMPT_VERSION:
            return self._recusar(
                f"o adaptador foi treinado com a prompt {ficha.get('prompt_version')!r}, "
                f"e este serviço constrói a {PROMPT_VERSION!r}"
            )

        dispositivo = escolher(self._settings.device)
        base = ficha.get("carregar_base") or {}
        dtype = DTYPES[base.get("bnb_4bit_compute_dtype", "bfloat16")]
        na_gpu = dispositivo.startswith("cuda")
        quantizado = bool(base.get("load_in_4bit")) and na_gpu

        # Off CUDA the weights go to main memory. Loading more than the machine holds does not
        # raise: it swaps for minutes and the container dies mid-generation.
        if not na_gpu:
            precisa = tamanho_dos_pesos(caminho)
            livre = memoria_disponivel()
            if precisa and livre is not None and livre < precisa * MARGEM_RAM:
                return self._recusar(
                    f"o modelo precisa de cerca de {precisa / 1e9:.0f} GB e só há "
                    f"{livre / 1e9:.1f} GB disponíveis neste contentor"
                )
            if base.get("load_in_4bit"):
                logger.warning(
                    "sem CUDA não há quantização de 4 bits: o modelo carrega em %s, em %s, "
                    "e não é a aritmética em que foi avaliado", dtype, dispositivo,
                )

        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        argumentos: dict = {"dtype": dtype}
        if quantizado:
            from transformers import BitsAndBytesConfig

            argumentos["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type=base.get("bnb_4bit_quant_type", "nf4"),
                bnb_4bit_use_double_quant=bool(base.get("bnb_4bit_use_double_quant", True)),
                bnb_4bit_compute_dtype=dtype,
            )
            # The whole model on one GPU, as in training.
            argumentos["device_map"] = {"": torch.device(dispositivo).index or 0}

        tokenizer = AutoTokenizer.from_pretrained(caminho, use_fast=True)
        antes = alocada()
        modelo = AutoModelForCausalLM.from_pretrained(caminho, **argumentos)
        if quantizado:
            from peft import prepare_model_for_kbit_training

            # The adapter was trained and evaluated over a base prepared this way (the layers
            # left unquantised in float32); without it the same weights write other questions.
            modelo = prepare_model_for_kbit_training(modelo, use_gradient_checkpointing=False)
        modelo = PeftModel.from_pretrained(modelo, adaptador)
        if not quantizado:
            modelo = modelo.to(dispositivo)
        modelo.config.use_cache = True

        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        self._tokenizer = tokenizer
        self._geracao = parametros_de_geracao(ficha.get("generation_config") or {})
        # A decoder's prompt was fitted to max_seq_length in training and evaluation.
        self._max_entrada = int(ficha["max_seq_length"])
        self._model = modelo.eval()
        self._casa = dispositivo
        self._na_gpu = na_gpu
        self.ocupa = alocada() - antes
        self._motivo = ""
        logger.info("modelo de geração de perguntas carregado: %s + %s em %s (geração: %s)",
                    caminho, adaptador, dispositivo, self._geracao)

    def _n_tokens(self, texto: str) -> int:
        return len(self._tokenizer(texto, add_special_tokens=True)["input_ids"])

    def _entrada(self, claim_span: str, publication_time: str, context: str) -> str:
        """The prompt with the ±1 sentence window, fitted to the model window minus the room
        the answer needs. A window that does not fit is cut by characters around the claim."""
        janela = claim_context(context, claim_span)
        entrada = build_question_input(claim_span, publication_time, janela)
        orcamento = max(32, self._max_entrada - self._geracao["max_new_tokens"])
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

    @torch.inference_mode()
    def generate(self, claim_span: str, publication_time: str, context: str) -> list[str]:
        if not self.loaded:
            raise RuntimeError("modelo de geração de perguntas não carregado")

        entrada = self._entrada(claim_span, publication_time, context)
        tokens = self._tokenizer(
            entrada, return_tensors="pt", truncation=True, max_length=self._max_entrada
        )
        tokens = {chave: valor.to(self._model.device) for chave, valor in tokens.items()}
        saida = self._model.generate(**tokens, **self._geracao)
        novos = saida[0][tokens["input_ids"].shape[1] :]
        bruto = self._tokenizer.decode(novos, skip_special_tokens=True).strip()
        return parse_questions(bruto)
