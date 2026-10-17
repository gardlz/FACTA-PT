"""Final training of one model on the whole training split, then one pass over the test split.

Epochs = median of the model's 15 selected epochs, tau = their mode (ties -> lower tau); fresh
fine-tuning without development set or early stopping. Writes to outputs/final/.
"""

import argparse
import json
import os
import pathlib

import torch
import torch.nn as nn

import carbono
import conjuntos as cj
import folds as fo
import grelhas as gr
import metricas as met
import motor
from correr import escrever_atomico

RAIZ = pathlib.Path(__file__).resolve().parents[1]
# cross-validation records the epochs and tau come from (written by correr.py)
RESULTADOS = RAIZ / "outputs/resultados.jsonl"
SAIDA = RAIZ / "outputs/final"


def config_de(tarefa, chave):
    """Final configuration of a model from its own 15 folds: median epoch, modal tau."""
    import collections
    import statistics
    prot = gr.protocolo()
    reg = [json.loads(l) for l in RESULTADOS.read_text(
        encoding="utf-8").splitlines() if l.strip()]
    reg = list({(r["tarefa"], r["modelo"]): r for r in reg}.values())
    v = next((r for r in reg if r["tarefa"] == tarefa and r["modelo"] == chave), None)
    if v is None:
        raise SystemExit(f"não há validação cruzada para {tarefa}/{chave}")
    e = v["epocas"]["melhor_epoca"]
    taus = [float(x) for x in v["tau"]["escolhidos"]]
    c = collections.Counter(taus)
    maxf = max(c.values())
    return {
        "tarefa": tarefa, "modelo": chave, "checkpoint": v["id"],
        "grupo_de_pre_treino": v["grupo"],
        "best_epoch_das_15_folds": e,
        "epoch_final": int(statistics.median(e)),
        "tau_das_15_folds": taus,
        "tau_distribuicao": {str(k): n for k, n in sorted(c.items())},
        "tau_final": min(k for k, n in c.items() if n == maxf),
        "seed_final": prot["treino_final"]["seed"],
        "cabeca_preservada": v["cabeca_preservada"],
        "cabeca": ("preservada e permutada pelo id2label do checkpoint"
                   if v["cabeca_preservada"] else
                   f"nova de {2 if tarefa == 'relevance' else 3} saídas"),
        "id2label_original": v["id2label_original"],
        "cv_resultados": os.path.relpath(RESULTADOS, RAIZ),
        "cv_n_folds": v["epocas"]["n_folds"],
        "cv_sementes": v.get("sementes"),
    }


def treinar_final(sel, treino, tarefa):
    """Fresh fine-tuning from the pre-trained checkpoint on the whole training split."""
    motor.semear(sel["seed_final"])
    classes = motor.classes_de(tarefa)
    n_classes = len(classes)
    m = gr.modelo_de(sel["modelo"])
    prot = gr.protocolo()["treino"]

    modelo = motor.Modelo(sel["checkpoint"], n_classes,
                          preservar_cabeca=(tarefa == "entailment"
                                            and m.get("cabeca_original_classes") == 3),
                          max_len=prot["max_len"],
                          seed=sel["seed_final"]).cuda()
    cfg_t = gr.config_de_treino(sel["modelo"], tarefa)   # memory-saving options, see motor.py
    if cfg_t["checkpointing"]:
        motor.ligar_checkpointing(modelo)

    x, y, _ = motor.preparar(treino, tarefa, modelo.tok, prot["max_len"])
    # class priors over the whole final training set
    conta = torch.bincount(y, minlength=n_classes).float()
    priors = conta / conta.sum()

    opt = motor.optimizador(modelo, float(prot["lr"]), prot["weight_decay"], cfg_t["adamw_cpu"])
    import math
    por_epoca = max(1, math.ceil(len(y) / prot["batch"]))
    passos_max = por_epoca * motor.EPOCAS_MAX          # the 20-epoch horizon, not epoch_final
    aquecimento = max(1, int(motor.WARMUP * passos_max))

    def factor(p):
        if p < aquecimento:
            return p / max(1, aquecimento)
        return max(0.0, (passos_max - p) / max(1, passos_max - aquecimento))

    sched = motor.scheduler_de(opt, factor)

    n = len(y)
    modelo.train()
    for epoca in range(1, sel["epoch_final"] + 1):
        ordem = torch.randperm(n)
        perdas = []
        for i in range(0, n, prot["batch"]):
            idx = ordem[i:i + prot["batch"]]
            bloco = {k: v[idx].cuda() for k, v in x.items()}
            logits = modelo(**bloco)
            perda = nn.functional.cross_entropy(logits.float(), y[idx].cuda())
            perda.backward()
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            perdas.append(float(perda))
        media = round(sum(perdas) / len(perdas), 5)
        lr = round(opt.param_groups[0]["lr"], 10)
        print(f"    época {epoca}/{sel['epoch_final']} · perda {media:.4f} · lr {lr:.3e}",
              flush=True)
    return modelo, priors


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--tarefa", choices=("relevance", "entailment"), required=True)
    p.add_argument("--modelo", required=True)
    p.add_argument("--guardar-checkpoint", type=pathlib.Path, default=None,
                   help="save the trained model (weights, tokenizer, decision rule) here")
    args = p.parse_args()

    tarefa = args.tarefa
    sel = config_de(tarefa, args.modelo)
    SAIDA.mkdir(parents=True, exist_ok=True)
    treino = fo.TAREFAS[tarefa](cj.pares("train"))
    teste = fo.TAREFAS[tarefa](cj.pares("test"))

    print(f"\n########## {tarefa} · {sel['modelo']} ##########")

    marca = f"{tarefa}__{args.modelo}"
    destino = SAIDA / f"{marca}_resultado.json"
    if destino.exists():
        print(f"  {destino.name} já existe; nada foi feito.")
        return

    print(f"  treino final: {len(treino)} exemplos, {sel['epoch_final']} épocas, "
          f"sem dev interno, sem paragem antecipada")
    with carbono.medir(f"final|{tarefa}|{sel['modelo']}") as m:
        modelo, priors = treinar_final(sel, treino, tarefa)

        # --- the single inference over the test split ------------------------------------- #
        classes = motor.classes_de(tarefa)
        xt, yt, _ = motor.preparar(teste, tarefa, modelo.tok,
                                   gr.protocolo()["treino"]["max_len"])
        modelo.eval()
        saida = []
        with torch.no_grad():
            for i in range(0, len(yt), motor.LOTE_INFERENCIA):
                b = {k: v[i:i + motor.LOTE_INFERENCIA].cuda() for k, v in xt.items()}
                saida.append(modelo(**b).float().cpu())
        logits = torch.cat(saida)
        ajust = motor.ajustar_logits(logits, priors, sel["tau_final"])
        previsto = [classes[i] for i in ajust.argmax(-1)]

    verdade = [fo.rotulo(x, tarefa) for x in teste]
    spans = [x["span_id"] for x in teste]
    r = met.avaliar(verdade, previsto, spans, classes=classes,
                    n_boot=gr.protocolo()["estatistica"]["n_boot"])
    if tarefa == "relevance":
        # recall of the decisive evidence: relevant pairs annotated Supported or Refuted
        alvo = [i for i, x in enumerate(teste) if x["rotulo4"] in ("supported", "refuted")]
        ap = sum(1 for i in alvo if previsto[i] == "relevante")
        r["revocacao_por_rotulo_original"] = {"decisivo": {
            "n": len(alvo), "revocacao": round(ap / len(alvo), 4) if alvo else None}}

    # The checkpoint is saved after the inference, so it is exactly the model behind the result.
    # Its config gets our id2label, not the source checkpoint's (whose class order may differ).
    if args.guardar_checkpoint:
        destino_ck = args.guardar_checkpoint / f"{tarefa}_{sel['modelo']}"
        destino_ck.mkdir(parents=True, exist_ok=True)
        modelo.encoder.config.id2label = {i: c for i, c in enumerate(classes)}
        modelo.encoder.config.label2id = {c: i for i, c in enumerate(classes)}
        modelo.encoder.save_pretrained(destino_ck, safe_serialization=True)
        modelo.tok.save_pretrained(destino_ck)
        (destino_ck / "COMO_USAR.json").write_text(json.dumps({
            "tarefa": tarefa,
            "checkpoint_de_origem": sel["checkpoint"],
            "classes_por_indice": list(classes),
            "entrada": {
                "premissa": ("documento da LUSA: título + '. ' + corpo, cortado a 380 palavras"
                             if tarefa == "relevance" else
                             "uma janela de TRÊS FRASES do documento, literal e seguida, "
                             "sem o título da notícia — ver folds.exemplos_entailment"),
                "hipotese": "o claim span, com espaços e pontos das pontas retirados",
                "ordem": "tokenizador(premissa, hipotese) — nesta ordem",
                "max_len": gr.protocolo()["treino"]["max_len"],
                "truncation": True,
            },
            "regra_de_decisao": {
                "tau": sel["tau_final"],
                "priors_de_classe": {c: round(float(v), 6) for c, v in zip(classes, priors)},
                "formula": "z'_c = z_c - tau * log(pi_c); com tau = 0 é o argmax dos logits",
            },
            "treino": {"epocas": sel["epoch_final"], "seed": sel["seed_final"],
                       "n_exemplos": len(treino), "precisao": "float32",
                       "cabeca": sel["cabeca"]},
            "desempenho": {
                "macro_f1_teste": r["macro_f1"],
                "por_classe_teste": {c: round(r["por_classe"][c]["f1"], 4) for c in classes},
            },
            "configuracao_de": sel.get("cv_resultados"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  checkpoint -> {destino_ck}")

    registo = {
        "tarefa": tarefa,
        "selecao": sel,
        "n_treino": len(treino), "n_teste": len(teste),
        "priors_de_classe": {c: round(float(v_), 5) for c, v_ in zip(classes, priors)},
        "resultado": r, "matriz_de_confusao": r["matriz"],
        "carbono": m.como_dict(),
    }
    os.sync()
    escrever_atomico(destino, json.dumps(registo, ensure_ascii=False, indent=2))
    met.imprimir(f"[{tarefa}] AVALIAÇÃO NO TESTE · {sel['modelo']}", r, classes=classes)
    print(f"  -> {destino}")


if __name__ == "__main__":
    main()
