"""Is this LUSA news item relevant to the claim?

The input is the training one (`Document Relevance and Claim-Evidence Entailment/src/entradas.py`): premise = headline +
". " + body cut at 380 words, hypothesis = the claim span, in this order, truncated at 512 tokens.
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch

from .dispositivo import escolher
from .gpu import ModeloMovel, bytes_de, copia_propria
from .settings import Settings

logger = logging.getLogger(__name__)

# The training budget for the document, which leaves the claim room inside the 512 tokens.
MAX_PALAVRAS_DOCUMENTO = 380
MAX_TOKENS = 512

CLASSES = ("relevante", "irrelevante")


def premissa(headline: str, content: str) -> str:
    """Headline followed by the body, cut at `MAX_PALAVRAS_DOCUMENTO` words."""
    topo = (headline or "").strip()
    corpo = " ".join((content or "").split()[:MAX_PALAVRAS_DOCUMENTO])
    return (topo + ". " + corpo).strip(" .") if topo else corpo.strip()


def hipotese(claim: str) -> str:
    """The claim span without edge spaces and dots; inner spacing is kept."""
    return (claim or "").strip(" .").strip()


# GPU memory a call needs beyond the weights, per news item in a batch of 512 tokens: measured
# 0.14 GB for a batch of 8.
POR_DOCUMENTO = int(25e6)


class RelevanceClassifier(ModeloMovel):
    descricao = "o classificador de relevância"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._tokenizer = None
        # Why the model is not loaded, when it is not.
        self.motivo = ""
        self._indice_para_classe: dict[int, str] = {}

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def folga(self) -> int:
        return max(1, self._settings.relevance_batch_size) * POR_DOCUMENTO

    def load(self) -> None:
        caminho = self._settings.relevance_model_path
        if not caminho or not Path(caminho).exists():
            self.motivo = f"RELEVANCE_MODEL_PATH por definir ou inexistente: {caminho!r}"
            logger.warning("relevância sem checkpoint: %s", self.motivo)
            return

        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(caminho, use_fast=True)
        # float32, the training precision.
        modelo = AutoModelForSequenceClassification.from_pretrained(caminho, dtype=torch.float32)
        # Class order is read from the checkpoint: swapping it would silently keep the
        # irrelevant items and drop the relevant ones.
        id2label = modelo.config.id2label or {}
        mapa = {int(i): str(nome).strip().lower() for i, nome in id2label.items()}
        if sorted(mapa.values()) != sorted(CLASSES):
            raise RuntimeError(
                f"classes do checkpoint de relevância não reconhecidas: id2label={id2label}"
            )

        dispositivo = escolher(self._settings.device)
        # On CUDA it waits in main memory, in a copy of its own, and goes to the GPU when it is
        # first asked for, with room made for it (`gpu.py`).
        no_cuda = dispositivo.startswith("cuda")
        self._model = (copia_propria(modelo) if no_cuda else modelo.to(dispositivo)).eval()
        self._casa = dispositivo
        self.ocupa = bytes_de(modelo)
        self._tokenizer = tokenizer
        self._indice_para_classe = mapa
        logger.info("classificador de relevância carregado: %s em %s (classes %s)",
                    caminho, dispositivo, mapa)

    @torch.inference_mode()
    def classify(self, claim: str, documentos: list[dict]) -> list[dict]:
        """Relevance of each news item: the argmax of the logits (the checkpoint's decision
        rule, tau = 0)."""
        if not self.loaded:
            raise RuntimeError("classificador de relevância não carregado")

        hipo = hipotese(claim)
        resultados: list[dict] = []
        tamanho = max(1, self._settings.relevance_batch_size)
        for inicio in range(0, len(documentos), tamanho):
            lote = documentos[inicio : inicio + tamanho]
            tokens = self._tokenizer(
                [premissa(d.get("headline", ""), d.get("content", "")) for d in lote],
                [hipo] * len(lote),
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=MAX_TOKENS,
            )
            tokens = {chave: valor.to(self._model.device) for chave, valor in tokens.items()}
            logits = self._model(**tokens).logits.float().cpu()

            for posicao, documento in enumerate(lote):
                classe = self._indice_para_classe[int(logits[posicao].argmax())]
                resultados.append(
                    {
                        "doc_id": documento.get("doc_id", ""),
                        "relevant": classe == "relevante",
                    }
                )
        return resultados
