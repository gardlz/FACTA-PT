"""Fine-tuning of one configuration-selection run (one fold of one seed).

AdamW with linear warm-up/decay built once for 20 epochs, early stopping on the inner development
set, then tau chosen on that same set. The excluded fold is never predicted.
"""

import math
import random

import torch
import torch.nn as nn

import entradas as ent
import metricas as met

CLASSES_RELEVANCIA = ("relevante", "irrelevante")
CLASSES_ENTAILMENT = ("supported", "refuted", "nei_relevante")
NLI_PARA_NOSSO = {"entailment": "supported", "contradiction": "refuted", "neutral": "nei_relevante"}

EPOCAS_MAX = 20
PACIENCIA = 5
TAUS = (0.0, 0.25, 0.5, 0.75, 1.0)
WARMUP = 0.10


# Memory-saving options (best-epoch snapshot on the CPU, inference batches of LOTE_INFERENCIA;
# per model, gradient checkpointing and/or `AdamWNaCPU`).
# They change where and in which order floating-point operations run, not what is computed.
LOTE_INFERENCIA = 8


class AdamWNaCPU:
    """`torch.optim.AdamW` with the master weights and moments on the CPU, in float32."""

    def __init__(self, modelo, lr, weight_decay):
        self.gpu = [p for p in modelo.parameters() if p.requires_grad]
        self.cpu = [p.detach().to("cpu", copy=True).requires_grad_(True) for p in self.gpu]
        self.interno = torch.optim.AdamW(self.cpu, lr=lr, weight_decay=weight_decay, fused=True)

    @property
    def param_groups(self):
        return self.interno.param_groups

    def step(self):
        for g, c in zip(self.gpu, self.cpu):
            c.grad = None if g.grad is None else g.grad.detach().to("cpu")
        self.interno.step()
        with torch.no_grad():
            for g, c in zip(self.gpu, self.cpu):
                g.copy_(c)

    def zero_grad(self, set_to_none=True):
        for p in self.gpu:
            p.grad = None
        for p in self.cpu:
            p.grad = None


def libertar_gpu():
    import gc
    gc.collect()
    torch.cuda.empty_cache()


def optimizador(modelo, lr, weight_decay, poupar=False):
    if not poupar:
        return torch.optim.AdamW(modelo.parameters(), lr=lr, weight_decay=weight_decay)
    return AdamWNaCPU(modelo, lr, weight_decay)


def scheduler_de(opt, factor):
    return torch.optim.lr_scheduler.LambdaLR(getattr(opt, "interno", opt), factor)


def ligar_checkpointing(modelo):
    modelo.encoder.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={"use_reentrant": False})


def semear(seed):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def classes_de(tarefa):
    return {"relevance": CLASSES_RELEVANCIA, "entailment": CLASSES_ENTAILMENT}[tarefa]


def alvo_de(exemplo, tarefa):
    """Label in the task's scheme: relevance maps every relevant label to `relevante`."""
    if tarefa == "relevance":
        return "irrelevante" if exemplo["rotulo4"] == "nei_irrelevante" else "relevante"
    return exemplo["rotulo4"]


def mapa_do_checkpoint(config, classes=CLASSES_ENTAILMENT):
    """{our class index: checkpoint index} read from id2label; None if not a 3-way NLI head."""
    id2label = {int(k): str(v).lower() for k, v in (getattr(config, "id2label", None) or {}).items()}
    if len(id2label) != 3:
        return None
    nosso = {}
    for i, nome in id2label.items():
        for chave, destino in NLI_PARA_NOSSO.items():
            if nome.startswith(chave[:4]) or chave.startswith(nome[:4]):
                nosso[destino] = i
    if len(nosso) != 3:
        return None
    return {classes.index(c): i for c, i in nosso.items()}


class Modelo(nn.Module):
    """Encoder plus task head; every parameter is fine-tuned."""

    def __init__(self, nome, n_classes, preservar_cabeca=False, max_len=512, seed=42):
        super().__init__()
        from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(nome)
        if max_len:
            # some tokenizers declare a shorter model_max_length (one declares 128)
            self.tok.model_max_length = max(self.tok.model_max_length or 0, max_len)

        crua = AutoConfig.from_pretrained(nome)
        # an NLI head can only be reused when the task also has three outputs
        lido = mapa_do_checkpoint(crua) if n_classes == 3 else None
        self.mapa = lido if (preservar_cabeca and lido) else None
        self.id2label_original = dict(getattr(crua, "id2label", None) or {})

        # float32 for every model: transformers 5 loads the dtype a checkpoint declares, and
        # pure fp16 training with AdamW turns the weights into nan at the first step
        base = AutoModelForSequenceClassification.from_pretrained(
            nome, num_labels=n_classes, ignore_mismatched_sizes=True, dtype=torch.float32)
        # `dtype=` leaves some buffers in the stored dtype (e.g. DeBERTa relative positions)
        base = base.to(torch.float32)

        dono, atributo, velha = self._cabeca(base)
        saidas = getattr(velha, "out_features", None)
        largura = getattr(velha, "in_features", None) or base.config.hidden_size
        tipo = velha.weight.dtype if hasattr(velha, "weight") else torch.float32

        # The head is always rebuilt: with `self.mapa` the checkpoint rows are copied in our
        # class order; otherwise it is a fresh N(0, 0.02) head from a seeded generator.
        g = torch.Generator().manual_seed(seed)
        nova = nn.Linear(largura, n_classes, dtype=tipo,
                         bias=getattr(velha, "bias", None) is not None)
        with torch.no_grad():
            nova.weight.copy_(torch.empty(n_classes, largura).normal_(0, 0.02, generator=g))
            if nova.bias is not None:
                nova.bias.zero_()
            if self.mapa and velha is not None and hasattr(velha, "weight") and saidas == 3:
                for destino, origem in self.mapa.items():
                    nova.weight[destino] = velha.weight[origem]
                    if nova.bias is not None and getattr(velha, "bias", None) is not None:
                        nova.bias[destino] = velha.bias[origem]
        setattr(dono, atributo, nova)
        base.config.num_labels = n_classes
        self.encoder = base
        self.cabeca_preservada = bool(self.mapa)

    @staticmethod
    def _cabeca(base):
        for atributo in ("classifier", "score", "cls"):
            alvo = getattr(base, atributo, None)
            if alvo is None:
                continue
            if isinstance(alvo, nn.Linear):
                return base, atributo, alvo
            lineares = [(m, n) for n, m in alvo.named_modules() if isinstance(m, nn.Linear)]
            if lineares:
                m, n = lineares[-1]
                dono = alvo
                for parte in n.split(".")[:-1]:
                    dono = getattr(dono, parte)
                return dono, n.split(".")[-1], m
        raise SystemExit(f"cabeça de classificação não encontrada em {type(base).__name__}")

    def forward(self, **x):
        return self.encoder(**x).logits


def preparar(exemplos, tarefa, tok, max_len):
    """Tokenises (premise, hypothesis) pairs, padded over the whole set, plus the targets."""
    classes = classes_de(tarefa)
    indice = {c: i for i, c in enumerate(classes)}
    if tarefa == "relevance":
        textos = [ent.construir(p) for p in exemplos]
    else:
        textos = [(p["evidencia_texto"], ent.hipotese(p)) for p in exemplos]
    x = tok([a for a, _ in textos], [b for _, b in textos], padding=True, truncation=True,
            max_length=max_len, return_tensors="pt")
    y = torch.tensor([indice[alvo_de(p, tarefa)] for p in exemplos])
    return x, y, classes


def ajustar_logits(logits, priors, tau):
    """Logit adjustment: z'_c = z_c - tau * log(pi_c)."""
    if tau == 0:
        return logits
    return logits - tau * torch.log(priors.clamp_min(1e-8)).to(logits.device)


def _macro(verdade, previsto, classes):
    pc = met.f1_por_classe(verdade, previsto, classes)
    return sum(pc[c]["f1"] for c in classes) / len(classes)


def treinar_fold(treino, dev, aval, tarefa, cfg):
    """One run: early stopping and tau on the inner development set; returns its diary."""
    semear(cfg["seed"])
    classes = classes_de(tarefa)
    n_classes = len(classes)

    modelo = Modelo(cfg["modelo"], n_classes,
                    preservar_cabeca=cfg.get("preservar_cabeca", False),
                    max_len=cfg["max_len"],
                    seed=cfg["seed"]).cuda()
    if cfg.get("checkpointing"):
        ligar_checkpointing(modelo)

    x_tr, y_tr, _ = preparar(treino, tarefa, modelo.tok, cfg["max_len"])
    x_dv, y_dv, _ = preparar(dev, tarefa, modelo.tok, cfg["max_len"])

    conta = torch.bincount(y_tr, minlength=n_classes).float()
    priors = conta / conta.sum()

    opt = optimizador(modelo, cfg["lr"], 0.01, cfg.get("adamw_cpu", False))

    # built once for the 20-epoch horizon; steps after an early stop are simply not run
    por_epoca = max(1, math.ceil(len(y_tr) / cfg["batch"]))
    passos_max = por_epoca * EPOCAS_MAX
    aquecimento = max(1, int(WARMUP * passos_max))

    def factor(passo):
        if passo < aquecimento:
            return passo / max(1, aquecimento)
        return max(0.0, (passos_max - passo) / max(1, passos_max - aquecimento))

    sched = scheduler_de(opt, factor)

    verdade_dv = [classes[i] for i in y_dv]

    def logits_de(x, lote=LOTE_INFERENCIA):
        modelo.eval()
        saida = []
        with torch.no_grad():
            for i in range(0, x["input_ids"].shape[0], lote):
                bloco = {k: v[i:i + lote].cuda() for k, v in x.items()}
                saida.append(modelo(**bloco).float().cpu())
        modelo.train()
        return torch.cat(saida)

    melhor = {"macro": -1.0, "estado": None, "epoca": 0}
    sem_melhorar, executadas, motivo = 0, 0, "max_epocas"
    n = len(y_tr)

    for epoca in range(1, EPOCAS_MAX + 1):
        modelo.train()
        ordem = torch.randperm(n)
        for i in range(0, n, cfg["batch"]):
            idx = ordem[i:i + cfg["batch"]]
            bloco = {k: v[idx].cuda() for k, v in x_tr.items()}
            logits = modelo(**bloco)
            perda = nn.functional.cross_entropy(logits.float(), y_tr[idx].cuda())
            perda.backward()
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
        executadas = epoca

        prev_dv = [classes[i] for i in logits_de(x_dv).argmax(-1)]
        macro_dv = _macro(verdade_dv, prev_dv, classes)

        # strict `>`: an exact tie keeps the earlier epoch
        if macro_dv > melhor["macro"]:
            melhor = {"macro": macro_dv, "epoca": epoca,
                      "estado": {k: v.detach().to("cpu", copy=True)
                                 for k, v in modelo.state_dict().items()}}
            sem_melhorar = 0
        else:
            sem_melhorar += 1
            if sem_melhorar >= PACIENCIA:
                motivo = "early_stopping"
                break

    if melhor["estado"]:
        modelo.load_state_dict(melhor["estado"])

    # tau with the weights fixed, on the same development set; strict `>` keeps the lower tau
    lg_dv = logits_de(x_dv)
    melhor_tau, melhor_val = TAUS[0], -1.0
    for tau in TAUS:
        prev = [classes[i] for i in ajustar_logits(lg_dv, priors, tau).argmax(-1)]
        v = _macro(verdade_dv, prev, classes)
        if v > melhor_val:
            melhor_val, melhor_tau = v, tau

    diario = {
        "melhor_epoca": melhor["epoca"], "epocas_executadas": executadas,
        "melhor_macro_dev": round(melhor["macro"], 6), "motivo_paragem": motivo,
        "tau": melhor_tau,
        "cabeca_preservada": modelo.cabeca_preservada,
        "id2label_original": modelo.id2label_original,
        "n_treino": len(treino), "n_dev": len(dev), "n_aval": len(aval),
    }
    del modelo
    torch.cuda.empty_cache()
    return diario


# --------------------------------------------------------------------------------------------- #
# One repetition, fold by fold, so that `correr.py` can save each fold as soon as it closes
# --------------------------------------------------------------------------------------------- #

def dividir_fold(exemplos, particao, i, grupo_de, cfg):
    """(train, dev, excluded fold, dev groups) of fold `i`; None if that fold is empty."""
    fora = set(particao[i])
    aval = [p for p in exemplos if grupo_de[p["span_id"]] in fora]
    if not aval:
        return None
    resto = sorted({grupo_de[p["span_id"]] for p in exemplos
                    if grupo_de[p["span_id"]] not in fora})
    rnd = random.Random(cfg["seed"] * 100 + i)
    rnd.shuffle(resto)
    n_dev = max(1, round(0.20 * len(resto)))
    dev_grupos = set(resto[:n_dev])
    treino = [p for p in exemplos if grupo_de[p["span_id"]] not in fora
              and grupo_de[p["span_id"]] not in dev_grupos]
    dev = [p for p in exemplos if grupo_de[p["span_id"]] in dev_grupos]
    if not dev or not treino:
        raise SystemExit(f"fold {i}: treino {len(treino)} dev {len(dev)} — divisão inválida")
    return treino, dev, aval, sorted(dev_grupos)


def imprimir_fold(diario, nota=""):
    print(f"    fold {diario['fold']}: treino {diario['n_treino']} · dev {diario['n_dev']} · "
          f"aval {diario['n_aval']} · melhor época {diario['melhor_epoca']}/"
          f"{diario['epocas_executadas']} ({diario['motivo_paragem']}) · "
          f"dev {diario['melhor_macro_dev']:.4f} · tau {diario['tau']}{nota}", flush=True)


def correr_fold(divisao, i, tarefa, cfg):
    """Trains fold `i` and returns it as a record: the excluded-fold ids and the diary."""
    treino, dev, aval, grupos_dev = divisao
    diario = treinar_fold(treino, dev, aval, tarefa, cfg)
    libertar_gpu()
    diario["fold"] = i
    diario["grupos_dev"] = grupos_dev
    imprimir_fold(diario)
    return {"fold": i, "ids": [p["id"] for p in aval], "diario": diario}


def juntar_folds(folds):
    """The diaries of one repetition, in fold order."""
    return [f["diario"] for f in folds]


def correr_cv(exemplos, particao, grupo_de, cfg, fazer):
    """One repetition: every fold excluded once; `fazer(i, divisao)` returns fold i's record."""
    folds = []
    for i in range(len(particao)):
        divisao = dividir_fold(exemplos, particao, i, grupo_de, cfg)
        if divisao is not None:
            folds.append(fazer(i, divisao))
    return juntar_folds(folds)
