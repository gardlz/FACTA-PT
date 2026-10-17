"""Citation support judge: an NLI classifier (MoritzLaurer/bge-m3-zeroshot-v2.0 by default).

Decides whether the cited evidence (premise) entails an article sentence (hypothesis). Pairs are sent
exactly as written and never truncated; decisions are cached on everything that can change them.
"""

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import cache as cache_mod
from . import config

REGRA_DE_DECISAO = "argmax(entailment, not_entailment); support = classe prevista é «entailment»"


def classe_de_entailment(rotulo: str) -> bool:
    """True if the label names the entailment class (exact match, so "not_entailment" never counts)."""
    r = str(rotulo).strip().lower().replace("-", "_").replace(" ", "_")
    return r in ("entailment", "entailed", "entails")


# --------------------------------------------------------------------------- backend
class BackendNLI:
    """An NLI classifier run with transformers, loaded on first use."""

    def __init__(self, model_id: str, revision: Optional[str] = None,
                 batch_size: int = config.CITATION_JUDGE_BATCH):   # only changes batching, not decisions
        self.model_id, self.revision, self.batch_size = model_id, revision, batch_size
        self.device: Optional[str] = None                          # cuda / mps / cpu, chosen on load
        self._tok = self._modelo = None
        self.classe_entailment: Optional[int] = None
        self.limite: Optional[int] = None

    def _carregar(self):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        # public checkpoint: token=False never sends a locally stored Hugging Face token
        self._tok = AutoTokenizer.from_pretrained(self.model_id, revision=self.revision, token=False)
        self._modelo = AutoModelForSequenceClassification.from_pretrained(
            self.model_id, revision=self.revision, token=False)
        self.device = self.device or ("cuda" if torch.cuda.is_available() else
                                      "mps" if torch.backends.mps.is_available() else "cpu")
        self._modelo.to(self.device).eval()
        # class order comes from config.json (id2label), never assumed
        rotulos = {int(i): str(r).lower() for i, r in self._modelo.config.id2label.items()}
        classes = [i for i, r in rotulos.items() if classe_de_entailment(r)]
        if len(classes) != 1:
            raise ValueError(f"{self.model_id}: o config.json tem de identificar exatamente uma classe de "
                             f"entailment ({rotulos})")
        self.classe_entailment = classes[0]
        self.limite = limite_real(self._modelo.config)

    @property
    def identidade(self) -> dict:
        """What determines the model's output (part of the cache key)."""
        # config.NLI_MAX_LENGTH stands in until the checkpoint loads, so it must equal the real limit
        return {"model": self.model_id, "revision": self.revision,
                "max_length": self.limite or config.NLI_MAX_LENGTH}

    def n_tokens(self, premissa: str, hipotese: str) -> int:
        if self._tok is None:
            self._carregar()
        return len(self._tok(premissa, hipotese, truncation=False)["input_ids"])      # includes special tokens

    def classificar(self, pares: Sequence[Tuple[str, str]]) -> List[dict]:
        import torch
        if self._modelo is None:
            self._carregar()
        saida = []
        for a in range(0, len(pares), self.batch_size):
            lote = pares[a:a + self.batch_size]
            enc = self._tok([p for p, _ in lote], [h for _, h in lote], truncation=False, padding=True,
                            return_tensors="pt").to(self.device)
            with torch.no_grad():
                probs = torch.softmax(self._modelo(**enc).logits, dim=-1).tolist()
            for linha in probs:
                # argmax; an exact tie goes to the lowest class index
                classe = max(range(len(linha)), key=lambda i: linha[i])
                saida.append({"entailed": classe == self.classe_entailment})
        return saida


def limite_real(cfg) -> int:
    """Real token limit of the checkpoint: its position embeddings, not the tokenizer's `model_max_length`."""
    mpe = getattr(cfg, "max_position_embeddings", None) or config.NLI_MAX_LENGTH
    if getattr(cfg, "model_type", "") in ("xlm-roberta", "roberta", "camembert"):
        # RoBERTa-style position ids start at pad_token_id + 1
        return mpe - (getattr(cfg, "pad_token_id", 1) or 1) - 1
    return mpe


# --------------------------------------------------------------------------- judge
class JuizNLI:
    """Decides (premise, hypothesis) pairs through a cache; an overlength pair gets support None, never 0."""

    def __init__(self, backend, cache_path: Optional[Path] = None):
        self.backend = backend
        self.cache = cache_mod.CacheJSONL(cache_path)
        self.contagem = {"pedidas": 0, "do_cache": 0, "ao_modelo": 0, "overlength": 0}

    def metadados(self) -> dict:
        """Judge identity hashed into every cache key: model, revision, token limit and decision rule."""
        return {"evaluator_model": self.backend.model_id, "evaluator_revision": self.backend.revision,
                "max_length": self.backend.identidade["max_length"], "decision_rule": REGRA_DE_DECISAO}

    def chave(self, premissa_enviada: str, hipotese_enviada: str) -> str:
        return cache_mod.chave(self.backend.model_id,
                               {**self.metadados(), "premise_sent": premissa_enviada,
                                "hypothesis_sent": hipotese_enviada})

    def decidir(self, pares: Sequence[Tuple[str, str]]) -> List[dict]:
        if not pares:
            return []
        chaves = [self.chave(p, h) for p, h in pares]
        self.contagem["pedidas"] += len(pares)
        ja = {k for k in chaves if k in self.cache}                 # cached before this call
        faltam = list(dict.fromkeys(k for k in chaves if k not in ja))
        por_chave = dict(zip(chaves, pares))
        cabem = []
        for k in faltam:
            p, h = por_chave[k]
            if self.backend.n_tokens(p, h) > self.backend.identidade["max_length"]:
                # never truncated: left unresolved as "overlength"
                self.cache.put(k, {"status": "overlength", "support": None})
            else:
                cabem.append((k, p, h))
        if cabem:
            saidas = self.backend.classificar([(p, h) for _, p, h in cabem])
            for (k, _, _), s in zip(cabem, saidas):
                self.cache.put(k, {"status": "ok", "support": 1 if s["entailed"] else 0})
        self.contagem["ao_modelo"] += len(cabem)
        self.contagem["do_cache"] += sum(k in ja for k in chaves)
        saida = []
        for k in chaves:
            reg = self.cache.get(k)
            self.contagem["overlength"] += reg["status"] == "overlength"
            saida.append(reg)
        return saida


# --------------------------------------------------------------------------- built from config
def _backend_de(spec: Dict[str, str], batch_size: int = config.CITATION_JUDGE_BATCH):
    return BackendNLI(spec["model_id"], spec.get("revision"), batch_size=batch_size)


def juiz_configurado(cache_path: Optional[Path] = None, batch_size: int = config.CITATION_JUDGE_BATCH) -> JuizNLI:
    """The judge set in `config.CITATION_SUPPORT_JUDGE`."""
    return JuizNLI(_backend_de(config.CITATION_SUPPORT_JUDGE, batch_size), cache_path)
