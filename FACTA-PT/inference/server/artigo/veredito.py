"""The overall classification and the fixed texts, as in `Article Generation/geracao/veredito.py`.

Computed from the evidence: the model only receives the conclusion sentence, as a `const`. The
reason, not the class, shapes the article; nei evidence never cancels a decision.
"""

from __future__ import annotations

SUPPORTED = "supported"
REFUTED = "refuted"
NEI = "nei"

M_APOIA = "supported_evidence"
M_CONTRARIA = "refuted_evidence"
M_CONFLITO = "conflicting_evidence"
M_NAO_DECISIVA = "non_decisive_evidence"
M_SEM_EVIDENCIA = "no_evidence"

# The sentences that close the article. They enter the prompt and the grammar (as `const`), so
# they live here only.
CONCLUSOES = {
    M_APOIA: "Tendo em conta as evidências recolhidas nesta verificação, a claim é sustentada.",
    M_CONTRARIA: "Tendo em conta as evidências recolhidas nesta verificação, a claim é refutada.",
    M_CONFLITO: ("As evidências recolhidas nesta verificação apontam em sentidos diferentes, pelo "
                 "que não é possível sustentar nem refutar a claim de forma conclusiva."),
    M_NAO_DECISIVA: ("As evidências recolhidas nesta verificação não permitem sustentar nem "
                     "refutar a claim de forma conclusiva."),
    M_SEM_EVIDENCIA: ("Não foram recuperadas evidências relevantes suficientes para sustentar "
                      "ou refutar a claim nesta verificação."),
}

# The limits are the same in every article except for the date, which comes computed: a model
# left to deduce it writes the date of one of the news items.
LIMITES = ("Esta verificação baseia-se exclusivamente em notícias da agência Lusa publicadas "
           "até {data_limite} e recuperadas automaticamente para esta verificação. A ausência de "
           "evidência recuperada pelo sistema não demonstra, por si só, a inexistência de outra "
           "evidência relevante.")

# The eight editorial cases: the combination (reason, is there nei?) that decides which sections
# the article has and what «A verificação» does.
CASO_APOIA = "supported"
CASO_CONTRARIA = "refuted"
CASO_CONFLITO = "conflicting"
CASO_NAO_DECISIVA = "non_decisive"
CASO_SEM_EVIDENCIA = "no_evidence"


def limites(data_limite: str) -> str:
    return LIMITES.format(data_limite=data_limite)


def decidir(tem_apoio: bool, tem_contradicao: bool, tem_nao_decisiva: bool) -> tuple[str, str]:
    """(class, reason): supported or refuted when only one side has evidence; nei when both do
    (conflicting), when there is only non-deciding evidence, or none."""
    if tem_apoio and tem_contradicao:
        return NEI, M_CONFLITO
    if tem_apoio:
        return SUPPORTED, M_APOIA
    if tem_contradicao:
        return REFUTED, M_CONTRARIA
    if tem_nao_decisiva:
        return NEI, M_NAO_DECISIVA
    return NEI, M_SEM_EVIDENCIA


def caso(motivo: str, tem_nao_decisiva: bool) -> str:
    if motivo == M_NAO_DECISIVA:
        return CASO_NAO_DECISIVA
    if motivo == M_SEM_EVIDENCIA:
        return CASO_SEM_EVIDENCIA
    base = {M_APOIA: CASO_APOIA, M_CONTRARIA: CASO_CONTRARIA, M_CONFLITO: CASO_CONFLITO}[motivo]
    return f"{base}_nei" if tem_nao_decisiva else base


def do_grupos(grupos: list[dict]) -> dict:
    """Class, reason, conclusion sentence and editorial case, from the plan's groups."""
    por_rotulo = {g["rotulo"]: g["evidencias"] for g in grupos}
    tem_nei = bool(por_rotulo.get(NEI))
    classe, motivo = decidir(bool(por_rotulo.get(SUPPORTED)), bool(por_rotulo.get(REFUTED)),
                             tem_nei)
    return {
        "classificacao": classe,
        "motivo": motivo,
        "conclusao_texto": CONCLUSOES[motivo],
        "caso": caso(motivo, tem_nei),
    }
