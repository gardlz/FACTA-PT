"""The relation between the claim and each three-sentence passage.

Premise = passage (the evidence), hypothesis = claim, in this order. Class order is read from
the checkpoint's config.json, never assumed: the wrong position silently swaps supported with
refuted.
"""

from __future__ import annotations

import logging
import torch

from . import checkpoint
from .dispositivo import escolher
from .gpu import ModeloMovel, bytes_de, copia_propria
from .relevance import hipotese
from .settings import Settings

logger = logging.getLogger(__name__)

MAX_TOKENS = 512
LABELS = ("supported", "refuted", "nei")
# The checkpoint's class names. `nei_relevante` is the interface's `nei`: training told it
# apart from irrelevant evidence, which never reaches this stage.
CLASSES_DO_CHECKPOINT = {"supported": "supported", "refuted": "refuted", "nei_relevante": "nei"}


# GPU memory a call needs beyond the weights, per passage in a batch of 512 tokens: measured
# 0.37 GB for a batch of 16.
POR_EXCERTO = int(30e6)


class StanceClassifier(ModeloMovel):
    descricao = "o classificador da relação"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._tokenizer = None
        # Why the model is not loaded, when it is not.
        self.motivo = ""
        self._indice_para_rotulo: dict[int, str] = {}

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def folga(self) -> int:
        return max(1, self._settings.stance_batch_size) * POR_EXCERTO

    def load(self) -> None:
        caminho = self._settings.stance_model_path
        if not caminho:
            self.motivo = "STANCE_MODEL_PATH por definir"
            logger.warning("classificador sem checkpoint: %s", self.motivo)
            return

        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        caminho = str(checkpoint.pasta(caminho, self._settings.stance_model_revision))
        tokenizer = AutoTokenizer.from_pretrained(caminho, use_fast=True)
        # float32, the training precision.
        modelo = AutoModelForSequenceClassification.from_pretrained(caminho, dtype=torch.float32)
        id2label = modelo.config.id2label or {}
        mapa = {
            int(indice): CLASSES_DO_CHECKPOINT.get(str(nome).strip().lower())
            for indice, nome in id2label.items()
        }
        if sorted(mapa.values(), key=str) != sorted(LABELS):
            raise RuntimeError(
                f"não foi possível mapear as classes do checkpoint {caminho}: id2label={id2label}"
            )

        dispositivo = escolher(self._settings.device)
        # On CUDA it waits in main memory, in a copy of its own, and goes to the GPU when it is
        # first asked for, with room made for it (`gpu.py`).
        no_cuda = dispositivo.startswith("cuda")
        self._model = (copia_propria(modelo) if no_cuda else modelo.to(dispositivo)).eval()
        self._casa = dispositivo
        self.ocupa = bytes_de(modelo)
        self._tokenizer = tokenizer
        self._indice_para_rotulo = mapa
        logger.info("classificador carregado: %s em %s (classes %s)", caminho, dispositivo, mapa)

    @torch.inference_mode()
    def classify(self, claim: str, excerpts: list[dict]) -> list[dict]:
        """Label and adjusted logits of each passage.

        The decision rule is the argmax of the adjusted logits z'_c = z_c - tau * log(pi_c).
        This checkpoint was selected with tau = 0, so z' = z: the logits are returned as they
        come out of the model, and the label is their argmax.
        """
        if not self.loaded:
            raise RuntimeError("classificador não carregado")

        hipo = hipotese(claim)
        resultados: list[dict] = []
        tamanho = max(1, self._settings.stance_batch_size)
        for inicio in range(0, len(excerpts), tamanho):
            lote = excerpts[inicio : inicio + tamanho]
            tokens = self._tokenizer(
                [e["text"] for e in lote],
                [hipo] * len(lote),
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=MAX_TOKENS,
            )
            tokens = {chave: valor.to(self._model.device) for chave, valor in tokens.items()}
            logits = self._model(**tokens).logits.float().cpu()

            for posicao, excerto in enumerate(lote):
                por_rotulo = {
                    rotulo: float(logits[posicao, indice])
                    for indice, rotulo in self._indice_para_rotulo.items()
                }
                resultados.append(
                    {
                        "id": excerto["id"],
                        "label": self._indice_para_rotulo[int(logits[posicao].argmax())],
                        "logits": {rotulo: por_rotulo[rotulo] for rotulo in LABELS},
                    }
                )
        return resultados
