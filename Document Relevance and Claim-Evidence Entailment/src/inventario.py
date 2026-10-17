"""Model table of the eleven encoders (Table 6.1 of the dissertation).

The parameter count is measured from each checkpoint; the other columns come from
configs/modelos.yaml. CPU only.
"""

import argparse

import grelhas as gr


def parametros(chave):
    """Parameter count of a checkpoint, loaded without imposing `num_labels`."""
    from transformers import AutoModelForSequenceClassification
    base = AutoModelForSequenceClassification.from_pretrained(gr.modelo_de(chave)["id"])
    return sum(p.numel() for p in base.parameters())


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    print("\n| modelo | checkpoint | grupo | params | língua | base | supervisão anterior | "
          "NLI | RTE | sim. | cabeça orig. |")
    print("|" + "---|" * 11)
    for chave in gr.encoders():
        x = gr.modelo_de(chave)
        print(f"| `{chave}` | `{x['id']}` | {x['grupo']} | {parametros(chave) / 1e6:.0f}M | "
              f"{x['lingua']} | {x['base']} | {x['supervisao']} | "
              f"{'sim' if x['nli'] else 'não'} | {'sim' if x['rte'] else 'não'} | "
              f"{'sim' if x['similaridade'] else 'não'} | "
              f"{x['cabeca_original_classes'] or 'nenhuma'} |")


if __name__ == "__main__":
    main()
