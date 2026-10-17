"""Which passages the article writer reads when they do not all fit the prompt cap.

They leave one at a time, from the relation with the most passages, lowest `priority` first. No
relation loses its last passage, so the conclusion is still the one all the evidence gives.
"""

from __future__ import annotations

from collections.abc import Callable

from .veredito import NEI


def ordem_de_saida(passagens: list[dict]) -> list[int]:
    """The indices of `passagens` in the order they leave: from the relation with the most left
    (among equals nei, then the one with the weaker weakest passage), its lowest-priority passage,
    the later among equals. The last passage of each relation is never in it."""
    por_relacao: dict[str, list[int]] = {}
    for indice, passagem in enumerate(passagens):
        por_relacao.setdefault(passagem["label"], []).append(indice)
    for indices in por_relacao.values():
        indices.sort(key=lambda i: (passagens[i].get("priority", 0.0), -i))

    ordem: list[int] = []
    while True:
        candidatas = [r for r, indices in por_relacao.items() if len(indices) > 1]
        if not candidatas:
            return ordem
        maior = max(len(por_relacao[r]) for r in candidatas)
        empatadas = [r for r in candidatas if len(por_relacao[r]) == maior]
        relacao = NEI if NEI in empatadas else min(
            empatadas, key=lambda r: passagens[por_relacao[r][0]].get("priority", 0.0)
        )
        ordem.append(por_relacao[relacao].pop(0))


def _sem(passagens: list[dict], fora: set[int]) -> list[dict]:
    return [p for i, p in enumerate(passagens) if i not in fora]


def admitir(passagens: list[dict], cabe: Callable[[list[dict]], bool]) -> list[dict]:
    """The passages read, in input order, leaving out as few as `cabe` (does this set fit?) needs;
    fewer passages never make the prompt longer, so the number is found by bisection. When not even
    one passage per relation fits, those few go anyway: an article must come out."""
    if cabe(passagens):
        return passagens
    ordem = ordem_de_saida(passagens)
    saem = len(ordem)
    if saem and cabe(_sem(passagens, set(ordem))):
        menos = 1
        while menos < saem:
            meio = (menos + saem) // 2
            if cabe(_sem(passagens, set(ordem[:meio]))):
                saem = meio
            else:
                menos = meio + 1
    return _sem(passagens, set(ordem[:saem]))


def metade(passagens: list[dict]) -> list[dict]:
    """The passages of a last, shorter attempt: half of those that can leave, leave."""
    ordem = ordem_de_saida(passagens)
    return _sem(passagens, set(ordem[: (len(ordem) + 1) // 2]))
