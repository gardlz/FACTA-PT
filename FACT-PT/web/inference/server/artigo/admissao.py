"""Which passages the writer reads, when they do not all fit.

The prompt is capped (`ARTICLE_MAX_PROMPT_TOKENS`, 16384 by default) for what reading it costs.
Reading builds a sliding-window attention mask that grows with the square of the prompt - about
0.8 GB at 16k tokens, 11 GB at 60k - and on CPU every ten thousand tokens take minutes. The cap
is not where the evidence runs out: given up to 18 pieces, the most it was given, the evaluated
writer cited every one in 111 of its 113 articles with evidence and all but one in the other two;
given 50, it cited 17. 16k tokens hold about 60.

When the passages do not fit, they leave one at a time: from the relation with the most passages,
the one worth least to the article (`priority`: for a decisive passage, how sure the classifier is
of its relation; for a nei passage, how close it came to deciding). No relation loses its last
passage. The conclusion is computed from which relations are present, so it stays the one all the
evidence gives.
"""

from __future__ import annotations

from collections.abc import Callable

from .veredito import NEI


def ordem_de_saida(passagens: list[dict]) -> list[int]:
    """The indices of `passagens` in the order they leave, for as long as they have to.

    Each one comes from the relation with the most passages left - nei first among equals, then
    the relation whose weakest passage is weaker - and is that relation's passage with the lowest
    priority, the later one among equals. The last passage of each relation is never in it.
    """
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


def admitir(
    passagens: list[dict], cabe: Callable[[list[dict]], bool]
) -> tuple[list[dict], list[dict]]:
    """(read, left out), in the order they came, with as few left out as the cap needs.

    `cabe` says whether a set of passages fits. Fewer passages never make the prompt longer, so
    the number that has to leave is found by halves. When not even one passage per relation fits,
    those few go anyway: an article must come out.
    """
    if cabe(passagens):
        return passagens, []
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
    fora = set(ordem[:saem])
    return _sem(passagens, fora), [p for i, p in enumerate(passagens) if i in fora]


def metade(passagens: list[dict]) -> list[dict]:
    """Half of what can leave, leaves: the shorter plan of a last attempt."""
    ordem = ordem_de_saida(passagens)
    return _sem(passagens, set(ordem[: (len(ordem) + 1) // 2]))
