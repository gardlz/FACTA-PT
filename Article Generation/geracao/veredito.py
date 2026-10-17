"""Global verdict of a claim span: three classes, five reasons and eight plan cases.

Computed from the plan's evidence groups, after any deduplication. The model never sees the class
or the reason as labels; the outcome reaches it as the conclusion sentence and, with a content plan,
in the plan's instructions. The fixed texts of the last two sections are also defined here.
"""

from typing import Dict, List, Optional, Tuple

SUPPORTED = "supported"
REFUTED = "refuted"
NEI = "nei"

# The five reasons (motivos) behind a verdict, in English like the class labels.
M_APOIA = "supported_evidence"
M_CONTRARIA = "refuted_evidence"
M_CONFLITO = "conflicting_evidence"
M_NAO_DECISIVA = "non_decisive_evidence"
M_SEM_EVIDENCIA = "no_evidence"

# Closing sentence of the article for each reason. The grammar imposes it verbatim (`const`).
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

# Text of the «Limites da verificação» section. Only the cut-off date varies, and the plan computes
# it (the day before the claim was published) instead of leaving it to the model.
LIMITES = ("Esta verificação baseia-se exclusivamente em notícias da agência Lusa publicadas "
           "até {data_limite} e recuperadas automaticamente para esta verificação. A ausência de "
           "evidência recuperada pelo sistema não demonstra, por si só, a inexistência de outra "
           "evidência relevante.")

# The annotation writes the relations as "Supported", "Refuted" and "NEI"; normalised on input.
_RELACOES = {"supported": SUPPORTED, "refuted": REFUTED, "nei": NEI}


def normalizar_relacao(relacao: str) -> str:
    chave = (relacao or "").strip().lower()
    if chave not in _RELACOES:
        raise ValueError(f"relação desconhecida: {relacao!r}")
    return _RELACOES[chave]


def limites(data_limite: str) -> str:
    """The «Limites da verificação» text for the given cut-off date."""
    return LIMITES.format(data_limite=data_limite)


def decidir(tem_apoio: bool, tem_contradicao: bool, tem_nao_decisiva: bool) -> Tuple[str, str]:
    """(class, reason) from the relations present among the plan's evidence."""
    if tem_apoio and tem_contradicao:
        return NEI, M_CONFLITO
    if tem_apoio:
        return SUPPORTED, M_APOIA
    if tem_contradicao:
        return REFUTED, M_CONTRARIA
    if tem_nao_decisiva:
        return NEI, M_NAO_DECISIVA
    return NEI, M_SEM_EVIDENCIA


# The eight plan cases are these five plus `supported_nei`, `refuted_nei` and `conflicting_nei`,
# built by `caso`. The case sets which sections the article has and what «A verificação» does.
CASO_APOIA = "supported"
CASO_CONTRARIA = "refuted"
CASO_CONFLITO = "conflicting"
CASO_NAO_DECISIVA = "non_decisive"
CASO_SEM_EVIDENCIA = "no_evidence"


def caso(motivo: str, tem_nao_decisiva: bool) -> str:
    """Plan case from the reason and whether the plan has NEI evidence."""
    if motivo == M_NAO_DECISIVA:
        return CASO_NAO_DECISIVA
    if motivo == M_SEM_EVIDENCIA:
        return CASO_SEM_EVIDENCIA
    base = {M_APOIA: CASO_APOIA, M_CONTRARIA: CASO_CONTRARIA, M_CONFLITO: CASO_CONFLITO}[motivo]
    return f"{base}_nei" if tem_nao_decisiva else base


def do_grupos(grupos: List[dict]) -> Dict[str, Optional[str]]:
    """Class, reason, conclusion sentence and case of a plan, from its evidence groups."""
    por_rotulo = {g["rotulo"]: g["evidencias"] for g in grupos}
    tem_nei = bool(por_rotulo.get(NEI))
    classe, motivo = decidir(bool(por_rotulo.get(SUPPORTED)),
                             bool(por_rotulo.get(REFUTED)),
                             tem_nei)
    return {
        "classificacao": classe,
        "motivo": motivo,
        "conclusao_texto": CONCLUSOES[motivo],
        "caso": caso(motivo, tem_nei),
    }
