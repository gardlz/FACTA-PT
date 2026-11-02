"""Baselines of the two test sets, next to the fine-tuned model of each task.

- Document relevance: the majority class of the training split (Irrelevant) predicted for every
  test pair, and stratified random prediction.
- Claim-Evidence Entailment: the XLM-R-large-XNLI checkpoint without fine-tuning, with its own
  three-class NLI head (entailment -> Supported, contradiction -> Refuted, neutral -> NEI) on the
  inputs of the fine-tuned model, and stratified random prediction.

Stratified random prediction gives each example a class at random, with the class proportions of
the training split. Its Macro-F1 is the exact expected value: for a class predicted with
probability q that has n_c of the n test examples, the true positives a ~ Bin(n_c, q) and the false
positives b ~ Bin(n - n_c, q) are independent, and the F1 of the class is 2a / (a + b + n_c), or 0
when a = 0.

The fine-tuned models, BERTimbau-base for relevance and XLM-R-large-XNLI for entailment, are read
from their final.py test predictions. The 95% CIs use the grouped bootstrap of metricas.py; in each
resample, stratified random prediction takes the expected Macro-F1 of the resampled claim spans,
every copy of a repeated claim span drawn independently. For Claim-Evidence Entailment, the CI of
the Macro-F1 difference between the fine-tuned model and stratified random prediction is paired:
both use the same resamples. Writes outputs/baselines.json.
"""

import argparse
import collections
import functools
import json
import pathlib

import numpy as np
from scipy import stats

import conjuntos as cj
import folds as fo
import grelhas as gr
import metricas as met
import motor

RAIZ = pathlib.Path(__file__).resolve().parents[1]
FINAL = RAIZ / "outputs/final"
SAIDA = RAIZ / "outputs/baselines.json"
# the fine-tuned model of each task, read from its final.py test predictions
AFINADO = {"relevance": "bertimbau_base", "entailment": "xlmr_large_xnli"}
# the entailment checkpoint that is also evaluated without fine-tuning
SEM_FINE_TUNING = "xlmr_large_xnli"


@functools.lru_cache(maxsize=None)
def f1_esperado(n_classe, n_outras, q):
    """Expected F1 of a class with `n_classe` examples among `n_outras` of other classes, when each
    example gets the class with probability `q`."""
    a, b = np.arange(n_classe + 1)[:, None], np.arange(n_outras + 1)[None, :]
    f1 = np.divide(2 * a, a + b + n_classe, out=np.zeros((len(a), b.shape[1])), where=a > 0)
    return float(stats.binom.pmf(a[:, 0], n_classe, q) @ f1 @ stats.binom.pmf(b[0], n_outras, q))


def macro_f1_estratificado(verdade, classes, q, escolha):
    """Expected Macro-F1 of stratified random prediction (class probabilities `q`) over the examples
    `escolha`, with repetitions."""
    conta = collections.Counter(verdade[i] for i in escolha)
    n = len(escolha)
    return sum(f1_esperado(conta[c], n - conta[c], p) for c, p in zip(classes, q)) / len(classes)


def previsoes_afinado(tarefa, teste):
    """Labels predicted by the fine-tuned model of the task, from its final.py test predictions."""
    caminho = FINAL / f"{tarefa}__{AFINADO[tarefa]}_previsoes.jsonl"
    if not caminho.exists():
        raise SystemExit(f"não há {caminho}.\nCorrer primeiro:\n"
                         f"    python src/final.py --tarefa {tarefa} --modelo {AFINADO[tarefa]}")
    linhas = [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
    if [(p["id"], p["verdade"]) for p in linhas] != [(x["id"], fo.rotulo(x, tarefa)) for x in teste]:
        raise SystemExit(f"{caminho.name} não tem os exemplos de teste de data/pares.jsonl")
    return [p["previsto"] for p in linhas]


def previsoes_sem_fine_tuning(teste, max_len):
    """Labels predicted by the XLM-R-large-XNLI checkpoint with its own NLI head, without
    fine-tuning; the premise, hypothesis and tokenization are those of motor.preparar."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    nome = gr.modelo_de(SEM_FINE_TUNING)["id"]
    classes = motor.classes_de("entailment")
    tok = AutoTokenizer.from_pretrained(nome)
    tok.model_max_length = max(tok.model_max_length or 0, max_len)      # as in motor.Modelo
    modelo = AutoModelForSequenceClassification.from_pretrained(nome, dtype=torch.float32)
    mapa = motor.mapa_do_checkpoint(modelo.config)          # {our class index: checkpoint index}
    if mapa is None:
        raise SystemExit(f"{nome} não tem uma cabeça de NLI de três classes")
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    modelo = modelo.to(torch.float32).to(dispositivo).eval()
    x, _, _ = motor.preparar(teste, "entailment", tok, max_len)
    saida = []
    with torch.no_grad():
        for i in range(0, x["input_ids"].shape[0], motor.LOTE_INFERENCIA):
            bloco = {k: v[i:i + motor.LOTE_INFERENCIA].to(dispositivo) for k, v in x.items()}
            saida.append(modelo(**bloco).logits.float().cpu())
    logits = torch.cat(saida)[:, [mapa[i] for i in range(len(classes))]]
    return [classes[i] for i in logits.argmax(-1)]


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    prot = gr.protocolo()
    n_boot, max_len = prot["estatistica"]["n_boot"], prot["treino"]["max_len"]
    saida = {"bootstrap": {"metodo": "scipy.stats.bootstrap, percentile", "unidade": "claim span",
                           "n_boot": n_boot, "seed": 42}}

    for tarefa in ("relevance", "entailment"):
        treino = fo.TAREFAS[tarefa](cj.pares("train"))
        teste = fo.TAREFAS[tarefa](cj.pares("test"))
        classes = motor.classes_de(tarefa)
        verdade = [fo.rotulo(x, tarefa) for x in teste]
        spans = [x["span_id"] for x in teste]
        conta = collections.Counter(fo.rotulo(x, tarefa) for x in treino)
        q = [conta[c] / len(treino) for c in classes]
        print(f"\n########## {tarefa}: {len(teste)} exemplos de teste, {len(set(spans))} claim spans; "
              f"proporções do treino " + " ".join(f"{c}={p:.4f}" for c, p in zip(classes, q)))

        previstos = {AFINADO[tarefa]: previsoes_afinado(tarefa, teste)}
        if tarefa == "relevance":
            previstos["maioritaria"] = [conta.most_common(1)[0][0]] * len(teste)
        else:
            previstos["sem_fine_tuning"] = previsoes_sem_fine_tuning(teste, max_len)

        sistemas = {}
        for nome, previsto in previstos.items():
            r = met.avaliar(verdade, previsto, spans, classes=classes, n_boot=n_boot)
            met.imprimir(f"[{tarefa}] {nome}", r, classes=classes)
            sistemas[nome] = {"macro_f1": r["macro_f1"], "macro_f1_ic95": list(r["macro_f1_ic95"]),
                              "por_classe": r["por_classe"], "matriz": r["matriz"]}

        def estratificado(escolha):
            return macro_f1_estratificado(verdade, classes, q, escolha)

        todos = range(len(verdade))
        baixo, alto = met.ic95_agrupado(spans, estratificado, n_boot)
        sistemas["estratificada"] = {"macro_f1": round(estratificado(todos), 4),
                                     "macro_f1_ic95": [round(baixo, 4), round(alto, 4)],
                                     "probabilidades": dict(zip(classes, q))}
        saida[tarefa] = {"n_teste": len(teste), "claim_spans_teste": len(set(spans)),
                         "classes": list(classes), "sistemas": sistemas}

        print(f"\n  [{tarefa}] macro-F1 e IC 95% ({n_boot} reamostragens de claim spans):")
        for nome, s in sistemas.items():
            lo, hi = s["macro_f1_ic95"]
            print(f"    {nome:20} {s['macro_f1']:.4f}  [{lo:.4f}, {hi:.4f}]")

        if tarefa == "entailment":
            # fine-tuned model minus stratified random prediction, on the same resamples
            def diferenca(escolha):
                return (met.macro_f1_em(verdade, previstos[AFINADO[tarefa]], classes, escolha)
                        - estratificado(escolha))

            baixo, alto = met.ic95_agrupado(spans, diferenca, n_boot)
            delta = {"sistema": AFINADO[tarefa], "menos": "estratificada",
                     "macro_f1": round(diferenca(todos), 4), "ic95": [round(baixo, 4), round(alto, 4)]}
            print(f"    {AFINADO[tarefa]} - estratificada: {delta['macro_f1']:.4f}  "
                  f"[{delta['ic95'][0]:.4f}, {delta['ic95'][1]:.4f}]")
            saida[tarefa]["diferenca"] = delta
            saida[tarefa]["previsoes_sem_fine_tuning"] = dict(zip([x["id"] for x in teste],
                                                                  previstos["sem_fine_tuning"]))

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {SAIDA}")


if __name__ == "__main__":
    main()
