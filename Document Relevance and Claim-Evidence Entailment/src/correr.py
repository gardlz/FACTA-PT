"""Configuration selection of one model on one task: 3 seeds x 5 folds on the training split.

Appends a record with the 15 selected epochs and taus to outputs/resultados.jsonl; each fold is
saved as it closes, so an interrupted run resumes.
"""

import argparse
import collections
import hashlib
import json
import os
import pathlib
import statistics
import time

import carbono
import conjuntos as cj
import folds as fo
import grelhas as gr
import motor

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "outputs/resultados.jsonl"
# the code that decides the training of a fold (the dev Macro-F1 decides stopping and tau)
FONTES_DO_TREINO = ("motor.py", "entradas.py", "metricas.py")


def escrever_atomico(caminho, texto):
    """Writes next to the target and swaps, so a crash never leaves half a file."""
    tmp = caminho.with_name(caminho.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(texto)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, caminho)


def assinatura(exemplos, cfg, d):
    """What must be identical for a saved fold to be reused."""
    import transformers
    h = hashlib.sha256()
    for nome in FONTES_DO_TREINO:
        h.update((pathlib.Path(__file__).parent / nome).read_bytes())
    h.update(json.dumps({"exemplos": exemplos, "cfg": cfg, "folds": d,
                         "torch": motor.torch.__version__,
                         "transformers": transformers.__version__},
                        sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
    return h.hexdigest()


def ler_parciais(caminho, assin):
    """Folds already closed by an interrupted run: {(seed, fold): record}."""
    if not caminho.exists():
        return {}
    # a crash in the middle of a multi-byte character must not block reading the good lines
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    boas, partidas = [], 0
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        try:
            boas.append((linha, json.loads(linha)))
        except json.JSONDecodeError:
            partidas += 1
    if any(r.get("assinatura") != assin for _, r in boas):
        lado = caminho.with_name(f"{caminho.stem}.posto_de_lado_{time.strftime('%Y%m%d_%H%M%S')}"
                                 f"{caminho.suffix}")
        os.replace(caminho, lado)
        print(f"  ATENÇÃO: as folds guardadas em {caminho.name} foram feitas com outros exemplos, "
              f"outra configuração, outras folds ou outro código de treino. Postas de lado em "
              f"{lado.name}; a validação cruzada corre do zero.", flush=True)
        return {}
    if partidas or not texto.endswith("\n"):
        # only the last line can be broken; rewrite without it so the next fold starts clean
        escrever_atomico(caminho, "".join(l + "\n" for l, _ in boas))
        if partidas:
            print(f"  {partidas} linha(s) partida(s) em {caminho.name} (queda a meio de uma "
                  f"escrita) retirada(s): essa(s) fold(s) correm outra vez.", flush=True)
    return {(r["semente"], r["fold"]): r for _, r in boas}


def gravar_fold(caminho, registo):
    """Appends a closed fold to the partial file and forces it to disk."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registo, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def somar_carbono(bloco, folds):
    """Cost = sum of the folds, each measured when it ran (resumed ones included)."""
    medidas = [f.get("carbono") or {} for f in folds]

    def soma(chave):
        v = [m.get(chave) for m in medidas]
        return None if not v or any(x is None for x in v) else sum(v)

    return {"bloco": bloco, "segundos": soma("segundos"), "emissoes_kg": soma("emissoes_kg"),
            "energia_kwh": soma("energia_kwh"),
            "medido": bool(medidas) and all(m.get("medido") for m in medidas),
            "motivo": next((m["motivo"] for m in medidas if m.get("motivo")), None)}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--tarefa", required=True, choices=("relevance", "entailment"))
    p.add_argument("--modelo", required=True)
    args = p.parse_args()

    prot = gr.protocolo()
    meta = gr.modelo_de(args.modelo)
    cfg = gr.config_de_treino(args.modelo, args.tarefa)

    pares = cj.pares("train")
    exemplos = fo.TAREFAS[args.tarefa](pares)
    d = gr.folds(args.tarefa)
    grupo_de = d["grupo_de"]

    c = collections.Counter(fo.rotulo(x, args.tarefa) for x in exemplos)
    print(f"{args.tarefa} · {args.modelo} ({meta['id']})")
    print(f"  grupo «{meta['grupo']}» · cabeça original de {meta['cabeca_original_classes']} "
          f"classes · preservar cabeça: {cfg['preservar_cabeca']}")
    print(f"  {len(exemplos)} exemplos · {len({x['span_id'] for x in exemplos})} spans · "
          f"{d['n_grupos']} grupos · " + " ".join(f"{k}={v}" for k, v in sorted(c.items())))
    print(f"  protocolo: AdamW lr {cfg['lr']} · batch {cfg['batch']} · max_len {cfg['max_len']} · "
          f"linear warmup {prot['treino']['warmup']:.0%} + decay sobre {motor.EPOCAS_MAX} épocas · "
          f"early stopping paciência {motor.PACIENCIA} no dev INTERNO\n")

    diarios = []
    marca = f"{args.tarefa}__{args.modelo}"
    bloco = f"{args.tarefa}|{args.modelo}"
    parcial = SAIDA.parent / "parciais" / f"{marca}.jsonl"
    assin = assinatura(exemplos, cfg, d)
    guardadas = ler_parciais(parcial, assin)
    if guardadas:
        print(f"  RETOMA: {len(guardadas)} fold(s) já fechada(s) numa corrida interrompida "
              f"({parcial}) — não se treinam outra vez\n", flush=True)
    feitas = []

    for s in d["sementes"]:
        print(f"  == repetição semente {s}")
        cfg_s = dict(cfg, seed=s)
        i = d["sementes"].index(s)

        def fazer(k, divisao, s=s, cfg_s=cfg_s):
            f = guardadas.get((s, k))
            if f is not None:
                if (f["ids"] != [x["id"] for x in divisao[2]]
                        or f["diario"]["grupos_dev"] != divisao[3]):
                    raise SystemExit(f"semente {s}, fold {k}: a fold guardada em {parcial} não é "
                                     f"a fold de agora (outra fold externa ou outro dev interno)")
                motor.imprimir_fold(f["diario"], f" · RETOMADA (fechou a {f['gravada_em']})")
            else:
                with carbono.medir(f"{bloco}|s{s}|f{k}") as m:
                    f = motor.correr_fold(divisao, k, args.tarefa, cfg_s)
                f.update(semente=s, assinatura=assin, carbono=m.como_dict(),
                         gravada_em=time.strftime("%Y-%m-%d %H:%M:%S"))
                gravar_fold(parcial, f)
            feitas.append(f)
            return f

        diarios += motor.correr_cv(exemplos, d["particoes"][i], grupo_de, cfg_s, fazer)

    registo = {
        "tarefa": args.tarefa, "modelo": args.modelo,
        "id": meta["id"], "grupo": meta["grupo"],
        "cabeca_preservada": diarios[0]["cabeca_preservada"],
        "id2label_original": diarios[0]["id2label_original"],
        "n_exemplos": len(exemplos), "n_spans": len({x["span_id"] for x in exemplos}),
        "n_grupos": d["n_grupos"], "k": d["k"], "sementes": d["sementes"],
        "epocas": {
            "melhor_epoca": [x["melhor_epoca"] for x in diarios],
            "epocas_executadas": [x["epocas_executadas"] for x in diarios],
            "motivo_paragem": collections.Counter(x["motivo_paragem"] for x in diarios),
            "melhor_epoca_mediana": statistics.median([x["melhor_epoca"] for x in diarios]),
            "melhor_foi_o_maximo": sum(1 for x in diarios if x["melhor_epoca"] == motor.EPOCAS_MAX),
            "n_folds": len(diarios)},
        "tau": {"escolhidos": [x["tau"] for x in diarios],
                "distribuicao": collections.Counter(str(x["tau"]) for x in diarios)},
        # the cost (time, energy, emissions) is the sum of the folds, each measured when it ran
        "carbono": somar_carbono(bloco, feitas),
    }

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    antes = SAIDA.read_text(encoding="utf-8") if SAIDA.exists() else ""
    if antes and not antes.endswith("\n"):
        antes += "\n"
    escrever_atomico(SAIDA, antes + json.dumps(registo, ensure_ascii=False, default=str) + "\n")
    # the record holds every fold, so the partial file is deleted
    parcial.unlink(missing_ok=True)

    ep = registo["epocas"]
    print(f"\n[{args.tarefa}/{args.modelo}] melhor época: mediana {ep['melhor_epoca_mediana']} · "
          f"{ep['melhor_foi_o_maximo']}/{ep['n_folds']} folds com a melhor na época "
          f"{motor.EPOCAS_MAX}")
    print(f"  paragem: {dict(ep['motivo_paragem'])} · tau: {dict(registo['tau']['distribuicao'])}")
    print(f"  -> {SAIDA}")


if __name__ == "__main__":
    main()
