"""The fixed evaluation sample of silver questions (seed 42, 50 claim spans) and the
aggregation of the two evaluation dimensions (CRITERIOS.md, CRITERIOS_CLEVER.md), shared by
app.py and tabelas_avaliacao.py.

The silver questions are those of ClaimPT (claimpt_train.json, claimpt_test.json); the manual
evaluation is in avaliacao/, next to this file.
"""

import random
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from clever_claimpt import CLAIMPT_ARTIGOS, CLAIMPT_JSON, unidades_silver  # noqa: E402

SEED = 42
N_SAMPLE = 50
FICHEIROS_SILVER = [CLAIMPT_JSON["train"], CLAIMPT_JSON["test"]]
CONTEXT_DIR = CLAIMPT_ARTIGOS
CRITERIOS_FILE = SCRIPT_DIR / "CRITERIOS.md"
CRITERIOS_CLEVER_FILE = SCRIPT_DIR / "CRITERIOS_CLEVER.md"
# The manual evaluation behind Tables 3.8 and 3.9, written by app.py.
AVALIACAO = SCRIPT_DIR / "avaliacao"
RATINGS_FILE = AVALIACAO / "ratings.json"
RATINGS_CLEVER_FILE = AVALIACAO / "ratings_clever.json"

# General question quality (CRITERIOS.md), judged per question.
METRICAS = ["relevancia", "fidelidade", "clareza", "ancora"]
NOMES = {"relevancia": "Relevância", "fidelidade": "Fidelidade",
         "clareza": "Clareza / pesquisabilidade", "ancora": "Âncora temporal e local"}

# Adherence to the CLEVER guidelines (CRITERIOS_CLEVER.md). Two criteria are properties of the
# question set (unit: claim span) and two of each question (unit: question); each rate is
# counted in the unit of its criterion.
METRICAS_CLEVER = ["estrutura", "objeto", "neutralidade", "casos_especiais"]
METRICAS_CLEVER_SPAN = ["estrutura", "casos_especiais"]
METRICAS_CLEVER_POR_PERGUNTA = ["objeto", "neutralidade"]
UNIDADE_CLEVER = {m: ("pergunta" if m in METRICAS_CLEVER_POR_PERGUNTA else "span")
                  for m in METRICAS_CLEVER}
NOMES_CLEVER = {"estrutura": "Estrutura geral → específica",
                "objeto": "Concordância com o claim object",
                "neutralidade": "Neutralidade e foco factual",
                "casos_especiais": "Casos especiais"}

# Special cases: (condition in the claim span, answer required from the questions). The
# verdict of the criterion is derived from these six answers (see `veredito_casos`).
CASOS_ESPECIAIS = [
    ("claimer_necessario", "claimer_incorporado",
     "A validade do facto depende de quem o profere?",
     "O ator está nomeado nas perguntas?"),
    ("comparacao_presente", "comparacao_coberta",
     "O claim span faz uma comparação?",
     "As perguntas cobrem os dois termos da comparação?"),
    ("estudo_mencionado", "estudo_localizavel",
     "O claim span invoca um estudo, relatório, sondagem ou documento?",
     "Alguma pergunta permite chegar ao documento original?"),
]


def respostas_qualidade(ratings, chave):
    """{metric: 0/1/None} of one question; values outside {0,1} count as unanswered."""
    guardadas = ratings.get(chave, {})
    return {m: (guardadas[m] if guardadas.get(m) in (0, 1) else None) for m in METRICAS}


def taxas_qualidade(ratings, chaves):
    """Rate of each quality criterion over the questions with the four criteria answered:
    {criterion: (met, denominator)}."""
    feitas = [respostas_qualidade(ratings, c) for c in chaves]
    feitas = [r for r in feitas if all(v is not None for v in r.values())]
    return {m: (sum(r[m] for r in feitas), len(feitas)) for m in METRICAS}


def span_avaliado(dados, n_perguntas):
    """True when the four criteria are answered (special cases may legitimately not apply)."""
    if not isinstance(dados, dict):
        return False
    dados = normalizar_clever(dados, n_perguntas)
    if dados["estrutura"] not in (0, 1):
        return False
    casos = dados["casos"]
    if any(casos.get(condicao) not in (0, 1) for condicao, _, _, _ in CASOS_ESPECIAIS):
        return False
    if any(casos.get(resposta) not in (0, 1) for condicao, resposta, _, _ in CASOS_ESPECIAIS
           if casos.get(condicao) == 1):
        return False
    feitas, n = perguntas_avaliadas(dados, n_perguntas)
    return n > 0 and feitas == n


def perguntas_avaliadas(dados, n_perguntas):
    """(questions with both per-question CLEVER criteria answered, number of questions)."""
    perguntas = normalizar_clever(dados, n_perguntas)["perguntas"]
    feitas = sum(1 for n in range(1, n_perguntas + 1)
                 if all(perguntas[n][m] in (0, 1) for m in METRICAS_CLEVER_POR_PERGUNTA))
    return feitas, n_perguntas


def veredito_casos(casos):
    """Verdict of the special-case criterion from the six answers: 1, 0 or None.

    None while a condition is unanswered, or a condition answered "yes" has no answer yet,
    and when the three conditions are "no" (not applicable).
    """
    if any(casos.get(condicao) not in (0, 1) for condicao, _, _, _ in CASOS_ESPECIAIS):
        return None                       # conditions still unanswered
    respostas = [casos.get(resposta) for condicao, resposta, _, _ in CASOS_ESPECIAIS
                 if casos.get(condicao) == 1]
    if not respostas:
        return None                       # no condition holds: not applicable
    if any(r not in (0, 1) for r in respostas):
        return None                       # a condition holds and its answer is missing
    return int(all(respostas))


def normalizar_clever(dados, n_perguntas):
    """A CLEVER-criteria evaluation in a fixed form, with None where an answer is missing."""
    dados = dados if isinstance(dados, dict) else {}
    bruto = {}
    for chave, valor in (dados.get("perguntas") or {}).items():
        try:
            bruto[int(chave)] = valor if isinstance(valor, dict) else {}
        except (TypeError, ValueError):
            continue
    perguntas = {n: {m: (bruto.get(n) or {}).get(m)
                     if (bruto.get(n) or {}).get(m) in (0, 1) else None
                     for m in METRICAS_CLEVER_POR_PERGUNTA}
                 for n in range(1, n_perguntas + 1)}
    estrutura = dados.get("estrutura")
    return {"n_perguntas": n_perguntas,
            "estrutura": estrutura if estrutura in (0, 1) else None,
            "casos": dict(dados.get("casos") or {}),
            "perguntas": perguntas}


def taxas_clever(avaliacoes):
    """Rate of the four criteria, each in its own unit: {criterion: (met, denominator, unit)}.

    `avaliacoes` are evaluations already passed through `normalizar_clever`. Missing answers
    and, for special cases, spans where no condition holds stay out of the denominator.
    """
    contas = {m: [0, 0] for m in METRICAS_CLEVER}
    for a in avaliacoes:
        for m in METRICAS_CLEVER_SPAN:
            veredito = a.get("estrutura") if m == "estrutura" else veredito_casos(a["casos"])
            if veredito in (0, 1):
                contas[m][0] += veredito
                contas[m][1] += 1
        for respostas in a["perguntas"].values():
            for m in METRICAS_CLEVER_POR_PERGUNTA:
                if respostas.get(m) in (0, 1):
                    contas[m][0] += respostas[m]
                    contas[m][1] += 1
    return {m: (ok, n, UNIDADE_CLEVER[m]) for m, (ok, n) in contas.items()}


def carregar_amostra(todos=False):
    """The claim spans to evaluate: the fixed seeded sample, or the whole dataset."""
    linhas = unidades_silver(FICHEIROS_SILVER)
    if not linhas:
        raise SystemExit(f"Sem perguntas silver em {', '.join(map(str, FICHEIROS_SILVER))}.")
    populacao = sorted(linhas, key=lambda r: r["id"])            # stable order
    if todos:
        return populacao
    return random.Random(SEED).sample(populacao, min(N_SAMPLE, len(populacao)))


def chave_pergunta(span_id, n):
    """Key of an evaluated question in ratings.json: `<span_id>::q<n>`."""
    return f"{span_id}::q{n}"


def _ler_criterios(caminho):
    if not caminho.exists():
        raise SystemExit(f"Falta o ficheiro de critérios: {caminho}.")
    return caminho.read_text(encoding="utf-8").strip()


def criterios():
    """The general-quality criteria, read from CRITERIOS.md."""
    return _ler_criterios(CRITERIOS_FILE)


def criterios_clever():
    """The CLEVER-guideline criteria, read from CRITERIOS_CLEVER.md."""
    return _ler_criterios(CRITERIOS_CLEVER_FILE)
