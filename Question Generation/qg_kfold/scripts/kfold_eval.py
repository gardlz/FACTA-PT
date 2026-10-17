"""Per-epoch evaluation on the gold dev fold and per-step learning-rate log (Trainer callbacks).

At the end of every epoch the dev questions are generated and scored with `src/metrics.py`;
the epoch is chosen afterwards by `aggregate_folds.py`. BERTScore runs on CPU by default.
"""

import json
from pathlib import Path
from typing import Callable, List, Optional

RAIZ = Path(__file__).resolve().parents[2]


def _importa_metricas():
    import sys
    if str(RAIZ / "src") not in sys.path:
        sys.path.insert(0, str(RAIZ / "src"))
    from metrics import evaluate_items, summarize, to_item
    return to_item, evaluate_items, summarize


def avalia_dev(dev_examples: List[dict], geracoes: List[tuple], *, modelo: str,
               config: str, arquitetura: str, device: Optional[str]) -> dict:
    """Metric summary (means over the claim spans) of an already generated dev fold."""
    to_item, evaluate_items, summarize = _importa_metricas()
    linhas = []
    for ex, (perguntas, raw) in zip(dev_examples, geracoes):
        linhas.append({
            "id": ex.get("id", ""), "claim_span": ex.get("claim_span", ""),
            "context": ex.get("context", ""), "publication_time": ex.get("publication_time", ""),
            "reference_questions": ex.get("reference_questions", []),
            "generated_questions": perguntas, "raw_output": raw,
            "model_short_name": modelo, "train_setting": config,
            "regime": "fine_tuning", "architecture": arquitetura,
        })
    itens = [to_item(l) for l in linhas]
    registos = evaluate_items(itens, device=device)
    return summarize(registos)[0] if registos else {}


def constroi_callback_lr(*, modelo: str, config: str, fold: int, arquitetura: str,
                         destino: Path, horizonte: Optional[int] = None):
    """Callback that logs the scheduler learning rate at every optimisation step.

    The file name carries the horizon, so a 30-epoch rerun does not overwrite the
    20-epoch curve; it is rewritten at the end of every epoch.
    """
    from transformers import TrainerCallback

    destino.mkdir(parents=True, exist_ok=True)
    sufixo = f"__h{horizonte}" if horizonte else ""
    ficheiro = (destino /
                f"{config}__{arquitetura}__{modelo}__fold{fold}{sufixo}__lr_por_step.jsonl")

    class RegistaLR(TrainerCallback):
        def __init__(self):
            self.passos = []

        def on_step_end(self, args, state, control, **kwargs):
            scheduler = kwargs.get("lr_scheduler")
            optimizer = kwargs.get("optimizer")
            if scheduler is not None:
                lr = float(scheduler.get_last_lr()[0])
            elif optimizer is not None:
                lr = float(optimizer.param_groups[0]["lr"])
            else:
                return
            self.passos.append({"modelo": modelo, "config": config, "fold": fold,
                                "horizonte": horizonte,
                                "step": int(state.global_step),
                                "epoch": round(float(state.epoch or 0), 4),
                                "learning_rate": lr})

        def _grava(self):
            with ficheiro.open("w", encoding="utf-8") as f:
                for linha in self.passos:
                    f.write(json.dumps(linha, ensure_ascii=False) + "\n")

        def on_epoch_end(self, args, state, control, **kwargs):
            self._grava()

        def on_train_end(self, args, state, control, **kwargs):
            self._grava()

    return RegistaLR()


def constroi_callback(*, dev_examples: List[dict], gerar: Callable, modelo: str, config: str,
                      fold: int, arquitetura: str, destino: Path,
                      device_metricas: Optional[str], training_meta: Optional[dict] = None):
    """Callback that evaluates the gold dev fold at the end of every epoch.

    `gerar(model)` returns the (questions, raw_output) list for the dev examples, in order.
    Writes one line per epoch to `<config>__<arch>__<model>__fold<n>__por_epoca.jsonl`.
    """
    from transformers import TrainerCallback

    destino.mkdir(parents=True, exist_ok=True)
    training_meta = dict(training_meta or {})
    base = f"{config}__{arquitetura}__{modelo}__fold{fold}"
    ficheiro_metricas = destino / f"{base}__por_epoca.jsonl"

    class AvaliaCadaEpoca(TrainerCallback):
        def on_evaluate(self, args, state, control, model=None, **kwargs):
            # Called after the Trainer's end-of-epoch evaluation of the dev fold.
            epoca = int(round(state.epoch or 0))
            estava_a_treinar = model.training
            model.eval()
            try:
                geracoes = gerar(model)
            finally:
                if estava_a_treinar:
                    model.train()

            sumario = avalia_dev(dev_examples, geracoes, modelo=modelo, config=config,
                                 arquitetura=arquitetura, device=device_metricas)

            registo = {
                "modelo": modelo, "config": config, "fold": fold, "arquitetura": arquitetura,
                "epoch": epoca, "epochs_max": int(args.num_train_epochs),
                "n_dev": len(dev_examples),
                **training_meta,
                "mean_h_bert": sumario.get("mean_h_bert"),
            }
            with open(ficheiro_metricas, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(registo, ensure_ascii=False) + "\n")
            print(f"    [época {epoca:>2}/{int(args.num_train_epochs)}] "
                  f"h_bert={sumario.get('mean_h_bert')}", flush=True)
            return control

    return AvaliaCadaEpoca()
